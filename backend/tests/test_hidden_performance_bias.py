"""Tests for hidden performance bias rating-point helpers."""
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from pathlib import Path
import sys


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.default_configuration import DEFAULT_CONFIG_PAYLOAD  # noqa: E402
from app.generators.hidden_performance_bias import (  # noqa: E402
    clamp,
    compute_age_adjustment,
    compute_experience_adjustment,
    compute_fatigue_adjustment,
    compute_hidden_team_adjustment,
    compute_partnership_affinity_adjustment,
    compute_region_strength_adjustment,
)
from app.generators.matches import MatchGenerationConfig  # noqa: E402


@dataclass(frozen=True)
class BiasTeam:
    id: int = 1
    avg_age: Decimal | None = Decimal("40")
    region_name: str | None = None
    team_total_prior_matches: int = 0
    recent_game_count: int = 0
    recent_pair_counts: dict[tuple[int, int], int] = field(default_factory=dict)
    club_ids: frozenset[int] = frozenset()
    primary_club_ids: frozenset[int] = frozenset()
    player_ids: tuple[int, ...] = (1, 2)


def hidden_config(overrides=None):
    payload = DEFAULT_CONFIG_PAYLOAD.copy()
    payload["hidden_performance_bias"] = {
        **DEFAULT_CONFIG_PAYLOAD["hidden_performance_bias"],
        **(overrides or {}),
    }
    return MatchGenerationConfig.from_payload(payload).hidden_performance_bias


def test_clamp_bounds_decimal_values():
    assert clamp(Decimal("12"), Decimal("-5"), Decimal("10")) == Decimal("10")
    assert clamp(Decimal("-8"), Decimal("-5"), Decimal("10")) == Decimal("-5")
    assert clamp(Decimal("3"), Decimal("-5"), Decimal("10")) == Decimal("3")


def test_disabled_config_returns_zero_total_adjustment():
    config = hidden_config({"enabled": False})

    adjustment = compute_hidden_team_adjustment(
        BiasTeam(avg_age=Decimal("30"), region_name="Florida"),
        BiasTeam(avg_age=Decimal("55"), region_name="Developing Region"),
        {"expected_competitiveness": Decimal("1")},
        config,
    )

    assert adjustment == Decimal("0")


def test_total_adjustment_respects_cap():
    config = hidden_config(
        {
            "enabled": True,
            "total_max_rating_points": 10,
            "age_advantage": {
                **DEFAULT_CONFIG_PAYLOAD["hidden_performance_bias"]["age_advantage"],
                "max_rating_points": 100,
                "points_per_year_gap": 10,
            },
        }
    )

    adjustment = compute_hidden_team_adjustment(
        BiasTeam(avg_age=Decimal("30"), region_name="Florida"),
        BiasTeam(avg_age=Decimal("60"), region_name="Developing Region"),
        {"expected_competitiveness": Decimal("1")},
        config,
    )

    assert adjustment == Decimal("10")


def test_age_advantage_favors_younger_team_and_close_match_multiplier():
    config = hidden_config().age_advantage

    adjustment = compute_age_adjustment(
        BiasTeam(avg_age=Decimal("40")),
        BiasTeam(avg_age=Decimal("50")),
        config,
        expected_competitiveness=Decimal("0.80"),
    )

    assert adjustment == Decimal("18.750")


def test_age_advantage_handles_missing_age():
    config = hidden_config().age_advantage

    adjustment = compute_age_adjustment(
        BiasTeam(avg_age=None),
        BiasTeam(avg_age=Decimal("50")),
        config,
        expected_competitiveness=Decimal("1"),
    )

    assert adjustment == Decimal("0")


def test_fatigue_penalizes_recent_games_and_caps_penalty():
    config = hidden_config().fatigue

    adjustment = compute_fatigue_adjustment(
        BiasTeam(recent_game_count=20),
        {},
        config,
    )

    assert adjustment == Decimal("-25")


def test_fatigue_recovery_threshold_removes_penalty():
    config = hidden_config().fatigue

    adjustment = compute_fatigue_adjustment(
        BiasTeam(id=10, recent_game_count=20),
        {
            "match_date": date(2024, 2, 1),
            "last_match_dates_by_team": {10: date(2024, 1, 20)},
        },
        config,
    )

    assert adjustment == Decimal("0")


def test_regional_strength_unknown_regions_default_to_zero():
    config = hidden_config().regional_strength

    adjustment = compute_region_strength_adjustment(
        BiasTeam(region_name="Florida"),
        BiasTeam(region_name="Unknown"),
        config,
    )

    assert adjustment == Decimal("15")


def test_regional_strength_respects_cap():
    config = hidden_config().regional_strength

    adjustment = compute_region_strength_adjustment(
        BiasTeam(region_name="Southern California"),
        BiasTeam(region_name="Developing Region"),
        config,
    )

    assert adjustment == Decimal("20")


def test_partnership_affinity_applies_history_and_cap():
    config = hidden_config().partnership_affinity

    adjustment = compute_partnership_affinity_adjustment(
        BiasTeam(
            team_total_prior_matches=30,
            recent_pair_counts={(1, 2): 3},
            primary_club_ids=frozenset({101}),
        ),
        {},
        config,
    )

    assert adjustment == Decimal("22")


def test_partnership_affinity_new_team_penalty():
    config = hidden_config().partnership_affinity

    adjustment = compute_partnership_affinity_adjustment(
        BiasTeam(team_total_prior_matches=0),
        {},
        config,
    )

    assert adjustment == Decimal("-10")


def test_experience_uses_log_scaling_and_close_match_multiplier():
    config = hidden_config().experience

    adjustment = compute_experience_adjustment(
        BiasTeam(team_total_prior_matches=9),
        BiasTeam(),
        {},
        config,
        expected_competitiveness=Decimal("0.80"),
    )

    assert adjustment.quantize(Decimal("0.0001")) == Decimal("5.7565")


def test_experience_respects_cap():
    config = hidden_config(
        {
            "experience": {
                **DEFAULT_CONFIG_PAYLOAD["hidden_performance_bias"]["experience"],
                "max_rating_points": 3,
            }
        }
    ).experience

    adjustment = compute_experience_adjustment(
        BiasTeam(team_total_prior_matches=100),
        BiasTeam(),
        {},
        config,
        expected_competitiveness=Decimal("1"),
    )

    assert adjustment == Decimal("3")
