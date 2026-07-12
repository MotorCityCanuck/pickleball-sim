"""Staged Parquet writer for student-facing dataset releases."""

from __future__ import annotations

import json
import logging
import os
import random
import resource
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from time import perf_counter
from typing import Any, Callable, Mapping
from uuid import UUID, uuid4

import pyarrow as pa
import pyarrow.parquet as pq
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from sqlalchemy.sql import sqltypes

from app.generation.runtime_metrics import RuntimeMetricRecorder
from app.exports.data_quality import (
    INSTRUCTOR_MANIFEST_FILE_NAME,
    DataQualityDuplicateLikeCaptures,
    DataQualityDuplicateLikePlan,
    DataQualityDuplicateLikeNextIds,
    DataQualityInjectionManifestEntry,
    DataQualityReleaseContext,
    apply_table_quality_rules,
    build_duplicate_like_rows,
    build_default_data_quality_config,
    create_injection_state,
    injection_summary_from_state,
    manifest_table,
    normalize_data_quality_level,
    plan_duplicate_like_rows,
    validate_streamed_injected_tables,
)
from app.exports.data_quality.config import (
    ISSUE_TYPE_DUPLICATE_LIKE_ROWS,
    SUPPORTED_ISSUE_TYPES,
    level_profile,
)
from app.exports.data_quality.injector import (
    ROW_RATE_ISSUES,
    _candidate_sample_limit,
    _measure_injection_phase,
    _mutated_value,
    _sample_candidate_ordinals,
    _target_count,
)
from app.exports.data_quality.rules import eligible_columns, next_primary_key, primary_key_column
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
EXPORT_RSS_GUARD_ENV_VAR = "STUDENT_DATASET_EXPORT_RSS_GUARD_MB"
SOURCE_QUERY_STREAM_BATCH_SIZE = 10_000
PARQUET_ROW_GROUP_SIZE = 10_000
DUPLICATE_LIKE_TABLE_ORDER = (
    "matches",
    "match_teams",
    "match_team_players",
    "match_games",
)
DUPLICATE_LIKE_TABLES = frozenset(DUPLICATE_LIKE_TABLE_ORDER)
ReleaseProgressCallback = Callable[[str, int, int], None]
ReleaseActivityCallback = Callable[[str], None]
logger = logging.getLogger("uvicorn.error")


class StudentDatasetWriteError(RuntimeError):
    """Raised when staged student dataset files cannot be written."""


class StudentDatasetExportMemoryLimitError(StudentDatasetWriteError):
    """Raised when the export exceeds its configured RSS guard."""


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
    rss_guard_mb: float | None = None


