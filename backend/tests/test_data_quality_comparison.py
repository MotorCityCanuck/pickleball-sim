"""Tests for clean-vs-tainted student export comparison."""

from pathlib import Path
import shutil
import sys

import pyarrow as pa
import pyarrow.parquet as pq


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.exports.data_quality import compare_export_locations  # noqa: E402
from app.exports.student_dataset import (  # noqa: E402
    StudentDatasetBuildParameters,
    write_staged_release_family,
)
from test_student_dataset_queries import (  # noqa: E402
    release_window,
    seed_snapshot_query_data,
    session,
    session_factory,
)


def test_compare_export_locations_reports_no_differences_for_same_release(
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
        release_name="clean_release",
        data_quality_level="none",
    )
    staged = write_staged_release_family(
        session=session,
        output_root=tmp_path,
        release_name="clean_release",
        release_windows=(release_window,),
        build_parameters=build_parameters,
    )
    release_dir = staged.releases[0].release_dir

    result = compare_export_locations(
        clean_path=release_dir,
        tainted_path=release_dir,
    )

    assert result.compared_release_count == 1
    assert result.total_issue_count == 0
    assert result.missing_clean_releases == ()
    assert result.missing_tainted_releases == ()


def test_compare_export_locations_detects_missingness_variants_and_duplicates(
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
        release_name="clean_release",
        data_quality_level="none",
    )
    staged = write_staged_release_family(
        session=session,
        output_root=tmp_path,
        release_name="clean_release",
        release_windows=(release_window,),
        build_parameters=build_parameters,
    )
    clean_release_dir = staged.releases[0].release_dir
    tainted_release_dir = tmp_path / "tainted_release"
    shutil.copytree(clean_release_dir, tainted_release_dir)

    player_master = pq.read_table(tainted_release_dir / "player_master.parquet").to_pylist()
    player_master[0]["dominant_hand"] = None
    player_master[0]["first_name"] = str(player_master[0]["first_name"]).upper()
    _write_rows(
        tainted_release_dir / "player_master.parquet",
        player_master,
        pq.read_table(clean_release_dir / "player_master.parquet").column_names,
    )

    matches = pq.read_table(tainted_release_dir / "matches.parquet").to_pylist()
    duplicate_match = dict(matches[0])
    duplicate_match["id"] = int(duplicate_match["id"]) + 1000
    matches.append(duplicate_match)
    _write_rows(
        tainted_release_dir / "matches.parquet",
        matches,
        pq.read_table(clean_release_dir / "matches.parquet").column_names,
    )

    result = compare_export_locations(
        clean_path=clean_release_dir,
        tainted_path=tainted_release_dir,
    )

    assert result.compared_release_count == 1
    assert result.total_issue_count > 0
    release = result.releases[0]
    players_table = next(table for table in release.tables if table.table_name == "player_master")
    assert any(
        issue.issue_type == "missing_optional_values" and issue.column_name == "dominant_hand"
        for issue in players_table.column_issues
    )
    assert any(
        issue.issue_type == "name_case_variants" and issue.column_name == "first_name"
        for issue in players_table.column_issues
    )
    matches_table = next(table for table in release.tables if table.table_name == "matches")
    assert matches_table.row_delta == 1
    assert matches_table.duplicate_like_extra_row_count == 1


def _write_rows(path: Path, rows: list[dict], column_names: list[str]) -> None:
    table = pa.table(
        {
            column_name: pa.array([row.get(column_name) for row in rows])
            for column_name in column_names
        }
    )
    pq.write_table(table, path)
