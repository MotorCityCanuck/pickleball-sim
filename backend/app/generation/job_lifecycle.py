"""Shared helpers for durable background job lifecycle state."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import JobStageProgress, JobStatus


DEFAULT_JOB_STALE_AFTER = timedelta(minutes=15)
TERMINAL_JOB_STATUSES = {"succeeded", "failed"}


def utc_now() -> datetime:
    """Return the naive UTC timestamp convention used by persisted job rows."""
    return datetime.now(UTC).replace(tzinfo=None)


def job_is_actively_processing(
    session: Session,
    job: JobStatus | None,
    *,
    now: datetime | None = None,
    stale_after: timedelta = DEFAULT_JOB_STALE_AFTER,
) -> bool:
    """Return whether a pending/running job still has a fresh activity signal."""
    if job is None or job.status in TERMINAL_JOB_STATUSES:
        return False

    current_time = now or utc_now()
    running_stage_exists = session.scalar(
        select(JobStageProgress.id)
        .where(
            JobStageProgress.job_status_id == job.id,
            JobStageProgress.status == "running",
            JobStageProgress.last_heartbeat_at.is_not(None),
            JobStageProgress.last_heartbeat_at >= current_time - stale_after,
        )
        .limit(1)
    )
    if running_stage_exists is not None:
        return True

    reference_time = job.started_at or job.created_at
    if reference_time is None:
        return False
    return (current_time - reference_time) <= stale_after


def overall_percent_complete(session: Session, job_status_id: int) -> Decimal:
    """Calculate top-level progress from all stage percentages, including partial work."""
    total_rows = session.scalar(
        select(func.count()).select_from(JobStageProgress).where(
            JobStageProgress.job_status_id == job_status_id
        )
    ) or 0
    if total_rows == 0:
        return Decimal("0.00")

    percent_sum = session.scalar(
        select(func.coalesce(func.sum(JobStageProgress.progress_percent), 0)).where(
            JobStageProgress.job_status_id == job_status_id
        )
    ) or Decimal("0.00")
    return (Decimal(str(percent_sum)) / Decimal(total_rows)).quantize(Decimal("0.01"))
