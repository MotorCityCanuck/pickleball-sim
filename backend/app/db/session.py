"""SQLAlchemy engine and session management."""
from __future__ import annotations

from contextlib import contextmanager
import os
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker


DEFAULT_DATABASE_URL = "postgresql://postgres:postgres@localhost:5432/pickleball"


def get_database_url() -> str:
    """Return the configured database URL."""
    return os.getenv("DATABASE_URL") or DEFAULT_DATABASE_URL


def create_database_engine(database_url: str | None = None, *, echo: bool | None = None) -> Engine:
    """Create a SQLAlchemy engine for the configured database."""
    if echo is None:
        echo = os.getenv("DATABASE_ECHO", "").lower() in {"1", "true", "yes", "on"}

    return create_engine(
        database_url or get_database_url(),
        echo=echo,
        pool_pre_ping=True,
        future=True,
    )


engine = create_database_engine()
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    future=True,
)


def get_session() -> Generator[Session, None, None]:
    """Yield a database session for dependency-injection style callers."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    """Provide a transactional session scope.

    Commits on successful exit, rolls back on exception, and always closes the
    session.
    """
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
