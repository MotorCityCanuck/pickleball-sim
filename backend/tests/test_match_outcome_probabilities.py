"""Tests for shared match outcome probability helpers."""
from datetime import date
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
import sys


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.default_configuration import DEFAULT_CONFIG_PAYLOAD  # noqa: E402
from app.generators.match_outcome_probabilities import (  # noqa: E402
    competitiveness,
    expected_win_probability,
    hidden_adjusted_win_probability,
    monthly_hidden_adjusted_win_probability,
    tournament_hidden_adjusted_win_probability,
)
from app.generators.matches import MatchGenerationConfig  # noqa: E402


def test_expected_win_probability_is_symmetric():
    team_one = expected_win_probability(Decimal("1500"), Decimal("1600"))
    team_two = expected_win_probability(Decimal("1600"), Decimal("1500"))

    assert team_one == Decimal("0.3599")
    assert team_two == Decimal("0.6401")
    assert team_one + team_two == Decimal("1.0000")


def test_competitiveness_is_highest_for_even_match():
    assert competitiveness(Decimal("0.5000")) == Decimal("1.000")
    assert competitiveness(Decimal("0.7500")) == Decimal("0.500")


def test_hidden_adjustment_skipped_when_policy_disabled():
    hidden_config = _hidden_config(enabled=True)
    younger = _team(avg_age=25, average_rating=Decimal("1500"))
    older = _team(avg_age=65, average_rating=Decimal("1500"))

    result = hidden_adjusted_win_probability(
        younger,
        older,
        match_date=date(2024, 1, 15),
        hidden_bias_config=hidden_config,
        apply_hidden_bias=False,
    )

    assert result.final_probability == Decimal("0.5000")
    assert result.team_one_effective_rating == Decimal("1500")
    assert result.team_one_breakdown.total == Decimal("0")
    assert result.applied_hidden_bias is False


def test_hidden_adjustment_can_be_forced_when_config_checkbox_disabled():
    hidden_config = _hidden_config(enabled=False)
    younger = _team(avg_age=25, average_rating=Decimal("1500"))
    older = _team(avg_age=65, average_rating=Decimal("1500"))

    result = hidden_adjusted_win_probability(
        younger,
        older,
        match_date=date(2024, 1, 15),
        hidden_bias_config=hidden_config,
        apply_hidden_bias=True,
    )

    assert result.visible_probability == Decimal("0.5000")
    assert result.final_probability > Decimal("0.5000")
    assert result.team_one_effective_rating > Decimal("1500")
    assert result.team_one_breakdown.age > Decimal("0")
    assert result.applied_hidden_bias is True


def test_monthly_helper_uses_config_checkbox_policy():
    hidden_config = _hidden_config(enabled=False)
    younger = _team(avg_age=25, average_rating=Decimal("1500"))
    older = _team(avg_age=65, average_rating=Decimal("1500"))

    result = monthly_hidden_adjusted_win_probability(
        younger,
        older,
        match_date=date(2024, 1, 15),
        hidden_bias_config=hidden_config,
    )

    assert result.final_probability == Decimal("0.5000")
    assert result.applied_hidden_bias is False


def test_tournament_helper_always_reuses_hidden_bias_config_with_team_like_dtos():
    hidden_config = _hidden_config(enabled=False)
    younger = _team(avg_age=25, average_rating=Decimal("1500"))
    older = _team(avg_age=65, average_rating=Decimal("1500"))

    result = tournament_hidden_adjusted_win_probability(
        younger,
        older,
        match_date=date(2024, 1, 15),
        hidden_bias_config=hidden_config,
    )

    assert hidden_config.enabled is False
    assert result.visible_probability == Decimal("0.5000")
    assert result.final_probability > Decimal("0.5000")
    assert result.team_one_breakdown.age > Decimal("0")
    assert result.applied_hidden_bias is True


def _hidden_config(*, enabled: bool):
    payload = {
        **DEFAULT_CONFIG_PAYLOAD,
        "hidden_performance_bias": {
            **DEFAULT_CONFIG_PAYLOAD["hidden_performance_bias"],
            "enabled": enabled,
            "total_max_rating_points": 250,
            "age_advantage": {
                **DEFAULT_CONFIG_PAYLOAD["hidden_performance_bias"]["age_advantage"],
                "enabled": True,
                "max_rating_points": 250,
                "points_per_year_gap": 5,
                "close_match_multiplier": 1,
            },
            "fatigue": {
                **DEFAULT_CONFIG_PAYLOAD["hidden_performance_bias"]["fatigue"],
                "enabled": False,
            },
            "regional_strength": {
                **DEFAULT_CONFIG_PAYLOAD["hidden_performance_bias"]["regional_strength"],
                "enabled": False,
            },
            "partnership_affinity": {
                **DEFAULT_CONFIG_PAYLOAD["hidden_performance_bias"][
                    "partnership_affinity"
                ],
                "enabled": False,
            },
            "experience": {
                **DEFAULT_CONFIG_PAYLOAD["hidden_performance_bias"]["experience"],
                "enabled": False,
            },
        },
    }
    return MatchGenerationConfig.from_payload(payload).hidden_performance_bias


def _team(*, avg_age: int, average_rating: Decimal):
    return SimpleNamespace(
        id=1,
        average_rating=average_rating,
        avg_age=Decimal(avg_age),
        recent_game_count=0,
        region_name=None,
        primary_club_ids=frozenset(),
        club_ids=frozenset(),
        team_total_prior_matches=0,
        recent_pair_counts={},
    )
