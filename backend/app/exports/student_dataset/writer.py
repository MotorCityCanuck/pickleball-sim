"""Staged Parquet writer for student-facing dataset releases."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any, Mapping
from uuid import uuid4

import pyarrow as pa
import pyarrow.parquet as pq
from sqlalchemy.orm import Session

from app.exports.data_quality import (
    INSTRUCTOR_MANIFEST_FILE_NAME,
    DataQualityInjectionManifestEntry,
    DataQualityReleaseContext,
    build_default_data_quality_config,
    inject_data_quality_issues,
    manifest_table,
    normalize_data_quality_level,
)

from .projection import (
    PROJECTION_BY_TABLE,
    STUDENT_DATASET_SCHEMA_VERSION,
    STUDENT_TABLE_ORDER,
)
from .queries import StudentDatasetQueryContext, build_student_dataset_query
from .release_windows import StudentDatasetReleaseWindow
from .validation import StudentDatasetValidationResult, validate_staged_release


MANIFEST_FILE_NAME = "manifest.json"
DEFAULT_PARQUET_COMPRESSION = "snappy"


class StudentDatasetWriteError(RuntimeError):
    """Raised when staged student dataset files cannot be written."""


@dataclass(frozen=True)
class StudentDatasetBuildParameters:
    """Build parameters captured in each staged release manifest."""

    generation_run_id: int
    initial_history_month_count: int
    subsequent_month_count: int
    output_root: Path
    release_name: str
    data_quality_level: str = "none"
    overwrite_existing: bool = False
    final_root: Path | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "data_quality_level",
            normalize_data_quality_level(self.data_quality_level),
        )

    def manifest_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable build parameter dictionary."""

        return {
            "generation_run_id": self.generation_run_id,
            "initial_history_month_count": self.initial_history_month_count,
            "subsequent_month_count": self.subsequent_month_count,
            "output_root": str(self.output_root),
            "release_name": self.release_name,
            "data_quality_level": self.data_quality_level,
            "overwrite_existing": self.overwrite_existing,
            "final_root": str(self.final_root) if self.final_root is not None else None,
        }


@dataclass(frozen=True)
class StudentDatasetFileManifest:
    """Manifest entry for one emitted Parquet file."""

    table_name: str
    file_name: str
    file_path: Path
    row_count: int
    columns: tuple[str, ...]
    schema_hash: str
    checksum: str

    def manifest_dict(self, release_dir: Path) -> dict[str, Any]:
        """Return a JSON-serializable file manifest dictionary."""

        return {
            "table_name": self.table_name,
            "file_name": self.file_name,
            "file_path": self.file_path.relative_to(release_dir).as_posix(),
            "row_count": self.row_count,
            "columns": list(self.columns),
            "schema_hash": self.schema_hash,
            "checksum": self.checksum,
        }


@dataclass(frozen=True)
class StagedStudentDatasetRelease:
    """Result of writing one release folder under a staging root."""

    release_name: str
    release_type: str
    release_dir: Path
    manifest_path: Path
    files: tuple[StudentDatasetFileManifest, ...]
    data_quality_manifest_entries: tuple[DataQualityInjectionManifestEntry, ...] = ()


@dataclass(frozen=True)
class StagedStudentDatasetFamily:
    """Result of writing all requested release folders under a staging root."""

    release_name: str
    staging_root: Path
    releases: tuple[StagedStudentDatasetRelease, ...]
    instructor_manifest_path: Path | None = None


def create_staging_root(output_root: Path, release_name: str) -> Path:
    """Create and return a unique staging directory for a release family."""

    safe_release_name = release_name.strip()
    if not safe_release_name:
        raise StudentDatasetWriteError("release_name is required.")
    staging_root = (
        output_root
        / f".{safe_release_name}.staging-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}-{uuid4().hex[:8]}"
    )
    staging_root.mkdir(parents=True, exist_ok=False)
    return staging_root


