"""Tests for staged student dataset Parquet writing."""

import json
from datetime import date
from pathlib import Path
import sys
from uuid import UUID

import pytest
import pyarrow as pa
import pyarrow.parquet as pq
from sqlalchemy import text


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.exports.data_quality import (  # noqa: E402
    INSTRUCTOR_MANIFEST_FILE_NAME,
    DataQualityReleaseContext,
    build_default_data_quality_config,
    create_injection_state,
    inject_data_quality_issues,
)
from app.exports.student_dataset import (  # noqa: E402
    MANIFEST_FILE_NAME,
    PROJECTION_BY_TABLE,
    STUDENT_TABLE_ORDER,
    PublishedStudentDatasetFamily,
    StagedStudentDatasetFamily,
    StudentDatasetBuildParameters,
    StudentDatasetExportMemoryLimitError,
    StudentDatasetPublishError,
    StudentDatasetValidationError,
    promote_staged_release_family,
    validate_staged_release,
    write_staged_release_family,
)
import app.exports.student_dataset.writer as student_dataset_writer  # noqa: E402
from app.exports.student_dataset.writer import _load_table_rows  # noqa: E402
from app.models import GenerationRuntimeMetric  # noqa: E402
from test_student_dataset_queries import (  # noqa: E402
    incremental_release_window,
    query_context,
    release_window,
    seed_snapshot_query_data,
    session,
    session_factory,
)


def _assert_external_player_key_exported_as_uuid_string(player_master_file: Path) -> None:
    arrow_schema = pq.read_schema(player_master_file)
    field = arrow_schema.field("external_player_key")
    assert field.type == pa.string()

    parquet_schema_text = str(pq.ParquetFile(player_master_file).schema)
    assert "UUID" not in parquet_schema_text
    assert "FIXED_LEN_BYTE_ARRAY" not in parquet_schema_text

    rows = pq.read_table(
        player_master_file,
        columns=["external_player_key"],
    ).to_pylist()
    assert rows
    for row in rows:
        value = row["external_player_key"]
        assert isinstance(value, str)
        assert str(UUID(value)) == value


class _StreamingOnlyExecuteResult:
    def __init__(self, result):
        self._result = result

    def mappings(self):
        return _StreamingOnlyMappingResult(self._result.mappings())


class _StreamingOnlyMappingResult:
    def __init__(self, result):
        self._result = result

    def all(self):
        raise AssertionError("student export source queries must stream partitions")

    def partitions(self, size):
        yield from self._result.partitions(size)

    def __iter__(self):
        return iter(self._result)


def _seed_incremental_match_shape(session) -> None:
    session.execute(
        text(
            """
            INSERT INTO match_teams (
                id, match_id, team_number, team_score, expected_win_probability,
                average_team_rating, source_team_id
            )
            VALUES (21, 2, 2, 1, 0.3, 1450.0, 2)
            """
        )
    )
    session.execute(
        text(
            """
            INSERT INTO match_team_players (
                id, match_team_id, player_id, player_position,
                player_rating_at_match
            )
            VALUES (201, 21, 1, 1, 1400.0)
            """
        )
    )
    session.commit()


def _enable_export_runtime_metrics(session, instrumentation_overrides=None) -> None:
    instrumentation = {
        "export_queries_enabled": True,
        "export_query_sql_text_enabled": True,
    }
    if instrumentation_overrides is not None:
        instrumentation.update(instrumentation_overrides)
    session.execute(
        text(
            """
            CREATE TABLE generation_runs (
                id integer primary key,
                generation_name varchar(255) not null,
                seed_value bigint not null,
                simulation_version varchar(100),
                parameter_snapshot json,
                started_at datetime,
                completed_at datetime,
                status varchar(30) not null,
                created_at datetime default current_timestamp not null,
                updated_at datetime default current_timestamp not null
            )
            """
        )
    )
    session.execute(
        text(
            """
            INSERT INTO generation_runs (
                id, generation_name, seed_value, simulation_version,
                parameter_snapshot, status
            ) VALUES (
                1, 'instrumented export', 1, 'test', :parameter_snapshot, 'succeeded'
            )
            """
        ),
        {
            "parameter_snapshot": json.dumps(
                {"instrumentation": instrumentation}
            )
        },
    )
    session.execute(
        text(
            """
            CREATE TABLE generation_runtime_metrics (
                id integer primary key autoincrement,
                generation_run_id bigint not null,
                job_status_id bigint,
                batch_id bigint,
                stage_name varchar(100) not null,
                subphase_name varchar(100) not null,
                event_type varchar(30) not null,
                started_at datetime not null,
                completed_at datetime not null,
                elapsed_ms bigint not null,
                input_count bigint,
                output_count bigint,
                attempt_count bigint,
                metadata_json json,
                created_at datetime default current_timestamp not null,
                updated_at datetime default current_timestamp not null
            )
            """
        )
    )
    session.commit()


def test_write_staged_release_family_emits_parquet_files_and_manifest(
    session,
    release_window,
    tmp_path,
):
    seed_snapshot_query_data(session)
    build_parameters = StudentDatasetBuildParameters(
        generation_run_id=1,
        initial_history_month_count=2,
        subsequent_month_count=0,
        output_root=tmp_path,
        release_name="napa_student_release",
        data_quality_level="none",
        overwrite_existing=False,
    )

    result = write_staged_release_family(
        session=session,
        output_root=tmp_path,
        release_name="napa_student_release",
        release_windows=(release_window,),
        build_parameters=build_parameters,
    )

    assert isinstance(result, StagedStudentDatasetFamily)
    assert result.staging_root.parent == tmp_path
    assert result.staging_root.name.startswith(".napa_student_release.staging-")
    assert len(result.releases) == 1

    release = result.releases[0]
    assert release.release_name == "napa_student_release_initial_history"
    assert release.release_type == "initial_snapshot"
    assert release.release_dir.parent == result.staging_root
    assert release.manifest_path == release.release_dir / MANIFEST_FILE_NAME
    assert release.manifest_path.exists()

    parquet_files = sorted(path.name for path in release.release_dir.glob("*.parquet"))
    assert parquet_files == sorted(f"{table_name}.parquet" for table_name in STUDENT_TABLE_ORDER)
    assert len(release.files) == len(STUDENT_TABLE_ORDER)


