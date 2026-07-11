"""Staged Parquet writer for student-facing dataset releases."""

from __future__ import annotations

import json
import logging
import os
import resource
from dataclasses import dataclass
from datetime import date, datetime, timezone
from hashlib import sha256
from pathlib import Path
from time import perf_counter
from typing import Any, Callable, Mapping
from uuid import uuid4

import pyarrow as pa
import pyarrow.parquet as pq
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.generation.runtime_metrics import RuntimeMetricRecorder
from app.exports.data_quality import (
    INSTRUCTOR_MANIFEST_FILE_NAME,
    DataQualityInjectionManifestEntry,
    DataQualityReleaseContext,
    build_default_data_quality_config,
    inject_data_quality_issues,
    manifest_table,
    normalize_data_quality_level,
)
from app.models import GenerationRun

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
ReleaseProgressCallback = Callable[[str, int, int], None]
ReleaseActivityCallback = Callable[[str], None]
logger = logging.getLogger("uvicorn.error")


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


@dataclass(frozen=True)
class ExportInstrumentationSettings:
    """Resolved config flags controlling export query instrumentation."""

    enabled: bool
    capture_sql_text: bool


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
    progress_callback: ReleaseProgressCallback | None = None,
    activity_callback: ReleaseActivityCallback | None = None,
) -> StagedStudentDatasetFamily:
    """Write all release windows under a unique staging root."""

    staging_root = create_staging_root(output_root, release_name)
    instrumentation = _resolve_export_instrumentation_settings(
        session=session,
        generation_run_id=build_parameters.generation_run_id,
    )
    runtime_recorder = _build_export_runtime_recorder(
        session=session,
        build_parameters=build_parameters,
        instrumentation=instrumentation,
    )
    total_releases = len(release_windows)
    releases_list: list[StagedStudentDatasetRelease] = []
    for index, release_window in enumerate(release_windows, start=1):
        if activity_callback is not None:
            activity_callback(
                f"Starting staged release folder {index} of {total_releases}: "
                f"{release_name}{release_window.folder_suffix}."
            )
        release = write_staged_release(
            session=session,
            staging_root=staging_root,
            release_name=release_name,
            release_window=release_window,
            build_parameters=build_parameters,
            compression=compression,
            activity_callback=activity_callback,
            runtime_recorder=runtime_recorder,
            instrumentation=instrumentation,
        )
        releases_list.append(release)
        if progress_callback is not None:
            progress_callback(release.release_name, index, total_releases)
    releases = tuple(releases_list)
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
    activity_callback: ReleaseActivityCallback | None = None,
    runtime_recorder: RuntimeMetricRecorder | None = None,
    instrumentation: ExportInstrumentationSettings | None = None,
) -> StagedStudentDatasetRelease:
    """Write one release folder and manifest under an existing staging root."""

    concrete_release_name = f"{release_name}{release_window.folder_suffix}"
    release_dir = staging_root / concrete_release_name
    release_dir.mkdir(parents=True, exist_ok=False)
    _log_export_observation(
        "release_folder_start",
        release_name=concrete_release_name,
        release_type=release_window.release_type,
        snapshot_month=release_window.snapshot_month.isoformat(),
        release_dir=str(release_dir),
    )

    context = StudentDatasetQueryContext(
        generation_run_id=build_parameters.generation_run_id,
        release_window=release_window,
    )
    clean_tables: dict[str, list[dict[str, Any]]] = {}
    for table_name in STUDENT_TABLE_ORDER:
        clean_tables[table_name] = _load_table_rows(
            session=session,
            table_name=table_name,
            context=context,
            release_name=concrete_release_name,
            activity_callback=activity_callback,
            runtime_recorder=runtime_recorder,
            instrumentation=instrumentation,
        )
    data_quality_config = build_default_data_quality_config(
        level=build_parameters.data_quality_level,
    )
    if activity_callback is not None:
        activity_callback(
            f"Applying data quality rules for {concrete_release_name}."
        )
    _log_export_observation(
        "data_quality_injection_start",
        release_name=concrete_release_name,
        release_type=release_window.release_type,
        snapshot_month=release_window.snapshot_month.isoformat(),
        table_count=len(clean_tables),
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
    _log_export_observation(
        "data_quality_injection_end",
        release_name=concrete_release_name,
        release_type=release_window.release_type,
        snapshot_month=release_window.snapshot_month.isoformat(),
        affected_rows=injection_result.summary.total_affected_rows,
        affected_fields=injection_result.summary.total_affected_fields,
        manifest_entry_count=len(injection_result.manifest_entries),
    )
    files_list: list[StudentDatasetFileManifest] = []
    for table_name in STUDENT_TABLE_ORDER:
        if activity_callback is not None:
            activity_callback(
                f"Writing parquet for {concrete_release_name}: {table_name}."
            )
        files_list.append(
            _write_table_rows(
                release_dir=release_dir,
                table_name=table_name,
                row_dicts=injection_result.tables[table_name],
                compression=compression,
                release_name=concrete_release_name,
                release_type=release_window.release_type,
                snapshot_month=release_window.snapshot_month,
                runtime_recorder=runtime_recorder,
            )
        )
    files = tuple(files_list)
    manifest_path = release_dir / MANIFEST_FILE_NAME
    manifest_row_counts = {
        file_manifest.table_name: file_manifest.row_count
        for file_manifest in files
    }
    if activity_callback is not None:
        activity_callback(
            f"Running DuckDB validation for {concrete_release_name}."
        )
    if runtime_recorder is None:
        validation_result = validate_staged_release(
            release_dir=release_dir,
            release_window=release_window,
            manifest_row_counts=manifest_row_counts,
        )
    else:
        validation_metadata = _export_metric_metadata(
            release_name=concrete_release_name,
            table_name=None,
            release_type=release_window.release_type,
            snapshot_month=release_window.snapshot_month,
        )
        with runtime_recorder.measure(
            "validate_release_folder",
            output_count=len(manifest_row_counts),
            metadata=validation_metadata,
        ):
            validation_result = validate_staged_release(
                release_dir=release_dir,
                release_window=release_window,
                manifest_row_counts=manifest_row_counts,
            )
        runtime_recorder.flush()
    manifest = _release_manifest(
        release_name=concrete_release_name,
        release_window=release_window,
        build_parameters=build_parameters,
        files=files,
        release_dir=release_dir,
        compression=compression,
        validation_result=validation_result,
    )
    if activity_callback is not None:
        activity_callback(
            f"Writing manifest for {concrete_release_name}."
        )
    _write_json(manifest_path, manifest)
    _log_export_observation(
        "release_folder_complete",
        release_name=concrete_release_name,
        release_type=release_window.release_type,
        snapshot_month=release_window.snapshot_month.isoformat(),
        release_dir=str(release_dir),
        file_count=len(files),
    )
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
    release_name: str,
    activity_callback: ReleaseActivityCallback | None = None,
    runtime_recorder: RuntimeMetricRecorder | None = None,
    instrumentation: ExportInstrumentationSettings | None = None,
) -> list[dict[str, Any]]:
    projection = PROJECTION_BY_TABLE[table_name]
    if activity_callback is not None:
        activity_callback(
            f"Building source query for {release_name}: {table_name}."
        )
    query = build_student_dataset_query(table_name, context)
    query_metadata = _export_metric_metadata(
        release_name=release_name,
        table_name=table_name,
        release_type=context.release_window.release_type,
        snapshot_month=context.release_window.snapshot_month,
    )
    if runtime_recorder is not None and instrumentation is not None and instrumentation.capture_sql_text:
        query_metadata["sql_text"] = _compiled_sql_text(
            query=query,
            bind=session.get_bind(),
        )
    if activity_callback is not None:
        activity_callback(
            f"Resolving database bind for {release_name}: {table_name}."
        )
    bind = session.get_bind()
    if activity_callback is not None:
        activity_callback(
            f"Resolved database bind for {release_name}: {table_name}. "
            f"{_pool_status(bind)}"
        )
        activity_callback(
            f"Acquiring database connection for {release_name}: {table_name}."
        )
    connection = session.connection()
    if activity_callback is not None:
        activity_callback(
            f"Connection acquired for {release_name}: {table_name}. "
            f"{_pool_status(connection)}"
        )
        activity_callback(
            f"Executing source query for {release_name}: {table_name}."
        )
    query_started = perf_counter()
    _log_export_observation(
        "source_query_start",
        release_name=release_name,
        table_name=table_name,
        release_type=context.release_window.release_type,
        snapshot_month=context.release_window.snapshot_month.isoformat(),
    )
    if runtime_recorder is None:
        rows = session.execute(query).mappings().all()
    else:
        with runtime_recorder.measure(
            "execute_source_query",
            metadata=query_metadata,
        ) as metric:
            rows = session.execute(query).mappings().all()
            metric["output_count"] = len(rows)
        runtime_recorder.flush()
    _log_export_observation(
        "source_query_end",
        release_name=release_name,
        table_name=table_name,
        release_type=context.release_window.release_type,
        snapshot_month=context.release_window.snapshot_month.isoformat(),
        row_count=len(rows),
        elapsed_ms=int((perf_counter() - query_started) * 1000),
    )
    if activity_callback is not None:
        activity_callback(
            f"Fetched {len(rows):,} source rows for {release_name}: {table_name}."
        )
    normalize_started = perf_counter()
    _log_export_observation(
        "normalize_source_rows_start",
        release_name=release_name,
        table_name=table_name,
        release_type=context.release_window.release_type,
        snapshot_month=context.release_window.snapshot_month.isoformat(),
        row_count=len(rows),
    )
    if runtime_recorder is None:
        normalized_rows = [
            {column_name: _normalize_value(row[column_name]) for column_name in projection.included_columns}
            for row in rows
        ]
    else:
        with runtime_recorder.measure(
            "normalize_source_rows",
            input_count=len(rows),
            metadata=query_metadata,
        ) as metric:
            normalized_rows = [
                {column_name: _normalize_value(row[column_name]) for column_name in projection.included_columns}
                for row in rows
            ]
            metric["output_count"] = len(normalized_rows)
        runtime_recorder.flush()
    _log_export_observation(
        "normalize_source_rows_end",
        release_name=release_name,
        table_name=table_name,
        release_type=context.release_window.release_type,
        snapshot_month=context.release_window.snapshot_month.isoformat(),
        row_count=len(normalized_rows),
        elapsed_ms=int((perf_counter() - normalize_started) * 1000),
    )
    if activity_callback is not None:
        activity_callback(
            f"Normalized {len(normalized_rows):,} source rows for {release_name}: {table_name}."
        )
    return normalized_rows


