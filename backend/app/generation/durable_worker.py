"""Reusable durable background worker primitives.

These helpers manage worker identity, registration, leases, and events in the
ops schema. They do not execute any workload directly.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import os
import socket
from typing import Any
from uuid import uuid4

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models import (
    BackgroundJobEvent,
    BackgroundJobLease,
    BackgroundWorker,
    JobStatus,
)


REALISM_AUDIT_JOB_TYPE = "realism_audit"
DEFAULT_LEASE_DURATION = timedelta(minutes=15)


@dataclass(frozen=True)
class WorkerIdentity:
    """Stable identity details for one worker process."""

    worker_id: str
    worker_type: str
    hostname: str
    process_id: int


def utc_now() -> datetime:
    """Return the naive UTC timestamp convention used by persisted job rows."""
    return datetime.now(UTC).replace(tzinfo=None)


def generate_worker_identity(
    worker_type: str,
    *,
    hostname: str | None = None,
    process_id: int | None = None,
    worker_id: str | None = None,
) -> WorkerIdentity:
    """Build a compact unique worker identity for the current process."""
    resolved_hostname = hostname or socket.gethostname()
    resolved_process_id = process_id if process_id is not None else os.getpid()
    resolved_worker_type = worker_type.strip() or "worker"
    if worker_id is None:
        safe_type = _compact_worker_type(resolved_worker_type)
        worker_id = f"{safe_type}-{resolved_process_id}-{uuid4().hex[:24]}"
    if len(worker_id) > 64:
        raise ValueError("worker_id must be 64 characters or fewer.")
    return WorkerIdentity(
        worker_id=worker_id,
        worker_type=resolved_worker_type,
        hostname=resolved_hostname,
        process_id=resolved_process_id,
    )


def register_worker(
    session: Session,
    identity: WorkerIdentity,
    *,
    now: datetime | None = None,
    metadata: dict[str, Any] | None = None,
) -> BackgroundWorker:
    """Insert or refresh one worker registration row."""
    current_time = now or utc_now()
    worker = session.get(BackgroundWorker, identity.worker_id)
    if worker is None:
        worker = BackgroundWorker(
            worker_id=identity.worker_id,
            worker_type=identity.worker_type,
            host_name=identity.hostname,
            process_id=identity.process_id,
            started_at=current_time,
            last_heartbeat_at=current_time,
            status="running",
            metadata_json=metadata,
        )
        session.add(worker)
    else:
        worker.worker_type = identity.worker_type
        worker.host_name = identity.hostname
        worker.process_id = identity.process_id
        worker.last_heartbeat_at = current_time
        worker.status = "running"
        if metadata is not None:
            worker.metadata_json = metadata
    session.flush()
    return worker


def heartbeat_worker(
    session: Session,
    worker_id: str,
    *,
    now: datetime | None = None,
    status: str = "running",
) -> BackgroundWorker:
    """Refresh a worker heartbeat."""
    worker = session.get(BackgroundWorker, worker_id)
    if worker is None:
        raise ValueError(f"Worker {worker_id!r} is not registered.")
    worker.last_heartbeat_at = now or utc_now()
    worker.status = status
    session.flush()
    return worker


def claim_next_realism_audit_job(
    session: Session,
    worker_id: str,
    *,
    now: datetime | None = None,
    lease_duration: timedelta = DEFAULT_LEASE_DURATION,
) -> BackgroundJobLease | None:
    """Claim the next eligible realism-audit job.

    Eligibility is intentionally narrow for Phase 2:
    - pending realism-audit jobs can be claimed when no fresh lease exists
    - running realism-audit jobs can be reclaimed only when the lease is missing
      or expired
    """
    _require_registered_worker(session, worker_id)
    current_time = now or utc_now()
    job = _next_claimable_realism_audit_job(session, current_time)
    if job is None:
        return None

    existing_lease = session.get(BackgroundJobLease, job.id)
    event_type = "job_claimed" if existing_lease is None else "job_reclaimed"
    attempt_count = 1
    if existing_lease is not None:
        attempt_count = (existing_lease.attempt_count or 0) + 1

    lease_token = uuid4().hex
    lease_expires_at = current_time + lease_duration
    if existing_lease is None:
        lease = BackgroundJobLease(
            job_status_id=job.id,
            worker_id=worker_id,
            lease_token=lease_token,
            claimed_at=current_time,
            lease_expires_at=lease_expires_at,
            last_heartbeat_at=current_time,
            attempt_count=attempt_count,
        )
        session.add(lease)
    else:
        lease = existing_lease
        lease.worker_id = worker_id
        lease.lease_token = lease_token
        lease.claimed_at = current_time
        lease.lease_expires_at = lease_expires_at
        lease.last_heartbeat_at = current_time
        lease.attempt_count = attempt_count

    job.status = "running"
    if job.started_at is None:
        job.started_at = current_time
    job.updated_at = current_time
    _write_job_event_without_flush(
        job_status_id=job.id,
        event_type=event_type,
        worker_id=worker_id,
        message=f"Worker {worker_id} claimed realism audit job {job.job_id}.",
        metadata={
            "lease_token": lease_token,
            "lease_expires_at": lease_expires_at.isoformat(),
            "attempt_count": attempt_count,
        },
        created_at=current_time,
        session=session,
    )
    session.flush()
    return lease


def renew_job_lease(
    session: Session,
    *,
    job_status_id: int,
    worker_id: str,
    lease_token: str,
    now: datetime | None = None,
    lease_duration: timedelta = DEFAULT_LEASE_DURATION,
) -> BackgroundJobLease | None:
    """Renew a fresh lease owned by the worker/token pair."""
    current_time = now or utc_now()
    lease = session.get(BackgroundJobLease, job_status_id)
    if (
        lease is None
        or lease.worker_id != worker_id
        or lease.lease_token != lease_token
        or lease.lease_expires_at <= current_time
    ):
        return None

    lease.last_heartbeat_at = current_time
    lease.lease_expires_at = current_time + lease_duration
    _write_job_event_without_flush(
        job_status_id=job_status_id,
        event_type="lease_renewed",
        worker_id=worker_id,
        message=f"Worker {worker_id} renewed job lease.",
        metadata={
            "lease_token": lease_token,
            "lease_expires_at": lease.lease_expires_at.isoformat(),
        },
        created_at=current_time,
        session=session,
    )
    session.flush()
    return lease


def release_job_lease(
    session: Session,
    *,
    job_status_id: int,
    worker_id: str,
    lease_token: str,
    final_status: str | None = None,
    now: datetime | None = None,
) -> bool:
    """Release a lease owned by the worker/token pair."""
    lease = session.get(BackgroundJobLease, job_status_id)
    if lease is None or lease.worker_id != worker_id or lease.lease_token != lease_token:
        return False

    current_time = now or utc_now()
    session.delete(lease)
    job = session.get(JobStatus, job_status_id)
    if job is not None:
        job.updated_at = current_time
        if final_status is not None:
            job.status = final_status
            if final_status in {"succeeded", "failed"}:
                job.completed_at = current_time
    _write_job_event_without_flush(
        job_status_id=job_status_id,
        event_type="lease_released",
        worker_id=worker_id,
        message=f"Worker {worker_id} released job lease.",
        metadata={"lease_token": lease_token, "final_status": final_status},
        created_at=current_time,
        session=session,
    )
    session.flush()
    return True


def write_job_event(
    session: Session,
    *,
    job_status_id: int,
    event_type: str,
    worker_id: str | None = None,
    message: str | None = None,
    metadata: dict[str, Any] | None = None,
    now: datetime | None = None,
) -> BackgroundJobEvent:
    """Append one durable job event."""
    event = _write_job_event_without_flush(
        session=session,
        job_status_id=job_status_id,
        event_type=event_type,
        worker_id=worker_id,
        message=message,
        metadata=metadata,
        created_at=now or utc_now(),
    )
    session.flush()
    return event


def _next_claimable_realism_audit_job(
    session: Session,
    now: datetime,
) -> JobStatus | None:
    statement = (
        select(JobStatus)
        .outerjoin(BackgroundJobLease, BackgroundJobLease.job_status_id == JobStatus.id)
        .where(
            JobStatus.job_type == REALISM_AUDIT_JOB_TYPE,
            JobStatus.status.in_(("pending", "running")),
            or_(
                BackgroundJobLease.job_status_id.is_(None),
                BackgroundJobLease.lease_expires_at <= now,
            ),
        )
        .order_by(JobStatus.created_at, JobStatus.id)
        .limit(1)
    )
    bind = session.get_bind()
    if bind.dialect.name == "postgresql":
        statement = statement.with_for_update(skip_locked=True, of=JobStatus)
    return session.execute(statement).scalar_one_or_none()


def _write_job_event_without_flush(
    *,
    session: Session,
    job_status_id: int,
    event_type: str,
    worker_id: str | None,
    message: str | None,
    metadata: dict[str, Any] | None,
    created_at: datetime,
) -> BackgroundJobEvent:
    event = BackgroundJobEvent(
        job_status_id=job_status_id,
        worker_id=worker_id,
        event_type=event_type,
        event_message=message,
        event_metadata_json=metadata,
        created_at=created_at,
    )
    session.add(event)
    return event


def _require_registered_worker(session: Session, worker_id: str) -> None:
    if session.get(BackgroundWorker, worker_id) is None:
        raise ValueError(f"Worker {worker_id!r} is not registered.")


def _compact_worker_type(worker_type: str) -> str:
    compacted = "".join(
        character if character.isalnum() else "-"
        for character in worker_type.lower()
    ).strip("-")
    return (compacted or "worker")[:24]
