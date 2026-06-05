"""Plain DTOs for in-memory tournament simulation."""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from app.generators.games import SimulatedMatchGames
from app.generators.match_outcome_probabilities import HiddenAdjustedWinProbability


@dataclass(frozen=True, order=True)
class PortfolioSlot:
    """One required student portfolio slot."""

    country_code: str
    division: str


@dataclass(frozen=True)
class StudentGroup:
    """Student group participating in a tournament exercise."""

    id: int
    name: str


@dataclass(frozen=True)
class TournamentTeamEntry:
    """Team-like tournament entry independent from ORM models."""

    id: int
    country_code: str
    division: str
    average_rating: Decimal
    selected_by_group_ids: tuple[int, ...] = ()
    avg_age: Decimal | None = None
    region_name: str | None = None
    primary_club_ids: frozenset[int] = field(default_factory=frozenset)
    club_ids: frozenset[int] = field(default_factory=frozenset)
    team_total_prior_matches: int = 0
    recent_pair_counts: dict[tuple[int, int], int] = field(default_factory=dict)
    recent_game_count: int = 0


@dataclass(frozen=True)
class TournamentDivision:
    """One country/division round-robin field."""

    slot: PortfolioSlot
    entries: tuple[TournamentTeamEntry, ...]


@dataclass(frozen=True)
class TournamentMatchResult:
    """Pure result for one round-robin match."""

    team_one_id: int
    team_two_id: int
    winning_team_id: int
    losing_team_id: int
    team_one_games_won: int
    team_two_games_won: int
    team_one_points: int
    team_two_points: int
    probability: HiddenAdjustedWinProbability
    games: SimulatedMatchGames


@dataclass(frozen=True)
class TeamStanding:
    """Computed standing for one tournament team."""

    team_id: int
    rank: int
    match_wins: int
    match_losses: int
    games_won: int
    games_lost: int
    points_for: int
    points_against: int
    game_differential: int
    point_differential: int
    selected_by_group_ids: tuple[int, ...]


@dataclass(frozen=True)
class DivisionResult:
    """Completed in-memory result for one division."""

    slot: PortfolioSlot
    standings: tuple[TeamStanding, ...]
    matches: tuple[TournamentMatchResult, ...]


@dataclass(frozen=True)
class StudentGroupScore:
    """Student-group score derived from selected team outcomes."""

    group_id: int
    score: Decimal
    champion_count: int
    runner_up_count: int
    top_four_count: int
    match_wins: int
