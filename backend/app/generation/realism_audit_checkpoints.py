"""Durable realism-audit query checkpoint helpers."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import RealismAuditQueryRun

from .durable_worker import utc_now
from .realism_audit import RealismAuditQuery, RealismAuditResult
from .realism_audit_report import results_to_json_ready


def initialize_realism_audit_query_checkpoints(
    session: Session,
    *,
    job_status_id: int,
    generation_run_id: int | None,
    batch_id: int | None,
    queries: Sequence[RealismAuditQuery],
) -> tuple[RealismAuditQueryRun, ...]:
    """Create one pending checkpoint row for each registered audit query."""
    existing_names = set(
        session.scalars(
            select(RealismAuditQueryRun.query_name).where(
                RealismAuditQueryRun.job_status_id == job_status_id
            )
        )
    )
    checkpoints: list[RealismAuditQueryRun] = []
    for index, query in enumerate(queries, start=1):
        if query.name in existing_names:
            continue
        checkpoint = RealismAuditQueryRun(
            job_status_id=job_status_id,
            generation_run_id=generation_run_id,
            batch_id=batch_id,
            query_index=index,
            query_name=query.name,
            status="pending",
        )
        session.add(checkpoint)
        checkpoints.append(checkpoint)
    session.flush()
    return tuple(checkpoints)


def load_realism_audit_query_checkpoints(
    session: Session,
    *,
    job_status_id: int,
    include_completed: bool = True,
) -> tuple[RealismAuditQueryRun, ...]:
    """Load checkpoint rows in deterministic resume order."""
    statement = select(RealismAuditQueryRun).where(
        RealismAuditQueryRun.job_status_id == job_status_id
    )
    if not include_completed:
        statement = statement.where(RealismAuditQueryRun.status != "succeeded")
    statement = statement.order_by(
        RealismAuditQueryRun.query_index.asc(),
        RealismAuditQueryRun.id.asc(),
    )
    return tuple(session.scalars(statement))


def mark_realism_audit_query_running(
    session: Session,
    checkpoint: RealismAuditQueryRun,
    *,
    now: datetime | None = None,
) -> RealismAuditQueryRun:
    """Mark one query checkpoint as actively running."""
    current_time = now or utc_now()
    checkpoint.status = "running"
    checkpoint.started_at = checkpoint.started_at or current_time
    checkpoint.completed_at = None
    checkpoint.error_message = None
    session.flush()
    return checkpoint


def mark_realism_audit_query_succeeded(
    session: Session,
    checkpoint: RealismAuditQueryRun,
    *,
    result: RealismAuditResult | dict[str, Any],
    elapsed_ms: int,
    now: datetime | None = None,
) -> RealismAuditQueryRun:
    """Store successful query result metadata in the checkpoint row."""
    result_payload = _result_to_payload(result)
    checkpoint.status = "succeeded"
    checkpoint.completed_at = now or utc_now()
    checkpoint.elapsed_ms = elapsed_ms
    checkpoint.row_count = len(result_payload.get("rows", ()))
    checkpoint.result_json = result_payload
    checkpoint.error_message = None
    session.flush()
    return checkpoint


def mark_realism_audit_query_failed(
    session: Session,
    checkpoint: RealismAuditQueryRun,
    *,
    error_message: str,
    elapsed_ms: int | None = None,
    now: datetime | None = None,
) -> RealismAuditQueryRun:
    """Store failed query state in the checkpoint row."""
    checkpoint.status = "failed"
    checkpoint.completed_at = now or utc_now()
    checkpoint.elapsed_ms = elapsed_ms
    checkpoint.error_message = error_message
    session.flush()
    return checkpoint


def _result_to_payload(result: RealismAuditResult | dict[str, Any]) -> dict[str, Any]:
    if isinstance(result, dict):
        return result
    return results_to_json_ready((result,))[0]
