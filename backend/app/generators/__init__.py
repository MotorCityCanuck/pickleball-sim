"""Synthetic data generation modules."""

from .club_memberships import (
    ClubMembershipGenerationConfig,
    ClubMembershipGenerationResult,
    ClubMembershipGenerator,
)
from .games import (
    GeneratedGames,
    SimulatedGameResult,
    SimulatedMatchGames,
    generate_match_games,
    simulate_match_games,
)
from .matches import (
    MatchGenerationConfig,
    MatchGenerationProgress,
    MatchGenerationResult,
    MatchGenerator,
)
from .match_outcome_probabilities import (
    HiddenAdjustedWinProbability,
    TeamProbabilityInput,
    hidden_adjusted_win_probability,
    monthly_hidden_adjusted_win_probability,
    tournament_hidden_adjusted_win_probability,
)
from .players import PlayerGenerator, PlayerGenerationResult
from .ratings import RatingUpdateConfig, RatingUpdateGenerator, RatingUpdateResult
from .teams import TeamFormationConfig, TeamGenerationResult, TeamGenerator
from .team_identity import TeamIdentityRegistry, TeamIdentityRecord, player_pair_key

__all__ = [
    "ClubMembershipGenerationConfig",
    "ClubMembershipGenerationResult",
    "ClubMembershipGenerator",
    "GeneratedGames",
    "HiddenAdjustedWinProbability",
    "MatchGenerationConfig",
    "MatchGenerationProgress",
    "MatchGenerationResult",
    "MatchGenerator",
    "PlayerGenerationResult",
    "PlayerGenerator",
    "RatingUpdateConfig",
    "RatingUpdateGenerator",
    "RatingUpdateResult",
    "SimulatedGameResult",
    "SimulatedMatchGames",
    "TeamProbabilityInput",
    "TeamFormationConfig",
    "TeamGenerationResult",
    "TeamIdentityRecord",
    "TeamIdentityRegistry",
    "TeamGenerator",
    "generate_match_games",
    "hidden_adjusted_win_probability",
    "monthly_hidden_adjusted_win_probability",
    "player_pair_key",
    "simulate_match_games",
    "tournament_hidden_adjusted_win_probability",
]