def test_clean_write_staged_release_family_skips_data_quality_injection(
    session,
    release_window,
    tmp_path,
    monkeypatch,
):
    seed_snapshot_query_data(session)

    def fail_if_called(**kwargs):
        raise AssertionError("clean exports should stream directly to parquet")

    monkeypatch.setattr(
        "app.exports.student_dataset.writer._write_data_quality_tainted_release_streaming",
        fail_if_called,
    )
    monkeypatch.setattr(
        "app.exports.student_dataset.writer._load_table_rows",
        fail_if_called,
    )
    build_parameters = StudentDatasetBuildParameters(
        generation_run_id=1,
        initial_history_month_count=2,
        subsequent_month_count=0,
        output_root=tmp_path,
        release_name="napa_student_release",
        data_quality_level="none",
        overwrite_existing=False,
    )

    result = write_staged_release_family(
        session=session,
        output_root=tmp_path,
        release_name="napa_student_release",
        release_windows=(release_window,),
        build_parameters=build_parameters,
    )

    assert len(result.releases) == 1
    assert result.releases[0].data_quality_manifest_entries == ()


def test_build_parameters_normalize_legacy_clean_alias(tmp_path):
    build_parameters = StudentDatasetBuildParameters(
        generation_run_id=1,
        initial_history_month_count=2,
        subsequent_month_count=0,
        output_root=tmp_path,
        release_name="napa_student_release",
        data_quality_level="clean",
    )

    assert build_parameters.data_quality_level == "none"


def test_write_staged_release_preserves_projection_column_order(
    session,
    release_window,
    tmp_path,
):
    seed_snapshot_query_data(session)
    build_parameters = StudentDatasetBuildParameters(
        generation_run_id=1,
        initial_history_month_count=2,
        subsequent_month_count=0,
        output_root=tmp_path,
        release_name="napa_student_release",
    )

    result = write_staged_release_family(
        session=session,
        output_root=tmp_path,
        release_name="napa_student_release",
        release_windows=(release_window,),
        build_parameters=build_parameters,
    )
    release_dir = result.releases[0].release_dir

    for table_name in STUDENT_TABLE_ORDER:
        table = pq.read_table(release_dir / f"{table_name}.parquet")
        assert table.column_names == list(
            PROJECTION_BY_TABLE[table_name].included_columns
        )


def test_write_staged_release_family_records_export_query_metrics_when_enabled(
    session,
    release_window,
    tmp_path,
):
    seed_snapshot_query_data(session)
    _enable_export_runtime_metrics(session)

    build_parameters = StudentDatasetBuildParameters(
        generation_run_id=1,
        initial_history_month_count=2,
        subsequent_month_count=0,
        output_root=tmp_path,
        release_name="napa_student_release",
        data_quality_level="none",
        overwrite_existing=False,
    )

    write_staged_release_family(
        session=session,
        output_root=tmp_path,
        release_name="napa_student_release",
        release_windows=(release_window,),
        build_parameters=build_parameters,
    )

    execute_metrics = (
        session.query(GenerationRuntimeMetric)
        .filter(
            GenerationRuntimeMetric.stage_name == "student_dataset_export",
            GenerationRuntimeMetric.subphase_name == "execute_source_query",
        )
        .all()
    )

    assert len(execute_metrics) == len(STUDENT_TABLE_ORDER)
    players_metric = next(
        metric
        for metric in execute_metrics
        if metric.metadata_json["table_name"] == "player_master"
    )
    assert players_metric.elapsed_ms >= 0
    assert players_metric.output_count == 1
    assert players_metric.metadata_json["release_name"] == (
        "napa_student_release_initial_history"
    )
    assert "rss_mb" in players_metric.metadata_json
    assert "SELECT" in players_metric.metadata_json["sql_text"].upper()

    assert (
        session.query(GenerationRuntimeMetric)
        .filter(
            GenerationRuntimeMetric.stage_name == "student_dataset_export",
            GenerationRuntimeMetric.subphase_name == "write_parquet_file",
        )
        .count()
        == len(STUDENT_TABLE_ORDER)
    )
    assert (
        session.query(GenerationRuntimeMetric)
        .filter(
            GenerationRuntimeMetric.stage_name == "student_dataset_export",
            GenerationRuntimeMetric.subphase_name == "validate_release_folder",
        )
        .count()
        == 1
    )


def test_write_staged_release_family_streams_source_query_rows(
    session,
    release_window,
    tmp_path,
    monkeypatch,
):
    seed_snapshot_query_data(session)
    original_execute = session.execute

    def execute_streaming_only(*args, **kwargs):
        return _StreamingOnlyExecuteResult(original_execute(*args, **kwargs))

    monkeypatch.setattr(session, "execute", execute_streaming_only)
    build_parameters = StudentDatasetBuildParameters(
        generation_run_id=1,
        initial_history_month_count=2,
        subsequent_month_count=0,
        output_root=tmp_path,
        release_name="napa_student_release",
        data_quality_level="none",
        overwrite_existing=False,
    )

    result = write_staged_release_family(
        session=session,
        output_root=tmp_path,
        release_name="napa_student_release",
        release_windows=(release_window,),
        build_parameters=build_parameters,
    )

    assert len(result.releases[0].files) == len(STUDENT_TABLE_ORDER)


