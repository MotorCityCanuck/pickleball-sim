"""Compatibility smoke tests for SQLAlchemy models.

The main tests live under `backend/tests`. This file remains as a simple entry
point for older instructions that run `python -m pytest backend/test_models.py`.
Database checks are opt-in with RUN_DB_TESTS=1.
"""
from pathlib import Path
import os
import sys

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, configure_mappers


BACKEND_DIR = Path(__file__).resolve().parent
TESTS_DIR = BACKEND_DIR / "tests"
for path in (BACKEND_DIR, TESTS_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from app.models import Base, FirstName, GenerationRun, Match, Player  # noqa: E402
from schema_expectations import EXPECTED_TABLES  # noqa: E402


DEFAULT_DATABASE_URL = "postgresql://postgres:postgres@localhost:5432/pickleball"


def _database_url() -> str:
    return (
        os.getenv("DB_TEST_DATABASE_URL")
        or os.getenv("DATABASE_URL")
        or DEFAULT_DATABASE_URL
    )


def _db_tests_enabled() -> bool:
    return os.getenv("RUN_DB_TESTS") == "1"


def test_models_import_and_metadata_matches_expected_tables():
    """Models should import without a database and expose the live schema scope."""
    configure_mappers()

    assert len(Base.metadata.tables) == 22
    assert set(Base.metadata.tables) == EXPECTED_TABLES
    assert FirstName.__tablename__ == "first_names"
    assert Match.__tablename__ == "matches"


def test_database_connection_and_basic_queries_when_enabled():
    """Opt-in smoke check for a local ORM-created development database."""
    if not _db_tests_enabled():
        pytest.skip("Set RUN_DB_TESTS=1 to run database connection checks.")

    engine = create_engine(_database_url())
    try:
        with engine.connect() as conn:
            assert conn.execute(text("SELECT 1")).scalar_one() == 1
    except SQLAlchemyError as exc:
        pytest.fail(f"Could not connect to test database: {exc}")

    with Session(engine) as session:
        session.query(GenerationRun).count()
        session.query(Player).count()
