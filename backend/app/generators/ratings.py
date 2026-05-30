"""Apply match-driven rating updates and write audit logs."""
from __future__ import annotations

from contextlib import nullcontext
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, ContextManager

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.default_configuration import DEFAULT_CONFIG_PAYLOAD
from app.db.session import session_scope
from app.models import (
    Match,
    MatchTeam,
    MonthlyBatch,
    PlayerRatingHistory,
    RatingsUpdateLog,
    GenerationRun,
)


CALCULATION_VERSION = "rating_update_v1"


@dataclass(frozen=True)
class RatingUpdateConfig:
    """Rating update settings resolved from a configuration payload."""

    rating_min: Decimal
    rating_max: Decimal
    k_factor_new_player: Decimal
    k_factor_established: Decimal
    k_factor_elite: Decimal
    confidence_max: Decimal
    confidence_increment_per_match: Decimal

    @classmethod
    def from_payload(cls, payload: dict[str, Any] | None) -> "RatingUpdateConfig":
        source = payload or DEFAULT_CONFIG_PAYLOAD
        ratings = source.get("ratings", {})
        confidence = source.get("confidence", {})
        rating_min = _decimal(ratings.get("rating_min", 0.0))
        rating_max = _decimal(ratings.get("rating_max", 5000.0))
        if rating_min < 0 or rating_max <= rating_min:
            raise ValueError("rating bounds are invalid")
        return cls(
            rating_min=rating_min,
            rating_max=rating_max,
            k_factor_new_player=_positive_decimal(
                ratings.get("k_factor_new_player", 48.0),
                "k_factor_new_player",
            ),
            k_factor_established=_positive_decimal(
                ratings.get("k_factor_established", 24.0),
                "k_factor_established",
            ),
            k_factor_elite=_positive_decimal(
                ratings.get("k_factor_elite", 16.0),
                "k_factor_elite",
            ),
            confidence_max=_probability(confidence.get("confidence_max", 1.0)),
            confidence_increment_per_match=_probability(
                confidence.get("confidence_increment_per_match", 0.02)
            ),
        )


@dataclass(frozen=True)
class RatingUpdateResult:
    """Summary of generated rating update rows."""

    batch_id: int
    match_count: int
    player_update_count: int
    rating_history_count: int
    log_count: int


@dataclass
class PlayerRatingState:
    """Mutable current rating state while processing a batch."""

    rating: Decimal
    confidence: Decimal | None
    match_count: int