@dataclass(frozen=True)
class _StreamedDataQualityWriteResult:
    files: tuple[StudentDatasetFileManifest, ...]
    manifest_entries: tuple[DataQualityInjectionManifestEntry, ...]
    original_table_row_counts: Mapping[str, int]
    injected_table_row_counts: Mapping[str, int]


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
    job_status_id: int | None = None,
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
        job_status_id=job_status_id,
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
    rss_guard_mb = instrumentation.rss_guard_mb if instrumentation is not None else None
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
    data_quality_config = build_default_data_quality_config(
        level=build_parameters.data_quality_level,
    )
    release_context = DataQualityReleaseContext(
        release_id=concrete_release_name,
        release_name=concrete_release_name,
        release_type=release_window.release_type,
        generation_run_id=build_parameters.generation_run_id,
        snapshot_month=release_window.snapshot_month,
    )
    files_list: list[StudentDatasetFileManifest] = []
    data_quality_manifest_entries: tuple[DataQualityInjectionManifestEntry, ...] = ()
    if _data_quality_injection_is_active(
        config=data_quality_config,
        release_type=release_window.release_type,
    ):
        if activity_callback is not None:
            activity_callback(
                f"Applying data quality rules for {concrete_release_name}."
            )
        _check_export_rss_guard(
            rss_guard_mb=rss_guard_mb,
            release_name=concrete_release_name,
            release_type=release_window.release_type,
            snapshot_month=release_window.snapshot_month,
            phase_name="before_data_quality_injection",
            activity_callback=activity_callback,
        )
        injection_metadata = _export_metric_metadata(
            release_name=concrete_release_name,
            table_name=None,
            release_type=release_window.release_type,
            snapshot_month=release_window.snapshot_month,
        )
        injection_observer = _build_data_quality_injection_observer(
            release_name=concrete_release_name,
            release_type=release_window.release_type,
            snapshot_month=release_window.snapshot_month,
            runtime_recorder=runtime_recorder,
            activity_callback=activity_callback,
            rss_guard_mb=rss_guard_mb,
        )
        if runtime_recorder is None:
            streaming_result = _write_data_quality_tainted_release_streaming(
                session=session,
                release_dir=release_dir,
                context=context,
                release_name=concrete_release_name,
                release_window=release_window,
                config=data_quality_config,
                release_context=release_context,
                compression=compression,
                activity_callback=activity_callback,
                runtime_recorder=runtime_recorder,
                instrumentation=instrumentation,
                injection_observer=injection_observer,
                rss_guard_mb=rss_guard_mb,
            )
        else:
            with runtime_recorder.measure(
                "inject_data_quality_issues",
                metadata=injection_metadata,
            ) as metric:
                streaming_result = _write_data_quality_tainted_release_streaming(
                    session=session,
                    release_dir=release_dir,
                    context=context,
                    release_name=concrete_release_name,
                    release_window=release_window,
                    config=data_quality_config,
                    release_context=release_context,
                    compression=compression,
                    activity_callback=activity_callback,
                    runtime_recorder=runtime_recorder,
                    instrumentation=instrumentation,
                    injection_observer=injection_observer,
                    rss_guard_mb=rss_guard_mb,
                )
                metric["input_count"] = sum(streaming_result.original_table_row_counts.values())
                metric["output_count"] = sum(streaming_result.injected_table_row_counts.values())
                _record_metric_rss(metric)
            runtime_recorder.flush()
        files_list.extend(streaming_result.files)
        data_quality_manifest_entries = streaming_result.manifest_entries
    else:
        _log_export_observation(
            "data_quality_injection_skipped",
            release_name=concrete_release_name,
            release_type=release_window.release_type,
            snapshot_month=release_window.snapshot_month.isoformat(),
            effective_level=data_quality_config.effective_level_for_release(
                release_window.release_type
            ),
        )
        for table_name in STUDENT_TABLE_ORDER:
            if activity_callback is not None:
                activity_callback(
                    f"Writing parquet for {concrete_release_name}: {table_name}."
                )
            files_list.append(
                _write_table_from_source_stream(
                    session=session,
                    release_dir=release_dir,
                    table_name=table_name,
                    context=context,
                    release_name=concrete_release_name,
                    compression=compression,
                    runtime_recorder=runtime_recorder,
                    instrumentation=instrumentation,
                    activity_callback=activity_callback,
                    rss_guard_mb=rss_guard_mb,
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
        ) as metric:
            validation_result = validate_staged_release(
                release_dir=release_dir,
                release_window=release_window,
                manifest_row_counts=manifest_row_counts,
            )
            _record_metric_rss(metric)
        runtime_recorder.flush()
    _check_export_rss_guard(
        rss_guard_mb=rss_guard_mb,
        release_name=concrete_release_name,
        release_type=release_window.release_type,
        snapshot_month=release_window.snapshot_month,
        phase_name="after_validate_release_folder",
        activity_callback=activity_callback,
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
        data_quality_manifest_entries=data_quality_manifest_entries,
    )


def _write_data_quality_tainted_release_streaming(
    *,
    session: Session,
    release_dir: Path,
    context: StudentDatasetQueryContext,
    release_name: str,
    release_window: StudentDatasetReleaseWindow,
    config,
    release_context: DataQualityReleaseContext,
    compression: str,
    activity_callback: ReleaseActivityCallback | None,
    runtime_recorder: RuntimeMetricRecorder | None,
    instrumentation: ExportInstrumentationSettings | None,
    injection_observer: Callable[[str, Mapping[str, Any]], None],
    rss_guard_mb: float | None,
) -> _StreamedDataQualityWriteResult:
    requested_level = normalize_data_quality_level(config.level)
    effective_level = config.effective_level_for_release(release_window.release_type)
    state = create_injection_state(
        config=config,
        release_context=release_context,
        effective_level=effective_level,
        instrumentation_callback=injection_observer,
    )
    files_by_table: dict[str, StudentDatasetFileManifest] = {}
    original_table_row_counts: dict[str, int] = {}
    injected_table_row_counts: dict[str, int] = {}
    temp_paths: dict[str, Path] = {}
    next_ids: dict[str, int] = {}
    processed_tables: set[str] = set()
    source_match_ids: set[object] = set()
    source_match_team_ids: set[object] = set()
    matches_by_id: dict[object, dict[str, Any]] = {}
    match_teams_by_match_id: defaultdict[object, list[dict[str, Any]]] = defaultdict(list)
    players_by_match_team_id: defaultdict[object, list[dict[str, Any]]] = defaultdict(list)
    games_by_match_id: defaultdict[object, list[dict[str, Any]]] = defaultdict(list)

    _log_export_observation(
        "data_quality_injection_start",
        release_name=release_name,
        release_type=release_window.release_type,
        snapshot_month=release_window.snapshot_month.isoformat(),
        table_count=len(STUDENT_TABLE_ORDER),
        mode="streaming",
    )
    capture_started = perf_counter()
    prepare_started = perf_counter()
    injection_observer(
        "capture_original_table_stats_start",
        {
            "phase_name": "capture_original_table_stats",
            "table_count": len(STUDENT_TABLE_ORDER),
        },
    )
    injection_observer(
        "prepare_injected_tables_start",
        {
            "phase_name": "prepare_injected_tables",
            "table_count": len(STUDENT_TABLE_ORDER),
            "copy_mode": "streaming",
        },
    )

    duplicate_plan = None

    def table_can_stream_direct(table_name: str) -> bool:
        if table_name in DUPLICATE_LIKE_TABLES:
            return False
        table_rule = config.table_rules.get(table_name)
        if table_rule is None or not table_rule.enabled:
            return True
        return len(table_rule.allowed_issue_types) == 0

    def table_can_stream_with_chunk_local_mutation(table_name: str) -> bool:
        table_rule = config.table_rules.get(table_name)
        if table_rule is None or not table_rule.enabled:
            return False
        return any(
            issue_type in SUPPORTED_ISSUE_TYPES and issue_type not in ROW_RATE_ISSUES
            for issue_type in table_rule.allowed_issue_types
        )

    def process_table(table_name: str) -> None:
        nonlocal duplicate_plan, source_match_ids, source_match_team_ids
        nonlocal matches_by_id, match_teams_by_match_id
        nonlocal players_by_match_team_id, games_by_match_id
        if table_can_stream_direct(table_name):
            if activity_callback is not None:
                activity_callback(f"Writing parquet for {release_name}: {table_name}.")
            file_manifest = _write_table_from_source_stream(
                session=session,
                release_dir=release_dir,
                table_name=table_name,
                context=context,
                release_name=release_name,
                compression=compression,
                runtime_recorder=runtime_recorder,
                instrumentation=instrumentation,
                activity_callback=activity_callback,
                rss_guard_mb=rss_guard_mb,
            )
            original_table_row_counts[table_name] = file_manifest.row_count
            injected_table_row_counts[table_name] = file_manifest.row_count
            files_by_table[table_name] = file_manifest
            processed_tables.add(table_name)
            _check_export_rss_guard(
                rss_guard_mb=rss_guard_mb,
                release_name=release_name,
                release_type=release_window.release_type,
                snapshot_month=release_window.snapshot_month,
                phase_name="after_streamed_data_quality_table",
                table_name=table_name,
                activity_callback=activity_callback,
            )
            return
        if table_can_stream_with_chunk_local_mutation(table_name):
            if activity_callback is not None:
                activity_callback(f"Writing parquet for {release_name}: {table_name}.")
            final_file_path = None
            if table_name in DUPLICATE_LIKE_TABLES:
                final_file_path = release_dir / f".{table_name}.base.parquet"
            file_manifest = _write_chunk_locally_mutated_table_from_source_stream(
                session=session,
                release_dir=release_dir,
                table_name=table_name,
                context=context,
                release_name=release_name,
                compression=compression,
                runtime_recorder=runtime_recorder,
                instrumentation=instrumentation,
                activity_callback=activity_callback,
                rss_guard_mb=rss_guard_mb,
                state=state,
                injection_observer=injection_observer,
                release_type=release_window.release_type,
                snapshot_month=release_window.snapshot_month,
                final_file_path=final_file_path,
            )
            original_table_row_counts[table_name] = file_manifest.row_count
            if table_name == "matches":
                (
                    duplicate_plan,
                    matches_by_id,
                    next_ids[table_name],
                ) = _plan_and_capture_duplicate_source_matches(
                    state=state,
                    file_path=file_manifest.file_path,
                    release_name=release_name,
                    injection_observer=injection_observer,
                )
                source_match_ids = set(duplicate_plan.source_match_ids)
            elif table_name == "match_teams":
                (
                    captured_match_teams,
                    source_match_team_ids,
                    next_ids[table_name],
                ) = _capture_match_teams_for_duplicate_rows(
                    file_path=file_manifest.file_path,
                    source_match_ids=source_match_ids,
                )
                match_teams_by_match_id = captured_match_teams
            elif table_name == "match_team_players":
                (
                    players_by_match_team_id,
                    next_ids[table_name],
                ) = _capture_match_team_players_for_duplicate_rows(
                    file_path=file_manifest.file_path,
                    source_match_team_ids=source_match_team_ids,
                )
            elif table_name == "match_games":
                (
                    games_by_match_id,
                    next_ids[table_name],
                ) = _capture_match_games_for_duplicate_rows(
                    file_path=file_manifest.file_path,
                    source_match_ids=source_match_ids,
                )
            if table_name in DUPLICATE_LIKE_TABLES:
                temp_paths[table_name] = file_manifest.file_path
            else:
                injected_table_row_counts[table_name] = file_manifest.row_count
                files_by_table[table_name] = file_manifest
            processed_tables.add(table_name)
            _check_export_rss_guard(
                rss_guard_mb=rss_guard_mb,
                release_name=release_name,
                release_type=release_window.release_type,
                snapshot_month=release_window.snapshot_month,
                phase_name="after_streamed_data_quality_table",
                table_name=table_name,
                activity_callback=activity_callback,
            )
            return
        load_started = perf_counter()
        injection_observer(
            "buffered_table_load_start",
            {
                "phase_name": "buffered_table_load",
                "table_name": table_name,
                "table_mode": "buffered",
            },
        )
        row_dicts = _load_table_rows(
            session=session,
            table_name=table_name,
            context=context,
            release_name=release_name,
            activity_callback=activity_callback,
            runtime_recorder=runtime_recorder,
            instrumentation=instrumentation,
            rss_guard_mb=rss_guard_mb,
        )
        injection_observer(
            "buffered_table_load_end",
            {
                "phase_name": "buffered_table_load",
                "table_name": table_name,
                "table_mode": "buffered",
                "row_count": len(row_dicts),
                "input_count": len(row_dicts),
                "output_count": len(row_dicts),
                "elapsed_ms": int((perf_counter() - load_started) * 1000),
            },
        )
        original_table_row_counts[table_name] = len(row_dicts)
        apply_started = perf_counter()
        apply_table_quality_rules(
            state,
            table_name=table_name,
            rows=row_dicts,
        )
        injection_observer(
            "buffered_table_apply_rules_end",
            {
                "phase_name": "buffered_table_apply_rules",
                "table_name": table_name,
                "table_mode": "buffered",
                "row_count": len(row_dicts),
                "input_count": len(row_dicts),
                "output_count": len(row_dicts),
                "elapsed_ms": int((perf_counter() - apply_started) * 1000),
            },
        )
        next_ids[table_name] = next_primary_key(row_dicts, table_name)
        capture_started = perf_counter()
        captured_row_count = 0
        if table_name == "matches":
            duplicate_plan = plan_duplicate_like_rows(state, matches=row_dicts)
            source_match_ids = set(duplicate_plan.source_match_ids)
            matches_by_id.update(
                {
                    row["id"]: dict(row)
                    for row in row_dicts
                    if row["id"] in source_match_ids
                }
            )
            captured_row_count = len(matches_by_id)
        elif table_name == "match_teams":
            for row in row_dicts:
                if row["match_id"] in source_match_ids:
                    cloned_row = dict(row)
                    match_teams_by_match_id[row["match_id"]].append(cloned_row)
                    source_match_team_ids.add(row["id"])
                    captured_row_count += 1
        elif table_name == "match_team_players":
            for row in row_dicts:
                if row["match_team_id"] in source_match_team_ids:
                    players_by_match_team_id[row["match_team_id"]].append(dict(row))
                    captured_row_count += 1
        elif table_name == "match_games":
            for row in row_dicts:
                if row["match_id"] in source_match_ids:
                    games_by_match_id[row["match_id"]].append(dict(row))
                    captured_row_count += 1
        injection_observer(
            "buffered_table_duplicate_capture_end",
            {
                "phase_name": "buffered_table_duplicate_capture",
                "table_name": table_name,
                "table_mode": "buffered",
                "row_count": len(row_dicts),
                "input_count": len(row_dicts),
                "output_count": captured_row_count,
                "captured_row_count": captured_row_count,
                "source_match_count": len(source_match_ids),
                "source_match_team_count": len(source_match_team_ids),
                "elapsed_ms": int((perf_counter() - capture_started) * 1000),
            },
        )

        if activity_callback is not None:
            activity_callback(f"Writing parquet for {release_name}: {table_name}.")
        write_started = perf_counter()
        if table_name in DUPLICATE_LIKE_TABLES:
            temp_path = release_dir / f".{table_name}.base.parquet"
            temp_paths[table_name] = temp_path
            _write_table_rows_to_file(
                file_path=temp_path,
                file_name=PROJECTION_BY_TABLE[table_name].output_file,
                table_name=table_name,
                row_dicts=row_dicts,
                compression=compression,
                release_name=release_name,
                release_type=release_window.release_type,
                snapshot_month=release_window.snapshot_month,
                runtime_recorder=runtime_recorder,
                activity_callback=activity_callback,
                rss_guard_mb=rss_guard_mb,
            )
        else:
            file_manifest = _write_table_rows(
                release_dir=release_dir,
                table_name=table_name,
                row_dicts=row_dicts,
                compression=compression,
                release_name=release_name,
                release_type=release_window.release_type,
                snapshot_month=release_window.snapshot_month,
                runtime_recorder=runtime_recorder,
                activity_callback=activity_callback,
                rss_guard_mb=rss_guard_mb,
            )
            files_by_table[table_name] = file_manifest
            injected_table_row_counts[table_name] = file_manifest.row_count
        injection_observer(
            "buffered_table_write_end",
            {
                "phase_name": "buffered_table_write",
                "table_name": table_name,
                "table_mode": "buffered",
                "row_count": len(row_dicts),
                "input_count": len(row_dicts),
                "output_count": (
                    file_manifest.row_count
                    if table_name not in DUPLICATE_LIKE_TABLES
                    else len(row_dicts)
                ),
                "elapsed_ms": int((perf_counter() - write_started) * 1000),
            },
        )
        processed_tables.add(table_name)
        del row_dicts
        _check_export_rss_guard(
            rss_guard_mb=rss_guard_mb,
            release_name=release_name,
            release_type=release_window.release_type,
            snapshot_month=release_window.snapshot_month,
            phase_name="after_streamed_data_quality_table",
            table_name=table_name,
            activity_callback=activity_callback,
        )

    process_table("matches")
    process_table("match_teams")
    for table_name in STUDENT_TABLE_ORDER:
        if table_name not in processed_tables:
            process_table(table_name)

    input_count = sum(original_table_row_counts.values())
    injection_observer(
        "capture_original_table_stats_end",
        {
            "phase_name": "capture_original_table_stats",
            "table_count": len(original_table_row_counts),
            "input_count": input_count,
            "output_count": input_count,
            "elapsed_ms": int((perf_counter() - capture_started) * 1000),
        },
    )

    if duplicate_plan is None:
        raise StudentDatasetWriteError("Data quality duplicate-like planning did not run.")
    duplicate_rows = build_duplicate_like_rows(
        state,
        plan=duplicate_plan,
        captures=DataQualityDuplicateLikeCaptures(
            matches_by_id=matches_by_id,
            match_teams_by_match_id=match_teams_by_match_id,
            players_by_match_team_id=players_by_match_team_id,
            games_by_match_id=games_by_match_id,
            related_input_count=(
                original_table_row_counts.get("match_teams", 0)
                + original_table_row_counts.get("match_team_players", 0)
                + original_table_row_counts.get("match_games", 0)
            ),
        ),
        next_ids=DataQualityDuplicateLikeNextIds(
            match_id=next_ids["matches"],
            match_team_id=next_ids["match_teams"],
            match_team_player_id=next_ids["match_team_players"],
            match_game_id=next_ids["match_games"],
        ),
    )
    for table_name in DUPLICATE_LIKE_TABLE_ORDER:
        file_manifest = _append_rows_to_parquet_file(
            source_path=temp_paths[table_name],
            final_path=release_dir / PROJECTION_BY_TABLE[table_name].output_file,
            table_name=table_name,
            extra_rows=duplicate_rows[table_name],
            compression=compression,
            release_name=release_name,
            release_type=release_window.release_type,
            snapshot_month=release_window.snapshot_month,
            runtime_recorder=runtime_recorder,
            activity_callback=activity_callback,
            rss_guard_mb=rss_guard_mb,
        )
        files_by_table[table_name] = file_manifest
        injected_table_row_counts[table_name] = file_manifest.row_count
        temp_paths[table_name].unlink(missing_ok=True)

    output_count = sum(injected_table_row_counts.values())
    injection_observer(
        "prepare_injected_tables_end",
        {
            "phase_name": "prepare_injected_tables",
            "table_count": len(STUDENT_TABLE_ORDER),
            "input_count": input_count,
            "output_count": output_count,
            "copy_mode": "streaming",
            "elapsed_ms": int((perf_counter() - prepare_started) * 1000),
        },
    )
    summary = injection_summary_from_state(
        state=state,
        requested_level=requested_level,
    )
    validation_started = perf_counter()
    injection_observer(
        "validate_injected_tables_start",
        {
            "phase_name": "validate_injected_tables",
            "table_count": len(STUDENT_TABLE_ORDER),
            "input_count": output_count,
        },
    )
    validate_streamed_injected_tables(
        original_table_row_counts=original_table_row_counts,
        injected_table_row_counts=injected_table_row_counts,
        config=config,
        summary=summary,
        manifest_entries=state.manifest_entries,
    )
    injection_observer(
        "validate_injected_tables_end",
        {
            "phase_name": "validate_injected_tables",
            "table_count": len(STUDENT_TABLE_ORDER),
            "input_count": output_count,
            "output_count": len(state.manifest_entries),
            "elapsed_ms": int((perf_counter() - validation_started) * 1000),
        },
    )
    _log_export_observation(
        "data_quality_injection_end",
        release_name=release_name,
        release_type=release_window.release_type,
        snapshot_month=release_window.snapshot_month.isoformat(),
        affected_rows=summary.total_affected_rows,
        affected_fields=summary.total_affected_fields,
        manifest_entry_count=len(state.manifest_entries),
        row_count=output_count,
        mode="streaming",
    )
    return _StreamedDataQualityWriteResult(
        files=tuple(files_by_table[table_name] for table_name in STUDENT_TABLE_ORDER),
        manifest_entries=tuple(state.manifest_entries),
        original_table_row_counts=original_table_row_counts,
        injected_table_row_counts=injected_table_row_counts,
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
    rss_guard_mb: float | None = None,
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
        stream_batch_size=SOURCE_QUERY_STREAM_BATCH_SIZE,
    )
    normalize_started = perf_counter()
    _log_export_observation(
        "normalize_source_rows_start",
        release_name=release_name,
        table_name=table_name,
        release_type=context.release_window.release_type,
        snapshot_month=context.release_window.snapshot_month.isoformat(),
        stream_batch_size=SOURCE_QUERY_STREAM_BATCH_SIZE,
    )
    if runtime_recorder is None:
        normalized_rows = _load_normalized_rows_from_stream(
            session=session,
            query=query,
            table_name=table_name,
            projection_columns=projection.included_columns,
            release_name=release_name,
            release_type=context.release_window.release_type,
            snapshot_month=context.release_window.snapshot_month,
            runtime_recorder=None,
            query_metadata=query_metadata,
        )
    else:
        with runtime_recorder.measure(
            "execute_source_query",
            metadata=query_metadata,
        ) as metric:
            metric["metadata"]["stream_batch_size"] = SOURCE_QUERY_STREAM_BATCH_SIZE
            normalized_rows = _load_normalized_rows_from_stream(
                session=session,
                query=query,
                table_name=table_name,
                projection_columns=projection.included_columns,
                release_name=release_name,
                release_type=context.release_window.release_type,
                snapshot_month=context.release_window.snapshot_month,
                runtime_recorder=runtime_recorder,
                query_metadata=query_metadata,
            )
            metric["output_count"] = len(normalized_rows)
            _record_metric_rss(metric)
        runtime_recorder.flush()
    _log_export_observation(
        "source_query_end",
        release_name=release_name,
        table_name=table_name,
        release_type=context.release_window.release_type,
        snapshot_month=context.release_window.snapshot_month.isoformat(),
        row_count=len(normalized_rows),
        elapsed_ms=int((perf_counter() - query_started) * 1000),
        stream_batch_size=SOURCE_QUERY_STREAM_BATCH_SIZE,
    )
    _check_export_rss_guard(
        rss_guard_mb=rss_guard_mb,
        release_name=release_name,
        release_type=context.release_window.release_type,
        snapshot_month=context.release_window.snapshot_month,
        phase_name="after_source_query",
        table_name=table_name,
        activity_callback=activity_callback,
    )
    if activity_callback is not None:
        activity_callback(
            f"Fetched {len(normalized_rows):,} source rows for {release_name}: {table_name}."
        )
    _log_export_observation(
        "normalize_source_rows_end",
        release_name=release_name,
        table_name=table_name,
        release_type=context.release_window.release_type,
        snapshot_month=context.release_window.snapshot_month.isoformat(),
        row_count=len(normalized_rows),
        elapsed_ms=int((perf_counter() - normalize_started) * 1000),
    )
    _check_export_rss_guard(
        rss_guard_mb=rss_guard_mb,
        release_name=release_name,
        release_type=context.release_window.release_type,
        snapshot_month=context.release_window.snapshot_month,
        phase_name="after_normalize_source_rows",
        table_name=table_name,
        activity_callback=activity_callback,
    )
    if activity_callback is not None:
        activity_callback(
            f"Normalized {len(normalized_rows):,} source rows for {release_name}: {table_name}."
        )
    return normalized_rows


def _write_table_from_source_stream(
    *,
    session: Session,
    release_dir: Path,
    table_name: str,
    context: StudentDatasetQueryContext,
    release_name: str,
    compression: str,
    runtime_recorder: RuntimeMetricRecorder | None = None,
    instrumentation: ExportInstrumentationSettings | None = None,
    activity_callback: ReleaseActivityCallback | None = None,
    rss_guard_mb: float | None = None,
) -> StudentDatasetFileManifest:
    projection = PROJECTION_BY_TABLE[table_name]
    file_path = release_dir / projection.output_file
    row_count, schema = _write_source_stream_to_parquet_file(
        session=session,
        file_path=file_path,
        table_name=table_name,
        context=context,
        release_name=release_name,
        compression=compression,
        runtime_recorder=runtime_recorder,
        instrumentation=instrumentation,
        activity_callback=activity_callback,
        rss_guard_mb=rss_guard_mb,
    )
    return StudentDatasetFileManifest(
        table_name=table_name,
        file_name=projection.output_file,
        file_path=file_path,
        row_count=row_count,
        columns=projection.included_columns,
        schema_hash=_schema_hash(schema),
        checksum=_file_checksum(file_path),
    )


def _write_source_stream_to_parquet_file(
    *,
    session: Session,
    file_path: Path,
    table_name: str,
    context: StudentDatasetQueryContext,
    release_name: str,
    compression: str,
    runtime_recorder: RuntimeMetricRecorder | None = None,
    instrumentation: ExportInstrumentationSettings | None = None,
    activity_callback: ReleaseActivityCallback | None = None,
    rss_guard_mb: float | None = None,
) -> tuple[int, pa.Schema]:
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
        stream_batch_size=SOURCE_QUERY_STREAM_BATCH_SIZE,
        mode="direct_to_parquet",
    )
    query_with_streaming = query.execution_options(
        stream_results=True,
        yield_per=SOURCE_QUERY_STREAM_BATCH_SIZE,
    )
    result = session.execute(query_with_streaming).mappings()
    execute_elapsed_ms = int((perf_counter() - query_started) * 1000)

    normalize_started = perf_counter()
    write_started = perf_counter()
    schema_started = perf_counter()
    _log_export_observation(
        "normalize_source_rows_start",
        release_name=release_name,
        table_name=table_name,
        release_type=context.release_window.release_type,
        snapshot_month=context.release_window.snapshot_month.isoformat(),
        stream_batch_size=SOURCE_QUERY_STREAM_BATCH_SIZE,
        mode="direct_to_parquet",
    )
    _log_export_observation(
        "write_parquet_file_start",
        release_name=release_name,
        table_name=table_name,
        release_type=context.release_window.release_type,
        snapshot_month=context.release_window.snapshot_month.isoformat(),
        file_path=str(file_path),
        parquet_row_group_size=PARQUET_ROW_GROUP_SIZE,
        mode="direct_to_parquet",
    )
    row_count = 0
    row_group_count = 0
    chunk_count = 0
    schema: pa.Schema | None = None
    writer: pq.ParquetWriter | None = None
    normalize_elapsed_ms = 0
    try:
        for chunk_count, partition in enumerate(
            _iter_mapping_partitions(result, SOURCE_QUERY_STREAM_BATCH_SIZE),
            start=1,
        ):
            chunk_normalize_started = perf_counter()
            normalized_chunk = _normalize_row_partition(
                partition,
                projection.included_columns,
            )
            normalize_elapsed_ms += int(
                (perf_counter() - chunk_normalize_started) * 1000
            )
            if schema is None:
                schema = _infer_arrow_schema(
                    row_dicts=normalized_chunk,
                    columns=projection.included_columns,
                )
                _log_export_observation(
                    "build_parquet_table_start",
                    release_name=release_name,
                    table_name=table_name,
                    release_type=context.release_window.release_type,
                    snapshot_month=context.release_window.snapshot_month.isoformat(),
                    row_count=len(normalized_chunk),
                    mode="direct_to_parquet",
                )
                _log_export_observation(
                    "build_parquet_table_end",
                    release_name=release_name,
                    table_name=table_name,
                    release_type=context.release_window.release_type,
                    snapshot_month=context.release_window.snapshot_month.isoformat(),
                    row_count=len(normalized_chunk),
                    elapsed_ms=int((perf_counter() - schema_started) * 1000),
                    parquet_row_group_size=PARQUET_ROW_GROUP_SIZE,
                    mode="direct_to_parquet",
                )
                writer = pq.ParquetWriter(
                    file_path,
                    schema=schema,
                    compression=compression,
                )
            assert writer is not None and schema is not None
            for row_group_chunk in _iter_row_chunks(
                normalized_chunk,
                PARQUET_ROW_GROUP_SIZE,
            ):
                writer.write_table(
                    _rows_to_arrow_table(
                        rows=row_group_chunk,
                        columns=projection.included_columns,
                        schema=schema,
                    )
                )
                row_count += len(row_group_chunk)
                row_group_count += 1
            _log_export_observation(
                "source_query_stream_chunk",
                release_name=release_name,
                table_name=table_name,
                release_type=context.release_window.release_type,
                snapshot_month=context.release_window.snapshot_month.isoformat(),
                chunk_index=chunk_count,
                row_count=len(normalized_chunk),
                cumulative_row_count=row_count,
                stream_batch_size=SOURCE_QUERY_STREAM_BATCH_SIZE,
                parquet_row_group_size=PARQUET_ROW_GROUP_SIZE,
                mode="direct_to_parquet",
            )
        if schema is None:
            schema = _projection_arrow_schema(table_name)
            empty_table = _rows_to_arrow_table(
                rows=[],
                columns=projection.included_columns,
                schema=schema,
            )
            pq.write_table(empty_table, file_path, compression=compression)
            row_group_count = 1
            _log_export_observation(
                "build_parquet_table_start",
                release_name=release_name,
                table_name=table_name,
                release_type=context.release_window.release_type,
                snapshot_month=context.release_window.snapshot_month.isoformat(),
                row_count=0,
                mode="direct_to_parquet",
            )
            _log_export_observation(
                "build_parquet_table_end",
                release_name=release_name,
                table_name=table_name,
                release_type=context.release_window.release_type,
                snapshot_month=context.release_window.snapshot_month.isoformat(),
                row_count=0,
                elapsed_ms=int((perf_counter() - schema_started) * 1000),
                parquet_row_group_size=PARQUET_ROW_GROUP_SIZE,
                mode="direct_to_parquet",
            )
    finally:
        if writer is not None:
            writer.close()

    write_elapsed_ms = int((perf_counter() - write_started) * 1000)
    _log_export_observation(
        "source_query_end",
        release_name=release_name,
        table_name=table_name,
        release_type=context.release_window.release_type,
        snapshot_month=context.release_window.snapshot_month.isoformat(),
        row_count=row_count,
        elapsed_ms=int((perf_counter() - query_started) * 1000),
        stream_batch_size=SOURCE_QUERY_STREAM_BATCH_SIZE,
        mode="direct_to_parquet",
    )
    _check_export_rss_guard(
        rss_guard_mb=rss_guard_mb,
        release_name=release_name,
        release_type=context.release_window.release_type,
        snapshot_month=context.release_window.snapshot_month,
        phase_name="after_source_query",
        table_name=table_name,
        activity_callback=activity_callback,
    )
    _log_export_observation(
        "normalize_source_rows_end",
        release_name=release_name,
        table_name=table_name,
        release_type=context.release_window.release_type,
        snapshot_month=context.release_window.snapshot_month.isoformat(),
        row_count=row_count,
        elapsed_ms=normalize_elapsed_ms,
        stream_batch_size=SOURCE_QUERY_STREAM_BATCH_SIZE,
        mode="direct_to_parquet",
    )
    _check_export_rss_guard(
        rss_guard_mb=rss_guard_mb,
        release_name=release_name,
        release_type=context.release_window.release_type,
        snapshot_month=context.release_window.snapshot_month,
        phase_name="after_normalize_source_rows",
        table_name=table_name,
        activity_callback=activity_callback,
    )
    _log_export_observation(
        "write_parquet_file_end",
        release_name=release_name,
        table_name=table_name,
        release_type=context.release_window.release_type,
        snapshot_month=context.release_window.snapshot_month.isoformat(),
        row_count=row_count,
        elapsed_ms=write_elapsed_ms,
        file_path=str(file_path),
        file_size_bytes=file_path.stat().st_size if file_path.exists() else None,
        row_group_count=row_group_count,
        parquet_row_group_size=PARQUET_ROW_GROUP_SIZE,
        mode="direct_to_parquet",
    )
    _check_export_rss_guard(
        rss_guard_mb=rss_guard_mb,
        release_name=release_name,
        release_type=context.release_window.release_type,
        snapshot_month=context.release_window.snapshot_month,
        phase_name="after_write_parquet_file",
        table_name=table_name,
        activity_callback=activity_callback,
    )
    if activity_callback is not None:
        activity_callback(
            f"Wrote {row_count:,} source rows for {release_name}: {table_name}."
        )
    if runtime_recorder is not None:
        _record_direct_stream_metric(
            runtime_recorder=runtime_recorder,
            subphase_name="execute_source_query",
            elapsed_ms=execute_elapsed_ms,
            output_count=row_count,
            metadata=query_metadata,
            chunk_count=chunk_count,
            row_group_count=row_group_count,
        )
        _record_direct_stream_metric(
            runtime_recorder=runtime_recorder,
            subphase_name="normalize_source_rows",
            elapsed_ms=normalize_elapsed_ms,
            input_count=row_count,
            output_count=row_count,
            metadata=query_metadata,
            chunk_count=chunk_count,
            row_group_count=row_group_count,
        )
        _record_direct_stream_metric(
            runtime_recorder=runtime_recorder,
            subphase_name="build_parquet_table",
            elapsed_ms=int((perf_counter() - schema_started) * 1000),
            input_count=row_count,
            output_count=row_count,
            metadata=query_metadata,
            chunk_count=chunk_count,
            row_group_count=row_group_count,
        )
        _record_direct_stream_metric(
            runtime_recorder=runtime_recorder,
            subphase_name="write_parquet_file",
            elapsed_ms=write_elapsed_ms,
            input_count=row_count,
            output_count=row_count,
            metadata=query_metadata,
            chunk_count=chunk_count,
            row_group_count=row_group_count,
        )
        runtime_recorder.flush()
    return row_count, schema