def test_write_staged_release_family_writes_parquet_row_groups(
    session,
    release_window,
    tmp_path,
    monkeypatch,
):
    seed_snapshot_query_data(session)
    monkeypatch.setattr(
        "app.exports.student_dataset.writer.PARQUET_ROW_GROUP_SIZE",
        1,
    )
    build_parameters = StudentDatasetBuildParameters(
        generation_run_id=1,
        initial_history_month_count=2,
        subsequent_month_count=0,
        output_root=tmp_path,
        release_name="napa_student_release",
        data_quality_level="none",
        overwrite_existing=False,
    )

    result = write_staged_release_family(
        session=session,
        output_root=tmp_path,
        release_name="napa_student_release",
        release_windows=(release_window,),
        build_parameters=build_parameters,
    )

    monthly_batches_file = (
        result.releases[0].release_dir / "monthly_batches.parquet"
    )
    assert pq.ParquetFile(monthly_batches_file).num_row_groups == 2


def test_write_staged_release_family_stops_when_rss_guard_is_exceeded(
    session,
    release_window,
    tmp_path,
    monkeypatch,
):
    seed_snapshot_query_data(session)
    _enable_export_runtime_metrics(
        session,
        {
            "export_queries_enabled": False,
            "export_query_sql_text_enabled": False,
            "export_rss_guard_mb": 1,
        },
    )
    monkeypatch.setattr(
        "app.exports.student_dataset.writer._current_rss_megabytes",
        lambda: 2.0,
    )
    activity_messages: list[str] = []

    build_parameters = StudentDatasetBuildParameters(
        generation_run_id=1,
        initial_history_month_count=2,
        subsequent_month_count=0,
        output_root=tmp_path,
        release_name="napa_student_release",
        data_quality_level="none",
        overwrite_existing=False,
    )

    with pytest.raises(StudentDatasetExportMemoryLimitError) as exc_info:
        write_staged_release_family(
            session=session,
            output_root=tmp_path,
            release_name="napa_student_release",
            release_windows=(release_window,),
            build_parameters=build_parameters,
            activity_callback=activity_messages.append,
        )

    assert "after_source_query" in str(exc_info.value)
    assert "limit_mb=1.0" in str(exc_info.value)
    assert any("RSS guard exceeded" in message for message in activity_messages)


def test_write_staged_release_family_reports_tainted_rss_guard_handoff_failure(
    session,
    release_window,
    tmp_path,
    monkeypatch,
):
    seed_snapshot_query_data(session)
    _enable_export_runtime_metrics(
        session,
        {
            "export_queries_enabled": False,
            "export_query_sql_text_enabled": False,
            "export_rss_guard_mb": 1,
        },
    )
    monkeypatch.setattr(
        "app.exports.student_dataset.writer._current_rss_megabytes",
        lambda: 2.0,
    )
    activity_messages: list[str] = []

    build_parameters = StudentDatasetBuildParameters(
        generation_run_id=1,
        initial_history_month_count=2,
        subsequent_month_count=0,
        output_root=tmp_path,
        release_name="napa_student_release",
        data_quality_level="medium",
        overwrite_existing=False,
    )

    with pytest.raises(StudentDatasetExportMemoryLimitError) as exc_info:
        write_staged_release_family(
            session=session,
            output_root=tmp_path,
            release_name="napa_student_release",
            release_windows=(release_window,),
            build_parameters=build_parameters,
            activity_callback=activity_messages.append,
        )

    message = str(exc_info.value)
    assert "blocked before tainted data quality injection" in message
    assert "Clean export staging completed" in message
    assert "before_data_quality_injection" in message
    assert any("Applying data quality rules" in msg for msg in activity_messages)


def test_write_staged_release_family_records_data_quality_injection_metrics_when_enabled(
    session,
    release_window,
    tmp_path,
):
    seed_snapshot_query_data(session)
    _enable_export_runtime_metrics(session)
    activity_messages: list[str] = []

    build_parameters = StudentDatasetBuildParameters(
        generation_run_id=1,
        initial_history_month_count=2,
        subsequent_month_count=0,
        output_root=tmp_path,
        release_name="napa_student_release",
        data_quality_level="medium",
        overwrite_existing=False,
    )

    job_status_id = 17
    write_staged_release_family(
        session=session,
        output_root=tmp_path,
        release_name="napa_student_release",
        release_windows=(release_window,),
        build_parameters=build_parameters,
        job_status_id=job_status_id,
        activity_callback=activity_messages.append,
    )

    subphase_names = {
        metric.subphase_name
        for metric in session.query(GenerationRuntimeMetric)
        .filter(GenerationRuntimeMetric.stage_name == "student_dataset_export")
        .all()
    }

    assert "inject_data_quality_issues" in subphase_names
    assert "data_quality_capture_original_table_stats" in subphase_names
    assert "data_quality_prepare_injected_tables" in subphase_names
    assert "data_quality_validate_injected_tables" in subphase_names
    assert "finalize_streamed_data_quality_file" in subphase_names
    assert any(
        message.startswith("Data quality injection capture original table stats start")
        for message in activity_messages
    )
    stats_metric = (
        session.query(GenerationRuntimeMetric)
        .filter(
            GenerationRuntimeMetric.stage_name == "student_dataset_export",
            GenerationRuntimeMetric.subphase_name == "data_quality_capture_original_table_stats",
        )
        .one()
    )
    assert stats_metric.input_count is not None
    assert "rss_mb" in stats_metric.metadata_json
    assert stats_metric.job_status_id == job_status_id
    prepare_metric = (
        session.query(GenerationRuntimeMetric)
        .filter(
            GenerationRuntimeMetric.stage_name == "student_dataset_export",
            GenerationRuntimeMetric.subphase_name == "data_quality_prepare_injected_tables",
        )
        .one()
    )
    assert prepare_metric.metadata_json["copy_mode"] == "streaming"
    finalize_metric = next(
        metric
        for metric in session.query(GenerationRuntimeMetric)
        .filter(
            GenerationRuntimeMetric.stage_name == "student_dataset_export",
            GenerationRuntimeMetric.subphase_name == "finalize_streamed_data_quality_file",
        )
        .all()
        if metric.metadata_json["table_name"] == "matches"
    )
    assert finalize_metric.metadata_json["row_group_count"] is not None
    assert finalize_metric.metadata_json["parquet_row_group_size"] is not None
    injection_metric = (
        session.query(GenerationRuntimeMetric)
        .filter(
            GenerationRuntimeMetric.stage_name == "student_dataset_export",
            GenerationRuntimeMetric.subphase_name == "inject_data_quality_issues",
        )
        .one()
    )
    assert "rss_mb" in injection_metric.metadata_json


