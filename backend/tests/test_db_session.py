"""Tests for database session infrastructure."""
from pathlib import Path
import os
import sys

import pytest
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.db.session import (  # noqa: E402
    DEFAULT_DATABASE_URL,
    SessionLocal,
    create_database_engine,
    get_database_url,
    get_session,
    session_scope,
)


def _db_tests_enabled() -> bool:
    return os.getenv("RUN_DB_TESTS") == "1"


def test_get_database_url_uses_default_when_env_missing(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)

    assert get_database_url() == DEFAULT_DATABASE_URL


def test_get_database_url_uses_environment_value(monkeypatch):
    database_url = "postgresql://example:example@localhost:5432/example"
    monkeypatch.setenv("DATABASE_URL", database_url)

    assert get_database_url() == database_url


def test_create_database_engine_uses_supplied_url_without_connecting():
    engine = create_database_engine("postgresql://u:p@localhost:5432/db", echo=False)

    assert str(engine.url) == "postgresql://u:***@localhost:5432/db"
    assert engine.echo is False


def test_session_factory_is_configured():
    session = SessionLocal()
    try:
        assert session.autoflush is False
        assert session.expire_on_commit is False
        assert session.bind is not None
        assert session.in_transaction() is False
    finally:
        session.close()


def test_get_session_yields_and_closes_session():
    session_generator = get_session()
    session = next(session_generator)

    assert session.bind is not None

    with pytest.raises(StopIteration):
        next(session_generator)


def test_database_select_one_when_enabled():
    if not _db_tests_enabled():
        pytest.skip("Set RUN_DB_TESTS=1 to run database session checks.")

    engine = create_database_engine()
    try:
        with engine.connect() as conn:
            assert conn.execute(text("SELECT 1")).scalar_one() == 1
    except SQLAlchemyError as exc:
        pytest.fail(f"Could not connect to test database: {exc}")


def test_session_scope_rolls_back_on_exception_when_enabled():
    if not _db_tests_enabled():
        pytest.skip("Set RUN_DB_TESTS=1 to run database transaction checks.")

    with pytest.raises(RuntimeError):
        with session_scope() as session:
            session.execute(
                text(
                    """
                    CREATE TEMP TABLE rollback_probe (
                        id integer
                    ) ON COMMIT DROP
                    """
                )
            )
            session.execute(text("INSERT INTO rollback_probe (id) VALUES (1)"))
            raise RuntimeError("force rollback")

    with session_scope() as session:
        assert session.execute(text("SELECT 1")).scalar_one() == 1