class RatingUpdateGenerator:
    """Generate post-match rating history and rating update audit rows."""

    def generate_for_batch(
        self,
        *,
        batch_id: int,
        session: Session | None = None,
        runtime_recorder: Any | None = None,
    ) -> RatingUpdateResult:
        """Apply rating updates for an existing monthly batch."""
        if session is not None:
            return self._generate_for_batch(
                batch_id=batch_id,
                session=session,
                runtime_recorder=runtime_recorder,
            )

        with session_scope() as active_session:
            return self._generate_for_batch(
                batch_id=batch_id,
                session=active_session,
                runtime_recorder=runtime_recorder,
            )

    def _generate_for_batch(
        self,
        *,
        batch_id: int,
        session: Session,
        runtime_recorder: Any | None = None,
    ) -> RatingUpdateResult:
        batch = session.get(MonthlyBatch, batch_id)
        if batch is None:
            raise ValueError(f"Monthly batch {batch_id} does not exist")

        existing_logs = session.scalar(
            select(func.count())
            .select_from(RatingsUpdateLog)
            .where(RatingsUpdateLog.batch_id == batch_id)
        )
        if existing_logs:
            raise ValueError(f"Monthly batch {batch_id} already has rating updates")

        generation_run = session.get(GenerationRun, batch.generation_run_id)
        config = RatingUpdateConfig.from_payload(
            generation_run.parameter_snapshot if generation_run else None
        )
        with _measure_runtime(
            runtime_recorder,
            "load_matches",
            metadata={"batch_month": batch.batch_month},
        ) as metric:
            matches = _matches_for_batch(session, batch_id)
            metric["output_count"] = len(matches)
        if not matches:
            raise ValueError(f"Monthly batch {batch_id} has no matches")

        with _measure_runtime(
            runtime_recorder,
            "collect_player_ids",
            input_count=len(matches),
        ) as metric:
            player_ids = sorted(
                {
                    player.player_id
                    for match in matches
                    for match_team in match.match_teams
                    for player in match_team.players
                }
            )
            metric["output_count"] = len(player_ids)
        with _measure_runtime(
            runtime_recorder,
            "load_initial_states",
            input_count=len(player_ids),
        ) as metric:
            states = _initial_rating_states(session, player_ids, batch_id)
            metric["output_count"] = len(states)
        missing_players = [player_id for player_id in player_ids if player_id not in states]
        if missing_players:
            raise ValueError(
                "Missing prior rating history for players: "
                + ", ".join(str(player_id) for player_id in missing_players[:10])
            )

        history_rows: list[PlayerRatingHistory] = []
        log_rows: list[RatingsUpdateLog] = []
        match_number = 0
        with _measure_runtime(
            runtime_recorder,
            "compute_rating_updates",
            input_count=len(matches),
        ) as metric:
            for match in matches:
                match_number += 1
                game_count = len(match.games)
                if game_count < 1:
                    raise ValueError(f"Match {match.id} has no games")

                team_summaries = _team_match_summaries(match)
                for match_team in sorted(match.match_teams, key=lambda item: item.team_number):
                    summary = team_summaries[match_team.team_number]
                    for match_player in sorted(
                        match_team.players,
                        key=lambda item: (item.player_position or 0, item.player_id),
                    ):
                        state = states[match_player.player_id]
                        rating_before = state.rating
                        confidence_before = state.confidence
                        k_factor = _k_factor(state, config)
                        rating_delta = (
                            k_factor
                            * (summary.actual_score_share - summary.expected_score_share)
                        ).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
                        rating_after = _clamp_rating(
                            rating_before + rating_delta,
                            config,
                        )
                        rating_delta = (rating_after - rating_before).quantize(
                            Decimal("0.001"),
                            rounding=ROUND_HALF_UP,
                        )
                        confidence_after = _next_confidence(confidence_before, config)
                        state.rating = rating_after
                        state.confidence = confidence_after
                        state.match_count += 1

                        history_rows.append(
                            PlayerRatingHistory(
                                player_id=match_player.player_id,
                                rating_date=match.match_date,
                                rating_type="match_update",
                                rating_value=rating_after,
                                confidence_score=confidence_after,
                                expected_performance=summary.expected_score_share,
                                match_count_used=state.match_count,
                                calculation_version=CALCULATION_VERSION,
                                batch_id=batch_id,
                            )
                        )
                        log_rows.append(
                            RatingsUpdateLog(
                                generation_run_id=batch.generation_run_id,
                                batch_id=batch_id,
                                match_id=match.id,
                                match_number=match_number,
                                match_date=match.match_date,
                                player_id=match_player.player_id,
                                match_team_id=match_team.id,
                                team_number=match_team.team_number,
                                rating_type="match_update",
                                rating_before=rating_before,
                                rating_after=rating_after,
                                rating_delta=rating_delta,
                                expected_score_share=summary.expected_score_share,
                                actual_score_share=summary.actual_score_share,
                                expected_raw_points=summary.expected_raw_points,
                                actual_raw_points=summary.actual_raw_points,
                                games_played=game_count,
                                games_won=summary.games_won,
                                match_won=(
                                    1 if match.winning_team_id == match_team.id else 0
                                ),
                                k_factor=k_factor,
                                confidence_before=confidence_before,
                                confidence_after=confidence_after,
                                calculation_version=CALCULATION_VERSION,
                            )
                        )
            metric["output_count"] = len(log_rows)
            metric["metadata"]["rating_history_count"] = len(history_rows)
            metric["metadata"]["log_count"] = len(log_rows)

        with _measure_runtime(
            runtime_recorder,
            "stage_rating_history_rows",
            input_count=len(history_rows),
        ) as metric:
            session.add_all(history_rows)
            metric["output_count"] = len(history_rows)
        with _measure_runtime(
            runtime_recorder,
            "stage_rating_log_rows",
            input_count=len(log_rows),
        ) as metric:
            session.add_all(log_rows)
            metric["output_count"] = len(log_rows)
        with _measure_runtime(
            runtime_recorder,
            "flush_rating_rows",
            input_count=len(history_rows) + len(log_rows),
            metadata={
                "rating_history_count": len(history_rows),
                "log_count": len(log_rows),
            },
        ) as metric:
            batch.rating_update_count = len(history_rows)
            session.flush()
            metric["output_count"] = len(history_rows) + len(log_rows)
        if runtime_recorder is not None:
            runtime_recorder.flush()
        return RatingUpdateResult(
            batch_id=batch_id,
            match_count=len(matches),
            player_update_count=len(log_rows),
            rating_history_count=len(history_rows),
            log_count=len(log_rows),
        )