def _pool_status(bind: Engine | Connection | Any) -> str:
    pool = getattr(bind, "pool", None)
    if pool is None:
        engine = getattr(bind, "engine", None)
        pool = getattr(engine, "pool", None)
    if pool is None or not hasattr(pool, "status"):
        return "Pool status unavailable."
    try:
        return pool.status()
    except Exception:
        return "Pool status unavailable."


def _write_table_rows(
    *,
    release_dir: Path,
    table_name: str,
    row_dicts: list[dict[str, Any]],
    compression: str,
    release_name: str,
    release_type: str,
    snapshot_month: date | None,
    runtime_recorder: RuntimeMetricRecorder | None = None,
) -> StudentDatasetFileManifest:
    projection = PROJECTION_BY_TABLE[table_name]
    metadata = _export_metric_metadata(
        release_name=release_name,
        table_name=table_name,
        release_type=release_type,
        snapshot_month=snapshot_month,
    )
    build_started = perf_counter()
    _log_export_observation(
        "build_parquet_table_start",
        release_name=release_name,
        table_name=table_name,
        release_type=release_type,
        snapshot_month=snapshot_month.isoformat() if snapshot_month is not None else None,
        row_count=len(row_dicts),
    )
    if runtime_recorder is None:
        table = pa.table(
            {
                column_name: pa.array([row[column_name] for row in row_dicts])
                for column_name in projection.included_columns
            }
        )
    else:
        with runtime_recorder.measure(
            "build_parquet_table",
            input_count=len(row_dicts),
            metadata=metadata,
        ) as metric:
            table = pa.table(
                {
                    column_name: pa.array([row[column_name] for row in row_dicts])
                    for column_name in projection.included_columns
                }
            )
            metric["output_count"] = table.num_rows
        runtime_recorder.flush()
    _log_export_observation(
        "build_parquet_table_end",
        release_name=release_name,
        table_name=table_name,
        release_type=release_type,
        snapshot_month=snapshot_month.isoformat() if snapshot_month is not None else None,
        row_count=table.num_rows,
        elapsed_ms=int((perf_counter() - build_started) * 1000),
    )
    file_path = release_dir / projection.output_file
    write_started = perf_counter()
    _log_export_observation(
        "write_parquet_file_start",
        release_name=release_name,
        table_name=table_name,
        release_type=release_type,
        snapshot_month=snapshot_month.isoformat() if snapshot_month is not None else None,
        row_count=table.num_rows,
        file_path=str(file_path),
    )
    if runtime_recorder is None:
        pq.write_table(table, file_path, compression=compression)
    else:
        with runtime_recorder.measure(
            "write_parquet_file",
            input_count=table.num_rows,
            output_count=table.num_rows,
            metadata=metadata,
        ):
            pq.write_table(table, file_path, compression=compression)
        runtime_recorder.flush()
    _log_export_observation(
        "write_parquet_file_end",
        release_name=release_name,
        table_name=table_name,
        release_type=release_type,
        snapshot_month=snapshot_month.isoformat() if snapshot_month is not None else None,
        row_count=table.num_rows,
        elapsed_ms=int((perf_counter() - write_started) * 1000),
        file_path=str(file_path),
        file_size_bytes=file_path.stat().st_size if file_path.exists() else None,
    )
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


