"""Generate game-level scores for a match."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
import random
from typing import Protocol

from app.models import Match, MatchGame


class GameGenerationConfig(Protocol):
    """Subset of match config required to generate games."""

    games_per_match: dict[str, int]
    game_target_score: int
    win_by_two_rule_enabled: bool
    win_by_two_extension_rate: Decimal
    score_noise_std_dev: Decimal
    upset_probability_boost: Decimal


@dataclass(frozen=True)
class GeneratedGames:
    """Generated game rows and match-level win counts."""

    team_one_games_won: int
    team_two_games_won: int
    games: list[MatchGame]


def generate_match_games(
    rng: random.Random,
    *,
    match: Match,
    expected_team_one_win_probability: Decimal,
    match_type: str,
    config: GameGenerationConfig,
) -> GeneratedGames:
    """Generate all game rows for one match."""
    game_count = games_per_match(match_type, config)
    team_one_games_won = 0
    team_two_games_won = 0
    games: list[MatchGame] = []
    for game_number in range(1, game_count + 1):
        adjusted_probability = adjusted_game_probability(
            rng,
            expected_team_one_win_probability,
            config,
        )
        team_one_wins = Decimal(str(rng.random())) < adjusted_probability
        if team_one_wins:
            team_one_games_won += 1
        else:
            team_two_games_won += 1

        team_one_score, team_two_score = game_score(
            rng,
            team_one_wins=team_one_wins,
            adjusted_probability=adjusted_probability,
            config=config,
        )
        expected_team_one_score, expected_team_two_score = expected_scores(
            expected_team_one_win_probability,
            config,
        )
        games.append(
            MatchGame(
                match_id=match.id,
                game_number=game_number,
                team_one_score=team_one_score,
                team_two_score=team_two_score,
                winning_team_number=1 if team_one_wins else 2,
                target_score=config.game_target_score,
                win_by=2,
                expected_team_one_score_share=expected_team_one_win_probability,
                actual_team_one_score_share=score_share(
                    team_one_score,
                    team_two_score,
                ),
                expected_team_one_score=expected_team_one_score,
                expected_team_two_score=expected_team_two_score,
                score_noise_factor=noise_value(rng, config.score_noise_std_dev),
            )
        )
    return GeneratedGames(
        team_one_games_won=team_one_games_won,
        team_two_games_won=team_two_games_won,
        games=games,
    )


def games_per_match(match_type: str, config: GameGenerationConfig) -> int:
    """Resolve configured game count for a match type."""
    if match_type in config.games_per_match:
        return config.games_per_match[match_type]
    if match_type == "tournament":
        return config.games_per_match.get("tournament", 3)
    if match_type in {"league", "ladder"}:
        return config.games_per_match.get("league", 2)
    return config.games_per_match.get("recreational", 1)


def adjusted_game_probability(
    rng: random.Random,
    expected_probability: Decimal,
    config: GameGenerationConfig,
) -> Decimal:
    """Apply bounded upset noise to the rating-derived game probability."""
    upset_noise = (
        Decimal(str(rng.random())) - Decimal("0.5")
    ) * config.upset_probability_boost
    adjusted = expected_probability + upset_noise
    adjusted = max(Decimal("0.05"), min(Decimal("0.95"), adjusted))
    return adjusted.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def game_score(
    rng: random.Random,
    *,
    team_one_wins: bool,
    adjusted_probability: Decimal,
    config: GameGenerationConfig,
) -> tuple[int, int]:
    """Generate a legal scoreline for a single game."""
    target = config.game_target_score
    closeness = Decimal("1") - abs(adjusted_probability - Decimal("0.5")) * 2
    if (
        config.win_by_two_rule_enabled
        and Decimal(str(rng.random())) < config.win_by_two_extension_rate
    ):
        extra_pairs = _extension_extra_pairs(rng, closeness)
        loser_score = target - 1 + extra_pairs
        winner_score = loser_score + 2
    else:
        max_loser_score = max(0, target - 2)
        center = int(
            _non_extended_loser_score_center(
                closeness,
                target=target,
            ).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        )
        spread = _score_spread(config.score_noise_std_dev)
        loser_score = max(
            0,
            min(max_loser_score, center + rng.randint(-spread, spread)),
        )
        winner_score = target

    if team_one_wins:
        return winner_score, loser_score
    return loser_score, winner_score


def expected_scores(
    expected_team_one_win_probability: Decimal,
    config: GameGenerationConfig,
) -> tuple[Decimal, Decimal]:
    """Convert rating-derived win probability into expected raw scores."""
    target = Decimal(config.game_target_score)
    expected_loser_score = _expected_loser_score(
        expected_team_one_win_probability,
        config,
    )
    if expected_team_one_win_probability >= Decimal("0.5"):
        return target.quantize(Decimal("0.001")), expected_loser_score
    return expected_loser_score, target.quantize(Decimal("0.001"))


def score_share(team_one_score: int, team_two_score: int) -> Decimal:
    """Calculate team one's share of points played."""
    total = team_one_score + team_two_score
    if total == 0:
        return Decimal("0.5000")
    return (Decimal(team_one_score) / Decimal(total)).quantize(
        Decimal("0.0001"),
        rounding=ROUND_HALF_UP,
    )


def noise_value(rng: random.Random, scale: Decimal) -> Decimal:
    """Return a bounded positive noise marker for auditability."""
    return (Decimal(str(rng.random())) * scale).quantize(
        Decimal("0.001"),
        rounding=ROUND_HALF_UP,
    )


def _expected_loser_score(
    expected_team_one_win_probability: Decimal,
    config: GameGenerationConfig,
) -> Decimal:
    target = Decimal(config.game_target_score)
    closeness = (
        Decimal("1")
        - abs(expected_team_one_win_probability - Decimal("0.5")) * 2
    )
    return _non_extended_loser_score_center(
        closeness,
        target=int(target),
    ).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)


def _non_extended_loser_score_center(closeness: Decimal, *, target: int) -> Decimal:
    """Bias expected loser scores downward faster for mismatched games."""
    target_score = Decimal(target)
    max_loser_score = max(Decimal("0"), target_score - Decimal("2"))
    min_loser_score = min(
        max_loser_score,
        target_score * Decimal("0.15"),
    )
    return min_loser_score + (max_loser_score - min_loser_score) * (closeness ** 2)


def _score_spread(score_noise_std_dev: Decimal) -> int:
    """Round configured noise to a practical integer score spread."""
    return max(
        1,
        int(score_noise_std_dev.quantize(Decimal("1"), rounding=ROUND_HALF_UP)),
    )


def _extension_extra_pairs(rng: random.Random, closeness: Decimal) -> int:
    """Return additional tied-score pairs after the first target-1 tie."""
    max_extra_pairs = 4
    continuation_probability = Decimal("0.15") + closeness * Decimal("0.35")
    extra_pairs = 0
    while (
        extra_pairs < max_extra_pairs
        and Decimal(str(rng.random())) < continuation_probability
    ):
        extra_pairs += 1
        continuation_probability *= Decimal("0.55")
    return extra_pairs
