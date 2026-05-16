"""Offline consistency checks for SQLAlchemy models.

These tests verify that the ORM registry matches the ORM-first schema contract.
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

EXPECTED_INDEXES = {
    "idx_assessment_batch",
    "idx_assessment_player_date",
    "idx_batch_runs_batch",
    "idx_batch_runs_status",
    "idx_club_memberships_club",
    "idx_club_memberships_dates",
    "idx_club_memberships_player",
    "idx_club_memberships_primary",
    "idx_clubs_generation_run",
    "idx_clubs_region",
    "idx_clubs_type",
    "idx_export_runs_batch",
    "idx_export_runs_created",
    "idx_export_runs_type",
    "idx_first_names_country",
    "idx_first_names_lookup",
    "idx_first_names_probability",
    "idx_generation_runs_started",
    "idx_generation_runs_status",
    "idx_job_status_started",
    "idx_job_status_status",
    "idx_job_status_type",
    "idx_last_names_country",
    "idx_last_names_lookup",
    "idx_match_team_players_player",
    "idx_match_team_players_team",
    "idx_match_teams_match",
    "idx_matches_batch",
    "idx_matches_date",
    "idx_matches_region",
    "idx_matches_tournament",
    "idx_matches_type",
    "idx_monthly_batches_generation_run",
    "idx_monthly_batches_month",
    "idx_monthly_batches_status",
    "idx_player_registrations_batch",
    "idx_player_registrations_month",
    "idx_player_registrations_player",
    "idx_players_generation_run",
    "idx_players_region",
    "idx_players_registration_date",
    "idx_players_status",
    "idx_rating_batch",
    "idx_rating_date_type",
    "idx_rating_player_date",
    "idx_rating_value",
    "idx_team_memberships_dates",
    "idx_team_memberships_player",
    "idx_team_memberships_team",
    "idx_teams_formation_date",
    "idx_teams_status",
    "idx_teams_type",
    "idx_tournaments_region",
    "idx_tournaments_start_date",
    "idx_uploaded_files_status",
    "idx_uploaded_files_timestamp",
    "idx_validation_results_batch",
    "idx_validation_results_rule",
    "idx_validation_results_severity",
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
    """High-value table columns should match the ORM-first contract."""
    for table_name, expected_columns in EXPECTED_KEY_COLUMNS.items():
        orm_columns = set(Base.metadata.tables[table_name].columns.keys())

        assert orm_columns == expected_columns, table_name


def test_expected_indexes_are_declared_with_stable_names():
    """ORM metadata should define the expected schema indexes explicitly."""
    orm_indexes = {
        index.name
        for table in Base.metadata.tables.values()
        for index in table.indexes
    }

    assert len(orm_indexes) == 59
    assert orm_indexes == EXPECTED_INDEXES
    assert not any(index_name.startswith("ix_") for index_name in orm_indexes)


def test_matches_winning_team_id_is_not_an_orm_foreign_key():
    """winning_team_id intentionally remains a plain integer for now."""
    column = Base.metadata.tables["matches"].columns["winning_team_id"]

    assert not column.foreign_keys