def _resolve_export_instrumentation_settings(
    *,
    session: Session,
    generation_run_id: int,
) -> ExportInstrumentationSettings:
    try:
        generation_run = session.get(GenerationRun, generation_run_id)
    except SQLAlchemyError:
        generation_run = None
    payload = generation_run.parameter_snapshot if generation_run is not None else None
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError:
            payload = None
    instrumentation = payload.get("instrumentation") if isinstance(payload, dict) else None
    if not isinstance(instrumentation, dict):
        return ExportInstrumentationSettings(
            enabled=False,
            capture_sql_text=False,
        )
    enabled = instrumentation.get("export_queries_enabled", False)
    capture_sql_text = instrumentation.get("export_query_sql_text_enabled", False)
    return ExportInstrumentationSettings(
        enabled=bool(enabled) if isinstance(enabled, bool) else False,
        capture_sql_text=bool(capture_sql_text)
        if isinstance(capture_sql_text, bool)
        else False,
    )


def _build_export_runtime_recorder(
    *,
    session: Session,
    build_parameters: StudentDatasetBuildParameters,
    instrumentation: ExportInstrumentationSettings,
) -> RuntimeMetricRecorder | None:
    if not instrumentation.enabled:
        return None
    return RuntimeMetricRecorder(
        session=session,
        generation_run_id=build_parameters.generation_run_id,
        stage_name="student_dataset_export",
    )


