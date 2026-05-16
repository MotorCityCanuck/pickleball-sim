"""SQLAlchemy engine and session management."""
from __future__ import annotations

from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import DEFAULT_DATABASE_URL, get_database_url, load_settings


def create_database_engine(database_url: str | None = None, *, echo: bool | None = None) -> Engine:
    """Create a SQLAlchemy engine for the configured database."""
    if echo is None:
        echo = load_settings().database_echo

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
    expire_on_commit=False,
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