def test_streamed_data_quality_writer_matches_in_memory_injection_rows(
    session,
    release_window,
    query_context,
    tmp_path,
):
    seed_snapshot_query_data(session)
    release_name = "napa_student_release"
    concrete_release_name = f"{release_name}{release_window.folder_suffix}"
    config = build_default_data_quality_config(level="medium")
    clean_tables = {
        table_name: _load_table_rows(
            session=session,
            table_name=table_name,
            context=query_context,
            release_name=concrete_release_name,
        )
        for table_name in STUDENT_TABLE_ORDER
    }
    expected = inject_data_quality_issues(
        tables=clean_tables,
        config=config,
        release_context=DataQualityReleaseContext(
            release_id=concrete_release_name,
            release_name=concrete_release_name,
            release_type=release_window.release_type,
            generation_run_id=1,
            snapshot_month=release_window.snapshot_month,
        ),
        copy_tables=False,
    )

    build_parameters = StudentDatasetBuildParameters(
        generation_run_id=1,
        initial_history_month_count=2,
        subsequent_month_count=0,
        output_root=tmp_path,
        release_name=release_name,
        data_quality_level="medium",
        overwrite_existing=False,
    )

    result = write_staged_release_family(
        session=session,
        output_root=tmp_path,
        release_name=release_name,
        release_windows=(release_window,),
        build_parameters=build_parameters,
    )

    release_dir = result.releases[0].release_dir
    for table_name in STUDENT_TABLE_ORDER:
        actual_rows = pq.read_table(release_dir / f"{table_name}.parquet").to_pylist()
        assert actual_rows == expected.tables[table_name]


def test_tainted_write_streams_only_safe_tables_directly(
    session,
    release_window,
    tmp_path,
    monkeypatch,
):
    seed_snapshot_query_data(session)
    streamed_tables: list[str] = []
    original_write_table_from_source_stream = (
        student_dataset_writer._write_table_from_source_stream
    )

    def recording_direct_stream(*args, **kwargs):
        streamed_tables.append(kwargs["table_name"])
        return original_write_table_from_source_stream(*args, **kwargs)

    monkeypatch.setattr(
        "app.exports.student_dataset.writer._write_table_from_source_stream",
        recording_direct_stream,
    )
    build_parameters = StudentDatasetBuildParameters(
        generation_run_id=1,
        initial_history_month_count=2,
        subsequent_month_count=0,
        output_root=tmp_path,
        release_name="napa_student_release",
        data_quality_level="medium",
        overwrite_existing=False,
    )

    write_staged_release_family(
        session=session,
        output_root=tmp_path,
        release_name="napa_student_release",
        release_windows=(release_window,),
        build_parameters=build_parameters,
    )

    assert "team_memberships" in streamed_tables
    assert "matches" not in streamed_tables
    assert "match_teams" not in streamed_tables
    assert "match_team_players" not in streamed_tables
    assert "match_games" not in streamed_tables


def test_tainted_write_streams_mutation_tables_without_row_buffering(
    session,
    release_window,
    tmp_path,
    monkeypatch,
):
    seed_snapshot_query_data(session)
    original_load_table_rows = student_dataset_writer._load_table_rows
    forbidden_tables = {
        "clubs",
        "club_memberships",
        "monthly_batches",
        "player_assessment_history",
        "player_master",
        "player_registrations",
        "regions",
        "teams",
    }

    def guarded_load_table_rows(*args, **kwargs):
        table_name = kwargs["table_name"]
        if table_name in forbidden_tables:
            raise AssertionError(
                f"tainted export should stream chunk-local mutations for {table_name}"
            )
        return original_load_table_rows(*args, **kwargs)

    monkeypatch.setattr(
        "app.exports.student_dataset.writer._load_table_rows",
        guarded_load_table_rows,
    )
    build_parameters = StudentDatasetBuildParameters(
        generation_run_id=1,
        initial_history_month_count=2,
        subsequent_month_count=0,
        output_root=tmp_path,
        release_name="napa_student_release",
        data_quality_level="medium",
        overwrite_existing=False,
    )

    write_staged_release_family(
        session=session,
        output_root=tmp_path,
        release_name="napa_student_release",
        release_windows=(release_window,),
        build_parameters=build_parameters,
    )


