"""Read-side query models for the operator control panel."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
import json
from typing import Callable

from sqlalchemy import case, select
from sqlalchemy.orm import Session

from app.models import (
    ConfigurationProfileVersion,
    GenerationRun,
    JobStageProgress,
    JobStatus,
    MonthlyBatch,
)


DEFAULT_STALE_AFTER = timedelta(minutes=15)


@dataclass(frozen=True)
class ConfigSummary:
    """UI-ready current valid configuration summary."""

    version_id: int
    profile_id: int
    profile_name: str
    version_number: int
    title: str
    config_hash: str | None
    created_at: datetime | None
    last_used_at: datetime | None
    simulation_name: str | None
    simulation_version: str | None
    first_batch_month: date | None
    historical_batch_count: int | None


@dataclass(frozen=True)
class StageProgressSummary:
    """UI-ready per-stage progress row."""

    stage_name: str
    stage_sequence: int | None
    status: str
    progress_current: int
    progress_total: int | None
    progress_percent: Decimal | None
    progress_unit: str | None
    progress_message: str | None
    last_heartbeat_at: datetime | None
    started_at: datetime | None
    completed_at: datetime | None
    error_message: str | None
    is_stale: bool


@dataclass(frozen=True)
class BatchSummary:
    """UI-ready monthly batch summary with stage rows attached."""

    batch_id: int
    batch_month: date
    batch_sequence: int
    batch_type: str
    processing_status: str
    started_at: datetime | None
    completed_at: datetime | None
    error_message: str | None
    stage_progress: tuple[StageProgressSummary, ...]


@dataclass(frozen=True)
class JobSummary:
    """UI-ready job status summary."""

    job_status_id: int
    job_type: str
    job_id: str
    status: str
    current_phase: str | None
    percent_complete: Decimal | None
    current_message: str | None
    started_at: datetime | None
    completed_at: datetime | None
    error_message: str | None


@dataclass(frozen=True)
class GenerationRunSummary:
    """UI-ready generation run summary."""

    generation_run_id: int
    generation_name: str
    status: str
    seed_value: int
    simulation_version: str | None
    started_at: datetime | None
    completed_at: datetime | None
    batch_count: int
    pending_batch_count: int
    running_batch_count: int
    succeeded_batch_count: int
    failed_batch_count: int
    overall_progress_percent: Decimal | None


@dataclass(frozen=True)
class AllowedActions:
    """Current operator actions and the blockers that disable them."""

    can_edit_config: bool
    can_start_generation_run: bool
    can_generate_student_dataset: bool
    start_generation_blockers: tuple[str, ...]
    student_dataset_blockers: tuple[str, ...]


@dataclass(frozen=True)
class ConfigEditorState:
    """Transient config editor state for validation and save workflows."""

    title: str
    notes: str
    payload_json: str
    validation_passed: bool
    validation_errors: tuple[str, ...]
    validation_hash: str | None
    status_message: str | None
    change_count: int | None


@dataclass(frozen=True)
class ControlPanelSnapshot:
    """Full read-model snapshot for the control panel landing page."""

    config_summary: ConfigSummary | None
    generation_run_summary: GenerationRunSummary | None
    batch_summaries: tuple[BatchSummary, ...]
    active_job_summary: JobSummary | None
    allowed_actions: AllowedActions
    warnings: tuple[str, ...]


class ControlPanelQueries:
    """Assemble transient read models for the operator control panel."""

    def __init__(
        self,
        *,
        stale_after: timedelta = DEFAULT_STALE_AFTER,
        now_fn: Callable[[], datetime] | None = None,
    ) -> None:
        self.stale_after = stale_after
        self.now_fn = now_fn or _utc_now

    def get_control_panel_snapshot(self, session: Session) -> ControlPanelSnapshot:
        config_summary, config_warning = self._get_current_valid_config_summary(session)
        generation_run = self.get_active_generation_run(session) or self.get_latest_generation_run(session)
        run_summary = None
        batch_summaries: tuple[BatchSummary, ...] = ()
        active_job = None
        warnings: list[str] = []

        if config_warning is not None:
            warnings.append(config_warning)

        if generation_run is not None:
            active_job = self.get_job_for_generation_run(
                session,
                generation_run_id=generation_run.id,
            )
            batch_summaries = self.get_generation_run_batches(
                session,
                generation_run_id=generation_run.id,
            )
            run_summary = self._build_generation_run_summary(
                generation_run,
                batch_summaries=batch_summaries,
                active_job=active_job,
            )
            warnings.extend(self._derive_run_warnings(generation_run, batch_summaries, active_job))

        allowed_actions = self._build_allowed_actions(
            config_summary=config_summary,
            generation_run=generation_run,
            batch_summaries=batch_summaries,
            active_job=active_job,
        )
        return ControlPanelSnapshot(
            config_summary=config_summary,
            generation_run_summary=run_summary,
            batch_summaries=batch_summaries,
            active_job_summary=active_job,
            allowed_actions=allowed_actions,
            warnings=tuple(warnings),
        )

    def get_active_generation_run(self, session: Session) -> GenerationRun | None:
        return session.scalar(
            select(GenerationRun)
            .where(GenerationRun.status == "running")
            .order_by(GenerationRun.started_at.desc(), GenerationRun.id.desc())
            .limit(1)
        )

    def get_latest_generation_run(self, session: Session) -> GenerationRun | None:
        return session.scalar(
            select(GenerationRun)
            .order_by(
                GenerationRun.created_at.desc(),
                GenerationRun.id.desc(),
            )
            .limit(1)
        )

    def get_job_for_generation_run(
        self,
        session: Session,
        *,
        generation_run_id: int,
    ) -> JobSummary | None:
        statement = (
            select(JobStatus)
            .join(JobStageProgress, JobStageProgress.job_status_id == JobStatus.id)
            .where(JobStageProgress.generation_run_id == generation_run_id)
            .distinct()
            .order_by(
                case((JobStatus.status == "running", 0), else_=1),
                JobStatus.started_at.desc(),
                JobStatus.created_at.desc(),
                JobStatus.id.desc(),
            )
            .limit(1)
        )
        job = session.scalar(statement)
        if job is None:
            return None
        return JobSummary(
            job_status_id=job.id,
            job_type=job.job_type,
            job_id=job.job_id,
            status=job.status,
            current_phase=job.current_phase,
            percent_complete=job.percent_complete,
            current_message=job.current_message,
            started_at=job.started_at,
            completed_at=job.completed_at,
            error_message=job.error_message,
        )

    def get_generation_run_batches(
        self,
        session: Session,
        *,
        generation_run_id: int,
    ) -> tuple[BatchSummary, ...]:
        batches = list(
            session.scalars(
                select(MonthlyBatch)
                .where(MonthlyBatch.generation_run_id == generation_run_id)
                .order_by(MonthlyBatch.batch_sequence.asc(), MonthlyBatch.batch_month.asc())
            )
        )
        if not batches:
            return ()

        progress_rows = list(
            session.scalars(
                select(JobStageProgress)
                .where(JobStageProgress.generation_run_id == generation_run_id)
                .order_by(
                    JobStageProgress.batch_id.asc(),
                    JobStageProgress.stage_sequence.asc(),
                    JobStageProgress.id.asc(),
                )
            )
        )
        progress_by_batch: dict[int, list[StageProgressSummary]] = {}
        now = self.now_fn()
        for row in progress_rows:
            if row.batch_id is None:
                continue
            progress_by_batch.setdefault(row.batch_id, []).append(
                StageProgressSummary(
                    stage_name=row.stage_name,
                    stage_sequence=_coerce_int(row.stage_sequence),
                    status=row.status,
                    progress_current=_coerce_int(row.progress_current, default=0),
                    progress_total=_coerce_int(row.progress_total),
                    progress_percent=row.progress_percent,
                    progress_unit=row.progress_unit,
                    progress_message=row.progress_message,
                    last_heartbeat_at=row.last_heartbeat_at,
                    started_at=row.started_at,
                    completed_at=row.completed_at,
                    error_message=row.error_message,
                    is_stale=self._is_stale(
                        status=row.status,
                        last_heartbeat_at=row.last_heartbeat_at,
                        now=now,
                    ),
                )
            )

        return tuple(
            BatchSummary(
                batch_id=batch.id,
                batch_month=batch.batch_month,
                batch_sequence=batch.batch_sequence,
                batch_type=batch.batch_type,
                processing_status=batch.processing_status,
                started_at=batch.started_at,
                completed_at=batch.completed_at,
                error_message=batch.error_message,
                stage_progress=tuple(progress_by_batch.get(batch.id, [])),
            )
            for batch in batches
        )

    def _get_current_valid_config_summary(
        self,
        session: Session,
    ) -> tuple[ConfigSummary | None, str | None]:
        valid_versions = list(
            session.scalars(
                select(ConfigurationProfileVersion)
                .where(ConfigurationProfileVersion.lifecycle_status == "valid")
                .order_by(ConfigurationProfileVersion.id.asc())
            )
        )
        if not valid_versions:
            return None, "No valid configuration is available."
        if len(valid_versions) > 1:
            return None, (
                "Multiple valid configuration versions exist. Resolve configuration state before using the control panel."
            )

        version = valid_versions[0]
        payload = version.config_payload or {}
        simulation = payload.get("simulation", {})
        return (
            ConfigSummary(
                version_id=version.id,
                profile_id=version.profile_id,
                profile_name=version.profile.profile_name,
                version_number=version.version_number,
                title=version.title,
                config_hash=version.config_hash,
                created_at=version.created_at,
                last_used_at=version.last_used_at,
                simulation_name=_coerce_str(simulation.get("simulation_name")),
                simulation_version=_coerce_str(simulation.get("simulation_version")),
                first_batch_month=_coerce_date(simulation.get("first_batch_month")),
                historical_batch_count=_coerce_int(simulation.get("historical_batch_count")),
            ),
            None,
        )

    def _build_generation_run_summary(
        self,
        generation_run: GenerationRun,
        *,
        batch_summaries: tuple[BatchSummary, ...],
        active_job: JobSummary | None,
    ) -> GenerationRunSummary:
        counts = _count_batch_statuses(batch_summaries)
        return GenerationRunSummary(
            generation_run_id=generation_run.id,
            generation_name=generation_run.generation_name,
            status=generation_run.status,
            seed_value=generation_run.seed_value,
            simulation_version=generation_run.simulation_version,
            started_at=generation_run.started_at,
            completed_at=generation_run.completed_at,
            batch_count=len(batch_summaries),
            pending_batch_count=counts["pending"],
            running_batch_count=counts["running"],
            succeeded_batch_count=counts["succeeded"],
            failed_batch_count=counts["failed"],
            overall_progress_percent=active_job.percent_complete if active_job else None,
        )

    def _build_allowed_actions(
        self,
        *,
        config_summary: ConfigSummary | None,
        generation_run: GenerationRun | None,
        batch_summaries: tuple[BatchSummary, ...],
        active_job: JobSummary | None,
    ) -> AllowedActions:
        start_blockers: list[str] = []
        if config_summary is None:
            start_blockers.append("A single valid configuration is required.")
        if generation_run is not None and generation_run.status == "running":
            start_blockers.append("A generation run is already running.")
        if active_job is not None and active_job.status == "running":
            start_blockers.append("A generation job is still running.")

        student_blockers: list[str] = []
        if generation_run is None:
            student_blockers.append("No generation run exists yet.")
        elif generation_run.status != "succeeded":
            student_blockers.append("Student dataset generation requires a succeeded generation run.")
        if any(batch.processing_status != "succeeded" for batch in batch_summaries):
            student_blockers.append("All monthly batches must be succeeded before student dataset generation.")
        if active_job is not None and active_job.status == "running":
            student_blockers.append("No write-heavy job can be active during student dataset generation.")

        can_edit_config = generation_run is None or generation_run.status != "running"
        return AllowedActions(
            can_edit_config=can_edit_config,
            can_start_generation_run=not start_blockers,
            can_generate_student_dataset=not student_blockers,
            start_generation_blockers=tuple(start_blockers),
            student_dataset_blockers=tuple(student_blockers),
        )

    def get_config_editor_state(self, session: Session) -> ConfigEditorState:
        """Return a default editor state from the current valid configuration."""
        valid_versions = list(
            session.scalars(
                select(ConfigurationProfileVersion)
                .where(ConfigurationProfileVersion.lifecycle_status == "valid")
                .order_by(ConfigurationProfileVersion.id.asc())
            )
        )
        if len(valid_versions) != 1:
            return ConfigEditorState(
                title="",
                notes="",
                payload_json="{}",
                validation_passed=False,
                validation_errors=(
                    "A single valid configuration is required before editing.",
                ),
                validation_hash=None,
                status_message=None,
                change_count=None,
            )
        version = valid_versions[0]
        return ConfigEditorState(
            title="",
            notes=version.notes or "",
            payload_json=json.dumps(version.config_payload, indent=2, sort_keys=True),
            validation_passed=False,
            validation_errors=(),
            validation_hash=version.config_hash,
            status_message=None,
            change_count=0,
        )

    def _derive_run_warnings(
        self,
        generation_run: GenerationRun,
        batch_summaries: tuple[BatchSummary, ...],
        active_job: JobSummary | None,
    ) -> list[str]:
        warnings: list[str] = []
        if generation_run.status == "failed":
            warnings.append("The latest generation run failed and must be restarted from the beginning.")
        if any(batch.processing_status == "failed" for batch in batch_summaries):
            warnings.append("One or more monthly batches failed.")
        if any(
            stage.is_stale
            for batch in batch_summaries
            for stage in batch.stage_progress
        ):
            warnings.append("Progress heartbeat is stale for one or more running stages.")
        if active_job is not None and active_job.status == "failed":
            warnings.append("The most recent generation job failed.")
        return warnings

    def _is_stale(
        self,
        *,
        status: str,
        last_heartbeat_at: datetime | None,
        now: datetime,
    ) -> bool:
        if status != "running" or last_heartbeat_at is None:
            return False
        return (now - last_heartbeat_at) > self.stale_after


def _count_batch_statuses(batch_summaries: tuple[BatchSummary, ...]) -> dict[str, int]:
    counts = {"pending": 0, "running": 0, "succeeded": 0, "failed": 0}
    for batch in batch_summaries:
        counts[batch.processing_status] = counts.get(batch.processing_status, 0) + 1
    return counts


def _coerce_int(value: object, default: int | None = None) -> int | None:
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, int):
        return default
    return value


def _coerce_str(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _coerce_date(value: object) -> date | None:
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        return date.fromisoformat(value)
    return None


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)
