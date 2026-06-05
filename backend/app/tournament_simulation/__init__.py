"""Pure in-memory tournament simulation engine."""

from .config import TournamentScoringConfig, TournamentSimulationConfig
from .dtos import (
    DivisionResult,
    PortfolioSlot,
    StudentGroup,
    StudentGroupScore,
    TeamStanding,
    TournamentDivision,
    TournamentMatchResult,
    TournamentTeamEntry,
)
from .monte_carlo import MonteCarloResult, run_monte_carlo
from .round_robin import build_division_from_submissions, round_robin_pairings
from .round_robin_simulator import simulate_division_round_robin
from .student_scoring import score_student_groups
from .team_loader import (
    SubmissionValidationIssue,
    TeamSubmission,
    ValidatedTournamentInput,
    latest_completed_source_batch,
    load_validated_tournament_input,
)

__all__ = [
    "DivisionResult",
    "MonteCarloResult",
    "PortfolioSlot",
    "StudentGroup",
    "StudentGroupScore",
    "TeamStanding",
    "SubmissionValidationIssue",
    "TeamSubmission",
    "TournamentDivision",
    "TournamentMatchResult",
    "TournamentScoringConfig",
    "TournamentSimulationConfig",
    "TournamentTeamEntry",
    "ValidatedTournamentInput",
    "build_division_from_submissions",
    "latest_completed_source_batch",
    "load_validated_tournament_input",
    "round_robin_pairings",
    "run_monte_carlo",
    "score_student_groups",
    "simulate_division_round_robin",
]