def test_tainted_write_streams_duplicate_family_without_row_buffering(
    session,
    release_window,
    tmp_path,
    monkeypatch,
):
    seed_snapshot_query_data(session)

    def fail_if_called(**kwargs):
        raise AssertionError(
            f"tainted export should not fully load table rows for {kwargs['table_name']}"
        )

    monkeypatch.setattr(
        "app.exports.student_dataset.writer._load_table_rows",
        fail_if_called,
    )
    build_parameters = StudentDatasetBuildParameters(
        generation_run_id=1,
        initial_history_month_count=2,
        subsequent_month_count=0,
        output_root=tmp_path,
        release_name="napa_student_release",
        data_quality_level="medium",
        overwrite_existing=False,
    )

    write_staged_release_family(
        session=session,
        output_root=tmp_path,
        release_name="napa_student_release",
        release_windows=(release_window,),
        build_parameters=build_parameters,
    )


def test_duplicate_like_match_planning_executes_streamed_path(tmp_path, monkeypatch):
    file_path = tmp_path / "matches.parquet"
    pq.write_table(
        pa.Table.from_pylist(
            [
                {"id": 1, "match_date": "2025-01-01"},
                {"id": 2, "match_date": "2025-01-02"},
                {"id": 3, "match_date": "2025-01-03"},
            ]
        ),
        file_path,
    )

    monkeypatch.setattr(
        student_dataset_writer,
        "_target_count",
        lambda **kwargs: 1,
    )
    state = create_injection_state(
        config=build_default_data_quality_config(level="medium"),
        release_context=DataQualityReleaseContext(
            release_id="release-1",
            release_name="napa_student_release",
            release_type="initial_snapshot",
            generation_run_id=1,
            snapshot_month=date(2025, 1, 1),
        ),
        effective_level="medium",
    )

    plan, captures, next_match_id = (
        student_dataset_writer._plan_and_capture_duplicate_source_matches(
            state=state,
            file_path=file_path,
            release_name="napa_student_release",
            injection_observer=lambda *_args, **_kwargs: None,
        )
    )

    assert plan.target_count == 1
    assert len(plan.source_match_ids) >= plan.target_count
    assert plan.sampled_count == len(plan.source_match_ids)
    assert captures[plan.source_match_ids[0]]["id"] == plan.source_match_ids[0]
    assert next_match_id == 4


def test_write_staged_release_manifest_reports_files_and_row_counts(
    session,
    release_window,
    tmp_path,
):
    seed_snapshot_query_data(session)
    build_parameters = StudentDatasetBuildParameters(
        generation_run_id=1,
        initial_history_month_count=2,
        subsequent_month_count=0,
        output_root=tmp_path,
        release_name="napa_student_release",
    )

    result = write_staged_release_family(
        session=session,
        output_root=tmp_path,
        release_name="napa_student_release",
        release_windows=(release_window,),
        build_parameters=build_parameters,
    )
    release = result.releases[0]
    manifest = json.loads(release.manifest_path.read_text(encoding="utf-8"))

    assert manifest["release_name"] == "napa_student_release_initial_history"
    assert manifest["release_sequence_number"] == 1
    assert manifest["release_mode"] == "baseline"
    assert manifest["release_type"] == "initial_snapshot"
    assert manifest["release_month"] is None
    assert manifest["included_months"] == [1, 2]
    assert manifest["load_strategy"] == "full_load"
    assert manifest["student_dataset_schema_version"] == "1.5"
    assert manifest["included_batch_sequences"] == [1, 2]
    assert manifest["included_batch_months"] == ["2025-01-01", "2025-02-01"]
    assert manifest["snapshot_batch_sequences"] == [1, 2]
    assert manifest["snapshot_batch_months"] == ["2025-01-01", "2025-02-01"]
    assert manifest["fact_batch_sequences"] == [1, 2]
    assert manifest["fact_batch_months"] == ["2025-01-01", "2025-02-01"]
    assert manifest["snapshot_month"] == "2025-02-01"
    assert manifest["snapshot_end_exclusive"] == "2025-03-01"
    assert "source_generation_run_id" not in manifest
    assert "data_quality_level" not in manifest
    assert "build_parameters" not in manifest
    assert manifest["validation_status"] == "passed"
    assert manifest["validation_summary"]["status"] == "passed"
    assert manifest["validation_summary"]["failed_check_count"] == 0

    assert manifest["row_counts"]["player_master"] == 1
    assert manifest["row_counts"]["matches"] == 1
    assert manifest["ordered_columns"]["player_master"] == list(
        PROJECTION_BY_TABLE["player_master"].included_columns
    )
    assert set(manifest["schema_hashes"]) == set(STUDENT_TABLE_ORDER)
    assert set(manifest["file_checksums"]) == set(STUDENT_TABLE_ORDER)
    assert len(manifest["output_files"]) == len(STUDENT_TABLE_ORDER)


def test_write_staged_release_parquet_contains_snapshot_transformed_values(
    session,
    release_window,
    tmp_path,
):
    seed_snapshot_query_data(session)
    build_parameters = StudentDatasetBuildParameters(
        generation_run_id=1,
        initial_history_month_count=2,
        subsequent_month_count=0,
        output_root=tmp_path,
        release_name="napa_student_release",
    )

    result = write_staged_release_family(
        session=session,
        output_root=tmp_path,
        release_name="napa_student_release",
        release_windows=(release_window,),
        build_parameters=build_parameters,
    )
    release_dir = result.releases[0].release_dir

    teams = pq.read_table(release_dir / "teams.parquet").to_pylist()
    assert teams[0]["country_code"] == "US"
    assert "chemistry_score" not in teams[0]
    assert "persistence_probability" not in teams[0]
    assert teams[0]["team_status"] == "active"
    assert teams[0]["dissolution_date"] is None

    team_memberships = pq.read_table(
        release_dir / "team_memberships.parquet"
    ).to_pylist()
    assert team_memberships[0]["left_date"] is None

    club_memberships = pq.read_table(
        release_dir / "club_memberships.parquet"
    ).to_pylist()
    assert club_memberships[0]["end_date"] is None


