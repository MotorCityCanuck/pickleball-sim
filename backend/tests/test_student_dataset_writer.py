"""Tests for staged student dataset Parquet writing."""

import json
from pathlib import Path
import sys

import pytest
import pyarrow as pa
import pyarrow.parquet as pq
from sqlalchemy import text


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.exports.data_quality import INSTRUCTOR_MANIFEST_FILE_NAME  # noqa: E402
from app.exports.student_dataset import (  # noqa: E402
    MANIFEST_FILE_NAME,
    PROJECTION_BY_TABLE,
    STUDENT_TABLE_ORDER,
    PublishedStudentDatasetFamily,
    StagedStudentDatasetFamily,
    StudentDatasetBuildParameters,
    StudentDatasetPublishError,
    StudentDatasetValidationError,
    promote_staged_release_family,
    validate_staged_release,
    write_staged_release_family,
)
from app.models import GenerationRuntimeMetric  # noqa: E402
from test_student_dataset_queries import (  # noqa: E402
    incremental_release_window,
    query_context,
    release_window,
    seed_snapshot_query_data,
    session,
    session_factory,
)


def _seed_incremental_match_shape(session) -> None:
    session.execute(
        text(
            """
            INSERT INTO match_teams (
                id, match_id, team_number, team_score, expected_win_probability,
                average_team_rating
            )
            VALUES (21, 2, 2, 1, 0.3, 1450.0)
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
                {
                    "instrumentation": {
                        "export_queries_enabled": True,
                        "export_query_sql_text_enabled": True,
                    }
                }
            )
        },
    )
    session.commit()
    session.execute(
        text(
            """
            CREATE TABLE generation_runtime_metrics (
                id integer primary key autoincrement,
                generation_run_id bigint not null,
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
        if metric.metadata_json["table_name"] == "players"
    )
    assert players_metric.elapsed_ms >= 0
    assert players_metric.output_count == 1
    assert players_metric.metadata_json["release_name"] == (
        "napa_student_release_initial_history"
    )
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
    assert manifest["student_dataset_schema_version"] == "1.3"
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

    assert manifest["row_counts"]["players"] == 1
    assert manifest["row_counts"]["matches"] == 1
    assert manifest["ordered_columns"]["players"] == list(
        PROJECTION_BY_TABLE["players"].included_columns
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
    assert [row["player_id"] for row in pq.read_table(release_dir / "players.parquet").to_pylist()] == [1, 2]


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
    players_file = release.release_dir / "players.parquet"
    pq.write_table(pq.read_table(players_file).slice(0, 0), players_file)
    row_counts["players"] = 0

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

    assert "required_non_empty:players" in failed_names
    assert (
        "relationship:club_memberships.player_id->players.player_id" in failed_names
        or "relationship:match_team_players.player_id->players.player_id" in failed_names
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
    players_file = release.release_dir / "players.parquet"
    players_table = pq.read_table(players_file)
    duplicate_row = players_table.slice(0, 1)
    pq.write_table(
        pa.concat_tables([players_table, duplicate_row]),
        players_file,
    )
    row_counts["players"] += 1

    with pytest.raises(StudentDatasetValidationError) as exc_info:
        validate_staged_release(
            release_dir=release.release_dir,
            release_window=release_window,
            manifest_row_counts=row_counts,
        )

    failed_names = {check.name for check in exc_info.value.result.failed_checks}
    assert "players:one_row_per_player" in failed_names


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
    players_file = release.release_dir / "players.parquet"
    players_table = pq.read_table(players_file)
    snapshot_month_index = players_table.column_names.index("snapshot_month")
    updated_columns = list(players_table.itercolumns())
    updated_columns[snapshot_month_index] = pa.array(
        ["2025-03-01"],
        type=players_table.schema.field("snapshot_month").type,
    )
    pq.write_table(
        pa.table(updated_columns, names=players_table.column_names),
        players_file,
    )

    with pytest.raises(StudentDatasetValidationError) as exc_info:
        validate_staged_release(
            release_dir=release.release_dir,
            release_window=release_window,
            manifest_row_counts=row_counts,
        )

    failed_names = {check.name for check in exc_info.value.result.failed_checks}
    assert "players:snapshot_month_consistent" in failed_names


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
    players_file = next(
        row for row in file_rows if row["table_name"] == "players"
    )
    assert players_file["file_path"] == str(
        release.release_dir / "players.parquet"
    )
    assert players_file["row_count"] == 1
    assert players_file["schema_hash"]
    assert players_file["checksum"]


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
