"""Persistence helpers for tournament simulation outputs."""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import (
    TournamentDivisionResult,
    TournamentGroupResult,
    TournamentOfficialGame,
    TournamentOfficialMatch,
    TournamentSimulationRun,
    TournamentTeamResult,
)

from .dtos import DivisionResult, StudentGroupScore
from .dtos import TournamentDivision
from .monte_carlo import MonteCarloResult


def replace_monte_carlo_results(
    session: Session,
    *,
    simulation_run: TournamentSimulationRun,
    result: MonteCarloResult,
    divisions: tuple[TournamentDivision, ...],
    team_slots: dict[int, tuple[str, str]],
    group_db_id_by_input_id: dict[int, int],
) -> None:
    """Persist Monte Carlo aggregate outputs for one run."""
    _delete_aggregate_results(session, simulation_run_id=simulation_run.id)
    for team_result in result.team_results:
        country_code, division = team_slots[team_result.team_id]
        session.add(
            TournamentTeamResult(
                simulation_run_id=simulation_run.id,
                slot_country_code=country_code,
                slot_division=division,
                team_id=team_result.team_id,
                championship_probability=team_result.championship_probability,
                top_three_probability=team_result.top_three_probability,
                average_finish=team_result.average_finish,
                win_percentage=team_result.win_percentage,
                upset_count=team_result.upset_count,
            )
        )

    for division in divisions:
        unique_team_count = len(division.entries)
        session.add(
            TournamentDivisionResult(
                simulation_run_id=simulation_run.id,
                slot_country_code=division.slot.country_code,
                slot_division=division.slot.division,
                iteration_count=result.iterations,
                unique_team_count=unique_team_count,
                match_count=unique_team_count * (unique_team_count - 1) // 2,
            )
        )

    for group_result in result.group_results:
        session.add(
            TournamentGroupResult(
                simulation_run_id=simulation_run.id,
                student_group_id=group_db_id_by_input_id[group_result.group_id],
                expected_score=group_result.expected_score,
                average_rank=group_result.average_rank,
                rank_distribution=group_result.rank_distribution,
            )
        )


def replace_official_results(
    session: Session,
    *,
    simulation_run: TournamentSimulationRun,
    division_results: tuple[DivisionResult, ...],
    group_scores: tuple[StudentGroupScore, ...],
    group_db_id_by_input_id: dict[int, int],
) -> None:
    """Persist official division, team, group, match, and game outputs."""
    _delete_official_results(session, simulation_run_id=simulation_run.id)
    match_number = 1
    for division_result in division_results:
        champion = division_result.standings[0] if division_result.standings else None
        session.add(
            TournamentDivisionResult(
                simulation_run_id=simulation_run.id,
                slot_country_code=division_result.slot.country_code,
                slot_division=division_result.slot.division,
                iteration_count=1,
                unique_team_count=len(division_result.standings),
                match_count=len(division_result.matches),
                champion_team_id=None if champion is None else champion.team_id,
                summary_payload={
                    "standings": [
                        {
                            "team_id": standing.team_id,
                            "rank": standing.rank,
                            "match_wins": standing.match_wins,
                            "match_losses": standing.match_losses,
                            "game_differential": standing.game_differential,
                            "point_differential": standing.point_differential,
                        }
                        for standing in division_result.standings
                    ]
                },
            )
        )
        for standing in division_result.standings:
            session.add(
                TournamentTeamResult(
                    simulation_run_id=simulation_run.id,
                    slot_country_code=division_result.slot.country_code,
                    slot_division=division_result.slot.division,
                    team_id=standing.team_id,
                    final_rank=standing.rank,
                    match_wins=standing.match_wins,
                    match_losses=standing.match_losses,
                    games_won=standing.games_won,
                    games_lost=standing.games_lost,
                    point_differential=standing.point_differential,
                )
            )
        for match in division_result.matches:
            official_match = TournamentOfficialMatch(
                simulation_run_id=simulation_run.id,
                slot_country_code=division_result.slot.country_code,
                slot_division=division_result.slot.division,
                match_number=match_number,
                team_one_id=match.team_one_id,
                team_two_id=match.team_two_id,
                winning_team_id=match.winning_team_id,
                team_one_games_won=match.team_one_games_won,
                team_two_games_won=match.team_two_games_won,
                team_one_points=match.team_one_points,
                team_two_points=match.team_two_points,
                visible_team_one_win_probability=match.probability.visible_probability,
                final_team_one_win_probability=match.probability.final_probability,
            )
            session.add(official_match)
            session.flush()
            for game in match.games.games:
                session.add(
                    TournamentOfficialGame(
                        official_match_id=official_match.id,
                        game_number=game.game_number,
                        team_one_score=game.team_one_score,
                        team_two_score=game.team_two_score,
                        winning_team_number=game.winning_team_number,
                        target_score=game.target_score,
                        win_by=game.win_by,
                        expected_team_one_score_share=game.expected_team_one_score_share,
                        actual_team_one_score_share=game.actual_team_one_score_share,
                    )
                )
            match_number += 1

    for rank, group_score in enumerate(
        sorted(group_scores, key=lambda score: (-score.score, score.group_id)),
        start=1,
    ):
        session.add(
            TournamentGroupResult(
                simulation_run_id=simulation_run.id,
                student_group_id=group_db_id_by_input_id[group_score.group_id],
                official_score=group_score.score,
                final_rank=rank,
                champion_count=group_score.champion_count,
                runner_up_count=group_score.runner_up_count,
                top_four_count=group_score.top_four_count,
                match_wins=group_score.match_wins,
            )
        )