def write_staged_release_family(
    *,
    session: Session,
    output_root: Path,
    release_name: str,
    release_windows: tuple[StudentDatasetReleaseWindow, ...],
    build_parameters: StudentDatasetBuildParameters,
    compression: str = DEFAULT_PARQUET_COMPRESSION,
) -> StagedStudentDatasetFamily:
    """Write all release windows under a unique staging root."""

    staging_root = create_staging_root(output_root, release_name)
    releases = tuple(
        write_staged_release(
            session=session,
            staging_root=staging_root,
            release_name=release_name,
            release_window=release_window,
            build_parameters=build_parameters,
            compression=compression,
        )
        for release_window in release_windows
    )
    instructor_manifest_path = _write_instructor_manifest(
        staging_root=staging_root,
        releases=releases,
        compression=compression,
    )
    return StagedStudentDatasetFamily(
        release_name=release_name,
        staging_root=staging_root,
        releases=releases,
        instructor_manifest_path=instructor_manifest_path,
    )


def write_staged_release(
    *,
    session: Session,
    staging_root: Path,
    release_name: str,
    release_window: StudentDatasetReleaseWindow,
    build_parameters: StudentDatasetBuildParameters,
    compression: str = DEFAULT_PARQUET_COMPRESSION,
) -> StagedStudentDatasetRelease:
    """Write one release folder and manifest under an existing staging root."""

    concrete_release_name = f"{release_name}{release_window.folder_suffix}"
    release_dir = staging_root / concrete_release_name
    release_dir.mkdir(parents=True, exist_ok=False)

    context = StudentDatasetQueryContext(
        generation_run_id=build_parameters.generation_run_id,
        release_window=release_window,
    )
    clean_tables = {
        table_name: _load_table_rows(
            session=session,
            table_name=table_name,
            context=context,
        )
        for table_name in STUDENT_TABLE_ORDER
    }
    data_quality_config = build_default_data_quality_config(
        level=build_parameters.data_quality_level,
    )
    injection_result = inject_data_quality_issues(
        tables=clean_tables,
        config=data_quality_config,
        release_context=DataQualityReleaseContext(
            release_id=concrete_release_name,
            release_name=concrete_release_name,
            release_type=release_window.release_type,
            generation_run_id=build_parameters.generation_run_id,
            snapshot_month=release_window.snapshot_month,
        ),
    )
    files = tuple(
        _write_table_rows(
            release_dir=release_dir,
            table_name=table_name,
            row_dicts=injection_result.tables[table_name],
            compression=compression,
        )
        for table_name in STUDENT_TABLE_ORDER
    )
    manifest_path = release_dir / MANIFEST_FILE_NAME
    manifest_row_counts = {
        file_manifest.table_name: file_manifest.row_count
        for file_manifest in files
    }
    validation_result = validate_staged_release(
        release_dir=release_dir,
        release_window=release_window,
        manifest_row_counts=manifest_row_counts,
    )
    manifest = _release_manifest(
        release_name=concrete_release_name,
        release_window=release_window,
        build_parameters=build_parameters,
        files=files,
        release_dir=release_dir,
        compression=compression,
        validation_result=validation_result,
    )
    _write_json(manifest_path, manifest)
    return StagedStudentDatasetRelease(
        release_name=concrete_release_name,
        release_type=release_window.release_type,
        release_dir=release_dir,
        manifest_path=manifest_path,
        files=files,
        data_quality_manifest_entries=injection_result.manifest_entries,
    )


def _load_table_rows(
    *,
    session: Session,
    table_name: str,
    context: StudentDatasetQueryContext,
) -> list[dict[str, Any]]:
    projection = PROJECTION_BY_TABLE[table_name]
    query = build_student_dataset_query(table_name, context)
    rows = session.execute(query).mappings().all()
    return [
        {column_name: _normalize_value(row[column_name]) for column_name in projection.included_columns}
        for row in rows
    ]


