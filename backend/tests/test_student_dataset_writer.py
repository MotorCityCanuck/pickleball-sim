"""Tests for staged student dataset Parquet writing."""

import json
from pathlib import Path
import sys

import pytest
import pyarrow.parquet as pq
from sqlalchemy import text


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

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
from test_student_dataset_queries import (  # noqa: E402
    query_context,
    release_window,
    seed_snapshot_query_data,
    session,
    session_factory,
)


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
        data_quality_level="clean",
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
    assert release.release_type == "historical_baseline"
    assert release.release_dir.parent == result.staging_root
    assert release.manifest_path == release.release_dir / MANIFEST_FILE_NAME
    assert release.manifest_path.exists()

    parquet_files = sorted(path.name for path in release.release_dir.glob("*.parquet"))
    assert parquet_files == sorted(f"{table_name}.parquet" for table_name in STUDENT_TABLE_ORDER)
    assert len(release.files) == len(STUDENT_TABLE_ORDER)


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
    assert manifest["release_type"] == "historical_baseline"
    assert manifest["student_dataset_schema_version"] == "1.0"
    assert manifest["source_generation_run_id"] == 1
    assert manifest["included_batch_sequences"] == [1, 2]
    assert manifest["included_batch_months"] == ["2025-01-01", "2025-02-01"]
    assert manifest["snapshot_month"] == "2025-02-01"
    assert manifest["snapshot_end_exclusive"] == "2025-03-01"
    assert manifest["data_quality_level"] == "clean"
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
        "relationship:club_memberships.player_id->players.id" in failed_names
        or "relationship:match_team_players.player_id->players.id" in failed_names
    )


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
    assert release_rows[0]["release_type"] == "historical_baseline"
    assert str(release_rows[0]["release_month"]) == "2025-02-01"
    assert release_rows[0]["generation_run_id"] == 1
    assert release_rows[0]["data_quality_level"] == "clean"
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
    players_file = next(row for row in file_rows if row["table_name"] == "players")
    assert players_file["file_path"] == str(release.release_dir / "players.parquet")
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