def test_uuid_values_are_materialized_as_parquet_strings():
    player_uuid = UUID("00000000-0000-0000-0000-000000000001")
    schema = student_dataset_writer._infer_arrow_schema(
        row_dicts=[{"player_id": 1, "external_player_key": player_uuid}],
        columns=("player_id", "external_player_key"),
        table_name="player_master",
    )

    assert schema.field("external_player_key").type == pa.string()
    table = student_dataset_writer._rows_to_arrow_table(
        rows=[{"player_id": 1, "external_player_key": player_uuid}],
        columns=("player_id", "external_player_key"),
        schema=schema,
    )

    assert table.schema.field("external_player_key").type == pa.string()
    assert table.to_pylist()[0]["external_player_key"] == str(player_uuid)


def test_clean_export_uuid_identifier_is_parquet_string(
    session,
    release_window,
    tmp_path,
):
    seed_snapshot_query_data(session)
    build_parameters = StudentDatasetBuildParameters(
        generation_run_id=1,
        initial_history_month_count=2,
        subsequent_month_count=0,
        output_root=tmp_path,
        release_name="napa_student_release",
    )

    result = write_staged_release_family(
        session=session,
        output_root=tmp_path,
        release_name="napa_student_release",
        release_windows=(release_window,),
        build_parameters=build_parameters,
    )

    _assert_external_player_key_exported_as_uuid_string(
        result.releases[0].release_dir / "player_master.parquet"
    )


def test_tainted_export_uuid_identifier_is_parquet_string(
    session,
    release_window,
    tmp_path,
):
    seed_snapshot_query_data(session)
    build_parameters = StudentDatasetBuildParameters(
        generation_run_id=1,
        initial_history_month_count=2,
        subsequent_month_count=0,
        output_root=tmp_path,
        release_name="napa_student_release",
        data_quality_level="medium",
    )

    result = write_staged_release_family(
        session=session,
        output_root=tmp_path,
        release_name="napa_student_release",
        release_windows=(release_window,),
        build_parameters=build_parameters,
    )

    _assert_external_player_key_exported_as_uuid_string(
        result.releases[0].release_dir / "player_master.parquet"
    )


def test_write_staged_release_family_writes_instructor_manifest_outside_student_release(
    session,
    release_window,
    tmp_path,
):
    seed_snapshot_query_data(session)
    build_parameters = StudentDatasetBuildParameters(
        generation_run_id=1,
        initial_history_month_count=2,
        subsequent_month_count=0,
        output_root=tmp_path,
        release_name="napa_student_release",
        data_quality_level="medium",
    )

    result = write_staged_release_family(
        session=session,
        output_root=tmp_path,
        release_name="napa_student_release",
        release_windows=(release_window,),
        build_parameters=build_parameters,
    )

    assert result.instructor_manifest_path == (
        result.staging_root / "instructor_only" / INSTRUCTOR_MANIFEST_FILE_NAME
    )
    assert result.instructor_manifest_path.exists()
    manifest_rows = pq.read_table(result.instructor_manifest_path).to_pylist()
    assert isinstance(manifest_rows, list)
    if manifest_rows:
        assert all(
            row["release_name"] == "napa_student_release_initial_history"
            for row in manifest_rows
        )


def test_write_staged_incremental_release_uses_snapshot_dimensions_and_fact_batches(
    session,
    incremental_release_window,
    tmp_path,
):
    seed_snapshot_query_data(session)
    _seed_incremental_match_shape(session)
    build_parameters = StudentDatasetBuildParameters(
        generation_run_id=1,
        initial_history_month_count=2,
        subsequent_month_count=1,
        output_root=tmp_path,
        release_name="napa_student_release",
    )

    result = write_staged_release_family(
        session=session,
        output_root=tmp_path,
        release_name="napa_student_release",
        release_windows=(incremental_release_window,),
        build_parameters=build_parameters,
    )
    release = result.releases[0]
    manifest = json.loads(release.manifest_path.read_text(encoding="utf-8"))

    assert release.release_name == "napa_student_release_snapshot_2025_03"
    assert manifest["release_sequence_number"] == 2
    assert manifest["release_mode"] == "monthly_incremental"
    assert manifest["release_type"] == "monthly_incremental"
    assert manifest["release_month"] == "2025-03-01"
    assert manifest["included_months"] == [3]
    assert manifest["load_strategy"] == "incremental_load"
    assert manifest["included_batch_sequences"] == [3]
    assert manifest["snapshot_batch_sequences"] == [1, 2, 3]
    assert manifest["fact_batch_sequences"] == [3]
    assert manifest["snapshot_month"] == "2025-03-01"
    assert manifest["snapshot_end_exclusive"] == "2025-04-01"

    release_dir = release.release_dir
    assert [row["id"] for row in pq.read_table(release_dir / "monthly_batches.parquet").to_pylist()] == [103]
    assert [row["id"] for row in pq.read_table(release_dir / "matches.parquet").to_pylist()] == [2]
    assert [row["id"] for row in pq.read_table(release_dir / "player_registrations.parquet").to_pylist()] == [2]
    assert [row["id"] for row in pq.read_table(release_dir / "player_assessment_history.parquet").to_pylist()] == [2]
    assert [row["player_id"] for row in pq.read_table(release_dir / "player_master.parquet").to_pylist()] == [1, 2]


