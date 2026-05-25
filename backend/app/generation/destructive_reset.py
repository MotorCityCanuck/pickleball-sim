"""Shared destructive reset helpers for generated synthetic data."""
from __future__ import annotations

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


def delete_generated_data(
    *,
    session: Session,
    preserve_job_status_id: int | None = None,
) -> None:
    """Delete generated synthetic data while optionally preserving one job's stage rows."""
    for model in DELETE_MODELS_IN_ORDER:
        statement = delete(model)
        if model is JobStageProgress and preserve_job_status_id is not None:
            statement = statement.where(
                JobStageProgress.job_status_id != preserve_job_status_id
            )
        session.execute(statement)
    session.flush()
