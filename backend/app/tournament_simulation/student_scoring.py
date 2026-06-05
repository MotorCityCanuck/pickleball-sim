"""Student-group scoring for tournament results."""
from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from .config import TournamentScoringConfig
from .dtos import DivisionResult, StudentGroupScore


def score_student_groups(
    division_results: tuple[DivisionResult, ...],
    *,
    config: TournamentScoringConfig,
) -> tuple[StudentGroupScore, ...]:
    """Score all credited student groups across division results."""
    scores: dict[int, Decimal] = defaultdict(lambda: Decimal("0"))
    champion_counts: dict[int, int] = defaultdict(int)
    runner_up_counts: dict[int, int] = defaultdict(int)
    top_four_counts: dict[int, int] = defaultdict(int)
    match_wins: dict[int, int] = defaultdict(int)

    for result in division_results:
        for standing in result.standings:
            for group_id in standing.selected_by_group_ids:
                scores[group_id] += Decimal(standing.match_wins) * config.match_win_points
                match_wins[group_id] += standing.match_wins

                if standing.rank == 1:
                    scores[group_id] += config.champion_points
                    champion_counts[group_id] += 1
                elif standing.rank == 2:
                    scores[group_id] += config.runner_up_points
                    runner_up_counts[group_id] += 1

                if standing.rank <= 4:
                    top_four_counts[group_id] += 1
                    if config.top_four_points_enabled:
                        scores[group_id] += config.top_four_points

    return tuple(
        StudentGroupScore(
            group_id=group_id,
            score=score,
            champion_count=champion_counts[group_id],
            runner_up_count=runner_up_counts[group_id],
            top_four_count=top_four_counts[group_id],
            match_wins=match_wins[group_id],
        )
        for group_id, score in sorted(scores.items())
    )