def _record_direct_stream_metric(
    *,
    runtime_recorder: RuntimeMetricRecorder,
    subphase_name: str,
    elapsed_ms: int,
    metadata: Mapping[str, Any],
    input_count: int | None = None,
    output_count: int | None = None,
    chunk_count: int | None = None,
    row_group_count: int | None = None,
) -> None:
    metric_metadata = dict(metadata)
    metric_metadata["stream_batch_size"] = SOURCE_QUERY_STREAM_BATCH_SIZE
    metric_metadata["parquet_row_group_size"] = PARQUET_ROW_GROUP_SIZE
    metric_metadata["chunk_count"] = chunk_count
    metric_metadata["row_group_count"] = row_group_count
    metric_metadata["rss_mb"] = _current_rss_megabytes()
    runtime_recorder.record_completed(
        subphase_name,
        elapsed_ms=elapsed_ms,
        input_count=input_count,
        output_count=output_count,
        metadata=metric_metadata,
    )


def _write_chunk_locally_mutated_table_from_source_stream(
    *,
    session: Session,
    release_dir: Path,
    table_name: str,
    context: StudentDatasetQueryContext,
    release_name: str,
    compression: str,
    runtime_recorder: RuntimeMetricRecorder | None,
    instrumentation: ExportInstrumentationSettings | None,
    activity_callback: ReleaseActivityCallback | None,
    rss_guard_mb: float | None,
    state: Any,
    injection_observer: Callable[[str, Mapping[str, Any]], None],
    release_type: str,
    snapshot_month: date,
    final_file_path: Path | None = None,
) -> StudentDatasetFileManifest:
    projection = PROJECTION_BY_TABLE[table_name]
    table_rule = state.config.table_rules.get(table_name)
    if table_rule is None:
        raise StudentDatasetWriteError(
            f"Missing data quality rule configuration for streamed mutation table {table_name}."
        )
    issue_types = [
        issue_type
        for issue_type in table_rule.allowed_issue_types
        if issue_type in SUPPORTED_ISSUE_TYPES and issue_type not in ROW_RATE_ISSUES
    ]
    if not issue_types:
        raise StudentDatasetWriteError(
            f"Chunk-local mutation requested for table without supported issue types: {table_name}."
        )

    base_path = release_dir / f".{table_name}.streamed-source.parquet"
    row_count, schema = _write_source_stream_to_parquet_file(
        session=session,
        file_path=base_path,
        table_name=table_name,
        context=context,
        release_name=release_name,
        compression=compression,
        runtime_recorder=runtime_recorder,
        instrumentation=instrumentation,
        activity_callback=activity_callback,
        rss_guard_mb=rss_guard_mb,
    )

    current_path = base_path
    current_schema = schema
    profile = level_profile(table_rule.issue_profile or state.effective_level)
    primary_key = primary_key_column(table_name)
    row_count_value = row_count

    for issue_type in issue_types:
        columns = eligible_columns(table_name, issue_type)
        state.issue_type_candidate_rows[issue_type] = (
            state.issue_type_candidate_rows.get(issue_type, 0) + row_count_value
        )
        state.table_issue_type_candidate_rows[(table_name, issue_type)] = (
            state.table_issue_type_candidate_rows.get((table_name, issue_type), 0)
            + row_count_value
        )
        if row_count_value <= 0 or not columns:
            continue

        target_count = _target_count(
            issue_type=issue_type,
            row_count=row_count_value,
            profile=profile,
        )
        if target_count <= 0:
            continue
        rng = random.Random(
            state.config.seed_for(
                state.release_context.release_id,
                table_name,
                issue_type,
            )
        )
        candidate_count = 0
        with _measure_injection_phase(
            injection_observer,
            "issue_candidate_build",
            table_name=table_name,
            issue_type=issue_type,
            row_count=row_count_value,
            target_count=target_count,
        ) as metric:
            for chunk in _iter_parquet_row_chunks(
                file_path=current_path,
                schema=current_schema,
            ):
                candidate_count += _count_candidate_locations(chunk, columns)
            metric["output_count"] = candidate_count
            metric["candidate_count"] = candidate_count
        if candidate_count <= 0:
            continue

        sample_limit = _candidate_sample_limit(
            candidate_count=candidate_count,
            target_count=target_count,
        )
        selected_ordinals = _sample_candidate_ordinals(
            candidate_count=candidate_count,
            sample_limit=sample_limit,
            rng=rng,
        )
        candidates: list[dict[str, Any]] = []
        with _measure_injection_phase(
            injection_observer,
            "issue_candidate_shuffle",
            table_name=table_name,
            issue_type=issue_type,
            input_count=candidate_count,
            target_count=target_count,
        ) as metric:
            ordinal = 0
            row_ordinal = 0
            for chunk in _iter_parquet_row_chunks(
                file_path=current_path,
                schema=current_schema,
            ):
                for row in chunk:
                    for column_name in columns:
                        if row.get(column_name) is None:
                            continue
                        if ordinal in selected_ordinals:
                            candidates.append(
                                {
                                    "row_ordinal": row_ordinal,
                                    "column_name": column_name,
                                    "row": dict(row),
                                }
                            )
                        ordinal += 1
                    row_ordinal += 1
                    if len(candidates) >= sample_limit:
                        break
                if len(candidates) >= sample_limit:
                    break
            if len(candidates) > sample_limit:
                candidates = candidates[:sample_limit]
            rng.shuffle(candidates)
            metric["output_count"] = len(candidates)
            metric["candidate_count"] = candidate_count
            metric["sampled_count"] = len(candidates)
            metric["selection_strategy"] = "deterministic_bounded_sample"

        mutation_plan: dict[int, dict[str, Any]] = {}
        applied = 0
        with _measure_injection_phase(
            injection_observer,
            "issue_apply",
            table_name=table_name,
            issue_type=issue_type,
            input_count=len(candidates),
            target_count=target_count,
        ) as metric:
            metric["candidate_count"] = candidate_count
            metric["sampled_count"] = len(candidates)
            noop_count = 0
            skipped_row_limit_count = 0
            for candidate in candidates:
                if applied >= target_count:
                    break
                row = candidate["row"]
                pk_value = row[primary_key]
                row_key = (table_name, pk_value)
                if (
                    state.row_field_counts[row_key]
                    >= state.config.global_limits.max_affected_fields_per_row
                ):
                    skipped_row_limit_count += 1
                    continue
                column_name = str(candidate["column_name"])
                original_value = row.get(column_name)
                injected_value = _mutated_value(
                    issue_type=issue_type,
                    table_name=table_name,
                    column_name=column_name,
                    row=row,
                    original_value=original_value,
                    rng=rng,
                )
                if injected_value == original_value:
                    noop_count += 1
                    continue
                mutation_plan.setdefault(int(candidate["row_ordinal"]), {})[column_name] = (
                    pk_value,
                    original_value,
                    injected_value,
                )
                state.row_field_counts[row_key] += 1
                state.affected_rows.add(row_key)
                state.issue_type_rows[issue_type].add(row_key)
                state.table_issue_type_rows[(table_name, issue_type)].add(row_key)
                state.issue_type_field_count[issue_type] += 1
                state.manifest_entries.append(
                    DataQualityInjectionManifestEntry.create(
                        release_id=state.release_context.release_id,
                        release_name=state.release_context.release_name,
                        table_name=table_name,
                        record_primary_key=pk_value,
                        column_name=column_name,
                        issue_type=issue_type,
                        original_value=original_value,
                        injected_value=injected_value,
                        injection_level=state.effective_level,
                        random_seed=state.config.random_seed,
                        rule_id=f"{table_name}.{issue_type}",
                    )
                )
                applied += 1
            metric["output_count"] = applied
            metric["applied_count"] = applied
            metric["noop_count"] = noop_count
            metric["skipped_row_limit_count"] = skipped_row_limit_count
            metric["candidate_count"] = candidate_count
            metric["sampled_count"] = len(candidates)

        next_path = release_dir / f".{table_name}.{issue_type}.parquet"
        current_schema = _rewrite_parquet_with_mutations(
            source_path=current_path,
            target_path=next_path,
            columns=projection.included_columns,
            schema=current_schema,
            mutation_plan=mutation_plan,
            compression=compression,
        )
        if current_path != base_path:
            current_path.unlink(missing_ok=True)
        current_path = next_path
        _check_export_rss_guard(
            rss_guard_mb=rss_guard_mb,
            release_name=release_name,
            release_type=release_type,
            snapshot_month=snapshot_month,
            phase_name="after_streamed_mutation_issue",
            table_name=table_name,
            activity_callback=activity_callback,
        )

    final_path = final_file_path or (release_dir / projection.output_file)
    if current_path != final_path:
        current_path.replace(final_path)
    if base_path != final_path:
        base_path.unlink(missing_ok=True)
    return StudentDatasetFileManifest(
        table_name=table_name,
        file_name=projection.output_file,
        file_path=final_path,
        row_count=row_count_value,
        columns=projection.included_columns,
        schema_hash=_schema_hash(current_schema),
        checksum=_file_checksum(final_path),
    )