def test_validate_staged_release_fails_referential_integrity(
    session,
    release_window,
    tmp_path,
):
    seed_snapshot_query_data(session)
    build_parameters = StudentDatasetBuildParameters(
        generation_run_id=1,
        initial_history_month_count=2,
        subsequent_month_count=0,
        output_root=tmp_path,
        release_name="napa_student_release",
    )

    result = write_staged_release_family(
        session=session,
        output_root=tmp_path,
        release_name="napa_student_release",
        release_windows=(release_window,),
        build_parameters=build_parameters,
    )
    release = result.releases[0]
    row_counts = {file.table_name: file.row_count for file in release.files}
    player_master_file = release.release_dir / "player_master.parquet"
    pq.write_table(pq.read_table(player_master_file).slice(0, 0), player_master_file)
    row_counts["player_master"] = 0

    try:
        validate_staged_release(
            release_dir=release.release_dir,
            release_window=release_window,
            manifest_row_counts=row_counts,
        )
    except StudentDatasetValidationError as exc:
        failed_names = {check.name for check in exc.result.failed_checks}
    else:
        raise AssertionError("Expected staged release validation to fail.")

    assert "required_non_empty:player_master" in failed_names
    assert (
        "relationship:club_memberships.player_id->player_master.player_id" in failed_names
        or "relationship:match_team_players.player_id->player_master.player_id" in failed_names
    )


def test_validate_staged_release_rejects_duplicate_players_rows(
    session,
    release_window,
    tmp_path,
):
    seed_snapshot_query_data(session)
    build_parameters = StudentDatasetBuildParameters(
        generation_run_id=1,
        initial_history_month_count=2,
        subsequent_month_count=0,
        output_root=tmp_path,
        release_name="napa_student_release",
    )

    result = write_staged_release_family(
        session=session,
        output_root=tmp_path,
        release_name="napa_student_release",
        release_windows=(release_window,),
        build_parameters=build_parameters,
    )
    release = result.releases[0]
    row_counts = {file.table_name: file.row_count for file in release.files}
    player_master_file = release.release_dir / "player_master.parquet"
    player_master_table = pq.read_table(player_master_file)
    duplicate_row = player_master_table.slice(0, 1)
    pq.write_table(
        pa.concat_tables([player_master_table, duplicate_row]),
        player_master_file,
    )
    row_counts["player_master"] += 1

    with pytest.raises(StudentDatasetValidationError) as exc_info:
        validate_staged_release(
            release_dir=release.release_dir,
            release_window=release_window,
            manifest_row_counts=row_counts,
        )

    failed_names = {check.name for check in exc_info.value.result.failed_checks}
    assert "player_master:one_row_per_player" in failed_names


def test_validate_staged_incremental_release_allows_empty_clubs_and_memberships(
    session,
    incremental_release_window,
    tmp_path,
):
    seed_snapshot_query_data(session)
    _seed_incremental_match_shape(session)
    build_parameters = StudentDatasetBuildParameters(
        generation_run_id=1,
        initial_history_month_count=2,
        subsequent_month_count=1,
        output_root=tmp_path,
        release_name="napa_student_release",
    )

    result = write_staged_release_family(
        session=session,
        output_root=tmp_path,
        release_name="napa_student_release",
        release_windows=(incremental_release_window,),
        build_parameters=build_parameters,
    )
    release = result.releases[0]
    row_counts = {file.table_name: file.row_count for file in release.files}

    for table_name in ("clubs", "club_memberships"):
        file_path = release.release_dir / f"{table_name}.parquet"
        existing = pq.read_table(file_path)
        empty_columns = {
            field.name: pa.array([], type=field.type)
            for field in existing.schema
        }
        pq.write_table(pa.table(empty_columns), file_path)
        row_counts[table_name] = 0

    validation_result = validate_staged_release(
        release_dir=release.release_dir,
        release_window=incremental_release_window,
        manifest_row_counts=row_counts,
    )

    assert validation_result.status == "passed"


def test_validate_staged_release_allows_null_nullable_relationships(
    session,
    release_window,
    tmp_path,
):
    seed_snapshot_query_data(session)
    build_parameters = StudentDatasetBuildParameters(
        generation_run_id=1,
        initial_history_month_count=2,
        subsequent_month_count=0,
        output_root=tmp_path,
        release_name="napa_student_release",
    )

    result = write_staged_release_family(
        session=session,
        output_root=tmp_path,
        release_name="napa_student_release",
        release_windows=(release_window,),
        build_parameters=build_parameters,
    )
    release = result.releases[0]
    row_counts = {file.table_name: file.row_count for file in release.files}
    matches_file = release.release_dir / "matches.parquet"
    matches_table = pq.read_table(matches_file)
    winning_team_index = matches_table.schema.get_field_index("winning_team_id")
    matches_table = matches_table.set_column(
        winning_team_index,
        "winning_team_id",
        pa.nulls(
            matches_table.num_rows,
            type=matches_table.schema.field(winning_team_index).type,
        ),
    )
    pq.write_table(matches_table, matches_file)

    validation_result = validate_staged_release(
        release_dir=release.release_dir,
        release_window=release_window,
        manifest_row_counts=row_counts,
    )

    assert validation_result.status == "passed"


