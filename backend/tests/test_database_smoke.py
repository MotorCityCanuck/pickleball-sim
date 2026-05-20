"""Opt-in PostgreSQL smoke tests for ORM-created development databases.

Run with:
    RUN_DB_TESTS=1 python -m pytest backend/tests/test_database_smoke.py -q

The target database defaults to the root compose setup:
    postgresql://postgres:postgres@localhost:5432/pickleball

Override with DB_TEST_DATABASE_URL or DATABASE_URL.
"""
from pathlib import Path
import os
import sys

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from schema_expectations import (  # noqa: E402
    EXPECTED_INDEXES,
    EXPECTED_TABLES,
    STALE_SPLIT_NAME_TABLES,
)


DEFAULT_DATABASE_URL = "postgresql://postgres:postgres@localhost:5432/pickleball"


def _db_tests_enabled() -> bool:
    return os.getenv("RUN_DB_TESTS") == "1"


@pytest.fixture(scope="session")
def engine():
    if not _db_tests_enabled():
        pytest.skip("Set RUN_DB_TESTS=1 to run database smoke tests.")

    database_url = (
        os.getenv("DB_TEST_DATABASE_URL")
        or os.getenv("DATABASE_URL")
        or DEFAULT_DATABASE_URL
    )
    engine = create_engine(database_url)
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        pytest.fail(f"Could not connect to test database: {exc}")
    return engine


def test_database_tables_match_expected_schema(engine):
    inspector = inspect(engine)
    tables = set(inspector.get_table_names(schema="public"))

    assert len(tables) == len(EXPECTED_TABLES)
    assert tables == EXPECTED_TABLES


def test_split_country_name_tables_are_absent(engine):
    inspector = inspect(engine)
    tables = set(inspector.get_table_names(schema="public"))

    assert STALE_SPLIT_NAME_TABLES.isdisjoint(tables)
    assert {"first_names", "last_names"}.issubset(tables)


def test_expected_explicit_indexes_exist(engine):
    with engine.connect() as conn:
        actual_indexes = {
            row[0]
            for row in conn.execute(
                text(
                    """
                    SELECT indexname
                    FROM pg_indexes
                    WHERE schemaname = 'public'
                    """
                )
            )
        }

    assert EXPECTED_INDEXES.issubset(actual_indexes)


