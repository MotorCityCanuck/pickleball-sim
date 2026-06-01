"""Service entrypoint for building student-facing dataset releases."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.orm import Session

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
