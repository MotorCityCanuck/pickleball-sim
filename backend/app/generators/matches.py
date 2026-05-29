"""Generate monthly matches, match teams, players, and games."""
from __future__ import annotations

from calendar import monthrange
from contextlib import nullcontext
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
import random
from typing import Any, Callable, ContextManager

from sqlalchemy import func, insert, or_, select
from sqlalchemy.orm import Session

from app.core.default_configuration import DEFAULT_CONFIG_PAYLOAD
from app.db.session import session_scope
from app.models import (
    Match,
    MatchGame,
    MatchTeam,
    MatchTeamPlayer,
    MonthlyBatch,
    Player,
    PlayerRatingHistory,
    Team,
    TeamMembership,
)

from .games import games_per_match, generate_match_games
from .players import WeightedSampler, _decimal


@dataclass(frozen=True)
class MatchGenerationConfig:
    """Match generation settings resolved from a configuration payload."""

    monthly_matches_per_active_player_mean: Decimal
    monthly_matches_per_active_player_std_dev: Decimal
    match_volume_noise_factor: Decimal
    matches_per_team_per_month: Decimal
    saturday_weight: Decimal
    sunday_weight: Decimal
    friday_weight: Decimal
    weekday_evening_weight: Decimal
    max_daily_matches_per_team: int
    match_type_weights: tuple[tuple[str, Decimal], ...]
    rating_band_width: dict[str, Decimal]
    matchmaking_noise_factor: Decimal
    rematch_penalty_window_days: int
    locality_weight: Decimal
    games_per_match: dict[str, int]
    game_target_score: int
    win_by_two_rule_enabled: bool
    win_by_two_extension_rate: Decimal
    score_noise_std_dev: Decimal
    upset_probability_boost: Decimal

    @classmethod
    def from_payload(cls, payload: dict[str, Any] | None) -> "MatchGenerationConfig":
        source = payload or DEFAULT_CONFIG_PAYLOAD
        scheduling = source.get("match_scheduling", {})
        match_types = source.get("match_types", {})
        matchmaking = source.get("matchmaking", {})
        games = source.get("games_and_scores", {})

        matches_per_team_per_month = scheduling.get("matches_per_team_per_month")
        monthly_matches_per_active_player_mean = scheduling.get(
            "monthly_matches_per_active_player_mean"
        )
        if matches_per_team_per_month is None:
            if monthly_matches_per_active_player_mean is None:
                resolved_team_matches = Decimal("4.0")
            else:
                resolved_team_matches = _positive_decimal(
                    _decimal(monthly_matches_per_active_player_mean) / Decimal("2"),
                    "monthly_matches_per_active_player_mean",
                )
        else:
            resolved_team_matches = _positive_decimal(
                matches_per_team_per_month,
                "matches_per_team_per_month",
            )

        if monthly_matches_per_active_player_mean is None:
            resolved_player_mean = resolved_team_matches * Decimal("2")
        else:
            resolved_player_mean = _positive_decimal(
                monthly_matches_per_active_player_mean,
                "monthly_matches_per_active_player_mean",
            )

        resolved_player_std_dev = _nonnegative_decimal(
            scheduling.get("monthly_matches_per_active_player_std_dev", 4.0),
            "monthly_matches_per_active_player_std_dev",
        )
        match_volume_noise_factor = _probability(
            scheduling.get("match_volume_noise_factor", 0.15),
            "match_volume_noise_factor",
        )

        max_daily = int(scheduling.get("max_daily_matches_per_team", 2))
        if max_daily < 1:
            raise ValueError("max_daily_matches_per_team must be at least 1")

        game_target_score = int(games.get("game_target_score", 11))
        if game_target_score not in {11, 15, 21}:
            raise ValueError("game_target_score must be 11, 15, or 21")

        return cls(
            monthly_matches_per_active_player_mean=resolved_player_mean,
            monthly_matches_per_active_player_std_dev=resolved_player_std_dev,
            match_volume_noise_factor=match_volume_noise_factor,
            matches_per_team_per_month=resolved_team_matches,
            saturday_weight=_positive_decimal(
                scheduling.get("saturday_weight", 2.25),
                "saturday_weight",
            ),
            sunday_weight=_positive_decimal(
                scheduling.get("sunday_weight", 1.85),
                "sunday_weight",
            ),
            friday_weight=_positive_decimal(
                scheduling.get("friday_weight", 1.2),
                "friday_weight",
            ),
            weekday_evening_weight=_positive_decimal(
                scheduling.get("weekday_evening_weight", 1.0),
                "weekday_evening_weight",
            ),
            max_daily_matches_per_team=max_daily,
            match_type_weights=_weighted_probabilities(
                match_types.get(
                    "weights",
                    {
                        "recreational": 0.55,
                        "league": 0.2,
                        "ladder": 0.1,
                        "tournament": 0.1,
                        "challenge": 0.04,
                        "clinic": 0.01,
                    },
                ),
                "match_types.weights",
            ),
            rating_band_width={
                key: _positive_decimal(value, f"rating_band_width.{key}")
                for key, value in matchmaking.get(
                    "rating_band_width",
                    {
                        "recreational": 400,
                        "competitive": 150,
                        "tournament": 100,
                    },
                ).items()
            },
            matchmaking_noise_factor=_probability(
                matchmaking.get("matchmaking_noise_factor", 0.2),
                "matchmaking_noise_factor",
            ),
            rematch_penalty_window_days=_nonnegative_int(
                matchmaking.get("rematch_penalty_window_days", 30),
                "rematch_penalty_window_days",
            ),
            locality_weight=_probability(
                matchmaking.get("locality_weight", 0.3),
                "locality_weight",
            ),
            games_per_match={
                key: _positive_int(value, f"games_per_match.{key}")
                for key, value in games.get(
                    "games_per_match",
                    {
                        "recreational": 1,
                        "league": 2,
                        "tournament": 3,
                    },
                ).items()
            },
            game_target_score=game_target_score,
            win_by_two_rule_enabled=bool(games.get("win_by_two_rule_enabled", True)),
            win_by_two_extension_rate=_probability(
                games.get("win_by_two_extension_rate", 0.10),
                "win_by_two_extension_rate",
            ),
            score_noise_std_dev=_positive_decimal(
                games.get("score_noise_std_dev", 1.5),
                "score_noise_std_dev",
            ),
            upset_probability_boost=_probability(
                games.get("upset_probability_boost", 0.15),
                "upset_probability_boost",
            ),
        )