@dataclass(frozen=True)
class TeamMatchSummary:
    """Aggregated expected and actual match performance for one team."""

    expected_score_share: Decimal
    actual_score_share: Decimal
    expected_raw_points: Decimal
    actual_raw_points: Decimal
    games_won: int


def _matches_for_batch(session: Session, batch_id: int) -> list[Match]:
    return list(
        session.scalars(
            select(Match)
            .where(Match.batch_id == batch_id)
            .options(
                selectinload(Match.games),
                selectinload(Match.match_teams).selectinload(MatchTeam.players),
            )
            .order_by(Match.match_date, Match.id)
        )
    )


def _measure_runtime(
    runtime_recorder: Any | None,
    subphase_name: str,
    *,
    input_count: int | None = None,
    output_count: int | None = None,
    attempt_count: int | None = None,
    metadata: dict[str, Any] | None = None,
) -> ContextManager[dict[str, Any]]:
    if runtime_recorder is None:
        return nullcontext(
            {
                "input_count": input_count,
                "output_count": output_count,
                "attempt_count": attempt_count,
                "metadata": dict(metadata or {}),
            }
        )
    return runtime_recorder.measure(
        subphase_name,
        input_count=input_count,
        output_count=output_count,
        attempt_count=attempt_count,
        metadata=metadata,
    )


