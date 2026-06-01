"""Service entrypoint for building student-facing dataset releases."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.generation.job_lifecycle import job_is_actively_processing, overall_percent_complete
from app.models import JobStageProgress, JobStatus

from .publisher import PublishedStudentDatasetFamily, promote_staged_release_family
from .release_windows import StudentDatasetReleaseWindow, plan_release_windows
from .writer import (
    DEFAULT_PARQUET_COMPRESSION,
    StagedStudentDatasetFamily,
    StudentDatasetBuildParameters,
    write_staged_release_family,
)


@dataclass(frozen=True)
class StudentDatasetBuildResult:
    """Result of a complete student dataset build and promotion."""

    build_parameters: StudentDatasetBuildParameters
    release_windows: tuple[StudentDatasetReleaseWindow, ...]
    staged_family: StagedStudentDatasetFamily
    published_family: PublishedStudentDatasetFamily


@dataclass(frozen=True)
class StudentDatasetExportRegistration:
    """Pending student dataset export job created before background execution."""

    job_status: JobStatus


class StudentDatasetExportService:
    """Operator-facing service for student dataset export jobs."""

    def register_export_job(
        self,
        *,
        session: Session,
        generation_run_id: int,
        initial_history_month_count: int,
        subsequent_month_count: int,
        output_root: Path,
        release_name: str,
        data_quality_level: str = "clean",
        overwrite_existing: bool = False,
    ) -> StudentDatasetExportRegistration:
        """Create a pending export job and progress rows."""

        self._ensure_no_active_export_job(session)
        job_status = JobStatus(
            job_type="student_dataset_export",
            job_id=f"student-dataset-export-{generation_run_id}-{uuid4().hex[:8]}",
            status="pending",
            current_phase="queued",
            percent_complete=Decimal("0.00"),
            current_message="Queued student dataset export.",
        )
        session.add(job_status)
        session.flush()
        for sequence, stage_name, total, unit in (
            (1, "preflight", 1, "check"),
            (2, "write_validate_parquet", 1, "release_family"),
            (3, "promote_metadata", 1, "release_family"),
        ):
            session.add(
                JobStageProgress(
                    job_status_id=job_status.id,
                    generation_run_id=generation_run_id,
                    batch_id=None,
                    stage_name=stage_name,
                    stage_sequence=sequence,
                    status="pending",
                    progress_current=0,
                    progress_total=total,
                    progress_unit=unit,
                    progress_percent=Decimal("0.00"),
                    progress_message="Pending.",
                    metadata_json={
                        "generation_run_id": generation_run_id,
                        "initial_history_month_count": initial_history_month_count,
                        "subsequent_month_count": subsequent_month_count,
                        "output_root": str(output_root),
                        "release_name": release_name,
                        "data_quality_level": data_quality_level,
                        "overwrite_existing": overwrite_existing,
                    },
                )
            )
        session.flush()
        return StudentDatasetExportRegistration(job_status=job_status)

    def execute_registered_export_in_background(
        self,
        *,
        job_status_id: int,
        generation_run_id: int,
        initial_history_month_count: int,
        subsequent_month_count: int,
        output_root: str,
        release_name: str,
        data_quality_level: str = "clean",
        overwrite_existing: bool = False,
    ) -> None:
        """Run a registered export job with durable background commits."""

        session = SessionLocal()
        try:
            self.execute_registered_export(
                session=session,
                job_status_id=job_status_id,
                generation_run_id=generation_run_id,
                initial_history_month_count=initial_history_month_count,
                subsequent_month_count=subsequent_month_count,
                output_root=Path(output_root),
                release_name=release_name,
                data_quality_level=data_quality_level,
                overwrite_existing=overwrite_existing,
                checkpoint=session.commit,
                re_raise=False,
            )
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def execute_registered_export(
        self,
        *,
        session: Session,
        job_status_id: int,
        generation_run_id: int,
        initial_history_month_count: int,
        subsequent_month_count: int,
        output_root: Path,
        release_name: str,
        data_quality_level: str = "clean",
        overwrite_existing: bool = False,
        checkpoint=None,
        re_raise: bool = True,
    ) -> StudentDatasetBuildResult | None:
        """Execute a registered student dataset export job."""

        job_status = session.get(JobStatus, job_status_id)
        if job_status is None:
            raise ValueError(f"Job status {job_status_id} does not exist.")
        if job_status.status != "pending":
            raise ValueError(
                f"Student dataset export job {job_status.job_id} is already {job_status.status}."
            )

        try:
            self._set_job_status(
                job_status,
                status="running",
                phase="preflight",
                message="Validating generation run and release window.",
                percent_complete=Decimal("0.00"),
                started=True,
            )
            self._mark_stage(
                session,
                job_status_id=job_status.id,
                stage_name="preflight",
                status="running",
                current=0,
                message="Validating generation run and release window.",
            )
            self._checkpoint(session, checkpoint)

            release_windows = plan_release_windows(
                session=session,
                generation_run_id=generation_run_id,
                initial_history_month_count=initial_history_month_count,
                subsequent_month_count=subsequent_month_count,
            )
            self._mark_stage(
                session,
                job_status_id=job_status.id,
                stage_name="preflight",
                status="succeeded",
                current=1,
                message=f"Planned {len(release_windows)} release window(s).",
            )

            build_parameters = StudentDatasetBuildParameters(
                generation_run_id=generation_run_id,
                initial_history_month_count=initial_history_month_count,
                subsequent_month_count=subsequent_month_count,
                output_root=output_root,
                release_name=release_name,
                data_quality_level=data_quality_level,
                overwrite_existing=overwrite_existing,
            )
            self._set_job_status(
                job_status,
                status="running",
                phase="write_validate_parquet",
                message="Writing staged Parquet files and validating with DuckDB.",
                percent_complete=overall_percent_complete(session, job_status.id),
            )
            self._mark_stage(
                session,
                job_status_id=job_status.id,
                stage_name="write_validate_parquet",
                status="running",
                current=0,
                message="Writing staged Parquet files and validating with DuckDB.",
            )
            self._checkpoint(session, checkpoint)

            staged_family = write_staged_release_family(
                session=session,
                output_root=output_root,
                release_name=release_name,
                release_windows=release_windows,
                build_parameters=build_parameters,
            )
            self._mark_stage(
                session,
                job_status_id=job_status.id,
                stage_name="write_validate_parquet",
                status="succeeded",
                current=1,
                message=f"Validated {len(staged_family.releases)} release folder(s).",
            )

            self._set_job_status(
                job_status,
                status="running",
                phase="promote_metadata",
                message="Promoting release folders and writing metadata.",
                percent_complete=overall_percent_complete(session, job_status.id),
            )
            self._mark_stage(
                session,
                job_status_id=job_status.id,
                stage_name="promote_metadata",
                status="running",
                current=0,
                message="Promoting release folders and writing metadata.",
            )
            self._checkpoint(session, checkpoint)

            published_family = promote_staged_release_family(
                session=session,
                staged_family=staged_family,
                build_parameters=build_parameters,
            )
            self._mark_stage(
                session,
                job_status_id=job_status.id,
                stage_name="promote_metadata",
                status="succeeded",
                current=1,
                message=f"Published {len(published_family.releases)} release folder(s).",
            )
            self._set_job_status(
                job_status,
                status="succeeded",
                phase="completed",
                message="Student dataset export completed successfully.",
                percent_complete=Decimal("100.00"),
                completed=True,
            )
            self._checkpoint(session, checkpoint)
            return StudentDatasetBuildResult(
                build_parameters=build_parameters,
                release_windows=release_windows,
                staged_family=staged_family,
                published_family=published_family,
            )
        except Exception as exc:
            self._fail_incomplete_stages(session, job_status.id, str(exc))
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
            return None

    def _ensure_no_active_export_job(self, session: Session) -> None:
        candidate_jobs = list(
            session.scalars(
                select(JobStatus)
                .where(
                    JobStatus.job_type == "student_dataset_export",
                    JobStatus.status.in_(("pending", "running")),
                )
                .order_by(JobStatus.id.desc())
            )
        )
        for job in candidate_jobs:
            if job_is_actively_processing(session, job):
                raise ValueError(
                    f"Student dataset export job {job.job_id} is already {job.status}."
                )

    def _mark_stage(
        self,
        session: Session,
        *,
        job_status_id: int,
        stage_name: str,
        status: str,
        current: int,
        message: str,
    ) -> None:
        stage = self._get_stage(session, job_status_id=job_status_id, stage_name=stage_name)
        now = _utc_now()
        stage.status = status
        stage.started_at = stage.started_at or now
        stage.last_heartbeat_at = now
        stage.progress_current = current
        stage.progress_percent = _percent(current, stage.progress_total or 1)
        stage.progress_message = message
        if status in {"succeeded", "failed"}:
            stage.completed_at = now
        if status == "failed":
            stage.error_message = message
        session.flush()

    def _get_stage(self, session: Session, *, job_status_id: int, stage_name: str) -> JobStageProgress:
        stage = session.scalar(
            select(JobStageProgress).where(
                JobStageProgress.job_status_id == job_status_id,
                JobStageProgress.stage_name == stage_name,
            )
        )
        if stage is None:
            raise ValueError(
                f"Missing job_stage_progress row for job={job_status_id}, stage={stage_name}."
            )
        return stage

    def _fail_incomplete_stages(
        self,
        session: Session,
        job_status_id: int,
        error_message: str,
    ) -> None:
        now = _utc_now()
        rows = session.scalars(
            select(JobStageProgress).where(
                JobStageProgress.job_status_id == job_status_id,
                JobStageProgress.status.in_(("pending", "running")),
            )
        )
        for row in rows:
            row.status = "failed"
            row.completed_at = now
            row.last_heartbeat_at = now
            row.error_message = error_message
        session.flush()

    @staticmethod
    def _set_job_status(
        job_status: JobStatus,
        *,
        status: str,
        phase: str,
        message: str,
        percent_complete: Decimal | None = None,
        started: bool = False,
        completed: bool = False,
    ) -> None:
        now = _utc_now()
        job_status.status = status
        job_status.current_phase = phase
        job_status.current_message = message
        job_status.updated_at = now
        if percent_complete is not None:
            job_status.percent_complete = percent_complete
        if started and job_status.started_at is None:
            job_status.started_at = now
        if completed:
            job_status.completed_at = now

    @staticmethod
    def _checkpoint(session: Session, checkpoint) -> None:
        session.flush()
        if checkpoint is not None:
            checkpoint()


def build_student_dataset_release(
    *,
    session: Session,
    generation_run_id: int,
    initial_history_month_count: int,
    subsequent_month_count: int,
    output_root: Path,
    release_name: str,
    data_quality_level: str = "clean",
    overwrite_existing: bool = False,
    compression: str = DEFAULT_PARQUET_COMPRESSION,
) -> StudentDatasetBuildResult:
    """Build, validate, promote, and persist a student dataset release family."""

    release_windows = plan_release_windows(
        session=session,
        generation_run_id=generation_run_id,
        initial_history_month_count=initial_history_month_count,
        subsequent_month_count=subsequent_month_count,
    )
    build_parameters = StudentDatasetBuildParameters(
        generation_run_id=generation_run_id,
        initial_history_month_count=initial_history_month_count,
        subsequent_month_count=subsequent_month_count,
        output_root=output_root,
        release_name=release_name,
        data_quality_level=data_quality_level,
        overwrite_existing=overwrite_existing,
    )
    staged_family = write_staged_release_family(
        session=session,
        output_root=output_root,
        release_name=release_name,
        release_windows=release_windows,
        build_parameters=build_parameters,
        compression=compression,
    )
    published_family = promote_staged_release_family(
        session=session,
        staged_family=staged_family,
        build_parameters=build_parameters,
    )
    return StudentDatasetBuildResult(
        build_parameters=build_parameters,
        release_windows=release_windows,
        staged_family=staged_family,
        published_family=published_family,
    )


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _percent(current: int, total: int) -> Decimal:
    if total <= 0:
        return Decimal("0.00")
    value = Decimal(current) * Decimal(100) / Decimal(total)
    return value.quantize(Decimal("0.01"))
