"""Shared probability helpers for match and tournament outcome simulation."""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
import random
from typing import Any, Mapping, Protocol

from .hidden_performance_bias import (
    HiddenTeamAdjustmentBreakdown,
    compute_hidden_team_adjustment_breakdown,
)


ZERO = Decimal("0")


class TeamProbabilityInput(Protocol):
    """Team-like input required for shared outcome probability helpers."""

    average_rating: Decimal


@dataclass(frozen=True)
class HiddenAdjustedWinProbability:
    """Probability result with visible and hidden-adjusted rating details."""

    visible_probability: Decimal
    final_probability: Decimal
    visible_competitiveness: Decimal
    team_one_effective_rating: Decimal
    team_two_effective_rating: Decimal
    team_one_breakdown: HiddenTeamAdjustmentBreakdown
    team_two_breakdown: HiddenTeamAdjustmentBreakdown
    applied_hidden_bias: bool


def expected_win_probability(rating_one: Decimal, rating_two: Decimal) -> Decimal:
    """Return team one's Elo-style win probability from two visible ratings."""
    exponent = float((rating_two - rating_one) / Decimal("400"))
    probability = Decimal(str(1 / (1 + 10**exponent)))
    return probability.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def competitiveness(expected_team_one_win_probability: Decimal) -> Decimal:
    """Return a 0-1 closeness score, where 1.0 means evenly matched."""
    value = (
        Decimal("1")
        - abs(expected_team_one_win_probability - Decimal("0.5")) * 2
    )
    return value.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)


def hidden_adjusted_win_probability(
    team_one: TeamProbabilityInput,
    team_two: TeamProbabilityInput,
    *,
    match_date: date,
    hidden_bias_config: Any,
    apply_hidden_bias: bool,
    rng: random.Random | None = None,
    extra_match_context: Mapping[str, Any] | None = None,
) -> HiddenAdjustedWinProbability:
    """Return visible or hidden-adjusted win probability for team one.

    ``apply_hidden_bias`` is an explicit policy switch. Monthly generation should
    pass the user-facing config checkbox value. Tournament simulation should
    pass ``True`` so it always uses the configured hidden factor weights.
    """
    visible_probability = expected_win_probability(
        team_one.average_rating,
        team_two.average_rating,
    )
    visible_competitiveness = competitiveness(visible_probability)
    zero_breakdown = _zero_breakdown()
    if not apply_hidden_bias:
        return HiddenAdjustedWinProbability(
            visible_probability=visible_probability,
            final_probability=visible_probability,
            visible_competitiveness=visible_competitiveness,
            team_one_effective_rating=team_one.average_rating,
            team_two_effective_rating=team_two.average_rating,
            team_one_breakdown=zero_breakdown,
            team_two_breakdown=zero_breakdown,
            applied_hidden_bias=False,
        )

    effective_config = _force_hidden_bias_enabled(hidden_bias_config)
    match_context: dict[str, Any] = {
        "match_date": match_date,
        "visible_team_one_rating": team_one.average_rating,
        "visible_team_two_rating": team_two.average_rating,
        "visible_probability": visible_probability,
        "expected_competitiveness": visible_competitiveness,
    }
    if extra_match_context:
        match_context.update(extra_match_context)

    team_one_breakdown = compute_hidden_team_adjustment_breakdown(
        team_one,
        team_two,
        match_context,
        effective_config,
        rng,
    )
    team_two_breakdown = compute_hidden_team_adjustment_breakdown(
        team_two,
        team_one,
        match_context,
        effective_config,
        rng,
    )
    team_one_effective_rating = team_one.average_rating + team_one_breakdown.total
    team_two_effective_rating = team_two.average_rating + team_two_breakdown.total
    final_probability = expected_win_probability(
        team_one_effective_rating,
        team_two_effective_rating,
    )
    return HiddenAdjustedWinProbability(
        visible_probability=visible_probability,
        final_probability=final_probability,
        visible_competitiveness=visible_competitiveness,
        team_one_effective_rating=team_one_effective_rating,
        team_two_effective_rating=team_two_effective_rating,
        team_one_breakdown=team_one_breakdown,
        team_two_breakdown=team_two_breakdown,
        applied_hidden_bias=True,
    )


def monthly_hidden_adjusted_win_probability(
    team_one: TeamProbabilityInput,
    team_two: TeamProbabilityInput,
    *,
    match_date: date,
    hidden_bias_config: Any,
    rng: random.Random | None = None,
    extra_match_context: Mapping[str, Any] | None = None,
) -> HiddenAdjustedWinProbability:
    """Return monthly-generation probability using the config checkbox policy."""
    return hidden_adjusted_win_probability(
        team_one,
        team_two,
        match_date=match_date,
        hidden_bias_config=hidden_bias_config,
        apply_hidden_bias=bool(getattr(hidden_bias_config, "enabled", False)),
        rng=rng,
        extra_match_context=extra_match_context,
    )


def tournament_hidden_adjusted_win_probability(
    team_one: TeamProbabilityInput,
    team_two: TeamProbabilityInput,
    *,
    match_date: date,
    hidden_bias_config: Any,
    rng: random.Random | None = None,
    extra_match_context: Mapping[str, Any] | None = None,
) -> HiddenAdjustedWinProbability:
    """Return tournament probability, always applying configured hidden factors."""
    return hidden_adjusted_win_probability(
        team_one,
        team_two,
        match_date=match_date,
        hidden_bias_config=hidden_bias_config,
        apply_hidden_bias=True,
        rng=rng,
        extra_match_context=extra_match_context,
    )


def _force_hidden_bias_enabled(config: Any) -> Any:
    if getattr(config, "enabled", False) is True:
        return config
    try:
        return replace(config, enabled=True)
    except TypeError:
        return _EnabledHiddenBiasConfig(config)


class _EnabledHiddenBiasConfig:
    """Read-only adapter that forces top-level hidden bias enablement."""

    def __init__(self, source: Any) -> None:
        self._source = source
        self.enabled = True

    def __getattr__(self, name: str) -> Any:
        return getattr(self._source, name)


def _zero_breakdown() -> HiddenTeamAdjustmentBreakdown:
    return HiddenTeamAdjustmentBreakdown(
        age=ZERO,
        fatigue=ZERO,
        regional_strength=ZERO,
        partnership_affinity=ZERO,
        experience=ZERO,
        total_before_cap=ZERO,
        total=ZERO,
    )
