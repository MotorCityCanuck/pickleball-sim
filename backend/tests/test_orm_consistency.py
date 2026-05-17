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
from schema_expectations import (  # noqa: E402
    EXPECTED_CHECK_CONSTRAINTS,
    EXPECTED_FOREIGN_KEYS,
    EXPECTED_INDEXES,
    EXPECTED_SERVER_DEFAULTS,
    EXPECTED_TABLES,
    EXPECTED_UNIQUE_CONSTRAINTS,
    STALE_SPLIT_NAME_TABLES,
)
from sqlalchemy import CheckConstraint, UniqueConstraint  # noqa: E402


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
        "bias_multiplier",
        "adjusted_frequency_count",
        "normalized_probability",
        "source_dataset",
        "created_at",
        "updated_at",
    },
    "regions": {
        "id",
        "country_code",
        "region_type",
        "region_name",
        "state_province_code",
        "population",
        "selection_probability",
        "competitiveness_multiplier",
        "latitude",
        "longitude",
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
    "raw_seed_load_runs": {
        "id",
        "dataset_type",
        "source_path",
        "source_file_count",
        "source_checksum",
        "started_at",
        "completed_at",
        "status",
        "rows_read",
        "rows_loaded",
        "rows_rejected",
        "error_message",
        "created_at",
        "updated_at",
    },
    "raw_seed_load_errors": {
        "id",
        "load_run_id",
        "source_file",
        "source_row_number",
        "error_code",
        "error_message",
        "raw_payload",
        "created_at",
        "updated_at",
    },
    "raw_metro_areas": {
        "id",
        "load_run_id",
        "source_file",
        "source_row_number",
        "raw_payload",
        "country_code",
        "state_province_code",
        "metro_area_name",
        "population",
        "selection_probability",
        "source_dataset",
        "created_at",
        "updated_at",
    },
    "raw_pickleball_club_names": {
        "id",
        "load_run_id",
        "source_file",
        "source_row_number",
        "raw_payload",
        "club_seed",
        "country_code",
        "state_province_code",
        "club_name",
        "club_type",
        "size_tier",
        "generation_method",
        "source_dataset",
        "created_at",
        "updated_at",
    },
    "raw_pickleball_club_distributions": {
        "id",
        "load_run_id",
        "source_file",
        "source_row_number",
        "raw_payload",
        "country_code",
        "state_province_code",
        "state_province_name",
        "target_club_count",
        "source_dataset",
        "created_at",
        "updated_at",
    },
    "raw_first_names": {
        "id",
        "load_run_id",
        "source_file",
        "source_row_number",
        "raw_payload",
        "country_code",
        "state_province_code",
        "gender",
        "birth_year",
        "first_name",
        "frequency_count",
        "source_dataset",
        "created_at",
        "updated_at",
    },
    "raw_last_names": {
        "id",
        "load_run_id",
        "source_file",
        "source_row_number",
        "raw_payload",
        "country_code",
        "last_name",
        "frequency_count",
        "source_dataset",
        "created_at",
        "updated_at",
    },
    "raw_state_prov_biases": {
        "id",
        "load_run_id",
        "source_file",
        "source_row_number",
        "raw_payload",
        "country_code",
        "state_province_code",
        "last_name",
        "bias_multiplier",
        "bias_reason",
        "source_dataset",
        "created_at",
        "updated_at",
    },
}

def test_all_models_import_and_mappers_configure():
    """Model registry should import and relationships should configure."""
    configure_mappers()


def test_expected_table_registry_matches_live_schema_scope():
    """ORM registry should expose exactly the expected live schema."""
    orm_tables = set(Base.metadata.tables)

    assert len(orm_tables) == len(EXPECTED_TABLES)
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

    assert len(orm_indexes) == len(EXPECTED_INDEXES)
    assert orm_indexes == EXPECTED_INDEXES
    assert not any(index_name.startswith("ix_") for index_name in orm_indexes)


def test_expected_check_constraints_are_declared():
    """ORM metadata should include the expected named check constraints."""
    actual = {
        table_name: {
            constraint.name
            for constraint in table.constraints
            if isinstance(constraint, CheckConstraint)
        }
        for table_name, table in Base.metadata.tables.items()
    }

    for table_name, expected_constraints in EXPECTED_CHECK_CONSTRAINTS.items():
        assert actual[table_name] == expected_constraints, table_name


def test_expected_unique_constraints_are_declared():
    """ORM metadata should include expected unique constraints."""
    actual = {}
    for table_name, table in Base.metadata.tables.items():
        unique_constraints = set()
        for constraint in table.constraints:
            if isinstance(constraint, UniqueConstraint):
                unique_constraints.add(tuple(column.name for column in constraint.columns))
        actual[table_name] = unique_constraints

    for table_name, expected_constraints in EXPECTED_UNIQUE_CONSTRAINTS.items():
        assert actual[table_name] == expected_constraints, table_name


def test_expected_foreign_keys_are_declared():
    """ORM metadata should include expected foreign keys."""
    actual = {
        table_name: {
            f"{foreign_key.parent.name}->{foreign_key.column.table.name}.{foreign_key.column.name}"
            for foreign_key in table.foreign_keys
        }
        for table_name, table in Base.metadata.tables.items()
    }

    for table_name, expected_foreign_keys in EXPECTED_FOREIGN_KEYS.items():
        assert actual[table_name] == expected_foreign_keys, table_name


def test_important_server_defaults_are_declared():
    """High-value database defaults should stay stable."""
    for table_name, expected_defaults in EXPECTED_SERVER_DEFAULTS.items():
        table = Base.metadata.tables[table_name]
        actual_defaults = {
            column.name: str(column.server_default.arg)
            for column in table.columns
            if column.name in expected_defaults and column.server_default is not None
        }

        assert actual_defaults == expected_defaults, table_name


def test_matches_winning_team_id_is_not_an_orm_foreign_key():
    """winning_team_id intentionally remains a plain integer for now."""
    column = Base.metadata.tables["matches"].columns["winning_team_id"]

    assert not column.foreign_keys
