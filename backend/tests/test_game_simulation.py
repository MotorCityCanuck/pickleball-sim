"""Tests for pure game simulation DTOs."""
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
import random
import sys


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.generators.games import (  # noqa: E402
    GeneratedGames,
    SimulatedGameResult,
    SimulatedMatchGames,
    generate_match_games,
    simulate_match_games,
)
from app.models import Match, MatchGame  # noqa: E402


@dataclass(frozen=True)
class StubGameConfig:
    games_per_match: dict[str, int]
    game_target_score: int = 11
    win_by_two_rule_enabled: bool = False
    win_by_two_extension_rate: Decimal = Decimal("0")
    score_noise_std_dev: Decimal = Decimal("1")
    upset_probability_boost: Decimal = Decimal("0")


def test_simulate_match_games_returns_pure_dtos_without_orm():
    result = simulate_match_games(
        random.Random(3),
        expected_team_one_win_probability=Decimal("0.7500"),
        match_type="tournament",
        config=StubGameConfig(games_per_match={"tournament": 3}),
    )

    assert isinstance(result, SimulatedMatchGames)
    assert len(result.games) == 3
    assert result.team_one_games_won + result.team_two_games_won == 3
    assert all(isinstance(game, SimulatedGameResult) for game in result.games)
    assert all(not isinstance(game, MatchGame) for game in result.games)
    assert [game.game_number for game in result.games] == [1, 2, 3]
    assert all(game.expected_team_one_score_share == Decimal("0.7500") for game in result.games)


def test_generate_match_games_keeps_monthly_orm_adapter_contract():
    match = Match(
        id=42,
        match_date=date(2024, 1, 1),
        match_type="tournament",
        batch_id=1,
    )

    result = generate_match_games(
        random.Random(3),
        match=match,
        expected_team_one_win_probability=Decimal("0.7500"),
        match_type="tournament",
        config=StubGameConfig(games_per_match={"tournament": 3}),
    )

    assert isinstance(result, GeneratedGames)
    assert len(result.games) == 3
    assert all(isinstance(game, MatchGame) for game in result.games)
    assert {game.match_id for game in result.games} == {42}
