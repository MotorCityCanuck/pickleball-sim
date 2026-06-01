"""Hidden effective-rating adjustment helpers for match generation."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
import math
import random
from typing import Any, Mapping


ZERO = Decimal("0")


def clamp(value: Decimal, min_value: Decimal, max_value: Decimal) -> Decimal:
    """Clamp a Decimal value to an inclusive range."""
    return max(min_value, min(max_value, value))


def compute_hidden_team_adjustment(
    team: Any,
    opponent: Any,
    match_context: Mapping[str, Any],
    config: Any,
    rng: random.Random | None = None,
) -> Decimal:
    """Return the total hidden rating-point adjustment for one team."""
    del rng
    if not config.enabled:
        return ZERO

    expected_competitiveness = _expected_competitiveness(match_context)
    adjustment = (
        compute_age_adjustment(
            team,
            opponent,
            config.age_advantage,
            expected_competitiveness=expected_competitiveness,
        )
        + compute_fatigue_adjustment(team, match_context, config.fatigue)
        + compute_region_strength_adjustment(
            team,
            opponent,
            config.regional_strength,
        )
        + compute_partnership_affinity_adjustment(
            team,
            match_context,
            config.partnership_affinity,
        )
        + compute_experience_adjustment(
            team,
            opponent,
            match_context,
            config.experience,
            expected_competitiveness=expected_competitiveness,
        )
    )
    cap = _decimal(config.total_max_rating_points)
    return clamp(adjustment, -cap, cap)


def compute_age_adjustment(
    team: Any,
    opponent: Any,
    config: Any,
    *,
    expected_competitiveness: Decimal | None = None,
) -> Decimal:
    """Return an age-gap adjustment where younger teams are favored."""
    if not config.enabled or team.avg_age is None or opponent.avg_age is None:
        return ZERO

    age_gap = _decimal(opponent.avg_age) - _decimal(team.avg_age)
    adjustment = age_gap * _decimal(config.points_per_year_gap)
    if _is_close_match(
        expected_competitiveness,
        config.close_match_competitiveness_threshold,
    ):
        adjustment *= _decimal(config.close_match_multiplier)

    cap = _decimal(config.max_rating_points)
    return clamp(adjustment, -cap, cap)


def compute_fatigue_adjustment(
    team: Any,
    match_context: Mapping[str, Any],
    config: Any,
) -> Decimal:
    """Return a workload penalty based on recent game volume."""
    if not config.enabled:
        return ZERO
    if _has_recovered(team, match_context, config):
        return ZERO

    recent_games = _decimal(getattr(team, "recent_game_count", 0) or 0)
    penalty = clamp(
        recent_games * _decimal(config.points_per_recent_game),
        ZERO,
        _decimal(config.max_rating_penalty),
    )
    return -penalty


def compute_region_strength_adjustment(
    team: Any,
    opponent: Any,
    config: Any,
) -> Decimal:
    """Return a relative region-strength adjustment."""
    if not config.enabled:
        return ZERO

    team_strength = _region_strength(team, config)
    opponent_strength = _region_strength(opponent, config)
    cap = _decimal(config.max_rating_points)
    return clamp(team_strength - opponent_strength, -cap, cap)


def compute_partnership_affinity_adjustment(
    team: Any,
    match_context: Mapping[str, Any],
    config: Any,
) -> Decimal:
    """Return a doubles-partnership familiarity adjustment."""
    del match_context
    if not config.enabled:
        return ZERO

    adjustment = ZERO
    if _has_shared_club(team):
        adjustment += _decimal(config.same_club_bonus)

    prior_matches = int(getattr(team, "team_total_prior_matches", 0) or 0)
    if prior_matches >= int(config.matches_together_threshold_2):
        adjustment += _decimal(config.matches_together_bonus_2)
    elif prior_matches >= int(config.matches_together_threshold_1):
        adjustment += _decimal(config.matches_together_bonus_1)
    elif prior_matches == 0:
        adjustment += _decimal(config.new_team_penalty)

    recent_pair_counts = getattr(team, "recent_pair_counts", {}) or {}
    recent_pair_match_count = sum(int(value) for value in recent_pair_counts.values())
    if recent_pair_match_count > 0:
        adjustment += _decimal(config.recent_matches_bonus)

    cap = _decimal(config.max_rating_points)
    return clamp(adjustment, -cap, cap)


def compute_experience_adjustment(
    team: Any,
    opponent: Any,
    match_context: Mapping[str, Any],
    config: Any,
    *,
    expected_competitiveness: Decimal | None = None,
) -> Decimal:
    """Return a log-scaled prior experience adjustment."""
    del opponent, match_context
    if not config.enabled:
        return ZERO

    prior_matches = max(0, int(getattr(team, "team_total_prior_matches", 0) or 0))
    adjustment = Decimal(str(math.log1p(prior_matches))) * _decimal(
        config.log_multiplier
    )
    if _is_close_match(
        expected_competitiveness,
        config.close_match_competitiveness_threshold,
    ):
        adjustment *= _decimal(config.close_match_multiplier)

    return clamp(adjustment, ZERO, _decimal(config.max_rating_points))


def _expected_competitiveness(match_context: Mapping[str, Any]) -> Decimal | None:
    value = match_context.get("expected_competitiveness")
    if value is None:
        return None
    return _decimal(value)


def _is_close_match(
    expected_competitiveness: Decimal | None,
    threshold: Decimal,
) -> bool:
    return (
        expected_competitiveness is not None
        and expected_competitiveness >= _decimal(threshold)
    )


def _has_recovered(
    team: Any,
    match_context: Mapping[str, Any],
    config: Any,
) -> bool:
    last_match_dates = match_context.get("last_match_dates_by_team", {})
    match_date = match_context.get("match_date")
    if not isinstance(last_match_dates, Mapping) or not isinstance(match_date, date):
        return False

    last_match_date = last_match_dates.get(getattr(team, "id", None))
    if not isinstance(last_match_date, date):
        return False
    return (match_date - last_match_date).days >= int(config.recovery_days_threshold)


def _region_strength(team: Any, config: Any) -> Decimal:
    region_name = getattr(team, "region_name", None)
    if region_name is None:
        return ZERO
    value = config.strength_map.get(region_name)
    return ZERO if value is None else _decimal(value)


def _has_shared_club(team: Any) -> bool:
    primary_club_ids = getattr(team, "primary_club_ids", frozenset()) or frozenset()
    if len(primary_club_ids) == 1:
        return True

    club_ids = getattr(team, "club_ids", frozenset()) or frozenset()
    return len(club_ids) == 1


def _decimal(value: Any) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))
