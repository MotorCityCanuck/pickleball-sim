"""Tests for the student-facing dataset projection contract."""

from pathlib import Path
import sys

import pytest


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.exports.student_dataset import (  # noqa: E402
    EXCLUDED_SOURCE_TABLES,
    PROJECTION_BY_TABLE,
    STUDENT_DATASET_SCHEMA_VERSION,
    STUDENT_TABLE_ORDER,
    ProjectionDriftError,
    get_projection,
    validate_projection_contract,
)
from app.models import Base  # noqa: E402
from schema_expectations import EXPECTED_TABLES  # noqa: E402


def test_student_dataset_schema_version_tracks_current_projection_contract():
    assert STUDENT_DATASET_SCHEMA_VERSION == "1.4"


def test_projection_table_order_matches_documented_release_files():
    assert STUDENT_TABLE_ORDER == (
        "clubs",
        "club_memberships",
        "match_games",
        "match_team_players",
        "match_teams",
        "matches",
        "monthly_batches",
        "player_assessment_history",
        "player_master",
        "player_registrations",
        "regions",
        "team_memberships",
        "teams",
    )
    assert tuple(PROJECTION_BY_TABLE) == STUDENT_TABLE_ORDER


def test_projection_and_excluded_tables_cover_the_full_orm_schema():
    assert set(PROJECTION_BY_TABLE).isdisjoint(EXCLUDED_SOURCE_TABLES)
    assert (
        {projection.source_table for projection in PROJECTION_BY_TABLE.values()}
        | EXCLUDED_SOURCE_TABLES
        == EXPECTED_TABLES
    )


def test_projection_contract_matches_orm_columns():
    validate_projection_contract(Base.metadata)


def test_each_projection_has_explicit_filter_and_output_file():
    for table_name in STUDENT_TABLE_ORDER:
        projection = PROJECTION_BY_TABLE[table_name]

        assert projection.output_file == f"{table_name}.parquet"
        assert projection.source_filter.key
        assert projection.source_filter.description
        assert projection.included_columns


def test_projection_columns_fail_closed_against_privileged_metadata():
    privileged_columns = {
        "created_at",
        "updated_at",
        "generation_run_id",
        "processing_status",
        "started_at",
        "completed_at",
        "error_message",
        "initial_skill_seed",
        "parameter_snapshot",
        "seed_value",
    }

    for projection in PROJECTION_BY_TABLE.values():
        assert privileged_columns.isdisjoint(projection.included_columns)


def test_get_projection_rejects_unknown_tables():
    with pytest.raises(KeyError):
        get_projection("generation_runs")


def test_validate_projection_contract_detects_missing_projection():
    broken = dict(PROJECTION_BY_TABLE)
    broken.pop("player_master")

    original = __import__(
        "app.exports.student_dataset.projection",
        fromlist=["PROJECTION_BY_TABLE"],
    )

    previous = original.PROJECTION_BY_TABLE
    try:
        original.PROJECTION_BY_TABLE = broken
        with pytest.raises(ProjectionDriftError, match="table mismatch"):
            validate_projection_contract(Base.metadata)
    finally:
        original.PROJECTION_BY_TABLE = previous
