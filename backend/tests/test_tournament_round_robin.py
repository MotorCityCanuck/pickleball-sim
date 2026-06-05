"""Tests for pure tournament round-robin simulation."""
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
import random
import sys


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.default_configuration import DEFAULT_CONFIG_PAYLOAD  # noqa: E402
from app.generators.matches import MatchGenerationConfig  # noqa: E402
from app.tournament_simulation import (  # noqa: E402
    PortfolioSlot,
    TournamentDivision,
    TournamentSimulationConfig,
    TournamentTeamEntry,
    build_division_from_submissions,
    round_robin_pairings,
    simulate_division_round_robin,
)


@dataclass(frozen=True)
class StubGameConfig:
    games_per_match: dict[str, int]
    game_target_score: int = 11
    win_by_two_rule_enabled: bool = False
    win_by_two_extension_rate: Decimal = Decimal("0")
    score_noise_std_dev: Decimal = Decimal("1")
    upset_probability_boost: Decimal = Decimal("0")


def test_round_robin_pairings_generate_unique_pairs():
    entries = tuple(_team(team_id) for team_id in [3, 1, 2, 4])

    pairings = round_robin_pairings(entries)

    assert len(pairings) == 6
    assert [(one.id, two.id) for one, two in pairings] == [
        (1, 2),
        (1, 3),
        (1, 4),
        (2, 3),
        (2, 4),
        (3, 4),
    ]


def test_build_division_collapses_duplicate_team_submissions_and_preserves_credit():
    slot = PortfolioSlot(country_code="US", division="mens")
    teams = {team_id: _team(team_id) for team_id in [10, 20]}

    division = build_division_from_submissions(
        slot=slot,
        submissions_by_group_id={1: 10, 2: 10, 3: 20},
        teams_by_id=teams,
    )

    assert [entry.id for entry in division.entries] == [10, 20]
    assert division.entries[0].selected_by_group_ids == (1, 2)
    assert division.entries[1].selected_by_group_ids == (3,)


def test_build_division_rejects_team_for_wrong_slot():
    slot = PortfolioSlot(country_code="CA", division="mens")

    try:
        build_division_from_submissions(
            slot=slot,
            submissions_by_group_id={1: 10},
            teams_by_id={10: _team(10, country_code="US")},
        )
    except ValueError as exc:
        assert "does not match portfolio slot" in str(exc)
    else:
        raise AssertionError("expected wrong-slot submission to fail")


def test_simulate_division_round_robin_is_deterministic_for_fixed_seed():
    division = TournamentDivision(
        slot=PortfolioSlot(country_code="US", division="mens"),
        entries=tuple(_team(team_id, average_rating=Decimal(1500 + team_id)) for team_id in [1, 2, 3]),
    )
    config = _simulation_config(seed=22)

    first = simulate_division_round_robin(
        division,
        config=config,
        rng=random.Random(config.seed),
    )
    second = simulate_division_round_robin(
        division,
        config=config,
        rng=random.Random(config.seed),
    )

    assert first == second
    assert len(first.matches) == 3
    assert [standing.rank for standing in first.standings] == [1, 2, 3]
    assert all(match.probability.applied_hidden_bias for match in first.matches)


def _simulation_config(*, seed: int) -> TournamentSimulationConfig:
    payload = {
        **DEFAULT_CONFIG_PAYLOAD,
        "hidden_performance_bias": {
            **DEFAULT_CONFIG_PAYLOAD["hidden_performance_bias"],
            "enabled": False,
            "age_advantage": {
                **DEFAULT_CONFIG_PAYLOAD["hidden_performance_bias"]["age_advantage"],
                "enabled": True,
                "max_rating_points": 25,
                "points_per_year_gap": 1,
            },
        },
    }
    match_config = MatchGenerationConfig.from_payload(payload)
    return TournamentSimulationConfig(
        match_date=date(2025, 1, 15),
        game_config=StubGameConfig(games_per_match={"tournament": 3}),
        hidden_bias_config=match_config.hidden_performance_bias,
        seed=seed,
    )


def _team(
    team_id: int,
    *,
    country_code: str = "US",
    division: str = "mens",
    average_rating: Decimal = Decimal("1500"),
) -> TournamentTeamEntry:
    return TournamentTeamEntry(
        id=team_id,
        country_code=country_code,
        division=division,
        average_rating=average_rating,
        avg_age=Decimal(30 + team_id),
    )