def _export_metric_metadata(
    *,
    release_name: str,
    table_name: str | None,
    release_type: str,
    snapshot_month: date | None,
) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "release_name": release_name,
        "release_type": release_type,
    }
    if table_name is not None:
        metadata["table_name"] = table_name
    if snapshot_month is not None:
        metadata["snapshot_month"] = snapshot_month.isoformat()
    return metadata


def _compiled_sql_text(
    *,
    query: Any,
    bind: Engine | Connection | Any,
    max_length: int = 20000,
) -> str:
    try:
        compiled = query.compile(
            dialect=getattr(bind, "dialect", None),
            compile_kwargs={"literal_binds": True},
        )
        sql_text = str(compiled)
    except Exception:
        sql_text = str(query)
    if len(sql_text) <= max_length:
        return sql_text
    return f"{sql_text[:max_length]}... [truncated]"


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


def _log_export_observation(event_name: str, **fields: Any) -> None:
    details = " ".join(
        f"{key}={value}"
        for key, value in sorted(
            {**fields, "rss_mb": _current_rss_megabytes()}.items()
        )
        if value is not None
    )
    logger.info("Student dataset export %s %s", event_name, details)


def _current_rss_megabytes() -> float | None:
    try:
        with open("/proc/self/status", encoding="utf-8") as handle:
            for line in handle:
                if line.startswith("VmRSS:"):
                    parts = line.split()
                    if len(parts) >= 2:
                        return round(int(parts[1]) / 1024, 2)
    except OSError:
        pass
    try:
        usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    except OSError:
        return None
    if os.name == "posix":
        return round(usage / 1024, 2)
    return round(usage / (1024 * 1024), 2)
