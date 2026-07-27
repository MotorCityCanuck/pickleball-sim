"""Durable realism-audit job handler."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from time import perf_counter
from typing import Callable, Mapping

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import JobStageProgress, JobStatus, MonthlyBatch, RealismAuditQueryRun

from .durable_worker import (
    DEFAULT_LEASE_DURATION,
    claim_next_realism_audit_job,
    utc_now,
    write_job_event,
)
from .realism_audit import (
    RealismAuditQuery,
    RealismAuditResult,
    RealismAuditRunner,
    resolve_realism_audit_parameters,
)
from .realism_audit_assessment import normalize_realism_audit_assessment_thresholds
from .realism_audit_checkpoints import (
    load_realism_audit_query_checkpoints,
    mark_realism_audit_query_failed,
    mark_realism_audit_query_running,
    mark_realism_audit_query_succeeded,
)
from .realism_audit_history import DEFAULT_REALISM_AUDIT_SNAPSHOT_DIR, save_realism_audit_snapshot
from .realism_audit_service import RealismAuditExecution


RunnerFactory = Callable[[Session], RealismAuditRunner]
NowFactory = Callable[[], datetime]


@dataclass(frozen=True)
class RealismAuditJobHandlerResult:
    """Result of one durable realism-audit handler execution."""

    job_status_id: int
    executed_query_count: int
    reused_query_count: int
    snapshot_path: Path | None


@dataclass(frozen=True)
class RealismAuditQueryExecutionError(RuntimeError):
    """One realism-audit query failed after checkpoint execution had already begun."""

    query_name: str
    error_message: str

    def __str__(self) -> str:
        return self.error_message


class RealismAuditJobHandler:
    """Execute one realism-audit job using durable query checkpoints."""

    def __init__(
        self,
        session: Session,
        *,
        snapshot_dir: str | Path = DEFAULT_REALISM_AUDIT_SNAPSHOT_DIR,
        runner_factory: RunnerFactory = RealismAuditRunner,
        now_factory: NowFactory = utc_now,
    ) -> None:
        self.session = session
        self.snapshot_dir = Path(snapshot_dir)
        self.runner_factory = runner_factory
        self.now_factory = now_factory

    def claim_next_job(
        self,
        *,
        worker_id: str,
        lease_duration=DEFAULT_LEASE_DURATION,
    ):
        """Claim the next eligible realism-audit job using the lease helper."""
        return claim_next_realism_audit_job(
            self.session,
            worker_id,
            now=self.now_factory(),
            lease_duration=lease_duration,
        )

    def run_claimed_job(
        self,
        *,
        job_status_id: int,
        worker_id: str | None = None,
    ) -> RealismAuditJobHandlerResult:
        """Run or resume one claimed realism-audit job."""
        job_status = self.session.get(JobStatus, job_status_id)
        if job_status is None:
            raise ValueError(f"Realism audit job {job_status_id} was not found.")

        stage_row = self._load_stage_row(job_status_id)
        checkpoints = load_realism_audit_query_checkpoints(
            self.session,
            job_status_id=job_status_id,
        )
        if not checkpoints:
            raise ValueError(f"Realism audit job {job_status_id} has no query checkpoints.")

        started_at = self.now_factory()
        self._reset_interrupted_checkpoints(checkpoints)
        self._mark_job_running(
            job_status=job_status,
            stage_row=stage_row,
            started_at=started_at,
            total_queries=len(checkpoints),
        )
        self.session.commit()

        runner = self.runner_factory(self.session)
        query_lookup = {query.name: query for query in runner.available_queries()}
        params = resolve_realism_audit_parameters(self.session)
        executed_count = 0

        try:
            for checkpoint in load_realism_audit_query_checkpoints(
                self.session,
                job_status_id=job_status_id,
            ):
                if checkpoint.status == "succeeded":
                    continue
                query = query_lookup.get(checkpoint.query_name)
                if query is None:
                    raise ValueError(
                        f"Checkpoint references unknown query {checkpoint.query_name!r}."
                    )
                self._run_one_query(
                    runner=runner,
                    params=params,
                    checkpoint=checkpoint,
                    query=query,
                    job_status_id=job_status_id,
                    total_queries=len(checkpoints),
                )
                executed_count += 1

            snapshot_path = self._save_snapshot_from_checkpoints(
                job_status_id=job_status_id,
                query_lookup=query_lookup,
                stage_row=stage_row,
            )
            self._mark_job_succeeded(job_status_id, total_queries=len(checkpoints))
            self.session.commit()
            return RealismAuditJobHandlerResult(
                job_status_id=job_status_id,
                executed_query_count=executed_count,
                reused_query_count=len(checkpoints) - executed_count,
                snapshot_path=snapshot_path,
            )
        except Exception as exc:
            self.session.rollback()
            self._mark_job_failed(
                job_status_id=job_status_id,
                error_message=str(exc),
                worker_id=worker_id,
            )
            self.session.commit()
            raise

    def _run_one_query(
        self,
        *,
        runner: RealismAuditRunner,
        params: Mapping[str, object],
        checkpoint: RealismAuditQueryRun,
        query: RealismAuditQuery,
        job_status_id: int,
        total_queries: int,
    ) -> None:
        started_at = self.now_factory()
        mark_realism_audit_query_running(self.session, checkpoint, now=started_at)
        self._update_progress(
            job_status_id=job_status_id,
            current_index=max(0, checkpoint.query_index - 1),
            total_queries=total_queries,
            query_name=query.name,
            message=f"Running realism audit query {checkpoint.query_index} of {total_queries}: {query.name}.",
        )
        self.session.commit()

        start_time = perf_counter()
        try:
            result = runner.run(query_names=[query.name], params=params)[0]
        except Exception as exc:
            elapsed_ms = int((perf_counter() - start_time) * 1000)
            self.session.rollback()
            failed_checkpoint = self.session.get(RealismAuditQueryRun, checkpoint.id)
            if failed_checkpoint is not None:
                mark_realism_audit_query_failed(
                    self.session,
                    failed_checkpoint,
                    error_message=str(exc),
                    elapsed_ms=elapsed_ms,
                    now=self.now_factory(),
                )
                self.session.commit()
            raise RealismAuditQueryExecutionError(
                query_name=query.name,
                error_message=str(exc),
            ) from exc

        elapsed_ms = int((perf_counter() - start_time) * 1000)
        mark_realism_audit_query_succeeded(
            self.session,
            checkpoint,
            result=result,
            elapsed_ms=elapsed_ms,
            now=self.now_factory(),
        )
        self._update_progress(
            job_status_id=job_status_id,
            current_index=checkpoint.query_index,
            total_queries=total_queries,
            query_name=query.name,
            message=(
                f"Completed realism audit query {checkpoint.query_index} "
                f"of {total_queries}: {query.name}."
            ),
        )
        self.session.commit()

    def _save_snapshot_from_checkpoints(
        self,
        *,
        job_status_id: int,
        query_lookup: Mapping[str, RealismAuditQuery],
        stage_row: JobStageProgress,
    ) -> Path:
        checkpoints = load_realism_audit_query_checkpoints(
            self.session,
            job_status_id=job_status_id,
        )
        missing = [row.query_name for row in checkpoints if row.status != "succeeded"]
        if missing:
            raise ValueError(
                "Cannot save realism audit snapshot; unfinished queries remain: "
                + ", ".join(missing)
            )
        results = tuple(
            _checkpoint_to_result(checkpoint, query_lookup)
            for checkpoint in checkpoints
        )
        generation_run_id = checkpoints[0].generation_run_id
        batch_id = checkpoints[0].batch_id
        batch_month = None
        if batch_id is not None:
            batch_month = self.session.scalar(
                select(MonthlyBatch.batch_month).where(MonthlyBatch.id == batch_id)
            )
        execution = RealismAuditExecution(
            generation_run_id=generation_run_id,
            batch_id=batch_id,
            batch_month=batch_month,
            executed_at=self.now_factory().replace(tzinfo=UTC),
            results=results,
        )
        return save_realism_audit_snapshot(
            execution,
            snapshot_dir=self.snapshot_dir,
            assessment_thresholds=_assessment_thresholds(stage_row),
        )

    def _load_stage_row(self, job_status_id: int) -> JobStageProgress:
        stage_row = self.session.scalar(
            select(JobStageProgress)
            .where(JobStageProgress.job_status_id == job_status_id)
            .order_by(JobStageProgress.stage_sequence.asc(), JobStageProgress.id.asc())
            .limit(1)
        )
        if stage_row is None:
            raise ValueError(f"Realism audit stage row for job {job_status_id} was not found.")
        return stage_row

    def _reset_interrupted_checkpoints(
        self,
        checkpoints: tuple[RealismAuditQueryRun, ...],
    ) -> None:
        for checkpoint in checkpoints:
            if checkpoint.status == "running":
                checkpoint.status = "pending"
                checkpoint.completed_at = None
                checkpoint.error_message = "Retrying after interrupted execution."
        self.session.flush()

    def _mark_job_running(
        self,
        *,
        job_status: JobStatus,
        stage_row: JobStageProgress,
        started_at: datetime,
        total_queries: int,
    ) -> None:
        completed_count = self._completed_query_count(job_status.id)
        progress_percent = _progress_percent(completed_count, total_queries)
        job_status.status = "running"
        job_status.current_phase = "running"
        job_status.started_at = job_status.started_at or started_at
        job_status.percent_complete = progress_percent
        job_status.current_message = (
            f"Running realism audit query {completed_count} of {total_queries}."
        )
        stage_row.status = "running"
        stage_row.started_at = stage_row.started_at or started_at
        stage_row.last_heartbeat_at = started_at
        stage_row.progress_current = completed_count
        stage_row.progress_total = total_queries
        stage_row.progress_unit = "query"
        stage_row.progress_percent = progress_percent
        stage_row.progress_message = job_status.current_message
        self.session.flush()

    def _update_progress(
        self,
        *,
        job_status_id: int,
        current_index: int,
        total_queries: int,
        query_name: str,
        message: str,
    ) -> None:
        heartbeat_at = self.now_factory()
        job_status = self.session.get(JobStatus, job_status_id)
        stage_row = self._load_stage_row(job_status_id)
        if job_status is None:
            raise ValueError(f"Realism audit job {job_status_id} disappeared.")
        progress_percent = _progress_percent(current_index, total_queries)
        job_status.status = "running"
        job_status.current_phase = query_name
        job_status.percent_complete = progress_percent
        job_status.current_message = message
        stage_row.status = "running"
        stage_row.last_heartbeat_at = heartbeat_at
        stage_row.progress_current = current_index
        stage_row.progress_total = total_queries
        stage_row.progress_unit = "query"
        stage_row.progress_percent = progress_percent
        stage_row.progress_message = message
        self.session.flush()

    def _mark_job_succeeded(self, job_status_id: int, *, total_queries: int) -> None:
        completed_at = self.now_factory()
        job_status = self.session.get(JobStatus, job_status_id)
        stage_row = self._load_stage_row(job_status_id)
        if job_status is None:
            raise ValueError(f"Realism audit job {job_status_id} disappeared.")
        stage_row.status = "succeeded"
        stage_row.completed_at = completed_at
        stage_row.last_heartbeat_at = completed_at
        stage_row.progress_current = total_queries
        stage_row.progress_total = total_queries
        stage_row.progress_percent = Decimal("100.00")
        stage_row.progress_message = "Release certification completed successfully."
        job_status.status = "succeeded"
        job_status.current_phase = "completed"
        job_status.completed_at = completed_at
        job_status.percent_complete = Decimal("100.00")
        job_status.current_message = "Release certification completed successfully."
        self.session.flush()

    def _mark_job_failed(
        self,
        *,
        job_status_id: int,
        error_message: str,
        worker_id: str | None,
    ) -> None:
        failed_at = self.now_factory()
        job_status = self.session.get(JobStatus, job_status_id)
        stage_row = self._load_stage_row(job_status_id)
        failed_checkpoint = self.session.scalar(
            select(RealismAuditQueryRun)
            .where(
                RealismAuditQueryRun.job_status_id == job_status_id,
                RealismAuditQueryRun.status == "failed",
            )
            .order_by(RealismAuditQueryRun.query_index.asc())
            .limit(1)
        )
        failed_query_name = failed_checkpoint.query_name if failed_checkpoint else None
        message = (
            f"Release certification failed at query {failed_query_name}: {error_message}"
            if failed_query_name
            else f"Release certification failed: {error_message}"
        )
        if stage_row is not None:
            stage_row.status = "failed"
            stage_row.completed_at = failed_at
            stage_row.last_heartbeat_at = failed_at
            stage_row.error_message = message
            stage_row.progress_message = message
        if job_status is not None:
            job_status.status = "failed"
            job_status.current_phase = failed_query_name or "failed"
            job_status.completed_at = failed_at
            job_status.error_message = message
            job_status.current_message = message
        write_job_event(
            self.session,
            job_status_id=job_status_id,
            event_type="query_failed",
            worker_id=worker_id,
            message=message,
            metadata={"query_name": failed_query_name},
            now=failed_at,
        )
        self.session.flush()

    def _completed_query_count(self, job_status_id: int) -> int:
        return sum(
            1
            for checkpoint in load_realism_audit_query_checkpoints(
                self.session,
                job_status_id=job_status_id,
            )
            if checkpoint.status == "succeeded"
        )


def _checkpoint_to_result(
    checkpoint: RealismAuditQueryRun,
    query_lookup: Mapping[str, RealismAuditQuery],
) -> RealismAuditResult:
    query = query_lookup.get(checkpoint.query_name)
    if query is None:
        raise ValueError(f"Checkpoint references unknown query {checkpoint.query_name!r}.")
    payload = checkpoint.result_json
    if not isinstance(payload, dict):
        raise ValueError(f"Checkpoint {checkpoint.query_name!r} has no result payload.")
    rows = payload.get("rows") or ()
    return RealismAuditResult(
        query=query,
        rows=tuple(dict(row) for row in rows if isinstance(row, dict)),
    )


def _assessment_thresholds(stage_row: JobStageProgress) -> dict[str, float]:
    metadata = stage_row.metadata_json if isinstance(stage_row.metadata_json, dict) else {}
    return normalize_realism_audit_assessment_thresholds(
        metadata.get("assessment_thresholds")
    )


def _progress_percent(current_index: int, total_queries: int) -> Decimal:
    if total_queries <= 0:
        return Decimal("0.00")
    return (
        Decimal(current_index) * Decimal("100.00") / Decimal(total_queries)
    ).quantize(Decimal("0.01"))
