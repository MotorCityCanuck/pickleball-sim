"""Division-level round-robin simulation."""
from __future__ import annotations

import random

from .config import TournamentSimulationConfig
from .dtos import DivisionResult, TournamentDivision
from .match_simulator import simulate_tournament_match
from .results_summary import summarize_standings
from .round_robin import round_robin_pairings


def simulate_division_round_robin(
    division: TournamentDivision,
    *,
    config: TournamentSimulationConfig,
    rng: random.Random | None = None,
) -> DivisionResult:
    """Simulate a full division round robin entirely in memory."""
    active_rng = rng or random.Random(config.seed)
    matches = tuple(
        simulate_tournament_match(
            active_rng,
            team_one=team_one,
            team_two=team_two,
            config=config,
        )
        for team_one, team_two in round_robin_pairings(division.entries)
    )
    return DivisionResult(
        slot=division.slot,
        standings=summarize_standings(
            entries=division.entries,
            matches=matches,
            seed=config.seed,
        ),
        matches=matches,
    )
