"""Operator recovery actions for stalled durable jobs."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.generation.job_lifecycle import job_is_actively_processing, utc_now
from app.models import (
    GenerationRun,
    JobStageProgress,
    JobStatus,
    MonthlyBatch,
    RawSeedLoadRun,
)


RECOVERY_MESSAGE = (
    "Cleared stalled job from control panel; no active heartbeat remained."
)


@dataclass(frozen=True)
class ClearedJob:
    """Summary of a successful stalled-job cleanup."""

    job_status_id: int
    job_id: str
    job_type: str


@dataclass(frozen=True)
class DismissedJob:
    """Summary of a failed job dismissed from operator status surfaces."""

    job_status_id: int
    job_id: str
    job_type: str


def clear_stalled_job(session: Session, *, job_status_id: int) -> ClearedJob:
    """Mark a stale pending/running job and its dependent status rows as failed."""
    job = session.get(JobStatus, job_status_id)
    if job is None:
        raise ValueError(f"Job status {job_status_id} does not exist.")
    if job.status in {"succeeded", "failed"}:
        raise ValueError(f"Job {job.job_id} is already {job.status}.")
    if job_is_actively_processing(session, job):
        raise ValueError(f"Job {job.job_id} still has a fresh activity signal.")

    now = utc_now()
    stage_rows = list(
        session.scalars(
            select(JobStageProgress).where(
                JobStageProgress.job_status_id == job_status_id
            )
        )
    )
    generation_run_ids = {
        row.generation_run_id for row in stage_rows if row.generation_run_id is not None
    }

    for row in stage_rows:
        if row.status in {"succeeded", "failed"}:
            continue
        row.status = "failed"
        row.completed_at = row.completed_at or now
        row.last_heartbeat_at = row.last_heartbeat_at or now
        row.error_message = row.error_message or RECOVERY_MESSAGE
        row.progress_message = row.progress_message or RECOVERY_MESSAGE
        row.progress_percent = row.progress_percent or Decimal("0.00")

    job.status = "failed"
    job.current_phase = "failed"
    job.current_message = RECOVERY_MESSAGE
    job.error_message = job.error_message or RECOVERY_MESSAGE
    job.completed_at = job.completed_at or now
    job.percent_complete = job.percent_complete or Decimal("0.00")

    for generation_run_id in generation_run_ids:
        generation_run = session.get(GenerationRun, generation_run_id)
        if generation_run is not None and generation_run.status not in {"succeeded", "failed"}:
            generation_run.status = "failed"
            generation_run.completed_at = generation_run.completed_at or now
        for batch in session.scalars(
            select(MonthlyBatch).where(
                MonthlyBatch.generation_run_id == generation_run_id,
                MonthlyBatch.processing_status.in_(("pending", "running")),
            )
        ):
            batch.processing_status = "failed"
            batch.completed_at = batch.completed_at or now
            batch.error_message = batch.error_message or RECOVERY_MESSAGE

    session.flush()
    return ClearedJob(
        job_status_id=job.id,
        job_id=job.job_id,
        job_type=job.job_type,
    )


def dismiss_failed_job(session: Session, *, job_status_id: int) -> DismissedJob:
    """Remove a failed job record from operator status surfaces without deleting domain data."""
    job = session.get(JobStatus, job_status_id)
    if job is None:
        raise ValueError(f"Job status {job_status_id} does not exist.")
    if job.status != "failed":
        raise ValueError(f"Job {job.job_id} is not failed.")

    for load_run in session.scalars(
        select(RawSeedLoadRun).where(RawSeedLoadRun.job_status_id == job_status_id)
    ):
        load_run.job_status_id = None

    for row in session.scalars(
        select(JobStageProgress).where(JobStageProgress.job_status_id == job_status_id)
    ):
        session.delete(row)

    session.delete(job)
    session.flush()
    return DismissedJob(
        job_status_id=job_status_id,
        job_id=job.job_id,
        job_type=job.job_type,
    )