@dataclass(frozen=True)
class MatchGenerationResult:
    """Summary of generated match rows."""

    batch_id: int
    match_count: int
    match_team_count: int
    match_team_player_count: int
    game_count: int


@dataclass(frozen=True)
class MatchGenerationProgress:
    """Progress update emitted during long-running match generation."""

    progress_current: int
    progress_total: int
    progress_unit: str
    message: str
    heartbeat_quiet_after_seconds: int | None = None
    heartbeat_likely_stalled_after_seconds: int | None = None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TeamCandidate:
    """Active team data used by matchmaking."""

    id: int
    team_type: str
    region_id: int | None
    average_rating: Decimal
    players: tuple[tuple[int, int, Decimal], ...]


class MatchTeamPool:
    """Indexed active team pool for scalable monthly matchmaking."""

    def __init__(self, teams: list[TeamCandidate]) -> None:
        self.by_id = {team.id: team for team in teams}
        self.all_ids = [team.id for team in teams]
        self.ids_by_region: dict[int, list[int]] = {}
        self.ids_by_type: dict[str, list[int]] = {}
        for team in teams:
            if team.region_id is not None:
                self.ids_by_region.setdefault(team.region_id, []).append(team.id)
            self.ids_by_type.setdefault(team.team_type, []).append(team.id)

    def choose_team(
        self,
        rng: random.Random,
        *,
        source_ids: list[int] | None = None,
        team_day_counts: dict[tuple[int, date], int],
        match_date: date,
        config: MatchGenerationConfig,
    ) -> TeamCandidate | None:
        team_id = self._random_available_id(
            rng,
            self.all_ids if source_ids is None else source_ids,
            team_day_counts=team_day_counts,
            match_date=match_date,
            config=config,
        )
        return self.by_id[team_id] if team_id is not None else None

    def choose_opponent(
        self,
        rng: random.Random,
        *,
        allowed_team_ids: set[int] | None = None,
        first_team: TeamCandidate,
        match_date: date,
        match_type: str,
        recent_pair_dates: dict[frozenset[int], list[date]],
        team_day_counts: dict[tuple[int, date], int],
        config: MatchGenerationConfig,
    ) -> TeamCandidate | None:
        band = _rating_band(match_type, config)
        sampled = self._sample_opponents(
            rng,
            first_team=first_team,
            source_ids=self._preferred_source_ids(
                first_team,
                allowed_team_ids=allowed_team_ids,
            ),
            match_date=match_date,
            band=band,
            require_rating_band=True,
            require_rematch_penalty=True,
            recent_pair_dates=recent_pair_dates,
            team_day_counts=team_day_counts,
            config=config,
        )
        if not sampled:
            sampled = self._sample_opponents(
                rng,
                first_team=first_team,
                source_ids=self._filtered_source_ids(allowed_team_ids),
                match_date=match_date,
                band=band,
                require_rating_band=True,
                require_rematch_penalty=True,
                recent_pair_dates=recent_pair_dates,
                team_day_counts=team_day_counts,
                config=config,
            )
        if not sampled:
            sampled = self._sample_opponents(
                rng,
                first_team=first_team,
                source_ids=self._filtered_source_ids(allowed_team_ids),
                match_date=match_date,
                band=band,
                require_rating_band=False,
                require_rematch_penalty=True,
                recent_pair_dates=recent_pair_dates,
                team_day_counts=team_day_counts,
                config=config,
            )
        if not sampled:
            sampled = self._sample_opponents(
                rng,
                first_team=first_team,
                source_ids=self._filtered_source_ids(allowed_team_ids),
                match_date=match_date,
                band=band,
                require_rating_band=False,
                require_rematch_penalty=False,
                recent_pair_dates=recent_pair_dates,
                team_day_counts=team_day_counts,
                config=config,
            )
        if not sampled:
            return None

        return _choose_weighted_opponent(
            rng,
            first_team=first_team,
            candidates=sampled,
            band=band,
            config=config,
        )

    def _preferred_source_ids(
        self,
        first_team: TeamCandidate,
        *,
        allowed_team_ids: set[int] | None = None,
    ) -> list[int]:
        if first_team.region_id is not None:
            region_ids = self.ids_by_region.get(first_team.region_id, [])
            if region_ids:
                filtered = self._filter_ids(region_ids, allowed_team_ids)
                if filtered:
                    return filtered
        type_ids = self.ids_by_type.get(first_team.team_type, self.all_ids)
        filtered = self._filter_ids(type_ids, allowed_team_ids)
        if filtered:
            return filtered
        return self._filtered_source_ids(allowed_team_ids)

    def _filtered_source_ids(self, allowed_team_ids: set[int] | None) -> list[int]:
        return self._filter_ids(self.all_ids, allowed_team_ids)

    @staticmethod
    def _filter_ids(
        source_ids: list[int],
        allowed_team_ids: set[int] | None,
    ) -> list[int]:
        if allowed_team_ids is None:
            return source_ids
        return [team_id for team_id in source_ids if team_id in allowed_team_ids]

    def _sample_opponents(
        self,
        rng: random.Random,
        *,
        first_team: TeamCandidate,
        source_ids: list[int],
        match_date: date,
        band: Decimal,
        require_rating_band: bool,
        require_rematch_penalty: bool,
        recent_pair_dates: dict[frozenset[int], list[date]],
        team_day_counts: dict[tuple[int, date], int],
        config: MatchGenerationConfig,
    ) -> list[TeamCandidate]:
        sample_size = min(16, max(8, len(source_ids)))
        sampled: dict[int, TeamCandidate] = {}
        attempts = min(max(sample_size * 20, 100), max(len(source_ids) * 2, 100))
        for _ in range(attempts):
            if len(sampled) >= sample_size:
                break
            if not source_ids:
                break
            team_id = source_ids[rng.randrange(len(source_ids))]
            if team_id in sampled:
                continue
            candidate = self.by_id[team_id]
            if self._valid_opponent(
                first_team,
                candidate,
                match_date=match_date,
                band=band,
                require_rating_band=require_rating_band,
                require_rematch_penalty=require_rematch_penalty,
                recent_pair_dates=recent_pair_dates,
                team_day_counts=team_day_counts,
                config=config,
            ):
                sampled[team_id] = candidate

        if sampled:
            return list(sampled.values())

        # Fallback for small or saturated source pools.
        for team_id in source_ids:
            candidate = self.by_id[team_id]
            if self._valid_opponent(
                first_team,
                candidate,
                match_date=match_date,
                band=band,
                require_rating_band=require_rating_band,
                require_rematch_penalty=require_rematch_penalty,
                recent_pair_dates=recent_pair_dates,
                team_day_counts=team_day_counts,
                config=config,
            ):
                sampled[team_id] = candidate
                if len(sampled) >= sample_size:
                    break
        return list(sampled.values())

    def _random_available_id(
        self,
        rng: random.Random,
        source_ids: list[int],
        *,
        team_day_counts: dict[tuple[int, date], int],
        match_date: date,
        config: MatchGenerationConfig,
    ) -> int | None:
        if not source_ids:
            return None
        attempts = min(max(len(source_ids), 100), 1_000)
        for _ in range(attempts):
            team_id = source_ids[rng.randrange(len(source_ids))]
            if (
                team_day_counts.get((team_id, match_date), 0)
                < config.max_daily_matches_per_team
            ):
                return team_id
        for team_id in source_ids:
            if (
                team_day_counts.get((team_id, match_date), 0)
                < config.max_daily_matches_per_team
            ):
                return team_id
        return None

    def _valid_opponent(
        self,
        first_team: TeamCandidate,
        candidate: TeamCandidate,
        *,
        match_date: date,
        band: Decimal,
        require_rating_band: bool,
        require_rematch_penalty: bool,
        recent_pair_dates: dict[frozenset[int], list[date]],
        team_day_counts: dict[tuple[int, date], int],
        config: MatchGenerationConfig,
    ) -> bool:
        return (
            candidate.id != first_team.id
            and team_day_counts.get((candidate.id, match_date), 0)
            < config.max_daily_matches_per_team
            and (
                not require_rematch_penalty
                or not _pairing_within_rematch_window(
                    first_team.id,
                    candidate.id,
                    match_date=match_date,
                    recent_pair_dates=recent_pair_dates,
                    config=config,
                )
            )
            and (
                not require_rating_band
                or abs(candidate.average_rating - first_team.average_rating) <= band
            )
        )