def _iter_parquet_row_chunks(
    *,
    file_path: Path,
    schema: pa.Schema | None = None,
) -> list[dict[str, Any]]:
    source_file = pq.ParquetFile(file_path)
    batch_schema = schema or source_file.schema_arrow
    for batch in source_file.iter_batches(batch_size=PARQUET_ROW_GROUP_SIZE):
        table = pa.Table.from_batches([batch], schema=batch_schema)
        yield table.to_pylist()


def _rewrite_parquet_with_mutations(
    *,
    source_path: Path,
    target_path: Path,
    columns: tuple[str, ...],
    schema: pa.Schema,
    mutation_plan: Mapping[int, Mapping[str, tuple[object, Any, Any]]],
    compression: str,
) -> pa.Schema:
    row_ordinal = 0
    with pq.ParquetWriter(target_path, schema=schema, compression=compression) as writer:
        for chunk in _iter_parquet_row_chunks(file_path=source_path, schema=schema):
            for row in chunk:
                row_mutations = mutation_plan.get(row_ordinal)
                if row_mutations:
                    for column_name, (_, _, injected_value) in row_mutations.items():
                        row[column_name] = injected_value
                row_ordinal += 1
            for row_group_chunk in _iter_row_chunks(chunk, PARQUET_ROW_GROUP_SIZE):
                writer.write_table(
                    _rows_to_arrow_table(
                        rows=row_group_chunk,
                        columns=columns,
                        schema=schema,
                    )
                )
    return schema