def test_pgcrypto_extension_is_available(engine):
    with engine.connect() as conn:
        installed = conn.execute(
            text(
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM pg_extension
                    WHERE extname = 'pgcrypto'
                )
                """
            )
        ).scalar_one()

    assert installed is True


def test_database_defaults_are_applied(engine):
    with engine.connect() as conn:
        transaction = conn.begin()
        try:
            generation_run = conn.execute(
                text(
                    """
                    INSERT INTO generation_runs (generation_name, seed_value)
                    VALUES ('default_probe', 123)
                    RETURNING id, status
                    """
                )
            ).one()

            region = conn.execute(
                text(
                    """
                    INSERT INTO regions (country_code, region_name)
                    VALUES ('US', 'Default Probe Region')
                    RETURNING id
                    """
                )
            ).one()

            batch = conn.execute(
                text(
                    """
                    INSERT INTO monthly_batches (
                        generation_run_id,
                        batch_month,
                        batch_sequence
                    )
                    VALUES (:generation_run_id, DATE '2024-01-01', 1)
                    RETURNING id, batch_type, processing_status
                    """
                ),
                {"generation_run_id": generation_run.id},
            ).one()

            player = conn.execute(
                text(
                    """
                    INSERT INTO players (
                        first_name,
                        last_name,
                        birth_date,
                        home_region_id,
                        registration_date,
                        generation_run_id
                    )
                    VALUES (
                        'Default',
                        'Probe',
                        DATE '1990-01-01',
                        :region_id,
                        DATE '2024-01-01',
                        :generation_run_id
                    )
                    RETURNING id, external_player_key, player_status
                    """
                ),
                {"region_id": region.id, "generation_run_id": generation_run.id},
            ).one()

            registration = conn.execute(
                text(
                    """
                    INSERT INTO player_registrations (
                        player_id,
                        batch_id,
                        registration_month,
                        assigned_region_id
                    )
                    VALUES (
                        :player_id,
                        :batch_id,
                        DATE '2024-01-01',
                        :region_id
                    )
                    RETURNING registration_source
                    """
                ),
                {"player_id": player.id, "batch_id": batch.id, "region_id": region.id},
            ).one()

            match = conn.execute(
                text(
                    """
                    INSERT INTO matches (
                        match_date,
                        region_id,
                        match_type,
                        batch_id
                    )
                    VALUES (
                        DATE '2024-01-02',
                        :region_id,
                        'recreational',
                        :batch_id
                    )
                    RETURNING id
                    """
                ),
                {"region_id": region.id, "batch_id": batch.id},
            ).one()

            game = conn.execute(
                text(
                    """
                    INSERT INTO match_games (
                        match_id,
                        game_number,
                        team_one_score,
                        team_two_score,
                        winning_team_number
                    )
                    VALUES (:match_id, 1, 11, 7, 1)
                    RETURNING target_score, win_by
                    """
                ),
                {"match_id": match.id},
            ).one()

            assert generation_run.status == "not_started"
            assert batch.batch_type == "future_increment"
            assert batch.processing_status == "pending"
            assert game.target_score == 11
            assert game.win_by == 2
            assert player.external_player_key is not None
            assert player.player_status == "ACTIVE"
            assert registration.registration_source == "synthetic"
        finally:
            transaction.rollback()


def test_database_defaults_probe_rolls_back(engine):
    with engine.connect() as conn:
        count = conn.execute(
            text(
                """
                SELECT COUNT(*)
                FROM generation_runs
                WHERE generation_name = 'default_probe'
                """
            )
        ).scalar_one()

    assert count == 0


def test_database_check_constraints_are_enforced(engine):
    with engine.connect() as conn:
        transaction = conn.begin()
        try:
            with pytest.raises(IntegrityError):
                conn.execute(
                    text(
                        """
                        INSERT INTO first_names (
                            country_code,
                            state_province_code,
                            birth_year,
                            gender,
                            first_name,
                            frequency_count
                        )
                        VALUES ('MX', 'MX', 1990, 'M', 'Probe', 1)
                        """
                    )
                )
        finally:
            transaction.rollback()


def test_database_match_game_constraints_are_enforced(engine):
    with engine.connect() as conn:
        transaction = conn.begin()
        try:
            generation_run = conn.execute(
                text(
                    """
                    INSERT INTO generation_runs (generation_name, seed_value)
                    VALUES ('match_game_constraint_probe', 456)
                    RETURNING id
                    """
                )
            ).one()
            region = conn.execute(
                text(
                    """
                    INSERT INTO regions (country_code, region_name)
                    VALUES ('US', 'Match Game Constraint Probe Region')
                    RETURNING id
                    """
                )
            ).one()
            batch = conn.execute(
                text(
                    """
                    INSERT INTO monthly_batches (
                        generation_run_id,
                        batch_month,
                        batch_sequence
                    )
                    VALUES (:generation_run_id, DATE '2024-02-01', 2)
                    RETURNING id
                    """
                ),
                {"generation_run_id": generation_run.id},
            ).one()
            match = conn.execute(
                text(
                    """
                    INSERT INTO matches (
                        match_date,
                        region_id,
                        match_type,
                        batch_id
                    )
                    VALUES (
                        DATE '2024-02-02',
                        :region_id,
                        'recreational',
                        :batch_id
                    )
                    RETURNING id
                    """
                ),
                {"region_id": region.id, "batch_id": batch.id},
            ).one()

            with pytest.raises(IntegrityError):
                conn.execute(
                    text(
                        """
                        INSERT INTO match_games (
                            match_id,
                            game_number,
                            team_one_score,
                            team_two_score,
                            winning_team_number,
                            target_score
                        )
                        VALUES (:match_id, 1, 11, 7, 1, 13)
                        """
                    ),
                    {"match_id": match.id},
                )
        finally:
            transaction.rollback()
