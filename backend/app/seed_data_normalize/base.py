"""Shared seed-data normalization primitives."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, TypeVar

from sqlalchemy.orm import Session

from app.db.session import session_scope


T = TypeVar("T")


@dataclass(frozen=True)
class SeedNormalizeResult:
    """Summary of a seed-data production normalization run."""

    dataset: str
    status: str
    rows_read: int
    rows_deleted: int
    rows_loaded: int


def run_in_transaction(callback: Callable[[Session], T], session: Session | None = None) -> T:
    """Run a normalization callback in a transaction or nested transaction."""
    if session is not None:
        with session.begin_nested():
            return callback(session)

    with session_scope() as active_session:
        with active_session.begin_nested():
            return callback(active_session)