def _plan_and_capture_duplicate_source_matches(
    *,
    state: Any,
    file_path: Path,
    release_name: str,
    injection_observer: Callable[[str, Mapping[str, Any]], None],
) -> tuple[Any, dict[object, dict[str, Any]], int]:
    row_count = 0
    max_id = 0
    for chunk in _iter_parquet_row_chunks(file_path=file_path):
        row_count += len(chunk)
        for row in chunk:
            row_id = int(row["id"])
            if row_id > max_id:
                max_id = row_id
    matches_rule = state.config.table_rules.get("matches")
    if (
        matches_rule is None
        or ISSUE_TYPE_DUPLICATE_LIKE_ROWS not in matches_rule.allowed_issue_types
    ):
        state.issue_type_candidate_rows.setdefault(ISSUE_TYPE_DUPLICATE_LIKE_ROWS, row_count)
        state.table_issue_type_candidate_rows.setdefault(
            ("matches", ISSUE_TYPE_DUPLICATE_LIKE_ROWS),
            row_count,
        )
        return (
            DataQualityDuplicateLikePlan((), 0, row_count, 0),
            {},
            max_id + 1,
        )

    profile = level_profile(matches_rule.issue_profile or state.effective_level)
    state.issue_type_candidate_rows.setdefault(ISSUE_TYPE_DUPLICATE_LIKE_ROWS, row_count)
    state.table_issue_type_candidate_rows.setdefault(
        ("matches", ISSUE_TYPE_DUPLICATE_LIKE_ROWS),
        row_count,
    )
    target_count = _target_count(
        issue_type=ISSUE_TYPE_DUPLICATE_LIKE_ROWS,
        row_count=row_count,
        profile=profile,
    )
    if target_count <= 0 or row_count <= 0:
        return (
            DataQualityDuplicateLikePlan((), 0, row_count, 0),
            {},
            max_id + 1,
        )

    rng = random.Random(
        state.config.seed_for(
            state.release_context.release_id,
            "matches",
            ISSUE_TYPE_DUPLICATE_LIKE_ROWS,
        )
    )
    with _measure_injection_phase(
        injection_observer,
        "duplicate_like_match_copy_shuffle",
        table_name="matches",
        issue_type=ISSUE_TYPE_DUPLICATE_LIKE_ROWS,
        input_count=row_count,
        target_count=target_count,
    ) as metric:
        sample_limit = _candidate_sample_limit(
            candidate_count=row_count,
            target_count=target_count,
            multiplier=8,
            min_extra=4096,
        )
        selected_ordinals = _sample_candidate_ordinals(
            candidate_count=row_count,
            sample_limit=sample_limit,
            rng=rng,
        )
        selected_rows: list[dict[str, Any]] = []
        ordinal = 0
        for chunk in _iter_parquet_row_chunks(file_path=file_path):
            for row in chunk:
                if ordinal in selected_ordinals:
                    selected_rows.append(dict(row))
                    if len(selected_rows) >= sample_limit:
                        break
                ordinal += 1
            if len(selected_rows) >= sample_limit:
                break
        rng.shuffle(selected_rows)
        metric["output_count"] = len(selected_rows)
        metric["candidate_count"] = row_count
        metric["sampled_count"] = len(selected_rows)
        metric["selection_strategy"] = "deterministic_bounded_sample"
    captures = {row["id"]: row for row in selected_rows}
    plan = DataQualityDuplicateLikePlan(
        source_match_ids=tuple(row["id"] for row in selected_rows),
        target_count=target_count,
        candidate_count=row_count,
        sampled_count=len(selected_rows),
    )
    return plan, captures, max_id + 1


