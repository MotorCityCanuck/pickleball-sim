"""Offline consistency checks for SQLAlchemy models.

These tests verify that the ORM registry matches the DDL-first schema contract.
They do not connect to PostgreSQL and must not create database tables.
"""
from pathlib import Path
import sys

from sqlalchemy.orm import configure_mappers


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.models import Base  # noqa: E402


EXPECTED_TABLES = {
    "batch_runs",
    "club_memberships",
    "clubs",
    "export_runs",
    "first_names",
    "generation_runs",
    "job_status",
    "last_names",
    "match_team_players",
    "match_teams",
    "matches",
    "monthly_batches",
    "player_assessment_history",
    "player_rating_history",
    "player_registrations",
    "players",
    "regions",
    "team_memberships",
    "teams",
    "tournaments",
    "uploaded_files",
    "validation_results",
}

STALE_SPLIT_NAME_TABLES = {
    "usa_first_names",
    "usa_last_names",
    "canada_first_names",
    "canada_last_names",
}

EXPECTED_KEY_COLUMNS = {
    "first_names": {
        "id",
        "country_code",
        "state_province_code",
        "birth_year",
        "gender",
        "first_name",
        "frequency_count",
        "normalized_probability",
        "source_dataset",
        "created_at",
        "updated_at",
    },
    "last_names": {
        "id",
        "country_code",
        "state_province_code",
        "last_name",
        "frequency_count",
        "normalized_probability",
        "source_dataset",
        "created_at",
        "updated_at",
    },
    "players": {
        "id",
        "external_player_key",
        "first_name",
        "last_name",
        "gender",
        "birth_date",
        "dominant_hand",
        "home_region_id",
        "registration_date",
        "initial_skill_seed",
        "player_status",
        "generation_run_id",
        "created_at",
        "updated_at",
    },
    "matches": {
        "id",
        "tournament_id",
        "match_date",
        "region_id",
        "match_type",
        "court_type",
        "match_format",
        "winning_team_id",
        "total_points_played",
        "expected_competitiveness",
        "simulation_noise_factor",
        "batch_id",
        "created_at",
        "updated_at",
    },
    "monthly_batches": {
        "id",
        "generation_run_id",
        "batch_month",
        "batch_sequence",
        "batch_type",
        "active_player_count_start",
        "new_player_count",
        "active_player_count_end",
        "match_count_generated",
        "rating_update_count",
        "assessment_update_count",
        "processing_status",
        "started_at",
        "completed_at",
        "error_message",
        "created_at",
        "updated_at",
    },
}


def test_all_models_import_and_mappers_configure():
    """Model registry should import and relationships should configure."""
    configure_mappers()


def test_expected_table_registry_matches_live_schema_scope():
    """ORM registry should expose exactly the live 22-table schema."""
    orm_tables = set(Base.metadata.tables)

    assert len(orm_tables) == 22
    assert orm_tables == EXPECTED_TABLES


def test_stale_country_split_name_tables_are_absent():
    """Reference names should use consolidated tables with country_code."""
    orm_tables = set(Base.metadata.tables)

    assert STALE_SPLIT_NAME_TABLES.isdisjoint(orm_tables)


def test_key_table_columns_match_schema_contract():
    """High-value table columns should match the DDL-first contract."""
    for table_name, expected_columns in EXPECTED_KEY_COLUMNS.items():
        orm_columns = set(Base.metadata.tables[table_name].columns.keys())

        assert orm_columns == expected_columns, table_name


def test_matches_winning_team_id_is_not_an_orm_foreign_key():
    """The ORM should not add a FK that is absent from backend/schema.sql."""
    column = Base.metadata.tables["matches"].columns["winning_team_id"]

    assert not column.foreign_keys
