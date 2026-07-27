"""Service-layer orchestration for realism audit execution."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Mapping, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import MonthlyBatch

from .realism_audit import (
    REALISM_AUDIT_QUERIES,
    RealismAuditQuery,
    RealismAuditResult,
    RealismAuditRunner,
    resolve_realism_audit_parameters,
)


@dataclass(frozen=True)
class RealismAuditExecution:
    """One realism-audit execution with resolved scope metadata."""

    generation_run_id: int | None
    batch_id: int | None
    batch_month: date | None
    executed_at: datetime
    parameters: Mapping[str, Any]
    results: tuple[RealismAuditResult, ...]


class RealismAuditService:
    """Orchestrate realism audit execution for the latest available dataset."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.runner = RealismAuditRunner(session)

    def available_queries(self) -> tuple[RealismAuditQuery, ...]:
        """Return the registered realism audit queries."""
        return REALISM_AUDIT_QUERIES

    def run(
        self,
        *,
        query_names: Sequence[str] | None = None,
    ) -> RealismAuditExecution:
        """Resolve scope metadata and execute one or more audit queries."""
        params = resolve_realism_audit_parameters(self.session)
        results = self.runner.run(query_names=query_names, params=params)
        batch_id = params.get("batch_id")
        batch_month = None
        if batch_id is not None:
            batch_month = self.session.scalar(
                select(MonthlyBatch.batch_month).where(MonthlyBatch.id == batch_id)
            )
        return RealismAuditExecution(
            generation_run_id=params.get("generation_run_id"),
            batch_id=batch_id,
            batch_month=batch_month,
            executed_at=datetime.now(timezone.utc),
            parameters=dict(params),
            results=results,
        )


def run_realism_audit(
    session: Session,
    *,
    query_names: Sequence[str] | None = None,
) -> RealismAuditExecution:
    """Convenience helper for one-shot realism audit execution."""
    return RealismAuditService(session).run(query_names=query_names)
