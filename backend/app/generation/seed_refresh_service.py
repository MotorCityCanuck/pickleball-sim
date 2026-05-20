"""Operator-facing orchestration for seed data ingest and normalization."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Callable
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import ConfigurationLifecycleService
from app.db.session import session_scope
from app.models import ConfigurationProfileVersion, JobStageProgress, JobStatus
from app.seed_data_ingest import load_raw_seed_dataset
from app.seed_data_ingest.base import RawSeedLoadResult
from app.seed_data_normalize import normalize_seed_dataset
from app.seed_data_normalize.base import SeedNormalizeResult


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


@dataclass(frozen=True)
class SeedRefreshResult:
    """Summary of a seed-stage orchestration action."""

    configuration_version: ConfigurationProfileVersion
    job_status: JobStatus
    raw_load_results: tuple[RawSeedLoadResult, ...]
    normalize_results: tuple[SeedNormalizeResult, ...]


class SeedRefreshService:
    """Launch operator-facing seed ingest and normalization jobs."""

    def __init__(
        self,
        *,
        configuration_lifecycle: ConfigurationLifecycleService | None = None,
        load_dataset_fn: Callable[..., RawSeedLoadResult] | None = None,
        normalize_dataset_fn: Callable[..., SeedNormalizeResult] | None = None,
    ) -> None:
        self.configuration_lifecycle = (
            configuration_lifecycle or ConfigurationLifecycleService()
        )
        self.load_dataset_fn = load_dataset_fn or load_raw_seed_dataset
        self.normalize_dataset_fn = normalize_dataset_fn or normalize_seed_dataset

    def refresh_seed_data(
        self,
        *,
        session: Session | None = None,
    ) -> SeedRefreshResult:
        """Run full Stage 1: raw ingest followed by normalization."""
        if session is not None:
            return self._refresh_seed_data(session)

        with session_scope() as active_session:
            return self._refresh_seed_data(active_session)

    def load_raw_seed_data(
        self,
        *,
        session: Session | None = None,
    ) -> SeedRefreshResult:
        """Run only raw seed ingest."""
        if session is not None:
            return self._load_raw_seed_data(session)

        with session_scope() as active_session:
            return self._load_raw_seed_data(active_session)

    def normalize_seed_data(
        self,
        *,
        session: Session | None = None,
    ) -> SeedRefreshResult:
        """Run only seed normalization from staged raw rows."""
        if session is not None:
            return self._normalize_seed_data(active_session=session)

        with session_scope() as active_session:
            return self._normalize_seed_data(active_session=active_session)

    def _refresh_seed_data(self, session: Session) -> SeedRefreshResult:
        config_version = self._resolve_single_valid_config(session)
        payload = config_version.config_payload or {}
        raw_datasets = _raw_datasets_from_payload(payload)
        normalize_datasets = _normalization_datasets_from_raw(raw_datasets)
        if not raw_datasets:
            raise ValueError("No raw seed datasets are configured for ingestion.")
        if not normalize_datasets:
            raise ValueError("No seed normalization datasets are configured.")
        self._ensure_no_active_seed_job(session)

        job_status = self._create_job_status(
            session,
            job_type="seed_refresh",
            initial_phase="initialize",
            initial_message="Preparing seed refresh.",
        )
        raw_stage = self._create_stage_row(
            session,
            job_status=job_status,
            stage_name="raw_seed_ingest",
            stage_sequence=1,
            progress_total=len(raw_datasets),
        )
        normalize_stage = self._create_stage_row(
            session,
            job_status=job_status,
            stage_name="seed_normalization",
            stage_sequence=2,
            progress_total=len(normalize_datasets),
        )

        raw_results: list[RawSeedLoadResult] = []
        normalize_results: list[SeedNormalizeResult] = []
        try:
            self.configuration_lifecycle.mark_version_used(
                session,
                version_id=config_version.id,
            )
            self._set_job_status(
                job_status,
                status="running",
                phase="raw_seed_ingest",
                message="Loading configured raw seed datasets.",
                started=True,
            )
            raw_results = self._run_raw_ingest_stage(
                session,
                job_status=job_status,
                stage_row=raw_stage,
                datasets=raw_datasets,
            )
            self._set_job_status(
                job_status,
                status="running",
                phase="seed_normalization",
                message="Normalizing staged seed datasets into reference tables.",
            )
            normalize_results = self._run_normalization_stage(
                session,
                job_status=job_status,
                stage_row=normalize_stage,
                datasets=normalize_datasets,
                config_payload=payload,
            )
            self._set_job_status(
                job_status,
                status="succeeded",
                phase="completed",
                message=(
                    "Seed refresh completed successfully. "
                    f"Ingested {len(raw_results)} raw datasets and normalized "
                    f"{len(normalize_results)} production datasets."
                ),
                percent_complete=Decimal("100.00"),
                completed=True,
            )
            session.flush()
            return SeedRefreshResult(
                configuration_version=config_version,
                job_status=job_status,
                raw_load_results=tuple(raw_results),
                normalize_results=tuple(normalize_results),
            )
        except Exception as exc:
            self._fail_incomplete_stages(raw_stage, normalize_stage)
            self._set_job_status(
                job_status,
                status="failed",
                phase="failed",
                message=str(exc),
                completed=True,
            )
            raise

    def _load_raw_seed_data(self, session: Session) -> SeedRefreshResult:
        config_version = self._resolve_single_valid_config(session)
        raw_datasets = _raw_datasets_from_payload(config_version.config_payload or {})
        if not raw_datasets:
            raise ValueError("No raw seed datasets are configured for ingestion.")
        self._ensure_no_active_seed_job(session)

        job_status = self._create_job_status(
            session,
            job_type="raw_seed_ingest",
            initial_phase="initialize",
            initial_message="Preparing raw seed ingest.",
        )
        raw_stage = self._create_stage_row(
            session,
            job_status=job_status,
            stage_name="raw_seed_ingest",
            stage_sequence=1,
            progress_total=len(raw_datasets),
        )
        try:
            self.configuration_lifecycle.mark_version_used(
                session,
                version_id=config_version.id,
            )
            self._set_job_status(
                job_status,
                status="running",
                phase="raw_seed_ingest",
                message="Loading configured raw seed datasets.",
                started=True,
            )
            raw_results = self._run_raw_ingest_stage(
                session,
                job_status=job_status,
                stage_row=raw_stage,
                datasets=raw_datasets,
            )
            self._set_job_status(
                job_status,
                status="succeeded",
                phase="completed",
                message=f"Raw seed ingest completed for {len(raw_results)} datasets.",
                percent_complete=Decimal("100.00"),
                completed=True,
            )
            session.flush()
            return SeedRefreshResult(
                configuration_version=config_version,
                job_status=job_status,
                raw_load_results=tuple(raw_results),
                normalize_results=(),
            )
        except Exception as exc:
            self._fail_incomplete_stages(raw_stage)
            self._set_job_status(
                job_status,
                status="failed",
                phase="failed",
                message=str(exc),
                completed=True,
            )
            raise

    def _normalize_seed_data(self, *, active_session: Session) -> SeedRefreshResult:
        config_version = self._resolve_single_valid_config(active_session)
        payload = config_version.config_payload or {}
        normalize_datasets = _normalization_datasets_from_raw(
            _raw_datasets_from_payload(payload)
        )
        if not normalize_datasets:
            raise ValueError("No seed normalization datasets are configured.")
        self._ensure_no_active_seed_job(active_session)

        job_status = self._create_job_status(
            active_session,
            job_type="seed_normalization",
            initial_phase="initialize",
            initial_message="Preparing seed normalization.",
        )
        normalize_stage = self._create_stage_row(
            active_session,
            job_status=job_status,
            stage_name="seed_normalization",
            stage_sequence=1,
            progress_total=len(normalize_datasets),
        )
        try:
            self.configuration_lifecycle.mark_version_used(
                active_session,
                version_id=config_version.id,
            )
            self._set_job_status(
                job_status,
                status="running",
                phase="seed_normalization",
                message="Normalizing staged seed datasets into reference tables.",
                started=True,
            )
            normalize_results = self._run_normalization_stage(
                active_session,
                job_status=job_status,
                stage_row=normalize_stage,
                datasets=normalize_datasets,
                config_payload=payload,
            )
            self._set_job_status(
                job_status,
                status="succeeded",
                phase="completed",
                message=(
                    f"Seed normalization completed for {len(normalize_results)} datasets."
                ),
                percent_complete=Decimal("100.00"),
                completed=True,
            )
            active_session.flush()
            return SeedRefreshResult(
                configuration_version=config_version,
                job_status=job_status,
                raw_load_results=(),
                normalize_results=tuple(normalize_results),
            )
        except Exception as exc:
            self._fail_incomplete_stages(normalize_stage)
            self._set_job_status(
                job_status,
                status="failed",
                phase="failed",
                message=str(exc),
                completed=True,
            )
            raise

    def _run_raw_ingest_stage(
        self,
        session: Session,
        *,
        job_status: JobStatus,
        stage_row: JobStageProgress,
        datasets: tuple[str, ...],
    ) -> list[RawSeedLoadResult]:
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
        session.flush()
        return results

    def _run_normalization_stage(
        self,
        session: Session,
        *,
        job_status: JobStatus,
        stage_row: JobStageProgress,
        datasets: tuple[str, ...],
        config_payload: dict[str, object],
    ) -> list[SeedNormalizeResult]:
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
        session.flush()
        return results

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
        active_job = session.scalar(
            select(JobStatus)
            .where(
                JobStatus.job_type.in_(tuple(SEED_JOB_TYPES)),
                JobStatus.status == "running",
            )
            .order_by(JobStatus.id.desc())
            .limit(1)
        )
        if active_job is not None:
            raise ValueError(
                f"Seed job {active_job.job_id} is already running; concurrent seed jobs are blocked."
            )

    def _create_job_status(
        self,
        session: Session,
        *,
        job_type: str,
        initial_phase: str,
        initial_message: str,
    ) -> JobStatus:
        job = JobStatus(
            job_type=job_type,
            job_id=f"{job_type}-{uuid4().hex[:8]}",
            status="pending",
            current_phase=initial_phase,
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
    ) -> JobStageProgress:
        stage_row = JobStageProgress(
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
        session.add(stage_row)
        session.flush()
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

    def _fail_incomplete_stages(self, *stage_rows: JobStageProgress) -> None:
        for stage_row in stage_rows:
            if stage_row.status in {"succeeded", "failed"}:
                continue
            self._update_stage_progress(
                stage_row,
                status="failed",
                progress_current=stage_row.progress_current or 0,
                progress_total=stage_row.progress_total or 1,
                progress_message=stage_row.progress_message or "Stage failed.",
                metadata=stage_row.metadata_json if isinstance(stage_row.metadata_json, dict) else None,
            )
            stage_row.error_message = "Stage failed."

    def _overall_percent_complete(self, session: Session, job_status_id: int) -> Decimal:
        total_rows = session.scalar(
            select(func.count()).select_from(JobStageProgress).where(
                JobStageProgress.job_status_id == job_status_id
            )
        ) or 0
        if total_rows == 0:
            return Decimal("0.00")
        completed_rows = session.scalar(
            select(func.count()).select_from(JobStageProgress).where(
                JobStageProgress.job_status_id == job_status_id,
                JobStageProgress.status == "succeeded",
            )
        ) or 0
        return (Decimal(completed_rows) * Decimal("100.00")) / Decimal(total_rows)

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
    configured = raw_config.get("supported_datasets", []) if isinstance(raw_config, dict) else []
    configured_set = {item for item in configured if isinstance(item, str)}
    return tuple(dataset for dataset in RAW_DATASET_ORDER if dataset in configured_set)


def _normalization_datasets_from_raw(raw_datasets: tuple[str, ...]) -> tuple[str, ...]:
    raw_dataset_set = set(raw_datasets)
    return tuple(
        dataset
        for dataset in NORMALIZATION_ORDER
        if raw_dataset_set.intersection(NORMALIZATION_REQUIREMENTS[dataset])
    )


def _percent(current: int, total: int) -> Decimal:
    if total <= 0:
        return Decimal("0.00")
    return (Decimal(current) * Decimal("100.00")) / Decimal(total)


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)