class MatchGenerator:
    """Generate scheduled matches and games for one monthly batch."""

    def generate_for_batch(
        self,
        *,
        batch_id: int,
        progress_listener: Callable[[MatchGenerationProgress], None] | None = None,
        session: Session | None = None,
        runtime_recorder: Any | None = None,
    ) -> MatchGenerationResult:
        """Generate matches for an existing monthly batch."""
        if session is not None:
            return self._generate_for_batch(
                batch_id=batch_id,
                progress_listener=progress_listener,
                session=session,
                runtime_recorder=runtime_recorder,
            )

        with session_scope() as active_session:
            return self._generate_for_batch(
                batch_id=batch_id,
                progress_listener=progress_listener,
                session=active_session,
                runtime_recorder=runtime_recorder,
            )

    def _generate_for_batch(
        self,
        *,
        batch_id: int,
        progress_listener: Callable[[MatchGenerationProgress], None] | None,
        session: Session,
        runtime_recorder: Any | None = None,
    ) -> MatchGenerationResult:
        batch = session.get(MonthlyBatch, batch_id)
        if batch is None:
            raise ValueError(f"Monthly batch {batch_id} does not exist")

        existing_matches = session.scalar(
            select(func.count()).select_from(Match).where(Match.batch_id == batch_id)
        )
        if existing_matches:
            raise ValueError(f"Monthly batch {batch_id} already has matches")

        config = MatchGenerationConfig.from_payload(
            batch.generation_run.parameter_snapshot
            if hasattr(batch, "generation_run") and batch.generation_run
            else _generation_payload(session, batch)
        )
        with _measure_runtime(
            runtime_recorder,
            "load_active_teams",
            metadata={"batch_month": batch.batch_month},
        ) as metric:
            teams = _active_teams(session, batch.generation_run_id, batch.batch_month)
            metric["output_count"] = len(teams)
        if len(teams) < 2:
            raise ValueError("At least two active teams are required")

        rng = random.Random(
            int(batch.generation_run_id) * 1_000_003 + int(batch_id) * 10_007 + 41
        )
        with _measure_runtime(
            runtime_recorder,
            "calculate_team_targets",
            input_count=len(teams),
        ) as metric:
            team_target_matches = _team_target_match_counts(teams, rng, config)
            target_match_count = sum(team_target_matches.values()) // 2
            metric["output_count"] = target_match_count
            metric["metadata"]["team_target_sum"] = sum(team_target_matches.values())
        date_sampler = _date_sampler(batch.batch_month, config)
        match_type_sampler = WeightedSampler(config.match_type_weights)
        with _measure_runtime(
            runtime_recorder,
            "load_recent_pair_dates",
            input_count=len(teams),
        ) as metric:
            recent_pair_dates = _recent_pair_dates(
                session,
                generation_run_id=batch.generation_run_id,
                batch_month=batch.batch_month,
                active_teams=teams,
            )
            metric["output_count"] = len(recent_pair_dates)
            metric["metadata"]["prior_pair_date_count"] = sum(
                len(pair_dates) for pair_dates in recent_pair_dates.values()
            )
        team_day_counts: dict[tuple[int, date], int] = {}
        team_month_counts: dict[int, int] = {}
        team_pool = MatchTeamPool(teams)
        matches: list[Match] = []
        pairings: list[tuple[Match, TeamCandidate, TeamCandidate, Decimal]] = []
        attempts = 0
        max_attempts = max(target_match_count * 40, 200)
        heartbeat_chunk_size = max(min(target_match_count // 20, 5_000), 500)
        self._emit_progress(
            progress_listener,
            progress_current=0,
            progress_total=max(target_match_count, 1),
            progress_unit="match",
            message=f"Planning up to {target_match_count} matches for batch {batch.batch_month}.",
            details={
                "phase": "planning",
                "target_match_count": target_match_count,
                "active_team_count": len(teams),
            },
        )

        with _measure_runtime(
            runtime_recorder,
            "planning",
            input_count=target_match_count,
            metadata={
                "active_team_count": len(teams),
                "max_attempts": max_attempts,
                "heartbeat_chunk_size": heartbeat_chunk_size,
            },
        ) as metric:
            while len(matches) < target_match_count and attempts < max_attempts:
                attempts += 1
                under_target_ids = [
                    team.id
                    for team in teams
                    if team_month_counts.get(team.id, 0) < team_target_matches[team.id]
                ]
                if len(under_target_ids) < 2:
                    break
                match_date = date_sampler.choose(rng)
                match_type = str(match_type_sampler.choose(rng))
                first_team = team_pool.choose_team(
                    rng,
                    source_ids=under_target_ids,
                    team_day_counts=team_day_counts,
                    match_date=match_date,
                    config=config,
                )
                if first_team is None:
                    continue
                second_team = team_pool.choose_opponent(
                    rng,
                    allowed_team_ids=set(under_target_ids),
                    first_team=first_team,
                    match_date=match_date,
                    match_type=match_type,
                    recent_pair_dates=recent_pair_dates,
                    team_day_counts=team_day_counts,
                    config=config,
                )
                if second_team is None:
                    continue

                expected_win_probability = _expected_win_probability(
                    first_team.average_rating,
                    second_team.average_rating,
                )
                match = Match(
                    match_date=match_date,
                    region_id=first_team.region_id or second_team.region_id,
                    match_type=match_type,
                    court_type="standard",
                    match_format=_match_format(match_type, config),
                    predicted_winning_team_number=(
                        1 if expected_win_probability >= Decimal("0.5") else 2
                    ),
                    predicted_win_probability=max(
                        expected_win_probability,
                        Decimal("1") - expected_win_probability,
                    ),
                    expected_competitiveness=_competitiveness(expected_win_probability),
                    simulation_noise_factor=_noise_value(
                        rng,
                        config.matchmaking_noise_factor,
                    ),
                    batch_id=batch_id,
                )
                matches.append(match)
                pairings.append((match, first_team, second_team, expected_win_probability))
                team_day_counts[(first_team.id, match_date)] = (
                    team_day_counts.get((first_team.id, match_date), 0) + 1
                )
                team_day_counts[(second_team.id, match_date)] = (
                    team_day_counts.get((second_team.id, match_date), 0) + 1
                )
                team_month_counts[first_team.id] = (
                    team_month_counts.get(first_team.id, 0) + 1
                )
                team_month_counts[second_team.id] = (
                    team_month_counts.get(second_team.id, 0) + 1
                )
                recent_pair_dates.setdefault(
                    frozenset((first_team.id, second_team.id)),
                    [],
                ).append(match_date)
                if len(matches) % heartbeat_chunk_size == 0:
                    self._emit_progress(
                        progress_listener,
                        progress_current=len(matches),
                        progress_total=max(target_match_count, 1),
                        progress_unit="match",
                        message=(
                            f"Planned {len(matches)}/{target_match_count} matches "
                            f"for {batch.batch_month}."
                        ),
                        details={
                            "phase": "planning",
                            "attempts": attempts,
                            "target_match_count": target_match_count,
                        },
                    )
            metric["output_count"] = len(matches)
            metric["attempt_count"] = attempts
            metric["metadata"]["target_match_count"] = target_match_count
            metric["metadata"]["success_rate"] = (
                round(len(matches) / attempts, 6) if attempts else None
            )

        with _measure_runtime(
            runtime_recorder,
            "persist_matches",
            input_count=len(matches),
        ) as metric:
            session.add_all(matches)
            session.flush()
            metric["output_count"] = len(matches)
        self._emit_progress(
            progress_listener,
            progress_current=len(matches),
            progress_total=max(target_match_count, 1),
            progress_unit="match",
            message=(
                f"Persisted {len(matches)}/{target_match_count} planned matches "
                f"for {batch.batch_month}."
            ),
            details={
                "phase": "matches_persisted",
                "attempts": attempts,
                "target_match_count": target_match_count,
            },
        )

        match_teams: list[MatchTeam] = []
        match_team_player_rows: list[dict[str, Any]] = []
        game_rows: list[dict[str, Any]] = []
        with _measure_runtime(
            runtime_recorder,
            "scoring",
            input_count=len(pairings),
        ) as metric:
            for index, (match, first_team, second_team, expected_prob) in enumerate(
                pairings,
                start=1,
            ):
                generated_games = generate_match_games(
                    rng,
                    match=match,
                    expected_team_one_win_probability=expected_prob,
                    match_type=match.match_type,
                    config=config,
                )
                team_one = MatchTeam(
                    match_id=match.id,
                    team_number=1,
                    team_score=generated_games.team_one_games_won,
                    expected_win_probability=expected_prob,
                    average_team_rating=first_team.average_rating,
                )
                team_two = MatchTeam(
                    match_id=match.id,
                    team_number=2,
                    team_score=generated_games.team_two_games_won,
                    expected_win_probability=Decimal("1") - expected_prob,
                    average_team_rating=second_team.average_rating,
                )
                match_teams.extend([team_one, team_two])
                game_rows.extend(_match_game_rows(generated_games.games))
                match.total_points_played = sum(
                    game.team_one_score + game.team_two_score
                    for game in generated_games.games
                )
                if index % heartbeat_chunk_size == 0:
                    self._emit_progress(
                        progress_listener,
                        progress_current=index,
                        progress_total=max(target_match_count, 1),
                        progress_unit="match",
                        message=(
                            f"Scored {index}/{target_match_count} matches "
                            f"for {batch.batch_month}."
                        ),
                        details={
                            "phase": "scoring",
                            "game_count_so_far": len(game_rows),
                            "target_match_count": target_match_count,
                        },
                    )
            metric["output_count"] = len(game_rows)
            metric["metadata"]["match_team_count"] = len(match_teams)
            metric["metadata"]["game_count"] = len(game_rows)

        with _measure_runtime(
            runtime_recorder,
            "persist_match_teams",
            input_count=len(match_teams),
        ) as metric:
            session.add_all(match_teams)
            session.flush()
            metric["output_count"] = len(match_teams)
        self._emit_progress(
            progress_listener,
            progress_current=len(pairings),
            progress_total=max(target_match_count, 1),
            progress_unit="match",
            message=(
                f"Persisted match teams for {len(pairings)}/{target_match_count} matches "
                f"in {batch.batch_month}."
            ),
            details={
                "phase": "match_teams_persisted",
                "match_team_count": len(match_teams),
                "target_match_count": target_match_count,
            },
        )

        with _measure_runtime(
            runtime_recorder,
            "build_match_team_players",
            input_count=len(pairings),
        ) as metric:
            for pairing_index, (_, first_team, second_team, _) in enumerate(pairings):
                team_one = match_teams[pairing_index * 2]
                team_two = match_teams[pairing_index * 2 + 1]
                match_team_player_rows.extend(
                    _match_team_player_rows(team_one, first_team)
                )
                match_team_player_rows.extend(
                    _match_team_player_rows(team_two, second_team)
                )
                match = pairings[pairing_index][0]
                winning_match_team = (
                    team_one if team_one.team_score > team_two.team_score else team_two
                )
                match.winning_team_id = winning_match_team.id
            metric["output_count"] = len(match_team_player_rows)

        with _measure_runtime(
            runtime_recorder,
            "persist_match_related_rows",
            input_count=len(match_team_player_rows) + len(game_rows),
            metadata={
                "match_team_player_count": len(match_team_player_rows),
                "game_count": len(game_rows),
            },
        ) as metric:
            if match_team_player_rows:
                session.execute(insert(MatchTeamPlayer), match_team_player_rows)
            if game_rows:
                session.execute(insert(MatchGame), game_rows)
            session.flush()
            metric["output_count"] = len(match_team_player_rows) + len(game_rows)

        with _measure_runtime(
            runtime_recorder,
            "finalize_batch",
            input_count=len(matches),
        ) as metric:
            batch.match_count_generated = len(matches)
            session.flush()
            metric["output_count"] = len(matches)

        if runtime_recorder is not None:
            runtime_recorder.flush()

        return MatchGenerationResult(
            batch_id=batch_id,
            match_count=len(matches),
            match_team_count=len(match_teams),
            match_team_player_count=len(match_team_player_rows),
            game_count=len(game_rows),
        )

    @staticmethod
    def _emit_progress(
        progress_listener: Callable[[MatchGenerationProgress], None] | None,
        *,
        progress_current: int,
        progress_total: int,
        progress_unit: str,
        message: str,
        details: dict[str, Any],
    ) -> None:
        if progress_listener is None:
            return
        progress_listener(
            MatchGenerationProgress(
                progress_current=progress_current,
                progress_total=progress_total,
                progress_unit=progress_unit,
                message=message,
                heartbeat_quiet_after_seconds=20 * 60,
                heartbeat_likely_stalled_after_seconds=60 * 60,
                details=details,
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


def _generation_payload(session: Session, batch: MonthlyBatch) -> dict[str, Any] | None:
    from app.models import GenerationRun

    generation_run = session.get(GenerationRun, batch.generation_run_id)
    return generation_run.parameter_snapshot if generation_run is not None else None


def _active_teams(
    session: Session,
    generation_run_id: int,
    batch_month: date,
) -> list[TeamCandidate]:
    latest_ratings = (
        select(
            PlayerRatingHistory.player_id.label("player_id"),
            PlayerRatingHistory.rating_value.label("rating_value"),
            func.row_number()
            .over(
                partition_by=PlayerRatingHistory.player_id,
                order_by=(
                    PlayerRatingHistory.rating_date.desc(),
                    PlayerRatingHistory.id.desc(),
                ),
            )
            .label("rating_rank"),
        )
        .join(Player, Player.id == PlayerRatingHistory.player_id)
        .where(
            Player.generation_run_id == generation_run_id,
            Player.player_status == "ACTIVE",
            PlayerRatingHistory.rating_date <= batch_month,
        )
        .subquery()
    )

    team_rows: dict[int, dict[str, Any]] = {}
    for (
        team_id,
        team_type,
        player_id,
        player_position,
        home_region_id,
        rating_value,
    ) in session.execute(
        select(
            Team.id,
            Team.team_type,
            TeamMembership.player_id,
            TeamMembership.player_position,
            Player.home_region_id,
            latest_ratings.c.rating_value,
        )
        .join(TeamMembership, TeamMembership.team_id == Team.id)
        .join(Player, Player.id == TeamMembership.player_id)
        .join(latest_ratings, latest_ratings.c.player_id == Player.id)
        .where(
            Team.generation_run_id == generation_run_id,
            Team.team_status == "active",
            Team.formation_date <= batch_month,
            or_(Team.dissolution_date.is_(None), Team.dissolution_date > batch_month),
            TeamMembership.joined_date <= batch_month,
            or_(
                TeamMembership.left_date.is_(None),
                TeamMembership.left_date > batch_month,
            ),
            latest_ratings.c.rating_rank == 1,
        )
        .order_by(Team.id, TeamMembership.player_position)
    ):
        row = team_rows.setdefault(
            team_id,
            {
                "team_type": team_type,
                "region_id": home_region_id,
                "players": [],
            },
        )
        row["players"].append(
            (player_id, player_position, _decimal(rating_value))
        )

    candidates: list[TeamCandidate] = []
    for team_id, row in team_rows.items():
        if len(row["players"]) != 2:
            continue
        players = tuple(sorted(row["players"], key=lambda player: player[1]))
        average_rating = (players[0][2] + players[1][2]) / Decimal("2")
        candidates.append(
            TeamCandidate(
                id=team_id,
                team_type=row["team_type"],
                region_id=row["region_id"],
                average_rating=average_rating,
                players=players,
            )
        )
    return candidates


def _date_sampler(
    batch_month: date,
    config: MatchGenerationConfig,
) -> WeightedSampler[date]:
    _, last_day = monthrange(batch_month.year, batch_month.month)
    weighted_dates = []
    for day in range(1, last_day + 1):
        current_date = date(batch_month.year, batch_month.month, day)
        weekday = current_date.weekday()
        if weekday == 5:
            weight = config.saturday_weight
        elif weekday == 6:
            weight = config.sunday_weight
        elif weekday == 4:
            weight = config.friday_weight
        else:
            weight = config.weekday_evening_weight
        weighted_dates.append((current_date, weight))
    return WeightedSampler(weighted_dates)


def _recent_pair_dates(
    session: Session,
    *,
    generation_run_id: int,
    batch_month: date,
    active_teams: list[TeamCandidate],
) -> dict[frozenset[int], list[date]]:
    roster_to_team_id = {
        _roster_key(player_id for player_id, _, _ in team.players): team.id
        for team in active_teams
    }
    match_team_rows = session.execute(
        select(
            Match.id,
            Match.match_date,
            MatchTeam.id,
            MatchTeamPlayer.player_id,
        )
        .join(MonthlyBatch, MonthlyBatch.id == Match.batch_id)
        .join(MatchTeam, MatchTeam.match_id == Match.id)
        .join(MatchTeamPlayer, MatchTeamPlayer.match_team_id == MatchTeam.id)
        .where(
            MonthlyBatch.generation_run_id == generation_run_id,
            Match.match_date < batch_month,
        )
        .order_by(Match.id, MatchTeam.id, MatchTeamPlayer.player_id)
    )

    grouped_match_teams: dict[tuple[int, date, int], list[int]] = {}
    for match_id, match_date, match_team_id, player_id in match_team_rows:
        grouped_match_teams.setdefault((match_id, match_date, match_team_id), []).append(
            player_id
        )

    match_team_ids_by_match: dict[tuple[int, date], list[int]] = {}
    for (match_id, match_date, _match_team_id), player_ids in grouped_match_teams.items():
        roster_key = _roster_key(player_ids)
        team_id = roster_to_team_id.get(roster_key)
        if team_id is None:
            continue
        match_team_ids_by_match.setdefault((match_id, match_date), []).append(team_id)

    pair_dates: dict[frozenset[int], list[date]] = {}
    for (_match_id, match_date), team_ids in match_team_ids_by_match.items():
        if len(team_ids) != 2 or team_ids[0] == team_ids[1]:
            continue
        pair_dates.setdefault(frozenset(team_ids), []).append(match_date)
    return pair_dates


def _roster_key(player_ids: Any) -> str:
    ordered_ids = sorted(int(player_id) for player_id in player_ids)
    if len(ordered_ids) != 2:
        return ""
    return f"{ordered_ids[0]}:{ordered_ids[1]}"


def _pairing_within_rematch_window(
    first_team_id: int,
    second_team_id: int,
    *,
    match_date: date,
    recent_pair_dates: dict[frozenset[int], list[date]],
    config: MatchGenerationConfig,
) -> bool:
    if config.rematch_penalty_window_days <= 0:
        return False
    pair_key = frozenset((first_team_id, second_team_id))
    prior_dates = recent_pair_dates.get(pair_key, [])
    return any(
        abs((match_date - prior_match_date).days) <= config.rematch_penalty_window_days
        for prior_match_date in prior_dates
    )


def _team_target_match_counts(
    teams: list[TeamCandidate],
    rng: random.Random,
    config: MatchGenerationConfig,
) -> dict[int, int]:
    mean = config.matches_per_team_per_month
    std_dev = (
        config.monthly_matches_per_active_player_std_dev / Decimal("2")
    ).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
    targets = {
        team.id: _sample_team_match_target(
            rng,
            mean=mean,
            std_dev=std_dev,
            noise_factor=config.match_volume_noise_factor,
        )
        for team in teams
    }
    total = sum(targets.values())
    if total % 2:
        selectable_ids = [team.id for team in teams if targets[team.id] > 0] or [
            team.id for team in teams
        ]
        targets[selectable_ids[rng.randrange(len(selectable_ids))]] += 1
    return targets


def _sample_team_match_target(
    rng: random.Random,
    *,
    mean: Decimal,
    std_dev: Decimal,
    noise_factor: Decimal,
) -> int:
    sampled = mean
    if std_dev > 0:
        sampled = Decimal(str(rng.gauss(float(mean), float(std_dev))))
    if noise_factor > 0:
        noise_span = float(mean * noise_factor)
        sampled += Decimal(str(rng.uniform(-noise_span, noise_span)))
    if sampled < 0:
        sampled = Decimal("0")
    return int(sampled.to_integral_value(rounding=ROUND_HALF_UP))


def _opponent_weight(
    first_team: TeamCandidate,
    candidate: TeamCandidate,
    band: Decimal,
    config: MatchGenerationConfig,
    rng: random.Random,
) -> Decimal:
    rating_gap = abs(candidate.average_rating - first_team.average_rating)
    rating_score = max(Decimal("0.01"), Decimal("1") - rating_gap / (band or 1))
    locality_score = (
        Decimal("1")
        if candidate.region_id == first_team.region_id
        else Decimal("0.25")
    )
    noise = Decimal(str(rng.random())) * config.matchmaking_noise_factor
    return rating_score + locality_score * config.locality_weight + noise


def _choose_weighted_opponent(
    rng: random.Random,
    *,
    first_team: TeamCandidate,
    candidates: list[TeamCandidate],
    band: Decimal,
    config: MatchGenerationConfig,
) -> TeamCandidate:
    weighted: list[tuple[TeamCandidate, float]] = []
    total = 0.0
    band_value = float(band or Decimal("1"))
    locality_weight = float(config.locality_weight)
    noise_scale = float(config.matchmaking_noise_factor)
    for candidate in candidates:
        rating_gap = abs(float(candidate.average_rating - first_team.average_rating))
        rating_score = max(0.01, 1.0 - rating_gap / band_value)
        locality_score = 1.0 if candidate.region_id == first_team.region_id else 0.25
        weight = rating_score + locality_score * locality_weight + rng.random() * noise_scale
        total += weight
        weighted.append((candidate, weight))

    threshold = rng.random() * total
    cumulative = 0.0
    for candidate, weight in weighted:
        cumulative += weight
        if cumulative >= threshold:
            return candidate
    return weighted[-1][0]


def _rating_band(match_type: str, config: MatchGenerationConfig) -> Decimal:
    if match_type == "tournament":
        return config.rating_band_width.get("tournament", Decimal("100"))
    if match_type in {"league", "ladder", "challenge"}:
        return config.rating_band_width.get("competitive", Decimal("150"))
    return config.rating_band_width.get("recreational", Decimal("400"))


def _match_format(match_type: str, config: MatchGenerationConfig) -> str:
    games = games_per_match(match_type, config)
    return "single_game" if games == 1 else f"best_of_{games}"


def _expected_win_probability(rating_one: Decimal, rating_two: Decimal) -> Decimal:
    exponent = float((rating_two - rating_one) / Decimal("400"))
    probability = Decimal(str(1 / (1 + 10**exponent)))
    return probability.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def _competitiveness(expected_win_probability: Decimal) -> Decimal:
    value = Decimal("1") - abs(expected_win_probability - Decimal("0.5")) * 2
    return value.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)


def _noise_value(rng: random.Random, scale: Decimal) -> Decimal:
    return (Decimal(str(rng.random())) * scale).quantize(
        Decimal("0.001"),
        rounding=ROUND_HALF_UP,
    )


def _match_team_player_rows(
    match_team: MatchTeam,
    team: TeamCandidate,
) -> list[dict[str, Any]]:
    return [
        {
            "match_team_id": match_team.id,
            "player_id": player_id,
            "player_position": position,
            "player_rating_at_match": rating,
        }
        for player_id, position, rating in team.players
    ]


def _match_game_rows(games: list[MatchGame]) -> list[dict[str, Any]]:
    return [
        {
            "match_id": game.match_id,
            "game_number": game.game_number,
            "team_one_score": game.team_one_score,
            "team_two_score": game.team_two_score,
            "winning_team_number": game.winning_team_number,
            "target_score": game.target_score,
            "win_by": game.win_by,
            "expected_team_one_score_share": game.expected_team_one_score_share,
            "actual_team_one_score_share": game.actual_team_one_score_share,
            "expected_team_one_score": game.expected_team_one_score,
            "expected_team_two_score": game.expected_team_two_score,
            "score_noise_factor": game.score_noise_factor,
        }
        for game in games
    ]


def _weighted_probabilities(
    value: dict[str, Any],
    name: str,
) -> tuple[tuple[str, Decimal], ...]:
    parsed = tuple((key, _decimal(weight)) for key, weight in value.items())
    if not parsed:
        raise ValueError(f"{name} cannot be empty")
    total = sum(weight for _, weight in parsed)
    if abs(total - Decimal("1")) > Decimal("0.01"):
        raise ValueError(f"{name} must sum to 1.0")
    if any(weight < 0 for _, weight in parsed):
        raise ValueError(f"{name} cannot contain negative weights")
    return parsed


def _positive_decimal(value: Any, name: str) -> Decimal:
    parsed = _decimal(value)
    if parsed <= 0:
        raise ValueError(f"{name} must be positive")
    return parsed


def _positive_int(value: Any, name: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a positive integer")
    parsed = int(value)
    if parsed <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return parsed


def _nonnegative_int(value: Any, name: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a non-negative integer")
    parsed = int(value)
    if parsed < 0:
        raise ValueError(f"{name} must be a non-negative integer")
    return parsed


def _probability(value: Any, name: str) -> Decimal:
    parsed = _decimal(value)
    if parsed < 0 or parsed > 1:
        raise ValueError(f"{name} must be between 0 and 1")
    return parsed


def _nonnegative_decimal(value: Any, name: str) -> Decimal:
    parsed = _decimal(value)
    if parsed < 0:
        raise ValueError(f"{name} must be non-negative")
    return parsed
