"""Configuration DTOs for pure tournament simulation."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any


@dataclass(frozen=True)
class TournamentSimulationConfig:
    """Settings needed to simulate tournament matches in memory."""

    match_date: date
    game_config: Any
    hidden_bias_config: Any
    seed: int = 1
    match_type: str = "tournament"


@dataclass(frozen=True)
class TournamentScoringConfig:
    """Student-group scoring settings for tournament results."""

    champion_points: Decimal = Decimal("10")
    runner_up_points: Decimal = Decimal("6")
    top_four_points: Decimal = Decimal("3")
    match_win_points: Decimal = Decimal("1")
    top_four_points_enabled: bool = False
