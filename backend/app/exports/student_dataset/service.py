"""Service entrypoint for building student-facing dataset releases."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
import logging
from pathlib import Path
import shutil
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.exports.data_quality import normalize_data_quality_level
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


logger = logging.getLogger("uvicorn.error")


@dataclass(frozen=True)
class StudentDatasetBuildResult:
    """Result of a complete student dataset build and promotion."""

    build_parameters: StudentDatasetBuildParameters
    release_windows: tuple[StudentDatasetReleaseWindow, ...]
    staged_family: StagedStudentDatasetFamily
    published_family: PublishedStudentDatasetFamily
    clean_staged_family: StagedStudentDatasetFamily | None = None
    clean_published_family: PublishedStudentDatasetFamily | None = None


@dataclass(frozen=True)
class StudentDatasetExportRegistration:
    """Pending student dataset export job created before background execution."""

    job_status: JobStatus


class StudentDatasetExportPreflightError(ValueError):
    """Raised when export preflight checks fail before file generation begins."""


class StudentDatasetExportService:
    """Operator-facing service for student dataset export jobs."""

    RELEASE_FAMILY_MODE = "baseline_plus_monthly_incrementals"

    def register_export_job(
        self,
        *,
        session: Session,
        generation_run_id: int,
        initial_history_month_count: int,
        subsequent_month_count: int,
        output_root: Path,
        release_name: str,
        data_quality_level: str = "none",
        clean_subfolder: str = "clean",
        tainted_subfolder: str = "tainted",
        overwrite_existing: bool = False,
    ) -> StudentDatasetExportRegistration:
        """Create a pending export job and progress rows."""

        self._ensure_no_active_export_job(session)
        normalized_level = normalize_data_quality_level(data_quality_level)
        planned_release_count = 1 + subsequent_month_count
        release_folder_count = planned_release_count * (
            2 if normalized_level != "none" else 1
        )
        job_status = JobStatus(
            job_type="student_dataset_export",
            job_id=f"student-dataset-export-{generation_run_id}-{uuid4().hex[:8]}",
            status="pending",
            current_phase="queued",
            percent_complete=Decimal("0.00"),
            current_message="Queued student dataset baseline and incremental export.",
        )
        session.add(job_status)
        session.flush()
        for sequence, stage_name, total, unit in (
            (1, "preflight", 1, "check"),
            (2, "write_validate_parquet", release_folder_count, "release_folder"),
            (3, "promote_metadata", release_folder_count, "release_folder"),
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
                        "release_family_mode": self.RELEASE_FAMILY_MODE,
                        "baseline_month_count": initial_history_month_count,
                        "incremental_month_count": subsequent_month_count,
                        "output_root": str(output_root),
                        "release_name": release_name,
                        "data_quality_level": normalized_level,
                        "clean_subfolder": clean_subfolder,
                        "tainted_subfolder": tainted_subfolder,
                        "overwrite_existing": overwrite_existing,
                        "release_folder_count": release_folder_count,
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
        data_quality_level: str = "none",
        clean_subfolder: str = "clean",
        tainted_subfolder: str = "tainted",
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
                clean_subfolder=clean_subfolder,
                tainted_subfolder=tainted_subfolder,
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
        data_quality_level: str = "none",
        clean_subfolder: str = "clean",
        tainted_subfolder: str = "tainted",
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
            normalized_level = normalize_data_quality_level(data_quality_level)
            clean_subfolder = _validate_output_subfolder("clean_subfolder", clean_subfolder)
            tainted_subfolder = _validate_output_subfolder("tainted_subfolder", tainted_subfolder)
            if clean_subfolder == tainted_subfolder:
                raise StudentDatasetExportPreflightError(
                    "Clean and tainted output subfolders must be different."
                )
            build_parameters = StudentDatasetBuildParameters(
                generation_run_id=generation_run_id,
                initial_history_month_count=initial_history_month_count,
                subsequent_month_count=subsequent_month_count,
                output_root=output_root,
                release_name=release_name,
                data_quality_level=normalized_level,
                overwrite_existing=overwrite_existing,
            )
            paired_output_root = (
                _timestamped_paired_output_root(
                    output_root=output_root,
                    release_name=release_name,
                    timestamp=datetime.now(timezone.utc),
                )
                if normalized_level != "none"
                else None
            )
            self._set_job_status(
                job_status,
                status="running",
                phase="preflight",
                message="Validating generation run, baseline/incremental plan, and output location.",
                percent_complete=Decimal("0.00"),
                started=True,
            )
            self._mark_stage(
                session,
                job_status_id=job_status.id,
                stage_name="preflight",
                status="running",
                current=0,
                message="Validating generation run, baseline/incremental plan, and output location.",
            )
            self._checkpoint(session, checkpoint)

            self._prepare_output_roots(
                build_parameters,
                clean_subfolder=clean_subfolder,
                tainted_subfolder=tainted_subfolder,
                paired_output_root=paired_output_root,
            )
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
                message=f"Planned {len(release_windows)} baseline/incremental release folder(s).",
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

            clean_staged_family = None
            clean_published_family = None
            if normalized_level == "none":
                logger.info(
                    "Student dataset export phase_start phase=clean_only_write_validate generation_run_id=%s release_name=%s data_quality_level=%s",
                    generation_run_id,
                    release_name,
                    normalized_level,
                )
                staged_family = write_staged_release_family(
                    session=session,
                    output_root=output_root,
                    release_name=release_name,
                    release_windows=release_windows,
                    build_parameters=build_parameters,
                    job_status_id=job_status.id,
                    progress_callback=lambda release_id, current, total: self._advance_stage_progress(
                        session=session,
                        checkpoint=checkpoint,
                        job_status=job_status,
                        stage_name="write_validate_parquet",
                        current=current,
                        total=total,
                        message=f"Wrote and validated release folder {current} of {total}: {release_id}.",
                    ),
                    activity_callback=lambda message: self._heartbeat_stage(
                        session=session,
                        checkpoint=checkpoint,
                        job_status=job_status,
                        stage_name="write_validate_parquet",
                        message=message,
                    ),
                )
                logger.info(
                    "Student dataset export phase_end phase=clean_only_write_validate generation_run_id=%s release_name=%s staged_root=%s release_count=%s",
                    generation_run_id,
                    release_name,
                    staged_family.staging_root,
                    len(staged_family.releases),
                )
            else:
                assert paired_output_root is not None
                clean_build_parameters = StudentDatasetBuildParameters(
                    generation_run_id=generation_run_id,
                    initial_history_month_count=initial_history_month_count,
                    subsequent_month_count=subsequent_month_count,
                    output_root=paired_output_root,
                    release_name=release_name,
                    data_quality_level="none",
                    overwrite_existing=overwrite_existing,
                    final_root=paired_output_root / clean_subfolder,
                )
                build_parameters = StudentDatasetBuildParameters(
                    generation_run_id=generation_run_id,
                    initial_history_month_count=initial_history_month_count,
                    subsequent_month_count=subsequent_month_count,
                    output_root=paired_output_root,
                    release_name=release_name,
                    data_quality_level=normalized_level,
                    overwrite_existing=overwrite_existing,
                    final_root=paired_output_root / tainted_subfolder,
                )
                logger.info(
                    "Student dataset export phase_start phase=clean_write_validate generation_run_id=%s release_name=%s data_quality_level=%s output_root=%s",
                    generation_run_id,
                    release_name,
                    clean_build_parameters.data_quality_level,
                    clean_build_parameters.output_root,
                )
                clean_staged_family = write_staged_release_family(
                    session=session,
                    output_root=paired_output_root,
                    release_name=release_name,
                    release_windows=release_windows,
                    build_parameters=clean_build_parameters,
                    job_status_id=job_status.id,
                    progress_callback=lambda release_id, current, total: self._advance_stage_progress(
                        session=session,
                        checkpoint=checkpoint,
                        job_status=job_status,
                        stage_name="write_validate_parquet",
                        current=current,
                        total=total * 2,
                        message=f"Wrote and validated clean release folder {current} of {total * 2}: {release_id}.",
                    ),
                    activity_callback=lambda message: self._heartbeat_stage(
                        session=session,
                        checkpoint=checkpoint,
                        job_status=job_status,
                        stage_name="write_validate_parquet",
                        message=message,
                    ),
                )
                logger.info(
                    "Student dataset export phase_end phase=clean_write_validate generation_run_id=%s release_name=%s staged_root=%s release_count=%s",
                    generation_run_id,
                    release_name,
                    clean_staged_family.staging_root,
                    len(clean_staged_family.releases),
                )
                logger.info(
                    "Student dataset export phase_start phase=tainted_write_validate generation_run_id=%s release_name=%s data_quality_level=%s output_root=%s",
                    generation_run_id,
                    release_name,
                    build_parameters.data_quality_level,
                    build_parameters.output_root,
                )
                staged_family = write_staged_release_family(
                    session=session,
                    output_root=paired_output_root,
                    release_name=release_name,
                    release_windows=release_windows,
                    build_parameters=build_parameters,
                    job_status_id=job_status.id,
                    progress_callback=lambda release_id, current, total: self._advance_stage_progress(
                        session=session,
                        checkpoint=checkpoint,
                        job_status=job_status,
                        stage_name="write_validate_parquet",
                        current=total + current,
                        total=total * 2,
                        message=f"Wrote and validated tainted release folder {total + current} of {total * 2}: {release_id}.",
                    ),
                    activity_callback=lambda message: self._heartbeat_stage(
                        session=session,
                        checkpoint=checkpoint,
                        job_status=job_status,
                        stage_name="write_validate_parquet",
                        message=message,
                    ),
                )
                logger.info(
                    "Student dataset export phase_end phase=tainted_write_validate generation_run_id=%s release_name=%s staged_root=%s release_count=%s",
                    generation_run_id,
                    release_name,
                    staged_family.staging_root,
                    len(staged_family.releases),
                )
            self._mark_stage(
                session,
                job_status_id=job_status.id,
                stage_name="write_validate_parquet",
                status="succeeded",
                current=self._stage_total(
                    session,
                    job_status_id=job_status.id,
                    stage_name="write_validate_parquet",
                ),
                message=(
                    f"Validated {len(staged_family.releases)} tainted and "
                    f"{len(clean_staged_family.releases)} clean release folder(s)."
                    if clean_staged_family is not None
                    else f"Validated {len(staged_family.releases)} release folder(s)."
                ),
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

            if clean_staged_family is not None:
                logger.info(
                    "Student dataset export phase_start phase=clean_promote generation_run_id=%s release_name=%s final_root=%s",
                    generation_run_id,
                    release_name,
                    clean_build_parameters.final_root,
                )
                clean_published_family = promote_staged_release_family(
                    session=session,
                    staged_family=clean_staged_family,
                    build_parameters=clean_build_parameters,
                    progress_callback=lambda release_id, current, total: self._advance_stage_progress(
                        session=session,
                        checkpoint=checkpoint,
                        job_status=job_status,
                        stage_name="promote_metadata",
                        current=current,
                        total=total * 2,
                        message=f"Promoted clean release folder {current} of {total * 2}: {release_id}.",
                    ),
                )
                logger.info(
                    "Student dataset export phase_end phase=clean_promote generation_run_id=%s release_name=%s final_root=%s release_count=%s",
                    generation_run_id,
                    release_name,
                    clean_published_family.final_root,
                    len(clean_published_family.releases),
                )
            logger.info(
                "Student dataset export phase_start phase=tainted_promote generation_run_id=%s release_name=%s final_root=%s",
                generation_run_id,
                release_name,
                build_parameters.final_root,
            )
            published_family = promote_staged_release_family(
                session=session,
                staged_family=staged_family,
                build_parameters=build_parameters,
                progress_callback=lambda release_id, current, total: self._advance_stage_progress(
                    session=session,
                    checkpoint=checkpoint,
                    job_status=job_status,
                    stage_name="promote_metadata",
                    current=(total + current) if clean_published_family is not None else current,
                    total=total * 2 if clean_published_family is not None else total,
                    message=(
                        f"Promoted tainted release folder {total + current} of {total * 2}: {release_id}."
                        if clean_published_family is not None
                        else f"Promoted release folder {current} of {total}: {release_id}."
                    ),
                ),
            )
            logger.info(
                "Student dataset export phase_end phase=tainted_promote generation_run_id=%s release_name=%s final_root=%s release_count=%s",
                generation_run_id,
                release_name,
                published_family.final_root,
                len(published_family.releases),
            )
            if clean_published_family is not None:
                self._assert_published_family_has_files(clean_published_family)
            self._assert_published_family_has_files(published_family)
            self._mark_stage(
                session,
                job_status_id=job_status.id,
                stage_name="promote_metadata",
                status="succeeded",
                current=self._stage_total(
                    session,
                    job_status_id=job_status.id,
                    stage_name="promote_metadata",
                ),
                message=(
                    f"Published {len(published_family.releases)} tainted and "
                    f"{len(clean_published_family.releases)} clean release folder(s)."
                    if clean_published_family is not None
                    else f"Published {len(published_family.releases)} release folder(s)."
                ),
            )
            self._set_job_status(
                job_status,
                status="succeeded",
                phase="completed",
                message="Student dataset baseline and incremental export completed successfully.",
                percent_complete=Decimal("100.00"),
                completed=True,
            )
            self._checkpoint(session, checkpoint)
            return StudentDatasetBuildResult(
                build_parameters=build_parameters,
                release_windows=release_windows,
                staged_family=staged_family,
                published_family=published_family,
                clean_staged_family=clean_staged_family,
                clean_published_family=clean_published_family,
            )
        except Exception as exc:
            if not session.is_active:
                session.rollback()
                job_status = session.get(JobStatus, job_status_id)
                if job_status is None:
                    raise ValueError(f"Job status {job_status_id} does not exist.") from exc
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

    @staticmethod
    def _prepare_output_root(build_parameters: StudentDatasetBuildParameters) -> None:
        StudentDatasetExportService._prepare_final_root(
            build_parameters.final_root
            or build_parameters.output_root / build_parameters.release_name,
            overwrite_existing=build_parameters.overwrite_existing,
        )

    @staticmethod
    def _prepare_output_roots(
        build_parameters: StudentDatasetBuildParameters,
        *,
        clean_subfolder: str,
        tainted_subfolder: str,
        paired_output_root: Path | None = None,
    ) -> None:
        if build_parameters.data_quality_level == "none":
            StudentDatasetExportService._prepare_output_root(build_parameters)
            return
        paired_root = paired_output_root or (
            build_parameters.output_root / build_parameters.release_name
        )
        for final_root in (
            paired_root / clean_subfolder,
            paired_root / tainted_subfolder,
        ):
            StudentDatasetExportService._prepare_final_root(
                final_root,
                overwrite_existing=build_parameters.overwrite_existing,
            )

    @staticmethod
    def _prepare_final_root(final_root: Path, *, overwrite_existing: bool) -> None:
        if not final_root.exists():
            return
        if not overwrite_existing:
            raise StudentDatasetExportPreflightError(
                "Expected release folder already exists. Enable delete confirmation to remove it before export."
            )
        if not final_root.is_dir():
            raise StudentDatasetExportPreflightError(
                f"Expected release folder path is not a directory: {final_root}"
            )
        shutil.rmtree(final_root)

    @staticmethod
    def _assert_published_family_has_files(
        published_family: PublishedStudentDatasetFamily,
    ) -> None:
        if not published_family.final_root.is_dir():
            raise StudentDatasetExportPreflightError(
                f"Published release folder is missing: {published_family.final_root}"
            )
        for release in published_family.releases:
            if not release.release_dir.is_dir():
                raise StudentDatasetExportPreflightError(
                    f"Published release folder is missing: {release.release_dir}"
                )
            if not any(release.release_dir.glob("*.parquet")):
                raise StudentDatasetExportPreflightError(
                    f"Published release folder has no Parquet files: {release.release_dir}"
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

    def _advance_stage_progress(
        self,
        *,
        session: Session,
        checkpoint,
        job_status: JobStatus,
        stage_name: str,
        current: int,
        total: int,
        message: str,
    ) -> None:
        stage = self._get_stage(session, job_status_id=job_status.id, stage_name=stage_name)
        now = _utc_now()
        stage.status = "running"
        stage.started_at = stage.started_at or now
        stage.last_heartbeat_at = now
        stage.progress_total = total
        stage.progress_current = current
        stage.progress_percent = _percent(current, total)
        stage.progress_message = message
        self._set_job_status(
            job_status,
            status="running",
            phase=stage_name,
            message=message,
            percent_complete=overall_percent_complete(session, job_status.id),
        )
        self._checkpoint(session, checkpoint)

    def _heartbeat_stage(
        self,
        *,
        session: Session,
        checkpoint,
        job_status: JobStatus,
        stage_name: str,
        message: str,
    ) -> None:
        stage = self._get_stage(session, job_status_id=job_status.id, stage_name=stage_name)
        now = _utc_now()
        stage.status = "running"
        stage.started_at = stage.started_at or now
        stage.last_heartbeat_at = now
        stage.progress_message = message
        self._set_job_status(
            job_status,
            status="running",
            phase=stage_name,
            message=message,
            percent_complete=job_status.percent_complete,
        )
        self._checkpoint(session, checkpoint)

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

    def _stage_total(
        self,
        session: Session,
        *,
        job_status_id: int,
        stage_name: str,
    ) -> int:
        stage = self._get_stage(
            session,
            job_status_id=job_status_id,
            stage_name=stage_name,
        )
        return int(stage.progress_total or 1)

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
    data_quality_level: str = "none",
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
        data_quality_level=normalize_data_quality_level(data_quality_level),
        overwrite_existing=overwrite_existing,
    )
    StudentDatasetExportService._prepare_output_root(build_parameters)
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


def _validate_output_subfolder(field_name: str, value: str) -> str:
    cleaned = str(value or "").strip()
    if not cleaned:
        raise StudentDatasetExportPreflightError(f"{field_name} is required.")
    candidate = Path(cleaned)
    if candidate.is_absolute() or ".." in candidate.parts or len(candidate.parts) != 1:
        raise StudentDatasetExportPreflightError(
            f"{field_name} must be a single relative folder name."
        )
    if not all(character.isalnum() or character in {"_", "-"} for character in cleaned):
        raise StudentDatasetExportPreflightError(
            f"{field_name} may only contain letters, numbers, underscores, and hyphens."
        )
    return cleaned


def _timestamped_paired_output_root(
    *,
    output_root: Path,
    release_name: str,
    timestamp: datetime,
) -> Path:
    timestamp_utc = timestamp.astimezone(timezone.utc)
    return (
        output_root
        / release_name
        / f"{timestamp_utc:%Y%m%d}"
        / f"{timestamp_utc:%H%M%SZ}"
    )


def _percent(current: int, total: int) -> Decimal:
    if total <= 0:
        return Decimal("0.00")
    value = Decimal(current) * Decimal(100) / Decimal(total)
    return value.quantize(Decimal("0.01"))