def _capture_match_teams_for_duplicate_rows(
    *,
    file_path: Path,
    source_match_ids: set[object],
) -> tuple[defaultdict[object, list[dict[str, Any]]], set[object], int]:
    captured: defaultdict[object, list[dict[str, Any]]] = defaultdict(list)
    source_match_team_ids: set[object] = set()
    max_id = 0
    for chunk in _iter_parquet_row_chunks(file_path=file_path):
        for row in chunk:
            row_id = int(row["id"])
            if row_id > max_id:
                max_id = row_id
            if row["match_id"] in source_match_ids:
                copied = dict(row)
                captured[row["match_id"]].append(copied)
                source_match_team_ids.add(row["id"])
    return captured, source_match_team_ids, max_id + 1


def _capture_match_team_players_for_duplicate_rows(
    *,
    file_path: Path,
    source_match_team_ids: set[object],
) -> tuple[defaultdict[object, list[dict[str, Any]]], int]:
    captured: defaultdict[object, list[dict[str, Any]]] = defaultdict(list)
    max_id = 0
    for chunk in _iter_parquet_row_chunks(file_path=file_path):
        for row in chunk:
            row_id = int(row["id"])
            if row_id > max_id:
                max_id = row_id
            if row["match_team_id"] in source_match_team_ids:
                captured[row["match_team_id"]].append(dict(row))
    return captured, max_id + 1


def _capture_match_games_for_duplicate_rows(
    *,
    file_path: Path,
    source_match_ids: set[object],
) -> tuple[defaultdict[object, list[dict[str, Any]]], int]:
    captured: defaultdict[object, list[dict[str, Any]]] = defaultdict(list)
    max_id = 0
    for chunk in _iter_parquet_row_chunks(file_path=file_path):
        for row in chunk:
            row_id = int(row["id"])
            if row_id > max_id:
                max_id = row_id
            if row["match_id"] in source_match_ids:
                captured[row["match_id"]].append(dict(row))
    return captured, max_id + 1


def _load_normalized_rows_from_stream(
    *,
    session: Session,
    query: Any,
    table_name: str,
    projection_columns: tuple[str, ...],
    release_name: str,
    release_type: str,
    snapshot_month: date,
    runtime_recorder: RuntimeMetricRecorder | None,
    query_metadata: Mapping[str, Any],
) -> list[dict[str, Any]]:
    normalized_rows: list[dict[str, Any]] = []
    query_with_streaming = query.execution_options(
        stream_results=True,
        yield_per=SOURCE_QUERY_STREAM_BATCH_SIZE,
    )
    result = session.execute(query_with_streaming).mappings()
    chunk_index = 0
    if runtime_recorder is None:
        for chunk_index, partition in enumerate(
            _iter_mapping_partitions(result, SOURCE_QUERY_STREAM_BATCH_SIZE),
            start=1,
        ):
            normalized_rows.extend(
                _normalize_row_partition(partition, projection_columns)
            )
            _log_export_observation(
                "source_query_stream_chunk",
                release_name=release_name,
                table_name=table_name,
                release_type=release_type,
                snapshot_month=snapshot_month.isoformat(),
                chunk_index=chunk_index,
                row_count=len(partition),
                cumulative_row_count=len(normalized_rows),
                stream_batch_size=SOURCE_QUERY_STREAM_BATCH_SIZE,
            )
        return normalized_rows

    with runtime_recorder.measure(
        "normalize_source_rows",
        metadata=dict(query_metadata),
    ) as metric:
        metric["metadata"]["stream_batch_size"] = SOURCE_QUERY_STREAM_BATCH_SIZE
        for chunk_index, partition in enumerate(
            _iter_mapping_partitions(result, SOURCE_QUERY_STREAM_BATCH_SIZE),
            start=1,
        ):
            normalized_rows.extend(
                _normalize_row_partition(partition, projection_columns)
            )
            _log_export_observation(
                "source_query_stream_chunk",
                release_name=release_name,
                table_name=table_name,
                release_type=release_type,
                snapshot_month=snapshot_month.isoformat(),
                chunk_index=chunk_index,
                row_count=len(partition),
                cumulative_row_count=len(normalized_rows),
                stream_batch_size=SOURCE_QUERY_STREAM_BATCH_SIZE,
            )
        metric["input_count"] = len(normalized_rows)
        metric["output_count"] = len(normalized_rows)
        metric["metadata"]["chunk_count"] = chunk_index
        _record_metric_rss(metric)
    runtime_recorder.flush()
    return normalized_rows


def _iter_mapping_partitions(result: Any, batch_size: int):
    if hasattr(result, "partitions"):
        yield from result.partitions(batch_size)
        return

    partition = []
    for row in result:
        partition.append(row)
        if len(partition) >= batch_size:
            yield partition
            partition = []
    if partition:
        yield partition


def _normalize_row_partition(
    rows: list[Any],
    projection_columns: tuple[str, ...],
) -> list[dict[str, Any]]:
    return [
        {
            column_name: _normalize_value(row[column_name])
            for column_name in projection_columns
        }
        for row in rows
    ]


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
    activity_callback: ReleaseActivityCallback | None = None,
    rss_guard_mb: float | None = None,
) -> StudentDatasetFileManifest:
    projection = PROJECTION_BY_TABLE[table_name]
    return _write_table_rows_to_file(
        file_path=release_dir / projection.output_file,
        file_name=projection.output_file,
        table_name=table_name,
        row_dicts=row_dicts,
        compression=compression,
        release_name=release_name,
        release_type=release_type,
        snapshot_month=snapshot_month,
        runtime_recorder=runtime_recorder,
        activity_callback=activity_callback,
        rss_guard_mb=rss_guard_mb,
    )


