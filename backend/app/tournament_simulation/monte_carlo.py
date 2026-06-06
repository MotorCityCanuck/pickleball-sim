"""Monte Carlo aggregation for in-memory tournament simulations."""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
import random
from typing import Callable

from .config import TournamentScoringConfig, TournamentSimulationConfig
from .dtos import DivisionResult, StudentGroupScore, TournamentDivision
from .round_robin_simulator import simulate_division_round_robin
from .student_scoring import score_student_groups


@dataclass(frozen=True)
class MonteCarloTeamAggregate:
    """Aggregate simulation result for one team."""

    team_id: int
    championship_probability: Decimal
    top_three_probability: Decimal
    average_finish: Decimal
    win_percentage: Decimal
    upset_count: int


@dataclass(frozen=True)
class MonteCarloGroupAggregate:
    """Aggregate simulation result for one student group."""

    group_id: int
    expected_score: Decimal
    average_rank: Decimal
    rank_distribution: dict[int, int]


@dataclass(frozen=True)
class MonteCarloResult:
    """Monte Carlo aggregate output."""

    iterations: int
    team_results: tuple[MonteCarloTeamAggregate, ...]
    group_results: tuple[MonteCarloGroupAggregate, ...]


def run_monte_carlo(
    divisions: tuple[TournamentDivision, ...],
    *,
    simulation_config: TournamentSimulationConfig,
    scoring_config: TournamentScoringConfig,
    iterations: int,
    progress_callback: Callable[[int, int], None] | None = None,
) -> MonteCarloResult:
    """Run repeated in-memory tournament simulations and aggregate results."""
    if iterations < 1:
        raise ValueError("iterations must be at least 1")

    team_counts: dict[int, Counter[str]] = defaultdict(Counter)
    team_finish_sum: dict[int, int] = defaultdict(int)
    group_score_sum: dict[int, Decimal] = defaultdict(lambda: Decimal("0"))
    group_rank_sum: dict[int, int] = defaultdict(int)
    group_rank_counts: dict[int, Counter[int]] = defaultdict(Counter)
    progress_step = max(1, iterations // 20)

    for iteration in range(iterations):
        rng = random.Random(simulation_config.seed + iteration)
        division_results = tuple(
            simulate_division_round_robin(
                division,
                config=simulation_config,
                rng=rng,
            )
            for division in divisions
        )
        _accumulate_team_results(team_counts, team_finish_sum, division_results)

        group_scores = score_student_groups(
            division_results,
            config=scoring_config,
        )
        ranked_scores = _rank_group_scores(group_scores)
        for rank, score in ranked_scores:
            group_score_sum[score.group_id] += score.score
            group_rank_sum[score.group_id] += rank
            group_rank_counts[score.group_id][rank] += 1

        if progress_callback is not None:
            completed_iterations = iteration + 1
            if (
                completed_iterations == iterations
                or completed_iterations % progress_step == 0
            ):
                progress_callback(completed_iterations, iterations)

    return MonteCarloResult(
        iterations=iterations,
        team_results=_team_aggregates(team_counts, team_finish_sum, iterations),
        group_results=_group_aggregates(
            group_score_sum,
            group_rank_sum,
            group_rank_counts,
            iterations,
        ),
    )


def _accumulate_team_results(
    team_counts: dict[int, Counter[str]],
    team_finish_sum: dict[int, int],
    division_results: tuple[DivisionResult, ...],
) -> None:
    for result in division_results:
        for standing in result.standings:
            counts = team_counts[standing.team_id]
            counts["appearances"] += 1
            counts["match_wins"] += standing.match_wins
            counts["match_losses"] += standing.match_losses
            if standing.rank == 1:
                counts["championships"] += 1
            if standing.rank <= 3:
                counts["top_three"] += 1
            team_finish_sum[standing.team_id] += standing.rank

        for match in result.matches:
            team_one_upset = (
                match.winning_team_id == match.team_one_id
                and match.probability.visible_probability < Decimal("0.5000")
            )
            team_two_upset = (
                match.winning_team_id == match.team_two_id
                and match.probability.visible_probability > Decimal("0.5000")
            )
            if team_one_upset or team_two_upset:
                team_counts[match.winning_team_id]["upsets"] += 1


def _rank_group_scores(
    group_scores: tuple[StudentGroupScore, ...],
) -> tuple[tuple[int, StudentGroupScore], ...]:
    ordered = sorted(group_scores, key=lambda score: (-score.score, score.group_id))
    return tuple((index + 1, score) for index, score in enumerate(ordered))


def _team_aggregates(
    team_counts: dict[int, Counter[str]],
    team_finish_sum: dict[int, int],
    iterations: int,
) -> tuple[MonteCarloTeamAggregate, ...]:
    return tuple(
        MonteCarloTeamAggregate(
            team_id=team_id,
            championship_probability=_ratio(counts["championships"], iterations),
            top_three_probability=_ratio(counts["top_three"], iterations),
            average_finish=_ratio(team_finish_sum[team_id], iterations),
            win_percentage=_ratio(
                counts["match_wins"],
                counts["match_wins"] + counts["match_losses"],
            ),
            upset_count=counts["upsets"],
        )
        for team_id, counts in sorted(team_counts.items())
    )


def _group_aggregates(
    score_sum: dict[int, Decimal],
    rank_sum: dict[int, int],
    rank_counts: dict[int, Counter[int]],
    iterations: int,
) -> tuple[MonteCarloGroupAggregate, ...]:
    return tuple(
        MonteCarloGroupAggregate(
            group_id=group_id,
            expected_score=(score / Decimal(iterations)).quantize(
                Decimal("0.001"),
                rounding=ROUND_HALF_UP,
            ),
            average_rank=_ratio(rank_sum[group_id], iterations),
            rank_distribution=dict(sorted(rank_counts[group_id].items())),
        )
        for group_id, score in sorted(score_sum.items())
    )


def _ratio(numerator: int | Decimal, denominator: int) -> Decimal:
    if denominator == 0:
        return Decimal("0.000")
    return (Decimal(numerator) / Decimal(denominator)).quantize(
        Decimal("0.001"),
        rounding=ROUND_HALF_UP,
    )
