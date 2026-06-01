"""Tests for staged student dataset Parquet writing."""

import json
from pathlib import Path
import sys

import pyarrow.parquet as pq


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.exports.student_dataset import (  # noqa: E402
    MANIFEST_FILE_NAME,
    PROJECTION_BY_TABLE,
    STUDENT_TABLE_ORDER,
    StagedStudentDatasetFamily,
    StudentDatasetBuildParameters,
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
    assert manifest["validation_status"] == "not_validated"

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