def _write_table_rows(
    *,
    release_dir: Path,
    table_name: str,
    row_dicts: list[dict[str, Any]],
    compression: str,
) -> StudentDatasetFileManifest:
    projection = PROJECTION_BY_TABLE[table_name]
    table = pa.table(
        {
            column_name: pa.array([row[column_name] for row in row_dicts])
            for column_name in projection.included_columns
        }
    )
    file_path = release_dir / projection.output_file
    pq.write_table(table, file_path, compression=compression)
    return StudentDatasetFileManifest(
        table_name=table_name,
        file_name=projection.output_file,
        file_path=file_path,
        row_count=table.num_rows,
        columns=projection.included_columns,
        schema_hash=_schema_hash(table.schema),
        checksum=_file_checksum(file_path),
    )


def _release_manifest(
    *,
    release_name: str,
    release_window: StudentDatasetReleaseWindow,
    build_parameters: StudentDatasetBuildParameters,
    files: tuple[StudentDatasetFileManifest, ...],
    release_dir: Path,
    compression: str,
    validation_result: StudentDatasetValidationResult,
) -> dict[str, Any]:
    release_mode = (
        "baseline"
        if release_window.release_type == "initial_snapshot"
        else "monthly_incremental"
    )
    manifest_release_type = release_window.release_type
    load_strategy = (
        "full_load"
        if release_window.release_type == "initial_snapshot"
        else "incremental_load"
    )
    return {
        "release_name": release_name,
        "release_sequence_number": release_window.release_sequence_number,
        "release_mode": release_mode,
        "release_type": manifest_release_type,
        "release_month": (
            release_window.release_month.isoformat()
            if release_window.release_month is not None
            else None
        ),
        "included_months": list(release_window.fact_batch_sequences),
        "load_strategy": load_strategy,
        "student_dataset_schema_version": STUDENT_DATASET_SCHEMA_VERSION,
        "included_batch_sequences": list(release_window.fact_batch_sequences),
        "included_batch_months": [
            batch_month.isoformat() for batch_month in release_window.fact_batch_months
        ],
        "snapshot_batch_sequences": list(release_window.snapshot_batch_sequences),
        "snapshot_batch_months": [
            batch_month.isoformat() for batch_month in release_window.snapshot_batch_months
        ],
        "fact_batch_sequences": list(release_window.fact_batch_sequences),
        "fact_batch_months": [
            batch_month.isoformat() for batch_month in release_window.fact_batch_months
        ],
        "snapshot_month": release_window.snapshot_month.isoformat(),
        "snapshot_end_exclusive": release_window.snapshot_end_exclusive.isoformat(),
        "parquet_compression": compression,
        "output_files": [
            file_manifest.manifest_dict(release_dir) for file_manifest in files
        ],
        "row_counts": {
            file_manifest.table_name: file_manifest.row_count
            for file_manifest in files
        },
        "ordered_columns": {
            file_manifest.table_name: list(file_manifest.columns)
            for file_manifest in files
        },
        "schema_hashes": {
            file_manifest.table_name: file_manifest.schema_hash
            for file_manifest in files
        },
        "file_checksums": {
            file_manifest.table_name: file_manifest.checksum
            for file_manifest in files
        },
        "build_timestamp": datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z"),
        "validation_status": validation_result.status,
        "validation_summary": validation_result.manifest_dict(),
    }


def _write_instructor_manifest(
    *,
    staging_root: Path,
    releases: tuple[StagedStudentDatasetRelease, ...],
    compression: str,
) -> Path | None:
    entries = [
        entry
        for release in releases
        for entry in release.data_quality_manifest_entries
    ]
    instructor_dir = staging_root / "instructor_only"
    instructor_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = instructor_dir / INSTRUCTOR_MANIFEST_FILE_NAME
    pq.write_table(
        manifest_table(entries),
        manifest_path,
        compression=compression,
    )
    return manifest_path


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _schema_hash(schema: pa.Schema) -> str:
    fields = [
        {"name": field.name, "type": str(field.type), "nullable": field.nullable}
        for field in schema
    ]
    encoded = json.dumps(fields, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return sha256(encoded).hexdigest()


def _file_checksum(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _normalize_value(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value
