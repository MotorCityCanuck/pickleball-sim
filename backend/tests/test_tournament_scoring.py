"""Tests for tournament standings tie-breaks and student scoring."""
from datetime import date
from decimal import Decimal
from pathlib import Path
import sys


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.generators.games import SimulatedMatchGames  # noqa: E402
from app.generators.match_outcome_probabilities import (  # noqa: E402
    hidden_adjusted_win_probability,
)
from app.tournament_simulation import (  # noqa: E402
    DivisionResult,
    PortfolioSlot,
    TournamentScoringConfig,
    TournamentTeamEntry,
    score_student_groups,
)
from app.tournament_simulation.dtos import TournamentMatchResult  # noqa: E402
from app.tournament_simulation.results_summary import summarize_standings  # noqa: E402


def test_head_to_head_breaks_two_team_match_win_tie():
    teams = tuple(_team(team_id) for team_id in [1, 2, 3, 4])
    matches = (
        _match(1, 2, winner=1),
        _match(1, 3, winner=1),
        _match(1, 4, winner=4),
        _match(2, 3, winner=2),
        _match(2, 4, winner=4),
        _match(3, 4, winner=4),
    )

    standings = summarize_standings(entries=teams, matches=matches, seed=7)

    assert [standing.team_id for standing in standings] == [4, 1, 2, 3]


def test_game_differential_breaks_three_team_circular_tie():
    teams = tuple(_team(team_id) for team_id in [1, 2, 3])
    matches = (
        _match(1, 2, winner=1, one_games=2, two_games=0),
        _match(2, 3, winner=2, one_games=2, two_games=1),
        _match(1, 3, winner=3, one_games=1, two_games=2),
    )

    standings = summarize_standings(entries=teams, matches=matches, seed=7)

    assert [standing.team_id for standing in standings] == [1, 3, 2]
    assert [standing.game_differential for standing in standings] == [1, 0, -1]


def test_point_differential_breaks_remaining_tie():
    teams = tuple(_team(team_id) for team_id in [1, 2, 3])
    matches = (
        _match(1, 2, winner=1, one_games=2, two_games=1, one_points=33, two_points=25),
        _match(2, 3, winner=2, one_games=2, two_games=1, one_points=33, two_points=20),
        _match(1, 3, winner=3, one_games=1, two_games=2, one_points=20, two_points=33),
    )

    standings = summarize_standings(entries=teams, matches=matches, seed=7)

    assert [standing.team_id for standing in standings] == [2, 3, 1]
    assert [standing.point_differential for standing in standings] == [5, 0, -5]


def test_seeded_tiebreak_is_reproducible():
    teams = tuple(_team(team_id) for team_id in [1, 2, 3])
    matches = (
        _match(1, 2, winner=1, one_games=2, two_games=1, one_points=30, two_points=30),
        _match(2, 3, winner=2, one_games=2, two_games=1, one_points=30, two_points=30),
        _match(1, 3, winner=3, one_games=1, two_games=2, one_points=30, two_points=30),
    )

    first = summarize_standings(entries=teams, matches=matches, seed=42)
    second = summarize_standings(entries=teams, matches=matches, seed=42)

    assert first == second


def test_score_student_groups_credits_duplicate_selected_teams():
    result = DivisionResult(
        slot=PortfolioSlot(country_code="US", division="mens"),
        standings=(
            _standing(team_id=10, rank=1, wins=2, group_ids=(1, 2)),
            _standing(team_id=20, rank=2, wins=1, group_ids=(3,)),
        ),
        matches=(),
    )

    scores = score_student_groups(
        (result,),
        config=TournamentScoringConfig(
            champion_points=Decimal("10"),
            runner_up_points=Decimal("5"),
            match_win_points=Decimal("2"),
        ),
    )

    assert [(score.group_id, score.score) for score in scores] == [
        (1, Decimal("14")),
        (2, Decimal("14")),
        (3, Decimal("7")),
    ]


def _standing(*, team_id: int, rank: int, wins: int, group_ids: tuple[int, ...]):
    from app.tournament_simulation import TeamStanding

    return TeamStanding(
        team_id=team_id,
        rank=rank,
        match_wins=wins,
        match_losses=0,
        games_won=0,
        games_lost=0,
        points_for=0,
        points_against=0,
        game_differential=0,
        point_differential=0,
        selected_by_group_ids=group_ids,
    )


def _match(
    team_one_id: int,
    team_two_id: int,
    *,
    winner: int,
    one_games: int = 2,
    two_games: int = 1,
    one_points: int = 33,
    two_points: int = 30,
) -> TournamentMatchResult:
    probability = hidden_adjusted_win_probability(
        _team(team_one_id),
        _team(team_two_id),
        match_date=date(2025, 1, 1),
        hidden_bias_config=_DisabledHiddenConfig(),
        apply_hidden_bias=False,
    )
    return TournamentMatchResult(
        team_one_id=team_one_id,
        team_two_id=team_two_id,
        winning_team_id=winner,
        losing_team_id=team_two_id if winner == team_one_id else team_one_id,
        team_one_games_won=one_games,
        team_two_games_won=two_games,
        team_one_points=one_points,
        team_two_points=two_points,
        probability=probability,
        games=SimulatedMatchGames(one_games, two_games, ()),
    )


def _team(team_id: int) -> TournamentTeamEntry:
    return TournamentTeamEntry(
        id=team_id,
        country_code="US",
        division="mens",
        average_rating=Decimal("1500"),
    )


class _DisabledHiddenConfig:
    enabled = False
