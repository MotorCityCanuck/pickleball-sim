"""Shared destructive reset helpers for generated synthetic data."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.models import (
    BatchRun,
    ClubMembership,
    ExportRun,
    JobStageProgress,
    Match,
    MatchGame,
    MatchTeam,
    MatchTeamPlayer,
    MonthlyBatch,
    Player,
    PlayerAssessmentHistory,
    PlayerRatingHistory,
    PlayerRegistration,
    RatingsUpdateLog,
    StudentDatasetRelease,
    StudentDatasetReleaseFile,
    Team,
    TeamMembership,
    Tournament,
    ValidationResult,
)


DELETE_MODELS_IN_ORDER = (
    JobStageProgress,
    StudentDatasetReleaseFile,
    StudentDatasetRelease,
    ValidationResult,
    ExportRun,
    BatchRun,
    RatingsUpdateLog,
    PlayerRatingHistory,
    PlayerAssessmentHistory,
    MatchTeamPlayer,
    MatchGame,
    MatchTeam,
    Match,
    TeamMembership,
    Team,
    ClubMembership,
    PlayerRegistration,
    Player,
    Tournament,
    MonthlyBatch,
)


@dataclass(frozen=True)
class ResetProgressEvent:
    """Structured progress event emitted while deleting generated data."""

    model_name: str
    model_label: str
    step_index: int
    total_steps: int
    status: str
    rows_affected: int | None = None


ResetProgressListener = Callable[[ResetProgressEvent], None]


def delete_generated_data(
    *,
    session: Session,
    preserve_job_status_id: int | None = None,
    progress_listener: ResetProgressListener | None = None,
) -> None:
    """Delete generated synthetic data while optionally preserving one job's stage rows."""
    total_steps = len(DELETE_MODELS_IN_ORDER)
    for index, model in enumerate(DELETE_MODELS_IN_ORDER, start=1):
        if progress_listener is not None:
            progress_listener(
                ResetProgressEvent(
                    model_name=model.__tablename__,
                    model_label=model.__name__,
                    step_index=index,
                    total_steps=total_steps,
                    status="running",
                )
            )
        statement = delete(model)
        if model is JobStageProgress and preserve_job_status_id is not None:
            statement = statement.where(
                JobStageProgress.job_status_id != preserve_job_status_id
            )
        result = session.execute(statement)
        if progress_listener is not None:
            progress_listener(
                ResetProgressEvent(
                    model_name=model.__tablename__,
                    model_label=model.__name__,
                    step_index=index,
                    total_steps=total_steps,
                    status="succeeded",
                    rows_affected=result.rowcount if result.rowcount is not None and result.rowcount >= 0 else None,
                )
            )
    session.flush()