def _write_table_rows_to_file(
    *,
    file_path: Path,
    file_name: str,
    table_name: str,
    row_dicts: list[dict[str, Any]],
    compression: str,
    release_name: str,
    release_type: str,
    snapshot_month: date | None,
    runtime_recorder: RuntimeMetricRecorder | None = None,
    activity_callback: ReleaseActivityCallback | None = None,
    rss_guard_mb: float | None = None,
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
        schema = _infer_arrow_schema(
            row_dicts=row_dicts,
            columns=projection.included_columns,
        )
    else:
        with runtime_recorder.measure(
            "build_parquet_table",
            input_count=len(row_dicts),
            metadata=metadata,
        ) as metric:
            schema = _infer_arrow_schema(
                row_dicts=row_dicts,
                columns=projection.included_columns,
            )
            metric["output_count"] = len(row_dicts)
            metric["metadata"]["parquet_row_group_size"] = PARQUET_ROW_GROUP_SIZE
            _record_metric_rss(metric)
        runtime_recorder.flush()
    _log_export_observation(
        "build_parquet_table_end",
        release_name=release_name,
        table_name=table_name,
        release_type=release_type,
        snapshot_month=snapshot_month.isoformat() if snapshot_month is not None else None,
        row_count=len(row_dicts),
        elapsed_ms=int((perf_counter() - build_started) * 1000),
        parquet_row_group_size=PARQUET_ROW_GROUP_SIZE,
    )
    _check_export_rss_guard(
        rss_guard_mb=rss_guard_mb,
        release_name=release_name,
        release_type=release_type,
        snapshot_month=snapshot_month,
        phase_name="after_build_parquet_table",
        table_name=table_name,
        activity_callback=activity_callback,
    )
    write_started = perf_counter()
    _log_export_observation(
        "write_parquet_file_start",
        release_name=release_name,
        table_name=table_name,
        release_type=release_type,
        snapshot_month=snapshot_month.isoformat() if snapshot_month is not None else None,
        row_count=len(row_dicts),
        file_path=str(file_path),
        parquet_row_group_size=PARQUET_ROW_GROUP_SIZE,
    )
    if runtime_recorder is None:
        row_group_count = _write_rows_to_parquet_file(
            file_path=file_path,
            schema=schema,
            columns=projection.included_columns,
            row_dicts=row_dicts,
            compression=compression,
        )
    else:
        with runtime_recorder.measure(
            "write_parquet_file",
            input_count=len(row_dicts),
            output_count=len(row_dicts),
            metadata=metadata,
        ) as metric:
            row_group_count = _write_rows_to_parquet_file(
                file_path=file_path,
                schema=schema,
                columns=projection.included_columns,
                row_dicts=row_dicts,
                compression=compression,
            )
            metric["metadata"]["parquet_row_group_size"] = PARQUET_ROW_GROUP_SIZE
            metric["metadata"]["row_group_count"] = row_group_count
            _record_metric_rss(metric)
        runtime_recorder.flush()
    _log_export_observation(
        "write_parquet_file_end",
        release_name=release_name,
        table_name=table_name,
        release_type=release_type,
        snapshot_month=snapshot_month.isoformat() if snapshot_month is not None else None,
        row_count=len(row_dicts),
        elapsed_ms=int((perf_counter() - write_started) * 1000),
        file_path=str(file_path),
        file_size_bytes=file_path.stat().st_size if file_path.exists() else None,
        row_group_count=row_group_count,
        parquet_row_group_size=PARQUET_ROW_GROUP_SIZE,
    )
    _check_export_rss_guard(
        rss_guard_mb=rss_guard_mb,
        release_name=release_name,
        release_type=release_type,
        snapshot_month=snapshot_month,
        phase_name="after_write_parquet_file",
        table_name=table_name,
        activity_callback=activity_callback,
    )
    return StudentDatasetFileManifest(
        table_name=table_name,
        file_name=file_name,
        file_path=file_path,
        row_count=len(row_dicts),
        columns=projection.included_columns,
        schema_hash=_schema_hash(schema),
        checksum=_file_checksum(file_path),
    )


def _write_rows_to_parquet_file(
    *,
    file_path: Path,
    schema: pa.Schema,
    columns: tuple[str, ...],
    row_dicts: list[dict[str, Any]],
    compression: str,
) -> int:
    if not row_dicts:
        pq.write_table(
            _rows_to_arrow_table(rows=[], columns=columns, schema=schema),
            file_path,
            compression=compression,
        )
        return 1

    row_group_count = 0
    with pq.ParquetWriter(file_path, schema=schema, compression=compression) as writer:
        for chunk in _iter_row_chunks(row_dicts, PARQUET_ROW_GROUP_SIZE):
            writer.write_table(
                _rows_to_arrow_table(rows=chunk, columns=columns, schema=schema)
            )
            row_group_count += 1
    return row_group_count


def _iter_row_chunks(rows: list[dict[str, Any]], chunk_size: int):
    for start in range(0, len(rows), chunk_size):
        yield rows[start : start + chunk_size]


def _rows_to_arrow_table(
    *,
    rows: list[dict[str, Any]],
    columns: tuple[str, ...],
    schema: pa.Schema,
) -> pa.Table:
    return pa.table(
        {
            column_name: pa.array(
                [row[column_name] for row in rows],
                type=schema.field(column_name).type,
            )
            for column_name in columns
        },
        schema=schema,
    )


def _infer_arrow_schema(
    *,
    row_dicts: list[dict[str, Any]],
    columns: tuple[str, ...],
) -> pa.Schema:
    return pa.schema(
        [
            pa.field(
                column_name,
                _infer_arrow_type(row.get(column_name) for row in row_dicts),
            )
            for column_name in columns
        ]
    )


def _projection_arrow_schema(table_name: str) -> pa.Schema:
    projection = PROJECTION_BY_TABLE[table_name]
    source_columns = projection.model.__table__.columns
    return pa.schema(
        [
            pa.field(
                column_name,
                _arrow_type_for_projection_column(
                    column_name=column_name,
                    source_columns=source_columns,
                ),
            )
            for column_name in projection.included_columns
        ]
    )


def _arrow_type_for_projection_column(
    *,
    column_name: str,
    source_columns,
) -> pa.DataType:
    source_column = source_columns.get(column_name)
    if source_column is None and column_name == "player_id":
        source_column = source_columns.get("id")
    if source_column is None:
        return pa.string()
    column_type = source_column.type
    if isinstance(column_type, (sqltypes.Date, sqltypes.DateTime)):
        return pa.string()
    if isinstance(column_type, sqltypes.Boolean):
        return pa.bool_()
    if isinstance(column_type, sqltypes.Integer):
        return pa.int64()
    if isinstance(column_type, sqltypes.Numeric):
        precision = int(column_type.precision or 38)
        scale = int(column_type.scale or 0)
        if precision <= 38:
            return pa.decimal128(precision, scale)
        return pa.decimal256(precision, scale)
    if isinstance(column_type, sqltypes.Float):
        return pa.float64()
    if column_type.__class__.__name__.lower() == "uuid":
        return pa.uuid()
    return pa.string()


def _infer_arrow_type(values) -> pa.DataType:
    has_float = False
    has_int = False
    has_bool = False
    has_string = False
    has_uuid = False
    decimal_integer_digits = 0
    decimal_scale = 0
    has_decimal = False
    for value in values:
        if value is None:
            continue
        if isinstance(value, bool):
            has_bool = True
        elif isinstance(value, int):
            has_int = True
        elif isinstance(value, float):
            has_float = True
        elif isinstance(value, Decimal):
            has_decimal = True
            integer_digits, scale = _decimal_shape(value)
            decimal_integer_digits = max(decimal_integer_digits, integer_digits)
            decimal_scale = max(decimal_scale, scale)
        elif isinstance(value, UUID):
            has_uuid = True
        else:
            has_string = True

    if has_string:
        return pa.string()
    if has_uuid:
        return pa.uuid()
    if has_decimal:
        precision = max(1, decimal_integer_digits + decimal_scale)
        if precision <= 38:
            return pa.decimal128(precision, decimal_scale)
        return pa.decimal256(precision, decimal_scale)
    if has_float:
        return pa.float64()
    if has_int:
        return pa.int64()
    if has_bool:
        return pa.bool_()
    return pa.null()


def _decimal_shape(value: Decimal) -> tuple[int, int]:
    sign, digits, exponent = value.as_tuple()
    del sign
    scale = max(0, -exponent)
    integer_digits = max(0, len(digits) - scale)
    if integer_digits == 0 and value != 0:
        integer_digits = 1
    return integer_digits, scale


def _append_rows_to_parquet_file(
    *,
    source_path: Path,
    final_path: Path,
    table_name: str,
    extra_rows: list[dict[str, Any]],
    compression: str,
    release_name: str,
    release_type: str,
    snapshot_month: date | None,
    runtime_recorder: RuntimeMetricRecorder | None = None,
    activity_callback: ReleaseActivityCallback | None = None,
    rss_guard_mb: float | None = None,
) -> StudentDatasetFileManifest:
    projection = PROJECTION_BY_TABLE[table_name]
    metadata = _export_metric_metadata(
        release_name=release_name,
        table_name=table_name,
        release_type=release_type,
        snapshot_month=snapshot_month,
    )
    _log_export_observation(
        "finalize_streamed_data_quality_file_start",
        release_name=release_name,
        table_name=table_name,
        release_type=release_type,
        snapshot_month=snapshot_month.isoformat() if snapshot_month is not None else None,
        source_path=str(source_path),
        final_path=str(final_path),
        extra_row_count=len(extra_rows),
    )
    if runtime_recorder is None:
        schema, row_count, row_group_count = _copy_parquet_file_with_extra_rows(
            source_path=source_path,
            final_path=final_path,
            columns=projection.included_columns,
            extra_rows=extra_rows,
            compression=compression,
        )
    else:
        with runtime_recorder.measure(
            "finalize_streamed_data_quality_file",
            input_count=len(extra_rows),
            metadata=metadata,
        ) as metric:
            schema, row_count, row_group_count = _copy_parquet_file_with_extra_rows(
                source_path=source_path,
                final_path=final_path,
                columns=projection.included_columns,
                extra_rows=extra_rows,
                compression=compression,
            )
            metric["output_count"] = row_count
            metric["metadata"]["parquet_row_group_size"] = PARQUET_ROW_GROUP_SIZE
            metric["metadata"]["row_group_count"] = row_group_count
            _record_metric_rss(metric)
        runtime_recorder.flush()
    _log_export_observation(
        "finalize_streamed_data_quality_file_end",
        release_name=release_name,
        table_name=table_name,
        release_type=release_type,
        snapshot_month=snapshot_month.isoformat() if snapshot_month is not None else None,
        row_count=row_count,
        final_path=str(final_path),
        file_size_bytes=final_path.stat().st_size if final_path.exists() else None,
        row_group_count=row_group_count,
        parquet_row_group_size=PARQUET_ROW_GROUP_SIZE,
    )
    _check_export_rss_guard(
        rss_guard_mb=rss_guard_mb,
        release_name=release_name,
        release_type=release_type,
        snapshot_month=snapshot_month,
        phase_name="after_finalize_streamed_data_quality_file",
        table_name=table_name,
        activity_callback=activity_callback,
    )
    return StudentDatasetFileManifest(
        table_name=table_name,
        file_name=projection.output_file,
        file_path=final_path,
        row_count=row_count,
        columns=projection.included_columns,
        schema_hash=_schema_hash(schema),
        checksum=_file_checksum(final_path),
    )


def _copy_parquet_file_with_extra_rows(
    *,
    source_path: Path,
    final_path: Path,
    columns: tuple[str, ...],
    extra_rows: list[dict[str, Any]],
    compression: str,
) -> tuple[pa.Schema, int, int]:
    source_file = pq.ParquetFile(source_path)
    schema = source_file.schema_arrow
    row_count = 0
    row_group_count = 0
    with pq.ParquetWriter(final_path, schema=schema, compression=compression) as writer:
        for batch in source_file.iter_batches(batch_size=PARQUET_ROW_GROUP_SIZE):
            table = pa.Table.from_batches([batch], schema=schema)
            writer.write_table(table)
            row_count += table.num_rows
            row_group_count += 1
        for chunk in _iter_row_chunks(extra_rows, PARQUET_ROW_GROUP_SIZE):
            table = _rows_to_arrow_table(
                rows=chunk,
                columns=columns,
                schema=schema,
            )
            writer.write_table(table)
            row_count += table.num_rows
            row_group_count += 1
    return schema, row_count, row_group_count


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
    env_rss_guard_mb = _optional_positive_float(os.getenv(EXPORT_RSS_GUARD_ENV_VAR))
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
            rss_guard_mb=env_rss_guard_mb,
        )
    enabled = instrumentation.get("export_queries_enabled", False)
    capture_sql_text = instrumentation.get("export_query_sql_text_enabled", False)
    rss_guard_mb = _optional_positive_float(
        instrumentation.get("export_rss_guard_mb")
    )
    return ExportInstrumentationSettings(
        enabled=bool(enabled) if isinstance(enabled, bool) else False,
        capture_sql_text=bool(capture_sql_text)
        if isinstance(capture_sql_text, bool)
        else False,
        rss_guard_mb=rss_guard_mb if rss_guard_mb is not None else env_rss_guard_mb,
    )


