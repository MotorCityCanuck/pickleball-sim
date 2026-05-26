"""Read-side query models for the operator control panel."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
import json
from typing import Callable

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.core import ConfigValidationIssue
from app.models import (
    Club,
    ConfigurationProfileVersion,
    FirstName,
    GenerationRun,
    JobStageProgress,
    JobStatus,
    LastName,
    MonthlyBatch,
    RawSeedLoadRun,
    Region,
)


DEFAULT_STALE_AFTER = timedelta(minutes=15)
SEED_CONFIG_KEYS = (
    "raw_seed_data",
    "name_assignment",
    "regional",
    "club_generation",
)


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
    target_total_players: int | None
    seed_dataset_count: int


@dataclass(frozen=True)
class SeedLoadRunSummary:
    """UI-ready raw seed load run summary."""

    load_run_id: int
    dataset_type: str
    status: str
    rows_read: int
    rows_loaded: int
    rows_rejected: int
    started_at: datetime | None
    completed_at: datetime | None
    error_message: str | None


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
    created_at: datetime | None


@dataclass(frozen=True)
class SeedDataSummary:
    """UI-ready seed/reference data readiness summary."""

    is_ready: bool
    readiness_label: str
    readiness_blockers: tuple[str, ...]
    latest_seed_job: JobSummary | None
    latest_seed_job_is_active: bool
    latest_seed_stage_progress: tuple[StageProgressSummary, ...]
    latest_raw_loads: tuple[SeedLoadRunSummary, ...]
    regions_count: int
    clubs_count: int
    first_names_count: int
    last_names_count: int


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
    completion_message: str | None
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
class GenerationRunSummary:
    """UI-ready generation run summary."""

    generation_run_id: int
    job_status_id: int | None
    generation_name: str
    status: str
    display_status: str
    status_detail: str | None
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
    can_start_seed_refresh: bool
    can_start_generation_run: bool
    can_generate_student_dataset: bool
    seed_refresh_blockers: tuple[str, ...]
    start_generation_blockers: tuple[str, ...]
    student_dataset_blockers: tuple[str, ...]


@dataclass(frozen=True)
class ConfigEditorState:
    """Transient config editor state for validation and save workflows."""

    title: str
    notes: str
    working_payload_json: str
    seed_payload_json: str
    synthetic_payload_json: str
    validation_passed: bool
    validation_issues: tuple[ConfigValidationIssue, ...]
    validation_errors: tuple[str, ...]
    validation_hash: str | None
    status_message: str | None
    change_count: int | None


@dataclass(frozen=True)
class ControlPanelSnapshot:
    """Full read-model snapshot for the control panel landing page."""

    config_summary: ConfigSummary | None
    seed_data_summary: SeedDataSummary
    generation_run_summary: GenerationRunSummary | None
    batch_summaries: tuple[BatchSummary, ...]
    active_job_summary: JobSummary | None
    active_job_stage_progress: tuple[StageProgressSummary, ...]
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
        seed_summary = self.get_seed_data_summary(session)
        generation_run = self.get_active_generation_run(session)
        run_summary = None
        batch_summaries: tuple[BatchSummary, ...] = ()
        active_job = None
        active_job_stage_progress: tuple[StageProgressSummary, ...] = ()
        warnings: list[str] = []

        if config_warning is not None:
            warnings.append(config_warning)
        if not seed_summary.is_ready:
            warnings.extend(seed_summary.readiness_blockers)

        if generation_run is not None:
            active_job = self.get_job_for_generation_run(
                session,
                generation_run_id=generation_run.id,
            )
            if active_job is not None:
                active_job_stage_progress = self.get_generation_job_stage_progress(
                    session,
                    job_status_id=active_job.job_status_id,
                    generation_run_id=generation_run.id,
                )
            batch_summaries = self.get_generation_run_batches(
                session,
                generation_run_id=generation_run.id,
            )
            active_job_is_active = self._job_is_actively_processing(
                active_job,
                stage_progress=active_job_stage_progress
                + _batch_stage_progress(batch_summaries),
            )
            run_summary = self._build_generation_run_summary(
                generation_run,
                batch_summaries=batch_summaries,
                active_job=active_job,
                active_job_stage_progress=active_job_stage_progress,
            )
            warnings.extend(self._derive_run_warnings(generation_run, batch_summaries, active_job))
            if not self._generation_run_is_actively_processing(
                generation_run,
                batch_summaries=batch_summaries,
                active_job=active_job,
                active_job_stage_progress=active_job_stage_progress,
            ):
                generation_run = None
                run_summary = None
                batch_summaries = ()
                active_job = None
                active_job_stage_progress = ()
                active_job_is_active = False
            elif not active_job_is_active:
                active_job = None
                active_job_stage_progress = ()

        if generation_run is None:
            generation_run = self.get_latest_generation_run(session)
            if generation_run is not None:
                active_job = self.get_job_for_generation_run(
                    session,
                    generation_run_id=generation_run.id,
                )
                if active_job is not None:
                    active_job_stage_progress = self.get_generation_job_stage_progress(
                        session,
                        job_status_id=active_job.job_status_id,
                        generation_run_id=generation_run.id,
                    )
                batch_summaries = self.get_generation_run_batches(
                    session,
                    generation_run_id=generation_run.id,
                )
                active_job_is_active = self._job_is_actively_processing(
                    active_job,
                    stage_progress=active_job_stage_progress
                    + _batch_stage_progress(batch_summaries),
                )
                run_summary = self._build_generation_run_summary(
                    generation_run,
                    batch_summaries=batch_summaries,
                    active_job=active_job,
                    active_job_stage_progress=active_job_stage_progress,
                )
                warnings.extend(
                    self._derive_run_warnings(generation_run, batch_summaries, active_job)
                )
                if not active_job_is_active:
                    active_job = None
                    active_job_stage_progress = ()

        allowed_actions = self._build_allowed_actions(
            config_summary=config_summary,
            seed_summary=seed_summary,
            generation_run=generation_run,
            batch_summaries=batch_summaries,
            active_job=active_job,
            active_job_stage_progress=active_job_stage_progress,
        )
        return ControlPanelSnapshot(
            config_summary=config_summary,
            seed_data_summary=seed_summary,
            generation_run_summary=run_summary,
            batch_summaries=batch_summaries,
            active_job_summary=active_job,
            active_job_stage_progress=active_job_stage_progress,
            allowed_actions=allowed_actions,
            warnings=tuple(dict.fromkeys(warnings)),
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
        job_sort_timestamp = func.coalesce(
            JobStatus.started_at,
            JobStatus.completed_at,
            JobStatus.created_at,
        )
        job_ids_for_run = (
            select(JobStageProgress.job_status_id)
            .where(JobStageProgress.generation_run_id == generation_run_id)
            .distinct()
        )
        statement = (
            select(JobStatus)
            .where(JobStatus.id.in_(job_ids_for_run))
            .order_by(
                case((JobStatus.status == "running", 0), else_=1),
                case((JobStatus.status == "pending", 1), else_=2),
                job_sort_timestamp.desc(),
                JobStatus.id.desc(),
            )
            .limit(1)
        )
        return _job_summary(session.scalar(statement))

    def get_seed_job(self, session: Session) -> JobSummary | None:
        job_sort_timestamp = func.coalesce(
            JobStatus.started_at,
            JobStatus.completed_at,
            JobStatus.created_at,
        )
        return _job_summary(
            session.scalar(
                select(JobStatus)
                .where(JobStatus.job_type.in_(("raw_seed_ingest", "seed_normalization", "seed_refresh")))
                .order_by(
                    case((JobStatus.status == "running", 0), else_=1),
                    case((JobStatus.status == "pending", 1), else_=2),
                    job_sort_timestamp.desc(),
                    JobStatus.id.desc(),
                )
                .limit(1)
            )
        )

    def get_seed_job_progress(
        self,
        session: Session,
        *,
        job_status_id: int,
    ) -> tuple[StageProgressSummary, ...]:
        rows = list(
            session.scalars(
                select(JobStageProgress)
                .where(
                    JobStageProgress.job_status_id == job_status_id,
                    JobStageProgress.generation_run_id.is_(None),
                )
                .order_by(
                    JobStageProgress.stage_sequence.asc(),
                    JobStageProgress.id.asc(),
                )
            )
        )
        now = self.now_fn()
        return tuple(
            StageProgressSummary(
                stage_name=row.stage_name,
                stage_sequence=_coerce_int(row.stage_sequence),
                status=row.status,
                progress_current=_coerce_int(row.progress_current, default=0) or 0,
                progress_total=_coerce_int(row.progress_total),
                progress_percent=row.progress_percent,
                progress_unit=row.progress_unit,
                progress_message=row.progress_message,
                completion_message=_completion_message(
                    row.status,
                    _coerce_mapping(row.metadata_json),
                ),
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
            for row in rows
        )

    def get_generation_job_stage_progress(
        self,
        session: Session,
        *,
        job_status_id: int,
        generation_run_id: int,
    ) -> tuple[StageProgressSummary, ...]:
        rows = list(
            session.scalars(
                select(JobStageProgress)
                .where(
                    JobStageProgress.job_status_id == job_status_id,
                    JobStageProgress.generation_run_id == generation_run_id,
                    JobStageProgress.batch_id.is_(None),
                )
                .order_by(
                    JobStageProgress.stage_sequence.asc(),
                    JobStageProgress.id.asc(),
                )
            )
        )
        now = self.now_fn()
        return tuple(
            StageProgressSummary(
                stage_name=row.stage_name,
                stage_sequence=_coerce_int(row.stage_sequence),
                status=row.status,
                progress_current=_coerce_int(row.progress_current, default=0) or 0,
                progress_total=_coerce_int(row.progress_total),
                progress_percent=row.progress_percent,
                progress_unit=row.progress_unit,
                progress_message=row.progress_message,
                completion_message=_completion_message(
                    row.status,
                    _coerce_mapping(row.metadata_json),
                ),
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
            for row in rows
        )

    def get_seed_data_summary(self, session: Session) -> SeedDataSummary:
        regions_count = int(session.scalar(select(func.count()).select_from(Region)) or 0)
        clubs_count = int(session.scalar(select(func.count()).select_from(Club)) or 0)
        first_names_count = int(session.scalar(select(func.count()).select_from(FirstName)) or 0)
        last_names_count = int(session.scalar(select(func.count()).select_from(LastName)) or 0)
        latest_seed_job = self.get_seed_job(session)
        latest_seed_stage_progress = (
            self.get_seed_job_progress(session, job_status_id=latest_seed_job.job_status_id)
            if latest_seed_job is not None
            else ()
        )
        latest_seed_job_is_active = self._job_is_actively_processing(
            latest_seed_job,
            stage_progress=latest_seed_stage_progress,
        )
        latest_raw_loads = tuple(
            SeedLoadRunSummary(
                load_run_id=load.id,
                dataset_type=load.dataset_type,
                status=load.status,
                rows_read=load.rows_read,
                rows_loaded=load.rows_loaded,
                rows_rejected=load.rows_rejected,
                started_at=load.started_at,
                completed_at=load.completed_at,
                error_message=load.error_message,
            )
            for load in (
                session.scalars(
                    select(RawSeedLoadRun)
                    .where(RawSeedLoadRun.job_status_id == latest_seed_job.job_status_id)
                    .order_by(RawSeedLoadRun.started_at.asc(), RawSeedLoadRun.id.asc())
                )
                if latest_seed_job is not None
                else ()
            )
        )

        blockers: list[str] = []
        if regions_count <= 0:
            blockers.append("Seed/reference readiness requires normalized regions.")
        if clubs_count <= 0:
            blockers.append("Seed/reference readiness requires normalized clubs.")
        if first_names_count <= 0:
            blockers.append("Seed/reference readiness requires normalized first names.")
        if last_names_count <= 0:
            blockers.append("Seed/reference readiness requires normalized last names.")
        if latest_seed_job is not None and latest_seed_job.status == "failed":
            blockers.append("The latest seed preparation job failed.")
        return SeedDataSummary(
            is_ready=not blockers,
            readiness_label="Ready" if not blockers else "Blocked",
            readiness_blockers=tuple(blockers),
            latest_seed_job=latest_seed_job,
            latest_seed_job_is_active=latest_seed_job_is_active,
            latest_seed_stage_progress=latest_seed_stage_progress,
            latest_raw_loads=latest_raw_loads,
            regions_count=regions_count,
            clubs_count=clubs_count,
            first_names_count=first_names_count,
            last_names_count=last_names_count,
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
                    progress_current=_coerce_int(row.progress_current, default=0) or 0,
                    progress_total=_coerce_int(row.progress_total),
                    progress_percent=row.progress_percent,
                    progress_unit=row.progress_unit,
                    progress_message=row.progress_message,
                    completion_message=_completion_message(
                        row.status,
                        _coerce_mapping(row.metadata_json),
                    ),
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
        raw_seed_data = payload.get("raw_seed_data", {})
        supported_datasets = raw_seed_data.get("supported_datasets", []) if isinstance(raw_seed_data, dict) else []
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
                target_total_players=_coerce_int(simulation.get("target_total_players")),
                seed_dataset_count=len(supported_datasets) if isinstance(supported_datasets, list) else 0,
            ),
            None,
        )

    def _build_generation_run_summary(
        self,
        generation_run: GenerationRun,
        *,
        batch_summaries: tuple[BatchSummary, ...],
        active_job: JobSummary | None,
        active_job_stage_progress: tuple[StageProgressSummary, ...],
    ) -> GenerationRunSummary:
        counts = _count_batch_statuses(batch_summaries)
        display_status, status_detail = self._display_generation_run_status(
            generation_run,
            batch_summaries=batch_summaries,
            active_job=active_job,
            active_job_stage_progress=active_job_stage_progress,
        )
        return GenerationRunSummary(
            generation_run_id=generation_run.id,
            job_status_id=active_job.job_status_id if active_job is not None else None,
            generation_name=generation_run.generation_name,
            status=generation_run.status,
            display_status=display_status,
            status_detail=status_detail,
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
        seed_summary: SeedDataSummary,
        generation_run: GenerationRun | None,
        batch_summaries: tuple[BatchSummary, ...],
        active_job: JobSummary | None,
        active_job_stage_progress: tuple[StageProgressSummary, ...],
    ) -> AllowedActions:
        generation_run_active = self._generation_run_is_actively_processing(
            generation_run,
            batch_summaries=batch_summaries,
            active_job=active_job,
            active_job_stage_progress=active_job_stage_progress,
        )
        seed_blockers: list[str] = []
        if config_summary is None:
            seed_blockers.append("A single valid configuration is required.")
        if generation_run_active:
            seed_blockers.append("Seed preparation cannot run while a generation run is running.")
        if active_job is not None and active_job.status in {"pending", "running"}:
            seed_blockers.append("Another write-heavy generation job is still running.")
        if seed_summary.latest_seed_job_is_active:
            seed_blockers.append("A seed preparation job is already running.")

        start_blockers: list[str] = []
        if config_summary is None:
            start_blockers.append("A single valid configuration is required.")
        if not seed_summary.is_ready:
            start_blockers.append("Seed/reference data must be prepared before synthetic generation can start.")
        if generation_run_active:
            start_blockers.append("A generation run is already running.")
        if active_job is not None and active_job.status in {"pending", "running"}:
            start_blockers.append("A generation job is still running.")
        if seed_summary.latest_seed_job_is_active:
            start_blockers.append("Seed preparation must finish before synthetic generation can start.")

        student_blockers: list[str] = []
        if generation_run is None:
            student_blockers.append("No generation run exists yet.")
        elif generation_run.status != "succeeded":
            student_blockers.append("Student dataset generation requires a succeeded generation run.")
        if not seed_summary.is_ready:
            student_blockers.append("Seed/reference readiness must be restored before student dataset generation.")
        if any(batch.processing_status != "succeeded" for batch in batch_summaries):
            student_blockers.append("All monthly batches must be succeeded before student dataset generation.")
        if active_job is not None and active_job.status in {"pending", "running"}:
            student_blockers.append("No write-heavy job can be active during student dataset generation.")
        if seed_summary.latest_seed_job_is_active:
            student_blockers.append("No seed preparation job can be active during student dataset generation.")

        can_edit_config = (
            not generation_run_active
            and (
                not seed_summary.latest_seed_job_is_active
            )
        )
        return AllowedActions(
            can_edit_config=can_edit_config,
            can_start_seed_refresh=not seed_blockers,
            can_start_generation_run=not start_blockers,
            can_generate_student_dataset=not student_blockers,
            seed_refresh_blockers=tuple(seed_blockers),
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
                working_payload_json="{}",
                seed_payload_json="{}",
                synthetic_payload_json="{}",
                validation_passed=False,
                validation_issues=(),
                validation_errors=(
                    "A single valid configuration is required before editing.",
                ),
                validation_hash=None,
                status_message=None,
                change_count=None,
            )
        version = valid_versions[0]
        seed_payload, synthetic_payload = split_payload_sections(version.config_payload)
        return ConfigEditorState(
            title=version.title,
            notes=version.notes or "",
            working_payload_json=json.dumps(version.config_payload, indent=2, sort_keys=True),
            seed_payload_json=json.dumps(seed_payload, indent=2, sort_keys=True),
            synthetic_payload_json=json.dumps(synthetic_payload, indent=2, sort_keys=True),
            validation_passed=False,
            validation_issues=(),
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

    def _generation_run_is_actively_processing(
        self,
        generation_run: GenerationRun | None,
        *,
        batch_summaries: tuple[BatchSummary, ...],
        active_job: JobSummary | None,
        active_job_stage_progress: tuple[StageProgressSummary, ...],
    ) -> bool:
        if generation_run is None:
            return False
        if generation_run.status == "not_started":
            return True
        if generation_run.status != "running":
            return False
        if self._job_is_actively_processing(
            active_job,
            stage_progress=active_job_stage_progress,
        ):
            return True
        if active_job is not None and active_job.status in {"pending", "running"}:
            return any(
                stage.status == "running" and not stage.is_stale
                for batch in batch_summaries
                for stage in batch.stage_progress
            )
        return False

    def _display_generation_run_status(
        self,
        generation_run: GenerationRun,
        *,
        batch_summaries: tuple[BatchSummary, ...],
        active_job: JobSummary | None,
        active_job_stage_progress: tuple[StageProgressSummary, ...],
    ) -> tuple[str, str | None]:
        if self._generation_run_is_actively_processing(
            generation_run,
            batch_summaries=batch_summaries,
            active_job=active_job,
            active_job_stage_progress=active_job_stage_progress,
        ):
            return generation_run.status, None
        if generation_run.status != "running":
            return generation_run.status, None
        if any(batch.processing_status == "failed" for batch in batch_summaries):
            return "stalled", "Stored run status is still running, but a batch has already failed."
        if active_job is not None and active_job.status == "failed":
            return "stalled", "Stored run status is still running, but the latest generation job has failed."
        if batch_summaries and all(
            batch.processing_status == "succeeded"
            for batch in batch_summaries
        ):
            return "completed", "Stored run status is still running, but all tracked batches have completed."
        if any(batch.processing_status in {"pending", "running"} for batch in batch_summaries):
            return "stalled", "Stored run status is still running, but no active job heartbeat remains."
        return "stalled", "Stored run status is still running, but no active job or batch remains."

    def _job_is_actively_processing(
        self,
        job: JobSummary | None,
        *,
        stage_progress: tuple[StageProgressSummary, ...],
    ) -> bool:
        if job is None:
            return False
        if job.status in {"succeeded", "failed"}:
            return False
        if any(
            stage.status == "running" and not stage.is_stale
            for stage in stage_progress
        ):
            return True
        reference_time = job.started_at or job.created_at
        if reference_time is None:
            return False
        return (self.now_fn() - reference_time) <= self.stale_after

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


def _job_summary(job: JobStatus | None) -> JobSummary | None:
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
        created_at=job.created_at,
    )


def _batch_stage_progress(
    batch_summaries: tuple[BatchSummary, ...],
) -> tuple[StageProgressSummary, ...]:
    return tuple(
        stage
        for batch in batch_summaries
        for stage in batch.stage_progress
    )


def split_payload_sections(payload: dict[str, object] | None) -> tuple[dict[str, object], dict[str, object]]:
    """Split a full configuration payload into seed and synthetic sections."""
    source = payload or {}
    seed_payload: dict[str, object] = {}
    synthetic_payload: dict[str, object] = {}
    for key, value in source.items():
        if key in SEED_CONFIG_KEYS:
            seed_payload[key] = value
        else:
            synthetic_payload[key] = value
    return seed_payload, synthetic_payload


def merge_payload_sections(
    seed_payload: dict[str, object],
    synthetic_payload: dict[str, object],
) -> tuple[dict[str, object], tuple[str, ...]]:
    """Merge seed and synthetic configuration sections into one payload."""
    overlap = sorted(set(seed_payload) & set(synthetic_payload))
    if overlap:
        return {}, (f"Configuration sections overlap: {', '.join(overlap)}.",)
    payload: dict[str, object] = {}
    payload.update(synthetic_payload)
    payload.update(seed_payload)
    return payload, ()


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


def _coerce_mapping(value: object) -> dict[str, object]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _completion_message(status: str, details: dict[str, object]) -> str | None:
    if status != "succeeded" or not details:
        return None

    row_count = _first_int(
        details,
        "completed_datasets",
        "rows_loaded",
        "membership_rows_loaded",
        "match_count",
        "log_count",
        "rating_history_count",
    )
    if row_count is None:
        return None

    label = _first_label(details)
    return f"{label}: {row_count:,}"


def _first_int(details: dict[str, object], *keys: str) -> int | None:
    for key in keys:
        value = details.get(key)
        if isinstance(value, bool):
            continue
        if isinstance(value, int):
            return value
    return None


def _first_label(details: dict[str, object]) -> str:
    if "completed_datasets" in details:
        return "Datasets completed"
    if "rows_loaded" in details or "membership_rows_loaded" in details:
        return "Rows created"
    if "match_count" in details:
        return "Matches created"
    if "rating_history_count" in details:
        return "Ratings created"
    if "log_count" in details:
        return "Log rows created"
    return "Rows created"


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)
