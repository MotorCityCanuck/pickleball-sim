"""Tests for pure tournament Monte Carlo aggregation."""
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
import sys


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.default_configuration import DEFAULT_CONFIG_PAYLOAD  # noqa: E402
from app.generators.matches import MatchGenerationConfig  # noqa: E402
from app.tournament_simulation import (  # noqa: E402
    PortfolioSlot,
    TournamentDivision,
    TournamentScoringConfig,
    TournamentSimulationConfig,
    TournamentTeamEntry,
    run_monte_carlo,
)


@dataclass(frozen=True)
class StubGameConfig:
    games_per_match: dict[str, int]
    game_target_score: int = 11
    win_by_two_rule_enabled: bool = False
    win_by_two_extension_rate: Decimal = Decimal("0")
    score_noise_std_dev: Decimal = Decimal("1")
    upset_probability_boost: Decimal = Decimal("0.05")


def test_monte_carlo_aggregates_are_reproducible_for_fixed_seed():
    divisions = (
        TournamentDivision(
            slot=PortfolioSlot(country_code="US", division="mens"),
            entries=(
                _team(1, rating=Decimal("1700"), group_ids=(1,)),
                _team(2, rating=Decimal("1600"), group_ids=(2,)),
                _team(3, rating=Decimal("1500"), group_ids=(3,)),
            ),
        ),
    )
    simulation_config = _simulation_config(seed=99)
    scoring_config = TournamentScoringConfig()

    first = run_monte_carlo(
        divisions,
        simulation_config=simulation_config,
        scoring_config=scoring_config,
        iterations=20,
    )
    second = run_monte_carlo(
        divisions,
        simulation_config=simulation_config,
        scoring_config=scoring_config,
        iterations=20,
    )

    assert first == second
    assert first.iterations == 20
    assert {result.team_id for result in first.team_results} == {1, 2, 3}
    assert {result.group_id for result in first.group_results} == {1, 2, 3}
    assert all(
        Decimal("0") <= result.championship_probability <= Decimal("1")
        for result in first.team_results
    )


def test_monte_carlo_rejects_zero_iterations():
    try:
        run_monte_carlo(
            (),
            simulation_config=_simulation_config(seed=1),
            scoring_config=TournamentScoringConfig(),
            iterations=0,
        )
    except ValueError as exc:
        assert "iterations must be at least 1" in str(exc)
    else:
        raise AssertionError("expected zero iterations to fail")


def test_monte_carlo_reports_intermediate_progress():
    divisions = (
        TournamentDivision(
            slot=PortfolioSlot(country_code="US", division="mens"),
            entries=(
                _team(1, rating=Decimal("1700"), group_ids=(1,)),
                _team(2, rating=Decimal("1600"), group_ids=(2,)),
                _team(3, rating=Decimal("1500"), group_ids=(3,)),
            ),
        ),
    )
    progress_updates: list[tuple[int, int]] = []

    result = run_monte_carlo(
        divisions,
        simulation_config=_simulation_config(seed=99),
        scoring_config=TournamentScoringConfig(),
        iterations=25,
        progress_callback=lambda completed, total: progress_updates.append(
            (completed, total)
        ),
    )

    assert result.iterations == 25
    assert progress_updates
    assert progress_updates[-1] == (25, 25)
    assert all(total == 25 for _, total in progress_updates)


def _simulation_config(*, seed: int) -> TournamentSimulationConfig:
    match_config = MatchGenerationConfig.from_payload(DEFAULT_CONFIG_PAYLOAD)
    return TournamentSimulationConfig(
        match_date=date(2025, 1, 15),
        game_config=StubGameConfig(games_per_match={"tournament": 3}),
        hidden_bias_config=match_config.hidden_performance_bias,
        seed=seed,
    )


def _team(
    team_id: int,
    *,
    rating: Decimal,
    group_ids: tuple[int, ...],
) -> TournamentTeamEntry:
    return TournamentTeamEntry(
        id=team_id,
        country_code="US",
        division="mens",
        average_rating=rating,
        selected_by_group_ids=group_ids,
        avg_age=Decimal("35"),
    )
