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
from sqlalchemy.exc import SQLAlchemyError


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

    assert len(tables) == 22
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