def _team_match_summaries(match: Match) -> dict[int, TeamMatchSummary]:
    team_numbers = sorted(match_team.team_number for match_team in match.match_teams)
    if team_numbers != [1, 2]:
        raise ValueError(f"Match {match.id} must have teams 1 and 2")
    empty_team_numbers = [
        match_team.team_number
        for match_team in match.match_teams
        if not match_team.players
    ]
    if empty_team_numbers:
        raise ValueError(
            f"Match {match.id} has teams without players: "
            + ", ".join(str(team_number) for team_number in empty_team_numbers)
        )

    games = sorted(match.games, key=lambda item: item.game_number)
    expected_one = sum(
        _required_decimal(
            game.expected_team_one_score_share,
            f"Match {match.id} game {game.game_number} expected_team_one_score_share",
        )
        for game in games
    ) / Decimal(len(games))
    actual_one = sum(
        _required_decimal(
            game.actual_team_one_score_share,
            f"Match {match.id} game {game.game_number} actual_team_one_score_share",
        )
        for game in games
    ) / Decimal(len(games))
    expected_one_points = sum(
        _required_decimal(
            game.expected_team_one_score,
            f"Match {match.id} game {game.game_number} expected_team_one_score",
        )
        for game in games
    )
    expected_two_points = sum(
        _required_decimal(
            game.expected_team_two_score,
            f"Match {match.id} game {game.game_number} expected_team_two_score",
        )
        for game in games
    )
    invalid_winners = [
        game.game_number for game in games if game.winning_team_number not in {1, 2}
    ]
    if invalid_winners:
        raise ValueError(
            f"Match {match.id} has games with invalid winning teams: "
            + ", ".join(str(game_number) for game_number in invalid_winners)
        )
    actual_one_points = sum(Decimal(game.team_one_score) for game in games)
    actual_two_points = sum(Decimal(game.team_two_score) for game in games)
    one_games_won = sum(1 for game in games if game.winning_team_number == 1)
    two_games_won = sum(1 for game in games if game.winning_team_number == 2)
    return {
        1: TeamMatchSummary(
            expected_score_share=expected_one.quantize(Decimal("0.0001")),
            actual_score_share=actual_one.quantize(Decimal("0.0001")),
            expected_raw_points=expected_one_points.quantize(Decimal("0.001")),
            actual_raw_points=actual_one_points.quantize(Decimal("0.001")),
            games_won=one_games_won,
        ),
        2: TeamMatchSummary(
            expected_score_share=(Decimal("1") - expected_one).quantize(
                Decimal("0.0001")
            ),
            actual_score_share=(Decimal("1") - actual_one).quantize(Decimal("0.0001")),
            expected_raw_points=expected_two_points.quantize(Decimal("0.001")),
            actual_raw_points=actual_two_points.quantize(Decimal("0.001")),
            games_won=two_games_won,
        ),
    }


def _initial_rating_states(
    session: Session,
    player_ids: list[int],
    batch_id: int,
) -> dict[int, PlayerRatingState]:
    states: dict[int, PlayerRatingState] = {}
    for player_id in player_ids:
        rows = list(
            session.scalars(
                select(PlayerRatingHistory)
                .where(
                    PlayerRatingHistory.player_id == player_id,
                    PlayerRatingHistory.batch_id <= batch_id,
                )
                .order_by(
                    PlayerRatingHistory.rating_date.desc(),
                    PlayerRatingHistory.id.desc(),
                )
            )
        )
        if not rows:
            continue
        latest = rows[0]
        states[player_id] = PlayerRatingState(
            rating=_decimal(latest.rating_value),
            confidence=(
                _decimal(latest.confidence_score)
                if latest.confidence_score is not None
                else None
            ),
            match_count=sum(1 for row in rows if row.rating_type == "match_update"),
        )
    return states


def _k_factor(state: PlayerRatingState, config: RatingUpdateConfig) -> Decimal:
    if state.rating >= Decimal("4000"):
        return config.k_factor_elite
    if state.match_count < 10:
        return config.k_factor_new_player
    return config.k_factor_established


def _next_confidence(
    confidence_before: Decimal | None,
    config: RatingUpdateConfig,
) -> Decimal | None:
    if confidence_before is None:
        return None
    return min(
        config.confidence_max,
        confidence_before + config.confidence_increment_per_match,
    ).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)


def _clamp_rating(value: Decimal, config: RatingUpdateConfig) -> Decimal:
    return max(config.rating_min, min(config.rating_max, value)).quantize(
        Decimal("0.001"),
        rounding=ROUND_HALF_UP,
    )


def _decimal(value: object) -> Decimal:
    return Decimal(str(value))


def _required_decimal(value: object | None, field_name: str) -> Decimal:
    if value is None:
        raise ValueError(f"{field_name} is required for rating updates")
    return _decimal(value)


def _positive_decimal(value: object, name: str) -> Decimal:
    parsed = _decimal(value)
    if parsed <= 0:
        raise ValueError(f"{name} must be positive")
    return parsed


def _probability(value: object) -> Decimal:
    parsed = _decimal(value)
    if parsed < 0 or parsed > 1:
        raise ValueError("probability must be between 0 and 1")
    return parsed