def _build_export_runtime_recorder(
    *,
    session: Session,
    build_parameters: StudentDatasetBuildParameters,
    instrumentation: ExportInstrumentationSettings,
    job_status_id: int | None = None,
) -> RuntimeMetricRecorder | None:
    if not instrumentation.enabled:
        return None
    return RuntimeMetricRecorder(
        session=session,
        generation_run_id=build_parameters.generation_run_id,
        job_status_id=job_status_id,
        stage_name="student_dataset_export",
    )


def _build_data_quality_injection_observer(
    *,
    release_name: str,
    release_type: str,
    snapshot_month: date | None,
    runtime_recorder: RuntimeMetricRecorder | None,
    activity_callback: ReleaseActivityCallback | None,
    rss_guard_mb: float | None,
) -> Callable[[str, Mapping[str, Any]], None]:
    def observe(event_name: str, fields: Mapping[str, Any]) -> None:
        event_fields = dict(fields)
        phase_name = str(event_fields.get("phase_name") or event_name)
        table_name = event_fields.get("table_name")
        issue_type = event_fields.get("issue_type")
        rss_mb = _current_rss_megabytes()
        _log_export_observation(
            f"data_quality_{event_name}",
            release_name=release_name,
            release_type=release_type,
            snapshot_month=snapshot_month.isoformat() if snapshot_month is not None else None,
            rss_mb=rss_mb,
            **event_fields,
        )
        if runtime_recorder is not None and (
            event_name.endswith("_end") or event_name.endswith("_failed")
        ):
            elapsed_ms = event_fields.get("elapsed_ms")
            if elapsed_ms is not None:
                metadata = _export_metric_metadata(
                    release_name=release_name,
                    table_name=str(table_name) if table_name is not None else None,
                    release_type=release_type,
                    snapshot_month=snapshot_month,
                )
                metadata.update(
                    {
                        "event_name": event_name,
                        "phase_name": phase_name,
                        "issue_type": issue_type,
                        "rss_mb": rss_mb,
                        "row_count": event_fields.get("row_count"),
                        "table_mode": event_fields.get("table_mode"),
                        "table_count": event_fields.get("table_count"),
                        "copy_mode": event_fields.get("copy_mode"),
                        "target_count": event_fields.get("target_count"),
                        "candidate_count": event_fields.get("candidate_count"),
                        "sampled_count": event_fields.get("sampled_count"),
                        "source_match_count": event_fields.get("source_match_count"),
                        "source_match_team_count": event_fields.get(
                            "source_match_team_count"
                        ),
                        "captured_row_count": event_fields.get("captured_row_count"),
                        "applied_count": event_fields.get("applied_count"),
                        "noop_count": event_fields.get("noop_count"),
                        "skipped_row_limit_count": event_fields.get(
                            "skipped_row_limit_count"
                        ),
                        "selection_strategy": event_fields.get("selection_strategy"),
                        "error": event_fields.get("error"),
                    }
                )
                runtime_recorder.record_completed(
                    f"data_quality_{phase_name}",
                    elapsed_ms=int(elapsed_ms),
                    input_count=_optional_metric_count(
                        event_fields.get("input_count", event_fields.get("row_count"))
                    ),
                    output_count=_optional_metric_count(event_fields.get("output_count")),
                    metadata=metadata,
                )
                runtime_recorder.flush()
        if activity_callback is not None:
            activity_callback(
                _data_quality_activity_message(
                    release_name=release_name,
                    event_name=event_name,
                    phase_name=phase_name,
                    table_name=table_name,
                    issue_type=issue_type,
                    rss_mb=rss_mb,
                )
            )
        _check_export_rss_guard(
            rss_guard_mb=rss_guard_mb,
            release_name=release_name,
            release_type=release_type,
            snapshot_month=snapshot_month,
            phase_name=phase_name,
            table_name=str(table_name) if table_name is not None else None,
            activity_callback=activity_callback,
        )

    return observe


def _data_quality_activity_message(
    *,
    release_name: str,
    event_name: str,
    phase_name: str,
    table_name: object,
    issue_type: object,
    rss_mb: float | None,
) -> str:
    parts = [
        f"Data quality injection {event_name.replace('_', ' ')}",
        f"phase={phase_name}",
    ]
    if table_name is not None:
        parts.append(f"table={table_name}")
    if issue_type is not None:
        parts.append(f"issue={issue_type}")
    if rss_mb is not None:
        parts.append(f"rss_mb={rss_mb}")
    parts.append(f"release={release_name}")
    return ". ".join(parts) + "."


def _data_quality_injection_is_active(
    *,
    config,
    release_type: str,
) -> bool:
    return (
        config.enabled
        and config.effective_level_for_release(release_type) != "none"
        and config.applies_to_release_type(release_type)
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


def _record_metric_rss(metric: dict[str, Any]) -> None:
    metadata = metric.setdefault("metadata", {})
    if isinstance(metadata, dict):
        metadata["rss_mb"] = _current_rss_megabytes()


def _table_row_count(tables: Mapping[str, list[dict[str, Any]]]) -> int:
    return sum(len(rows) for rows in tables.values())


def _optional_metric_count(value: Any) -> int | None:
    if value is None:
        return None
    return int(value)


def _optional_positive_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        parsed = float(value)
    elif isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        try:
            parsed = float(stripped)
        except ValueError:
            return None
    else:
        return None
    return parsed if parsed > 0 else None


def _check_export_rss_guard(
    *,
    rss_guard_mb: float | None,
    release_name: str,
    release_type: str,
    snapshot_month: date | None,
    phase_name: str,
    table_name: str | None = None,
    activity_callback: ReleaseActivityCallback | None = None,
) -> None:
    if rss_guard_mb is None:
        return
    rss_mb = _current_rss_megabytes()
    if rss_mb is None or rss_mb < rss_guard_mb:
        return

    message_parts = [
        f"Student dataset export RSS guard exceeded for {release_name}",
        f"phase={phase_name}",
        f"rss_mb={rss_mb}",
        f"limit_mb={rss_guard_mb}",
    ]
    if table_name is not None:
        message_parts.append(f"table={table_name}")
    message = ". ".join(message_parts) + "."
    _log_export_observation(
        "rss_guard_exceeded",
        release_name=release_name,
        release_type=release_type,
        snapshot_month=snapshot_month.isoformat() if snapshot_month is not None else None,
        phase_name=phase_name,
        table_name=table_name,
        rss_guard_mb=rss_guard_mb,
    )
    if activity_callback is not None:
        activity_callback(message)
    raise StudentDatasetExportMemoryLimitError(message)


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