def test_validate_staged_release_rejects_players_snapshot_month_mismatch(
    session,
    release_window,
    tmp_path,
):
    seed_snapshot_query_data(session)
    build_parameters = StudentDatasetBuildParameters(
        generation_run_id=1,
        initial_history_month_count=2,
        subsequent_month_count=0,
        output_root=tmp_path,
        release_name="napa_student_release",
    )

    result = write_staged_release_family(
        session=session,
        output_root=tmp_path,
        release_name="napa_student_release",
        release_windows=(release_window,),
        build_parameters=build_parameters,
    )
    release = result.releases[0]
    row_counts = {file.table_name: file.row_count for file in release.files}
    player_master_file = release.release_dir / "player_master.parquet"
    player_master_table = pq.read_table(player_master_file)
    snapshot_month_index = player_master_table.column_names.index("snapshot_month")
    updated_columns = list(player_master_table.itercolumns())
    updated_columns[snapshot_month_index] = pa.array(
        ["2025-03-01"],
        type=player_master_table.schema.field("snapshot_month").type,
    )
    pq.write_table(
        pa.table(updated_columns, names=player_master_table.column_names),
        player_master_file,
    )

    with pytest.raises(StudentDatasetValidationError) as exc_info:
        validate_staged_release(
            release_dir=release.release_dir,
            release_window=release_window,
            manifest_row_counts=row_counts,
        )

    failed_names = {check.name for check in exc_info.value.result.failed_checks}
    assert "player_master:snapshot_month_consistent" in failed_names


def test_promote_staged_release_family_moves_files_and_persists_metadata(
    session,
    release_window,
    tmp_path,
):
    seed_snapshot_query_data(session)
    build_parameters = StudentDatasetBuildParameters(
        generation_run_id=1,
        initial_history_month_count=2,
        subsequent_month_count=0,
        output_root=tmp_path,
        release_name="napa_student_release",
    )
    staged = write_staged_release_family(
        session=session,
        output_root=tmp_path,
        release_name="napa_student_release",
        release_windows=(release_window,),
        build_parameters=build_parameters,
    )
    staging_root = staged.staging_root

    published = promote_staged_release_family(
        session=session,
        staged_family=staged,
        build_parameters=build_parameters,
    )

    assert isinstance(published, PublishedStudentDatasetFamily)
    assert not staging_root.exists()
    assert published.final_root == tmp_path / "napa_student_release"
    assert published.final_root.exists()
    assert len(published.releases) == 1
    release = published.releases[0]
    assert release.release_dir == published.final_root / "napa_student_release_initial_history"
    assert release.manifest_path.exists()
    assert release.file_count == len(STUDENT_TABLE_ORDER)

    release_rows = session.execute(
        text(
            """
            SELECT release_name, release_type, release_month, generation_run_id,
                   data_quality_level, output_path, status
            FROM student_dataset_releases
            """
        )
    ).mappings().all()
    assert len(release_rows) == 1
    assert release_rows[0]["release_name"] == "napa_student_release_initial_history"
    assert release_rows[0]["release_type"] == "initial_snapshot"
    assert release_rows[0]["release_month"] is None
    assert release_rows[0]["generation_run_id"] == 1
    assert release_rows[0]["data_quality_level"] == "none"
    assert release_rows[0]["output_path"] == str(release.release_dir)
    assert release_rows[0]["status"] == "succeeded"

    file_rows = session.execute(
        text(
            """
            SELECT table_name, file_path, row_count, schema_hash, checksum
            FROM student_dataset_release_files
            ORDER BY table_name
            """
        )
    ).mappings().all()
    assert len(file_rows) == len(STUDENT_TABLE_ORDER)
    assert {row["table_name"] for row in file_rows} == set(STUDENT_TABLE_ORDER)
    player_master_file = next(
        row for row in file_rows if row["table_name"] == "player_master"
    )
    assert player_master_file["file_path"] == str(
        release.release_dir / "player_master.parquet"
    )
    assert player_master_file["row_count"] == 1
    assert player_master_file["schema_hash"]
    assert player_master_file["checksum"]


def test_promote_staged_release_family_blocks_existing_final_folder(
    session,
    release_window,
    tmp_path,
):
    seed_snapshot_query_data(session)
    build_parameters = StudentDatasetBuildParameters(
        generation_run_id=1,
        initial_history_month_count=2,
        subsequent_month_count=0,
        output_root=tmp_path,
        release_name="napa_student_release",
    )
    staged = write_staged_release_family(
        session=session,
        output_root=tmp_path,
        release_name="napa_student_release",
        release_windows=(release_window,),
        build_parameters=build_parameters,
    )
    final_root = tmp_path / "napa_student_release"
    final_root.mkdir()

    with pytest.raises(StudentDatasetPublishError, match="already exists"):
        promote_staged_release_family(
            session=session,
            staged_family=staged,
            build_parameters=build_parameters,
        )

    assert staged.staging_root.exists()
    assert session.execute(text("SELECT COUNT(*) FROM student_dataset_releases")).scalar_one() == 0


def test_promote_staged_release_family_rejects_unvalidated_manifest(
    session,
    release_window,
    tmp_path,
):
    seed_snapshot_query_data(session)
    build_parameters = StudentDatasetBuildParameters(
        generation_run_id=1,
        initial_history_month_count=2,
        subsequent_month_count=0,
        output_root=tmp_path,
        release_name="napa_student_release",
    )
    staged = write_staged_release_family(
        session=session,
        output_root=tmp_path,
        release_name="napa_student_release",
        release_windows=(release_window,),
        build_parameters=build_parameters,
    )
    manifest_path = staged.releases[0].manifest_path
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["validation_status"] = "failed"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(StudentDatasetPublishError, match="not validated"):
        promote_staged_release_family(
            session=session,
            staged_family=staged,
            build_parameters=build_parameters,
        )

    assert staged.staging_root.exists()
    assert not (tmp_path / "napa_student_release").exists()
