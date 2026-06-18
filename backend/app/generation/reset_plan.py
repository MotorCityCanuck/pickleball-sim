"""Shared runtime reset-domain classification for orchestration workflows."""
from __future__ import annotations

from dataclasses import dataclass

from app.models import (
    BatchRun,
    Club,
    ClubMembership,
    ConfigurationProfile,
    ConfigurationProfileVersion,
    ExportRun,
    FirstName,
    GenerationRun,
    GenerationRuntimeMetric,
    JobStageProgress,
    JobStatus,
    LastName,
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
    RawFirstName,
    RawLastName,
    RawMetroArea,
    RawPickleballClubDistribution,
    RawPickleballClubName,
    RawSeedLoadError,
    RawSeedLoadRun,
    RawStateProvBias,
    Region,
    StudentDatasetRelease,
    StudentDatasetReleaseFile,
    Team,
    TeamLifecycleEvent,
    TeamMembership,
    Tournament,
    TournamentDivisionResult,
    TournamentEvent,
    TournamentGroupResult,
    TournamentOfficialGame,
    TournamentOfficialMatch,
    TournamentSimulationRun,
    TournamentStudentGroup,
    TournamentSubmission,
    TournamentTeamResult,
    UploadedFile,
    ValidationResult,
)


@dataclass(frozen=True)
class ResetDomainPlan:
    """Runtime table classification for one reset domain."""

    domain_key: str
    label: str
    preserve_by_default: bool
    models: tuple[type[object], ...]


CONTROL_PLANE_PRESERVED_MODELS = (
    ConfigurationProfile,
    ConfigurationProfileVersion,
    JobStatus,
    JobStageProgress,
    GenerationRuntimeMetric,
    GenerationRun,
    MonthlyBatch,
    BatchRun,
    ValidationResult,
    ExportRun,
    StudentDatasetRelease,
    StudentDatasetReleaseFile,
    UploadedFile,
)

REFERENCE_SEED_REBUILDABLE_MODELS = (
    Region,
    Club,
    FirstName,
    LastName,
)

RAW_SEED_HISTORY_PRESERVED_MODELS = (
    RawSeedLoadRun,
    RawSeedLoadError,
)

RAW_SEED_STAGING_REBUILDABLE_MODELS = (
    RawMetroArea,
    RawPickleballClubName,
    RawPickleballClubDistribution,
    RawFirstName,
    RawLastName,
    RawStateProvBias,
)

GENERATED_OPERATIONAL_REBUILDABLE_MODELS = (
    TournamentOfficialGame,
    TournamentOfficialMatch,
    TournamentDivisionResult,
    TournamentGroupResult,
    TournamentTeamResult,
    TournamentSimulationRun,
    TournamentSubmission,
    TournamentStudentGroup,
    TournamentEvent,
    RatingsUpdateLog,
    PlayerRatingHistory,
    PlayerAssessmentHistory,
    MatchTeamPlayer,
    MatchGame,
    MatchTeam,
    Match,
    TeamLifecycleEvent,
    TeamMembership,
    Team,
    ClubMembership,
    PlayerRegistration,
    Player,
    Tournament,
)

RESET_DOMAIN_PLANS = (
    ResetDomainPlan(
        domain_key="control_plane",
        label="Control and configuration history",
        preserve_by_default=True,
        models=CONTROL_PLANE_PRESERVED_MODELS,
    ),
    ResetDomainPlan(
        domain_key="reference_seed",
        label="Reference and seed-derived production data",
        preserve_by_default=False,
        models=REFERENCE_SEED_REBUILDABLE_MODELS,
    ),
    ResetDomainPlan(
        domain_key="raw_seed_history",
        label="Raw seed load history",
        preserve_by_default=True,
        models=RAW_SEED_HISTORY_PRESERVED_MODELS,
    ),
    ResetDomainPlan(
        domain_key="raw_seed_staging",
        label="Raw seed staging data",
        preserve_by_default=False,
        models=RAW_SEED_STAGING_REBUILDABLE_MODELS,
    ),
    ResetDomainPlan(
        domain_key="generated_operational",
        label="Generated synthetic operational data",
        preserve_by_default=False,
        models=GENERATED_OPERATIONAL_REBUILDABLE_MODELS,
    ),
)

RESET_MODELS_BY_DOMAIN = {
    domain.domain_key: domain.models for domain in RESET_DOMAIN_PLANS
}