def latest_run_summary(
    session: Session,
    *,
    event_id: int,
) -> dict[str, Any] | None:
    """Return a compact latest-result summary for one event."""
    run = session.execute(
        select(TournamentSimulationRun)
        .where(TournamentSimulationRun.event_id == event_id)
        .order_by(TournamentSimulationRun.id.desc())
        .limit(1)
    ).scalar_one_or_none()
    if run is None:
        return None

    team_rows = session.execute(
        select(TournamentTeamResult).where(
            TournamentTeamResult.simulation_run_id == run.id
        )
    ).scalars()
    group_rows = session.execute(
        select(TournamentGroupResult).where(
            TournamentGroupResult.simulation_run_id == run.id
        )
    ).scalars()
    division_rows = session.execute(
        select(TournamentDivisionResult).where(
            TournamentDivisionResult.simulation_run_id == run.id
        )
    ).scalars()
    return {
        "simulation_run_id": run.id,
        "run_type": run.run_type,
        "status": run.status,
        "team_results": [
            {
                "team_id": row.team_id,
                "slot_country_code": row.slot_country_code,
                "slot_division": row.slot_division,
                "championship_probability": _decimal_or_none(row.championship_probability),
                "top_three_probability": _decimal_or_none(row.top_three_probability),
                "average_finish": _decimal_or_none(row.average_finish),
                "win_percentage": _decimal_or_none(row.win_percentage),
                "final_rank": row.final_rank,
                "match_wins": row.match_wins,
            }
            for row in team_rows
        ],
        "group_results": [
            {
                "student_group_id": row.student_group_id,
                "expected_score": _decimal_or_none(row.expected_score),
                "official_score": _decimal_or_none(row.official_score),
                "average_rank": _decimal_or_none(row.average_rank),
                "final_rank": row.final_rank,
                "rank_distribution": row.rank_distribution,
            }
            for row in group_rows
        ],
        "division_results": [
            {
                "slot_country_code": row.slot_country_code,
                "slot_division": row.slot_division,
                "unique_team_count": row.unique_team_count,
                "match_count": row.match_count,
                "champion_team_id": row.champion_team_id,
            }
            for row in division_rows
        ],
    }


def _delete_aggregate_results(session: Session, *, simulation_run_id: int) -> None:
    session.execute(
        delete(TournamentTeamResult).where(
            TournamentTeamResult.simulation_run_id == simulation_run_id
        )
    )
    session.execute(
        delete(TournamentGroupResult).where(
            TournamentGroupResult.simulation_run_id == simulation_run_id
        )
    )
    session.execute(
        delete(TournamentDivisionResult).where(
            TournamentDivisionResult.simulation_run_id == simulation_run_id
        )
    )


def _delete_official_results(session: Session, *, simulation_run_id: int) -> None:
    official_match_ids = [
        row[0]
        for row in session.execute(
            select(TournamentOfficialMatch.id).where(
                TournamentOfficialMatch.simulation_run_id == simulation_run_id
            )
        )
    ]
    if official_match_ids:
        session.execute(
            delete(TournamentOfficialGame).where(
                TournamentOfficialGame.official_match_id.in_(official_match_ids)
            )
        )
    session.execute(
        delete(TournamentOfficialMatch).where(
            TournamentOfficialMatch.simulation_run_id == simulation_run_id
        )
    )
    _delete_aggregate_results(session, simulation_run_id=simulation_run_id)


def _decimal_or_none(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return str(value)
    return str(value)
