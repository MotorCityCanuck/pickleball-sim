"""Operator-facing orchestration for seed data ingest and normalization."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
import logging
from typing import Callable
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import ConfigurationLifecycleService
from app.db.session import SessionLocal, session_scope
from app.models import ConfigurationProfileVersion, JobStageProgress, JobStatus
from app.seed_data_ingest import load_raw_seed_dataset
from app.seed_data_ingest.base import RawSeedLoadResult
from app.seed_data_normalize import normalize_seed_dataset
from app.seed_data_normalize.base import SeedNormalizeResult

from .destructive_reset import delete_generated_data
from .job_lifecycle import job_is_actively_processing, overall_percent_complete


RAW_DATASET_ORDER = (
    "metro_areas_us",
    "metro_areas_ca",
    "first_names_us",
    "first_names_ca",
    "last_names_us",
    "last_names_ca",
    "state_prov_biases_us",
    "state_prov_biases_ca",
    "pickleball_club_names",
    "pickleball_club_distributions",
)
NORMALIZATION_ORDER = (
    "metro_areas",
    "first_names",
    "last_names",
    "pickleball_clubs",
)
NORMALIZATION_REQUIREMENTS = {
    "metro_areas": frozenset({"metro_areas_us", "metro_areas_ca"}),
    "first_names": frozenset({"first_names_us", "first_names_ca"}),
    "last_names": frozenset({"last_names_us", "last_names_ca"}),
    "pickleball_clubs": frozenset(
        {"pickleball_club_names", "pickleball_club_distributions"}
    ),
}
SEED_JOB_TYPES = frozenset({"raw_seed_ingest", "seed_normalization", "seed_refresh"})
SEED_JOB_PHASES = {
    "load": "raw_seed_ingest",
    "normalize": "seed_normalization",
    "refresh": "seed_refresh",
}


logger = logging.getLogger("uvicorn.error")


@dataclass(frozen=True)
class SeedRefreshResult:
    """Summary of a seed-stage orchestration action."""

    configuration_version: ConfigurationProfileVersion
    job_status: JobStatus
    raw_load_results: tuple[RawSeedLoadResult, ...]
    normalize_results: tuple[SeedNormalizeResult, ...]


@dataclass(frozen=True)
class SeedRefreshRegistration:
    """Pending job records created before background execution starts."""

    configuration_version: ConfigurationProfileVersion
    job_status: JobStatus
    mode: str


class SeedRefreshService:
    """Launch operator-facing seed ingest and normalization jobs."""

    def __init__(
        self,
        *,
        configuration_lifecycle: ConfigurationLifecycleService | None = None,
        load_dataset_fn: Callable[..., RawSeedLoadResult] | None = None,
        normalize_dataset_fn: Callable[..., SeedNormalizeResult] | None = None,
        reset_generated_data_fn: Callable[..., None] | None = None,
    ) -> None:
        self.configuration_lifecycle = (
            configuration_lifecycle or ConfigurationLifecycleService()
        )
        self.load_dataset_fn = load_dataset_fn or load_raw_seed_dataset
        self.normalize_dataset_fn = normalize_dataset_fn or normalize_seed_dataset
        self.reset_generated_data_fn = reset_generated_data_fn or delete_generated_data

    def register_seed_refresh(
        self,
        *,
        session: Session | None = None,
    ) -> SeedRefreshRegistration:
        """Create a pending full seed refresh job."""
        if session is not None:
            return self._register_seed_job("refresh", session=session)

        with session_scope() as active_session:
            return self._register_seed_job("refresh", session=active_session)

    def register_raw_seed_ingest(
        self,
        *,
        session: Session | None = None,
    ) -> SeedRefreshRegistration:
        """Create a pending raw-ingest-only job."""
        if session is not None:
            return self._register_seed_job("load", session=session)

        with session_scope() as active_session:
            return self._register_seed_job("load", session=active_session)

    def register_seed_normalization(
        self,
        *,
        session: Session | None = None,
    ) -> SeedRefreshRegistration:
        """Create a pending normalization-only job."""
        if session is not None:
            return self._register_seed_job("normalize", session=session)

        with session_scope() as active_session:
            return self._register_seed_job("normalize", session=active_session)

    def execute_registered_seed_job(
        self,
        *,
        config_version_id: int,
        job_status_id: int,
        mode: str,
        session: Session | None = None,
    ) -> SeedRefreshResult:
        """Run a previously registered seed job."""
        if session is not None:
            return self._execute_registered_seed_job(
                config_version_id=config_version_id,
                job_status_id=job_status_id,
                mode=mode,
                session=session,
            )

        with session_scope() as active_session:
            return self._execute_registered_seed_job(
                config_version_id=config_version_id,
                job_status_id=job_status_id,
                mode=mode,
                session=active_session,
            )

    def execute_registered_seed_job_in_background(
        self,
        *,
        config_version_id: int,
        job_status_id: int,
        mode: str,
    ) -> None:
        """Run a previously registered seed job with durable background commits."""
        logger.info(
            "Starting background seed job config_version_id=%s job_status_id=%s mode=%s",
            config_version_id,
            job_status_id,
            mode,
        )
        session = SessionLocal()
        try:
            self._execute_registered_seed_job(
                config_version_id=config_version_id,
                job_status_id=job_status_id,
                mode=mode,
                session=session,
                checkpoint=session.commit,
                re_raise=False,
            )
            session.commit()
            logger.info(
                "Completed background seed job config_version_id=%s job_status_id=%s mode=%s",
                config_version_id,
                job_status_id,
                mode,
            )
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def refresh_seed_data(
        self,
        *,
        session: Session | None = None,
    ) -> SeedRefreshResult:
        """Run full Stage 1: raw ingest followed by normalization."""
        if session is not None:
            registration = self._register_seed_job("refresh", session=session)
            return self._execute_registered_seed_job(
                config_version_id=registration.configuration_version.id,
                job_status_id=registration.job_status.id,
                mode=registration.mode,
                session=session,
            )

        with session_scope() as active_session:
            registration = self._register_seed_job("refresh", session=active_session)
            return self._execute_registered_seed_job(
                config_version_id=registration.configuration_version.id,
                job_status_id=registration.job_status.id,
                mode=registration.mode,
                session=active_session,
            )

    def load_raw_seed_data(
        self,
        *,
        session: Session | None = None,
    ) -> SeedRefreshResult:
        """Run only raw seed ingest."""
        if session is not None:
            registration = self._register_seed_job("load", session=session)
            return self._execute_registered_seed_job(
                config_version_id=registration.configuration_version.id,
                job_status_id=registration.job_status.id,
                mode=registration.mode,
                session=session,
            )

        with session_scope() as active_session:
            registration = self._register_seed_job("load", session=active_session)
            return self._execute_registered_seed_job(
                config_version_id=registration.configuration_version.id,
                job_status_id=registration.job_status.id,
                mode=registration.mode,
                session=active_session,
            )

    def normalize_seed_data(
        self,
        *,
        session: Session | None = None,
    ) -> SeedRefreshResult:
        """Run only seed normalization from staged raw rows."""
        if session is not None:
            registration = self._register_seed_job("normalize", session=session)
            return self._execute_registered_seed_job(
                config_version_id=registration.configuration_version.id,
                job_status_id=registration.job_status.id,
                mode=registration.mode,
                session=session,
            )

        with session_scope() as active_session:
            registration = self._register_seed_job("normalize", session=active_session)
            return self._execute_registered_seed_job(
                config_version_id=registration.configuration_version.id,
                job_status_id=registration.job_status.id,
                mode=registration.mode,
                session=active_session,
            )

    def _register_seed_job(
        self,
        mode: str,
        *,
        session: Session,
    ) -> SeedRefreshRegistration:
        config_version = self._resolve_single_valid_config(session)
        payload = config_version.config_payload or {}
        raw_datasets = _raw_datasets_from_payload(payload)
        normalize_datasets = _normalization_datasets_from_raw(raw_datasets)
        if mode in {"load", "refresh"} and not raw_datasets:
            raise ValueError("No raw seed datasets are configured for ingestion.")
        if mode in {"normalize", "refresh"} and not normalize_datasets:
            raise ValueError("No seed normalization datasets are configured.")
        self._ensure_no_active_seed_job(session)

        job_type = {
            "load": "raw_seed_ingest",
            "normalize": "seed_normalization",
            "refresh": "seed_refresh",
        }[mode]
        job_status = self._create_job_status(
            session,
            job_type=job_type,
            initial_message={
                "load": "Queued raw seed ingest.",
                "normalize": "Queued seed normalization.",
                "refresh": "Queued seed refresh.",
            }[mode],
        )
        if mode in {"load", "refresh"}:
            self._create_stage_row(
                session,
                job_status=job_status,
                stage_name="raw_seed_ingest",
                stage_sequence=1,
                progress_total=len(raw_datasets),
            )
        if mode == "refresh":
            stage_sequence = 2
        else:
            stage_sequence = 1
        if mode in {"normalize", "refresh"}:
            self._create_stage_row(
                session,
                job_status=job_status,
                stage_name="seed_normalization",
                stage_sequence=stage_sequence,
                progress_total=len(normalize_datasets),
            )

        self.configuration_lifecycle.mark_version_used(
            session,
            version_id=config_version.id,
        )
        session.flush()
        return SeedRefreshRegistration(
            configuration_version=config_version,
            job_status=job_status,
            mode=mode,
        )

    def _execute_registered_seed_job(
        self,
        *,
        config_version_id: int,
        job_status_id: int,
        mode: str,
        session: Session,
        checkpoint: Callable[[], None] | None = None,
        re_raise: bool = True,
    ) -> SeedRefreshResult:
        config_version = session.get(ConfigurationProfileVersion, config_version_id)
        if config_version is None:
            raise ValueError(f"Configuration profile version {config_version_id} does not exist.")
        job_status = session.get(JobStatus, job_status_id)
        if job_status is None:
            raise ValueError(f"Job status {job_status_id} does not exist.")
        if job_status.status != "pending":
            raise ValueError(
                f"Seed job {job_status.job_id} is already {job_status.status}; "
                "background execution requires a pending job."
            )

        payload = config_version.config_payload or {}
        raw_datasets = _raw_datasets_from_payload(payload)
        normalize_datasets = _normalization_datasets_from_raw(raw_datasets)
        raw_results: list[RawSeedLoadResult] = []
        normalize_results: list[SeedNormalizeResult] = []

        try:
            if mode in {"load", "refresh"}:
                self._set_job_status(
                    job_status,
                    status="running",
                    phase="raw_seed_ingest",
                    message="Loading configured raw seed datasets.",
                    started=True,
                )
                self._checkpoint(session, checkpoint)
                raw_results = self._run_raw_ingest_stage(
                    session,
                    job_status=job_status,
                    stage_name="raw_seed_ingest",
                    datasets=raw_datasets,
                    checkpoint=checkpoint,
                )

            if mode in {"normalize", "refresh"}:
                self._set_job_status(
                    job_status,
                    status="running",
                    phase="seed_normalization",
                    message="Clearing generated data that depends on reference tables.",
                    started=mode == "normalize",
                )
                self._checkpoint(session, checkpoint)
                self.reset_generated_data_fn(
                    session=session,
                    preserve_job_status_id=job_status.id,
                )
                self._checkpoint(session, checkpoint)
                normalize_results = self._run_normalization_stage(
                    session,
                    job_status=job_status,
                    stage_name="seed_normalization",
                    datasets=normalize_datasets,
                    config_payload=payload,
                    checkpoint=checkpoint,
                )

            self._set_job_status(
                job_status,
                status="succeeded",
                phase="completed",
                message=_completion_message_for_mode(
                    mode,
                    raw_count=len(raw_results),
                    normalize_count=len(normalize_results),
                ),
                percent_complete=Decimal("100.00"),
                completed=True,
            )
            self._checkpoint(session, checkpoint)
            return SeedRefreshResult(
                configuration_version=config_version,
                job_status=job_status,
                raw_load_results=tuple(raw_results),
                normalize_results=tuple(normalize_results),
            )
        except Exception as exc:
            self._fail_incomplete_stages(session, job_status.id)
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
            return SeedRefreshResult(
                configuration_version=config_version,
                job_status=job_status,
                raw_load_results=tuple(raw_results),
                normalize_results=tuple(normalize_results),
            )

    def _run_raw_ingest_stage(
        self,
        session: Session,
        *,
        job_status: JobStatus,
        stage_name: str,
        datasets: tuple[str, ...],
        checkpoint: Callable[[], None] | None = None,
    ) -> list[RawSeedLoadResult]:
        stage_row = self._get_stage_row(
            session,
            job_status_id=job_status.id,
            stage_name=stage_name,
        )
        results: list[RawSeedLoadResult] = []
        for index, dataset in enumerate(datasets, start=1):
            self._update_stage_progress(
                stage_row,
                status="running",
                progress_current=index - 1,
                progress_total=len(datasets),
                progress_message=f"Loading {dataset} ({index}/{len(datasets)})",
                metadata={
                    "current_dataset": dataset,
                    "completed_datasets": index - 1,
                    "total_datasets": len(datasets),
                },
            )
            self._set_job_status(
                job_status,
                status="running",
                phase="raw_seed_ingest",
                message=f"Loading {dataset} ({index}/{len(datasets)})",
                percent_complete=self._overall_percent_complete(session, job_status.id),
            )
            self._checkpoint(session, checkpoint)
            result = self.load_dataset_fn(dataset, session=session)
            results.append(result)
            self._update_stage_progress(
                stage_row,
                status="running",
                progress_current=index,
                progress_total=len(datasets),
                progress_message=(
                    f"Loaded {dataset}: {result.rows_loaded} rows accepted, "
                    f"{result.rows_rejected} rejected."
                ),
                metadata={
                    "current_dataset": dataset,
                    "rows_loaded": result.rows_loaded,
                    "rows_rejected": result.rows_rejected,
                    "completed_datasets": index,
                    "total_datasets": len(datasets),
                },
            )
            self._checkpoint(session, checkpoint)
        self._update_stage_progress(
            stage_row,
            status="succeeded",
            progress_current=len(datasets),
            progress_total=len(datasets),
            progress_message=f"Loaded {len(datasets)} raw seed datasets.",
            metadata={
                "completed_datasets": len(datasets),
                "total_datasets": len(datasets),
            },
        )
        self._set_job_status(
            job_status,
            status="running",
            phase="raw_seed_ingest",
            message=f"Loaded {len(datasets)} raw seed datasets.",
            percent_complete=self._overall_percent_complete(session, job_status.id),
        )
        self._checkpoint(session, checkpoint)
        return results

    def _run_normalization_stage(
        self,
        session: Session,
        *,
        job_status: JobStatus,
        stage_name: str,
        datasets: tuple[str, ...],
        config_payload: dict[str, object],
        checkpoint: Callable[[], None] | None = None,
    ) -> list[SeedNormalizeResult]:
        stage_row = self._get_stage_row(
            session,
            job_status_id=job_status.id,
            stage_name=stage_name,
        )
        results: list[SeedNormalizeResult] = []
        for index, dataset in enumerate(datasets, start=1):
            self._update_stage_progress(
                stage_row,
                status="running",
                progress_current=index - 1,
                progress_total=len(datasets),
                progress_message=f"Normalizing {dataset} ({index}/{len(datasets)})",
                metadata={
                    "current_dataset": dataset,
                    "completed_datasets": index - 1,
                    "total_datasets": len(datasets),
                },
            )
            self._set_job_status(
                job_status,
                status="running",
                phase="seed_normalization",
                message=f"Normalizing {dataset} ({index}/{len(datasets)})",
                percent_complete=self._overall_percent_complete(session, job_status.id),
            )
            self._checkpoint(session, checkpoint)
            result = self.normalize_dataset_fn(
                dataset,
                replace_production=True,
                config_payload=config_payload,
                session=session,
            )
            results.append(result)
            self._update_stage_progress(
                stage_row,
                status="running",
                progress_current=index,
                progress_total=len(datasets),
                progress_message=(
                    f"Normalized {dataset}: {result.rows_loaded} rows loaded, "
                    f"{result.rows_deleted} replaced."
                ),
                metadata={
                    "current_dataset": dataset,
                    "rows_loaded": result.rows_loaded,
                    "rows_deleted": result.rows_deleted,
                    "completed_datasets": index,
                    "total_datasets": len(datasets),
                },
            )
            self._checkpoint(session, checkpoint)
        self._update_stage_progress(
            stage_row,
            status="succeeded",
            progress_current=len(datasets),
            progress_total=len(datasets),
            progress_message=f"Normalized {len(datasets)} seed datasets.",
            metadata={
                "completed_datasets": len(datasets),
                "total_datasets": len(datasets),
            },
        )
        self._set_job_status(
            job_status,
            status="running",
            phase="seed_normalization",
            message=f"Normalized {len(datasets)} seed datasets.",
            percent_complete=self._overall_percent_complete(session, job_status.id),
        )
        self._checkpoint(session, checkpoint)
        return results

    @staticmethod
    def _checkpoint(
        session: Session,
        checkpoint: Callable[[], None] | None,
    ) -> None:
        session.flush()
        if checkpoint is not None:
            checkpoint()

    def _resolve_single_valid_config(self, session: Session) -> ConfigurationProfileVersion:
        valid_versions = list(
            session.scalars(
                select(ConfigurationProfileVersion)
                .where(ConfigurationProfileVersion.lifecycle_status == "valid")
                .order_by(ConfigurationProfileVersion.id.asc())
            )
        )
        if len(valid_versions) != 1:
            raise ValueError(
                "Expected exactly one valid configuration version before seed orchestration; "
                f"found {len(valid_versions)}."
            )
        return valid_versions[0]

    def _ensure_no_active_seed_job(self, session: Session) -> None:
        candidate_jobs = list(
            session.scalars(
                select(JobStatus)
                .where(
                    JobStatus.job_type.in_(tuple(SEED_JOB_TYPES)),
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
                f"Seed job {active_job.job_id} is already {active_job.status}; "
                "concurrent seed jobs are blocked."
            )

    def _create_job_status(
        self,
        session: Session,
        *,
        job_type: str,
        initial_message: str,
    ) -> JobStatus:
        job = JobStatus(
            job_type=job_type,
            job_id=f"{job_type}-{uuid4().hex[:8]}",
            status="pending",
            current_phase="initialize",
            percent_complete=Decimal("0.00"),
            current_message=initial_message,
        )
        session.add(job)
        session.flush()
        return job

    def _create_stage_row(
        self,
        session: Session,
        *,
        job_status: JobStatus,
        stage_name: str,
        stage_sequence: int,
        progress_total: int,
    ) -> None:
        session.add(
            JobStageProgress(
                job_status_id=job_status.id,
                generation_run_id=None,
                batch_id=None,
                stage_name=stage_name,
                stage_sequence=stage_sequence,
                status="pending",
                progress_current=0,
                progress_total=progress_total,
                progress_unit="dataset",
                progress_percent=Decimal("0.00"),
                progress_message="Pending execution.",
            )
        )
        session.flush()

    def _get_stage_row(
        self,
        session: Session,
        *,
        job_status_id: int,
        stage_name: str,
    ) -> JobStageProgress:
        stage_row = session.scalar(
            select(JobStageProgress).where(
                JobStageProgress.job_status_id == job_status_id,
                JobStageProgress.stage_name == stage_name,
            )
        )
        if stage_row is None:
            raise ValueError(
                f"Missing job_stage_progress row for job={job_status_id}, stage={stage_name}."
            )
        return stage_row

    def _update_stage_progress(
        self,
        stage_row: JobStageProgress,
        *,
        status: str,
        progress_current: int,
        progress_total: int,
        progress_message: str,
        metadata: dict[str, object] | None = None,
    ) -> None:
        now = _utc_now()
        stage_row.status = status
        stage_row.progress_current = progress_current
        stage_row.progress_total = progress_total
        stage_row.progress_message = progress_message
        stage_row.metadata_json = metadata or None
        stage_row.last_heartbeat_at = now
        stage_row.progress_percent = _percent(progress_current, progress_total)
        if status == "running":
            stage_row.started_at = stage_row.started_at or now
            stage_row.completed_at = None
            stage_row.error_message = None
        elif status == "succeeded":
            stage_row.started_at = stage_row.started_at or now
            stage_row.completed_at = now
            stage_row.error_message = None
        elif status == "failed":
            stage_row.started_at = stage_row.started_at or now
            stage_row.completed_at = now

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
            self._update_stage_progress(
                row,
                status="failed",
                progress_current=row.progress_current or 0,
                progress_total=row.progress_total or 1,
                progress_message=row.progress_message or "Stage failed.",
                metadata=row.metadata_json if isinstance(row.metadata_json, dict) else None,
            )
            row.error_message = "Stage failed."

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


def _raw_datasets_from_payload(payload: dict[str, object]) -> tuple[str, ...]:
    raw_config = payload.get("raw_seed_data")
    configured = (
        raw_config.get("supported_datasets", []) if isinstance(raw_config, dict) else []
    )
    configured_set = {item for item in configured if isinstance(item, str)}
    return tuple(dataset for dataset in RAW_DATASET_ORDER if dataset in configured_set)


def _normalization_datasets_from_raw(raw_datasets: tuple[str, ...]) -> tuple[str, ...]:
    raw_dataset_set = set(raw_datasets)
    return tuple(
        dataset
        for dataset in NORMALIZATION_ORDER
        if raw_dataset_set.intersection(NORMALIZATION_REQUIREMENTS[dataset])
    )


def _completion_message_for_mode(
    mode: str,
    *,
    raw_count: int,
    normalize_count: int,
) -> str:
    if mode == "load":
        return f"Raw seed ingest completed for {raw_count} datasets."
    if mode == "normalize":
        return f"Seed normalization completed for {normalize_count} datasets."
    return (
        "Seed refresh completed successfully. "
        f"Ingested {raw_count} raw datasets and normalized {normalize_count} production datasets."
    )


def _percent(current: int, total: int) -> Decimal:
    if total <= 0:
        return Decimal("0.00")
    return (Decimal(current) * Decimal("100.00")) / Decimal(total)


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)
