"""Operator-facing generation run orchestration service."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
import logging
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import ConfigurationLifecycleService, SimulationSettings, load_settings
from app.db.session import SessionLocal, session_scope
from app.models import (
    ConfigurationProfileVersion,
    GenerationRun,
    JobStageProgress,
    JobStatus,
    MonthlyBatch,
)

from .control_plane import GenerationControlPlane
from .destructive_reset import (
    DELETE_MODELS_IN_ORDER,
    ResetProgressEvent,
    reset_progress_message,
    reset_progress_metadata,
    reset_generated_data,
)
from .job_lifecycle import (
    DEFAULT_JOB_STALE_AFTER,
    job_is_actively_processing,
    overall_percent_complete,
    utc_now,
)
from .progress_liveness import DEFAULT_STAGE_QUIET_AFTER
from .monthly_pipeline import (
    MonthlyGenerationPipeline,
    MultiMonthPipelineResult,
    PIPELINE_STEPS,
    PipelineProgressEvent,
)


logger = logging.getLogger("uvicorn.error")


@dataclass(frozen=True)
class GenerationRunLaunchResult:
    """Outcome of launching a full destructive generation run."""

    configuration_version: ConfigurationProfileVersion
    generation_run: GenerationRun
    job_status: JobStatus
    monthly_batches: tuple[MonthlyBatch, ...]
    pipeline_result: MultiMonthPipelineResult


@dataclass(frozen=True)
class GenerationRunRegistration:
    """Pending generation run created before background execution starts."""

    configuration_version: ConfigurationProfileVersion
    generation_run: GenerationRun
    job_status: JobStatus


class GenerationRunService:
    """Core service for launching operator-facing generation runs."""

    def __init__(
        self,
        *,
        settings: SimulationSettings | None = None,
        configuration_lifecycle: ConfigurationLifecycleService | None = None,
        control_plane: GenerationControlPlane | None = None,
        pipeline: MonthlyGenerationPipeline | None = None,
    ) -> None:
        self.settings = settings or load_settings()
        self.configuration_lifecycle = (
            configuration_lifecycle or ConfigurationLifecycleService()
        )
        self.control_plane = control_plane or GenerationControlPlane(self.settings)
        self.pipeline = pipeline or MonthlyGenerationPipeline(
            control_plane=self.control_plane
        )

    def register_generation_run(
        self,
        generation_name: str,
        *,
        session: Session | None = None,
    ) -> GenerationRunRegistration:
        """Create a pending generation run and job before background execution."""
        if session is not None:
            return self._register_generation_run(generation_name, session=session)

        with session_scope() as active_session:
            return self._register_generation_run(generation_name, session=active_session)

    def execute_registered_generation_run(
        self,
        *,
        config_version_id: int,
        generation_run_id: int,
        job_status_id: int,
        session: Session | None = None,
    ) -> GenerationRunLaunchResult:
        """Run a previously registered generation job."""
        if session is not None:
            return self._execute_registered_generation_run(
                config_version_id=config_version_id,
                generation_run_id=generation_run_id,
                job_status_id=job_status_id,
                session=session,
            )

        with session_scope() as active_session:
            return self._execute_registered_generation_run(
                config_version_id=config_version_id,
                generation_run_id=generation_run_id,
                job_status_id=job_status_id,
                session=active_session,
            )

    def execute_registered_generation_run_in_background(
        self,
        *,
        config_version_id: int,
        generation_run_id: int,
        job_status_id: int,
    ) -> None:
        """Run a previously registered generation job with durable background commits."""
        logger.info(
            "Starting background generation job config_version_id=%s generation_run_id=%s job_status_id=%s",
            config_version_id,
            generation_run_id,
            job_status_id,
        )
        session = SessionLocal()
        try:
            self._execute_registered_generation_run(
                config_version_id=config_version_id,
                generation_run_id=generation_run_id,
                job_status_id=job_status_id,
                session=session,
                checkpoint=session.commit,
                re_raise=False,
            )
            session.commit()
            logger.info(
                "Completed background generation job config_version_id=%s generation_run_id=%s job_status_id=%s",
                config_version_id,
                generation_run_id,
                job_status_id,
            )
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def launch_generation_run(
        self,
        generation_name: str,
        *,
        session: Session | None = None,
    ) -> GenerationRunLaunchResult:
        """Launch a full destructive generation run from the current valid config."""
        if session is not None:
            registration = self._register_generation_run(generation_name, session=session)
            return self._execute_registered_generation_run(
                config_version_id=registration.configuration_version.id,
                generation_run_id=registration.generation_run.id,
                job_status_id=registration.job_status.id,
                session=session,
            )

        with session_scope() as active_session:
            registration = self._register_generation_run(
                generation_name,
                session=active_session,
            )
            return self._execute_registered_generation_run(
                config_version_id=registration.configuration_version.id,
                generation_run_id=registration.generation_run.id,
                job_status_id=registration.job_status.id,
                session=active_session,
            )

    def _register_generation_run(
        self,
        generation_name: str,
        *,
        session: Session,
    ) -> GenerationRunRegistration:
        config_version = self._resolve_single_valid_config(session)
        validation = self.configuration_lifecycle.validate_working_copy(
            config_version.config_payload,
            profile_name=config_version.profile.profile_name,
            profile_version=config_version.version_number,
        )
        if not validation.is_valid or validation.settings is None:
            raise ValueError(
                "Current valid configuration payload failed validation: "
                + "; ".join(validation.errors)
            )
        self._ensure_no_active_generation_job(session)

        parameter_snapshot = validation.normalized_payload
        generation_run = self.control_plane.create_generation_run(
            generation_name,
            seed_value=validation.settings.default_seed_value,
            parameter_snapshot=parameter_snapshot,
            settings=validation.settings,
            session=session,
        )
        job_status = self._create_job_status(session, generation_run)
        self._create_setup_stage_row(
            session,
            job_status=job_status,
            generation_run=generation_run,
        )
        self.configuration_lifecycle.mark_version_used(
            session,
            version_id=config_version.id,
        )
        session.flush()
        return GenerationRunRegistration(
            configuration_version=config_version,
            generation_run=generation_run,
            job_status=job_status,
        )

    def _execute_registered_generation_run(
        self,
        *,
        config_version_id: int,
        generation_run_id: int,
        job_status_id: int,
        session: Session,
        checkpoint: Any | None = None,
        re_raise: bool = True,
    ) -> GenerationRunLaunchResult:
        config_version = session.get(ConfigurationProfileVersion, config_version_id)
        if config_version is None:
            raise ValueError(f"Configuration profile version {config_version_id} does not exist.")
        generation_run = session.get(GenerationRun, generation_run_id)
        if generation_run is None:
            raise ValueError(f"Generation run {generation_run_id} does not exist.")
        job_status = session.get(JobStatus, job_status_id)
        if job_status is None:
            raise ValueError(f"Job status {job_status_id} does not exist.")
        if job_status.status != "pending":
            raise ValueError(
                f"Generation job {job_status.job_id} is already {job_status.status}; "
                "background execution requires a pending job."
            )
        if generation_run.status != "not_started":
            raise ValueError(
                f"Generation run {generation_run.id} is already {generation_run.status}; "
                "background execution requires a not_started run."
            )

        validation = self.configuration_lifecycle.validate_working_copy(
            generation_run.parameter_snapshot or {},
            profile_name=config_version.profile.profile_name,
            profile_version=config_version.version_number,
        )
        if not validation.is_valid or validation.settings is None:
            raise ValueError(
                "Registered generation configuration payload failed validation: "
                + "; ".join(validation.errors)
            )

        first_batch_month = _parse_first_batch_month(validation.normalized_payload)
        month_count = _parse_month_count(validation.normalized_payload)

        try:
            self.control_plane.start_generation_run(generation_run.id, session=session)
            self._set_job_status(
                job_status,
                status="running",
                phase="destructive_reset",
                message="Resetting generated data from previous runs.",
                started=True,
            )
            self._mark_setup_stage_running(
                session,
                job_status_id=job_status.id,
            )
            self._checkpoint(session, checkpoint)
            self._perform_destructive_reset(
                session,
                job_status=job_status,
                preserve_job_status_id=job_status.id,
                checkpoint=checkpoint,
            )
            self._mark_setup_stage_succeeded(
                session,
                job_status_id=job_status.id,
            )

            monthly_batches = self._create_monthly_batches(
                session,
                generation_run_id=generation_run.id,
                first_batch_month=first_batch_month,
                month_count=month_count,
            )
            self._seed_stage_progress(
                session,
                job_status=job_status,
                generation_run=generation_run,
                monthly_batches=monthly_batches,
            )
            self._set_job_status(
                job_status,
                status="running",
                phase="generation_pipeline",
                message="Running monthly generation pipeline.",
                percent_complete=self._overall_percent_complete(session, job_status.id),
            )
            self._checkpoint(session, checkpoint)

            pipeline_result = self.pipeline.run_months(
                generation_run_id=generation_run.id,
                months=month_count,
                skip_existing=True,
                progress_listener=lambda event: self._record_progress_event(
                    session,
                    job_status=job_status,
                    event=event,
                    checkpoint=checkpoint,
                ),
                session=session,
            )

            self.control_plane.complete_generation_run(
                generation_run.id,
                session=session,
            )
            self._set_job_status(
                job_status,
                status="succeeded",
                phase="completed",
                message="Generation run completed successfully.",
                percent_complete=Decimal("100.00"),
                completed=True,
            )
            self._checkpoint(session, checkpoint)
            return GenerationRunLaunchResult(
                configuration_version=config_version,
                generation_run=generation_run,
                job_status=job_status,
                monthly_batches=tuple(monthly_batches),
                pipeline_result=pipeline_result,
            )
        except Exception as exc:
            self._fail_incomplete_stages(session, job_status.id)
            self.control_plane.fail_generation_run(generation_run.id, session=session)
            self._set_job_status(
                job_status,
                status="failed",
                phase="failed",
                message=str(exc),
                completed=True,
            )
            self._checkpoint(session, checkpoint)
            if re_raise:
                raise
            monthly_batches = list(
                session.scalars(
                    select(MonthlyBatch)
                    .where(MonthlyBatch.generation_run_id == generation_run.id)
                    .order_by(MonthlyBatch.batch_sequence.asc(), MonthlyBatch.id.asc())
                )
            )
            return GenerationRunLaunchResult(
                configuration_version=config_version,
                generation_run=generation_run,
                job_status=job_status,
                monthly_batches=tuple(monthly_batches),
                pipeline_result=MultiMonthPipelineResult(
                    generation_run_id=generation_run.id,
                    months_requested=0,
                    batch_results=(),
                ),
            )

    def _resolve_single_valid_config(self, session: Session) -> ConfigurationProfileVersion:
        valid_versions = list(
            session.scalars(
                select(ConfigurationProfileVersion)
                .where(ConfigurationProfileVersion.lifecycle_status == "valid")
                .order_by(ConfigurationProfileVersion.id)
            )
        )
        if len(valid_versions) != 1:
            raise ValueError(
                "Expected exactly one valid configuration version before launch; "
                f"found {len(valid_versions)}."
            )
        return valid_versions[0]

    def _ensure_no_active_generation_job(self, session: Session) -> None:
        candidate_jobs = list(
            session.scalars(
                select(JobStatus)
                .where(
                    JobStatus.job_type == "generation_run",
                    JobStatus.status.in_(("pending", "running")),
                )
                .order_by(JobStatus.id.desc())
            )
        )
        active_job = next(
            (
                job
                for job in candidate_jobs
                if job_is_actively_processing(session, job)
            ),
            None,
        )
        if active_job is not None:
            raise ValueError(
                f"Generation job {active_job.job_id} is already {active_job.status}; "
                "concurrent runs are blocked."
            )

        candidate_runs = list(
            session.scalars(
                select(GenerationRun).where(
                    GenerationRun.status.in_(("not_started", "running"))
                )
            )
        )
        for active_run in candidate_runs:
            run_job = self._get_job_for_generation_run(
                session,
                generation_run_id=active_run.id,
            )
            if job_is_actively_processing(session, run_job):
                raise ValueError(
                    f"Generation run {active_run.id} is already {active_run.status}; "
                    "concurrent runs are blocked."
                )
            if run_job is None and _record_is_recent(
                active_run.started_at or active_run.created_at
            ):
                raise ValueError(
                    f"Generation run {active_run.id} is already {active_run.status}; "
                    "concurrent runs are blocked."
                )

    def _get_job_for_generation_run(
        self,
        session: Session,
        *,
        generation_run_id: int,
    ) -> JobStatus | None:
        job_ids_for_run = (
            select(JobStageProgress.job_status_id)
            .where(JobStageProgress.generation_run_id == generation_run_id)
            .distinct()
        )
        return session.scalar(
            select(JobStatus)
            .where(JobStatus.id.in_(job_ids_for_run))
            .order_by(JobStatus.id.desc())
            .limit(1)
        )

    def _perform_destructive_reset(
        self,
        session: Session,
        *,
        job_status: JobStatus,
        preserve_job_status_id: int,
        checkpoint: Any | None = None,
    ) -> None:
        stage_row = self._get_stage_row(
            session,
            job_status_id=job_status.id,
            batch_id=None,
            stage_name="destructive_reset",
        )

        def progress_listener(event: ResetProgressEvent) -> None:
            if event.status == "running":
                progress_current = max(event.step_index - 1, 0)
            else:
                progress_current = event.step_index
            progress_message = reset_progress_message(event)
            stage_row.status = "running"
            stage_row.started_at = stage_row.started_at or _utc_now()
            stage_row.last_heartbeat_at = _utc_now()
            stage_row.progress_current = progress_current
            stage_row.progress_total = event.total_steps
            stage_row.progress_percent = _percent(progress_current, event.total_steps)
            stage_row.progress_message = progress_message
            stage_row.metadata_json = reset_progress_metadata(
                event,
                progress_current=progress_current,
            )
            self._set_job_status(
                job_status,
                status="running",
                phase="destructive_reset",
                message=progress_message,
                percent_complete=self._overall_percent_complete(session, job_status.id),
            )
            self._checkpoint(session, checkpoint)

        reset_generated_data(
            session=session,
            preserve_job_status_id=preserve_job_status_id,
            progress_listener=progress_listener,
        )

    def _create_monthly_batches(
        self,
        session: Session,
        *,
        generation_run_id: int,
        first_batch_month: date,
        month_count: int,
    ) -> list[MonthlyBatch]:
        batches = [
            self.control_plane.get_or_create_monthly_batch(
                generation_run_id,
                _add_months(first_batch_month, offset),
                batch_sequence=offset + 1,
                batch_type="historical_initial",
                session=session,
            )
            for offset in range(month_count)
        ]
        session.flush()
        return batches

    def _create_job_status(
        self,
        session: Session,
        generation_run: GenerationRun,
    ) -> JobStatus:
        job = JobStatus(
            job_type="generation_run",
            job_id=f"generation-run-{generation_run.id}-{uuid4().hex[:8]}",
            status="pending",
            current_phase="initialize",
            percent_complete=Decimal("0.00"),
            current_message="Queued generation run.",
        )
        session.add(job)
        session.flush()
        return job

    def _create_setup_stage_row(
        self,
        session: Session,
        *,
        job_status: JobStatus,
        generation_run: GenerationRun,
    ) -> None:
        session.add(
            JobStageProgress(
                job_status_id=job_status.id,
                generation_run_id=generation_run.id,
                batch_id=None,
                stage_name="destructive_reset",
                stage_sequence=0,
                status="pending",
                progress_current=0,
                progress_total=len(DELETE_MODELS_IN_ORDER),
                progress_unit="table",
                progress_percent=Decimal("0.00"),
                progress_message="Pending generated-data reset.",
            )
        )
        session.flush()

    def _mark_setup_stage_running(self, session: Session, *, job_status_id: int) -> None:
        stage_row = self._get_stage_row(
            session,
            job_status_id=job_status_id,
            batch_id=None,
            stage_name="destructive_reset",
        )
        now = _utc_now()
        stage_row.status = "running"
        stage_row.started_at = stage_row.started_at or now
        stage_row.last_heartbeat_at = now
        stage_row.progress_message = "Resetting generated data from previous runs."
        stage_row.progress_current = 0
        stage_row.progress_total = len(DELETE_MODELS_IN_ORDER)
        stage_row.progress_percent = Decimal("0.00")
        session.flush()

    def _mark_setup_stage_succeeded(self, session: Session, *, job_status_id: int) -> None:
        stage_row = self._get_stage_row(
            session,
            job_status_id=job_status_id,
            batch_id=None,
            stage_name="destructive_reset",
        )
        now = _utc_now()
        stage_row.status = "succeeded"
        stage_row.completed_at = now
        stage_row.last_heartbeat_at = now
        stage_row.progress_message = "Generated data reset completed."
        stage_row.progress_current = len(DELETE_MODELS_IN_ORDER)
        stage_row.progress_total = len(DELETE_MODELS_IN_ORDER)
        stage_row.progress_percent = Decimal("100.00")
        session.flush()

    def _seed_stage_progress(
        self,
        session: Session,
        *,
        job_status: JobStatus,
        generation_run: GenerationRun,
        monthly_batches: list[MonthlyBatch],
    ) -> None:
        for batch in monthly_batches:
            for index, step in enumerate(PIPELINE_STEPS, start=1):
                session.add(
                    JobStageProgress(
                        job_status_id=job_status.id,
                        generation_run_id=generation_run.id,
                        batch_id=batch.id,
                        stage_name=step,
                        stage_sequence=index,
                        status="pending",
                        progress_current=0,
                        progress_total=1,
                        progress_unit="stage",
                        progress_percent=Decimal("0.00"),
                        progress_message="Pending execution.",
                    )
                )
        session.flush()

    def _record_progress_event(
        self,
        session: Session,
        *,
        job_status: JobStatus,
        event: PipelineProgressEvent,
        checkpoint: Any | None = None,
    ) -> None:
        stage_row = self._get_stage_row(
            session,
            job_status_id=job_status.id,
            batch_id=event.batch_id,
            stage_name=event.step,
        )

        stage_row.status = event.status
        stage_row.progress_message = _format_progress_message(event)
        stage_row.metadata_json = _progress_metadata(event)
        stage_row.last_heartbeat_at = _utc_now()
        if event.status == "running":
            stage_row.started_at = stage_row.started_at or _utc_now()
            progress_current = event.progress_current or 0
            progress_total = event.progress_total or stage_row.progress_total or 1
            stage_row.progress_current = progress_current
            stage_row.progress_total = progress_total
            stage_row.progress_unit = event.progress_unit or stage_row.progress_unit or "stage"
            stage_row.progress_percent = _percent(progress_current, progress_total)
            self._set_job_status(
                job_status,
                status="running",
                phase=event.step,
                message=f"{event.batch_month}: {stage_row.progress_message}",
                percent_complete=self._overall_percent_complete(session, job_status.id),
            )
        elif event.status == "succeeded":
            stage_row.started_at = stage_row.started_at or _utc_now()
            stage_row.completed_at = _utc_now()
            progress_total = event.progress_total or stage_row.progress_total or 1
            stage_row.progress_current = event.progress_current or progress_total
            stage_row.progress_total = progress_total
            stage_row.progress_unit = event.progress_unit or stage_row.progress_unit or "stage"
            stage_row.progress_percent = Decimal("100.00")
            self._set_job_status(
                job_status,
                status="running",
                phase=event.step,
                message=f"{event.batch_month}: {stage_row.progress_message}",
                percent_complete=self._overall_percent_complete(session, job_status.id),
            )
        elif event.status == "failed":
            stage_row.started_at = stage_row.started_at or _utc_now()
            stage_row.completed_at = _utc_now()
            stage_row.error_message = str(event.details.get("error_message", "Stage failed."))
            stage_row.progress_percent = Decimal("0.00")
            self._set_job_status(
                job_status,
                status="running",
                phase=event.step,
                message=f"{event.batch_month}: {stage_row.error_message}",
                percent_complete=self._overall_percent_complete(session, job_status.id),
            )
        self._checkpoint(session, checkpoint)

    @staticmethod
    def _checkpoint(session: Session, checkpoint: Any | None) -> None:
        session.flush()
        if checkpoint is not None:
            checkpoint()

    def _get_stage_row(
        self,
        session: Session,
        *,
        job_status_id: int,
        batch_id: int | None,
        stage_name: str,
    ) -> JobStageProgress:
        statement = select(JobStageProgress).where(
            JobStageProgress.job_status_id == job_status_id,
            JobStageProgress.stage_name == stage_name,
        )
        if batch_id is None:
            statement = statement.where(JobStageProgress.batch_id.is_(None))
        else:
            statement = statement.where(JobStageProgress.batch_id == batch_id)
        stage_row = session.scalar(statement)
        if stage_row is None:
            raise ValueError(
                f"Missing job_stage_progress row for job={job_status_id}, "
                f"batch={batch_id}, step={stage_name}."
            )
        return stage_row

    def _fail_incomplete_stages(self, session: Session, job_status_id: int) -> None:
        rows = list(
            session.scalars(
                select(JobStageProgress).where(
                    JobStageProgress.job_status_id == job_status_id
                )
            )
        )
        for row in rows:
            if row.status in {"succeeded", "failed"}:
                continue
            row.status = "failed"
            row.completed_at = _utc_now()
            row.last_heartbeat_at = _utc_now()
            row.error_message = row.error_message or "Stage failed."
            row.progress_percent = Decimal("0.00")
        session.flush()

    def _overall_percent_complete(self, session: Session, job_status_id: int) -> Decimal:
        return overall_percent_complete(session, job_status_id)

    def _set_job_status(
        self,
        job_status: JobStatus,
        *,
        status: str,
        phase: str,
        message: str,
        percent_complete: Decimal | None = None,
        started: bool = False,
        completed: bool = False,
    ) -> None:
        job_status.status = status
        job_status.current_phase = phase
        job_status.current_message = message
        if percent_complete is not None:
            job_status.percent_complete = percent_complete
        if started and job_status.started_at is None:
            job_status.started_at = _utc_now()
        if completed:
            job_status.completed_at = _utc_now()


def _parse_first_batch_month(payload: dict[str, Any]) -> date:
    raw_value = payload["simulation"]["first_batch_month"]
    if isinstance(raw_value, date):
        return date(raw_value.year, raw_value.month, 1)
    if not isinstance(raw_value, str):
        raise ValueError("simulation.first_batch_month must be an ISO date string.")
    parsed = date.fromisoformat(raw_value)
    return date(parsed.year, parsed.month, 1)


def _parse_month_count(payload: dict[str, Any]) -> int:
    raw_value = payload["simulation"]["historical_batch_count"]
    if isinstance(raw_value, bool) or not isinstance(raw_value, int):
        raise ValueError("simulation.historical_batch_count must be an integer.")
    if raw_value < 1:
        raise ValueError("simulation.historical_batch_count must be at least 1.")
    return raw_value


def _format_progress_message(event: PipelineProgressEvent) -> str:
    if event.message:
        return event.message
    if event.status == "running":
        return f"{event.step} running"
    if event.status == "failed":
        return str(event.details.get("error_message", f"{event.step} failed"))
    if not event.details:
        return f"{event.step} succeeded"
    detail_parts = ", ".join(
        f"{key}={value}" for key, value in sorted(event.details.items())
    )
    return f"{event.step} succeeded ({detail_parts})"


def _progress_metadata(event: PipelineProgressEvent) -> dict[str, Any] | None:
    metadata = dict(event.details)
    quiet_after = (
        event.heartbeat_quiet_after_seconds
        if event.heartbeat_quiet_after_seconds is not None
        else int(DEFAULT_STAGE_QUIET_AFTER.total_seconds())
    )
    metadata["heartbeat_quiet_after_seconds"] = quiet_after
    if event.heartbeat_likely_stalled_after_seconds is not None:
        metadata["heartbeat_likely_stalled_after_seconds"] = (
            event.heartbeat_likely_stalled_after_seconds
        )
    if event.progress_current is not None:
        metadata["progress_current"] = event.progress_current
    if event.progress_total is not None:
        metadata["progress_total"] = event.progress_total
    if event.progress_unit is not None:
        metadata["progress_unit"] = event.progress_unit
    return metadata or None


def _percent(current: int, total: int) -> Decimal:
    if total <= 0:
        return Decimal("0.00")
    return (Decimal(current) / Decimal(total) * Decimal("100")).quantize(
        Decimal("0.01")
    )


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _record_is_recent(value: datetime | None) -> bool:
    if value is None:
        return True
    return (utc_now() - value) <= DEFAULT_JOB_STALE_AFTER


def _add_months(value: date, months: int) -> date:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    return date(year, month, 1)
