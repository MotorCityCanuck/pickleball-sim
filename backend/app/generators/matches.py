"""Generate monthly matches, match teams, players, and games."""
from __future__ import annotations

from calendar import monthrange
from contextlib import nullcontext
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
import logging
import random
from time import perf_counter
from typing import Any, Callable, ContextManager, Mapping

from sqlalchemy import func, insert, inspect, or_, select
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
    ClubMembership,
    Region,
    Team,
    TeamMembership,
)

from .games import games_per_match, generate_match_games
from .hidden_performance_bias import compute_hidden_team_adjustment_breakdown
from .players import WeightedSampler, _decimal


logger = logging.getLogger("uvicorn.error")


@dataclass(frozen=True)
class AgeAdvantageBiasConfig:
    """Hidden effective-rating settings for age-based performance effects."""

    enabled: bool
    max_rating_points: Decimal
    points_per_year_gap: Decimal
    close_match_multiplier: Decimal
    close_match_competitiveness_threshold: Decimal


@dataclass(frozen=True)
class FatigueBiasConfig:
    """Hidden effective-rating settings for recent workload effects."""

    enabled: bool
    window_days: int
    points_per_recent_game: Decimal
    max_rating_penalty: Decimal
    recovery_days_threshold: int


@dataclass(frozen=True)
class RegionalStrengthBiasConfig:
    """Hidden effective-rating settings for regional strength effects."""

    enabled: bool
    max_rating_points: Decimal
    strength_map: dict[str, Decimal]


@dataclass(frozen=True)
class PartnershipAffinityBiasConfig:
    """Hidden effective-rating settings for doubles partnership effects."""

    enabled: bool
    same_club_bonus: Decimal
    matches_together_threshold_1: int
    matches_together_bonus_1: Decimal
    matches_together_threshold_2: int
    matches_together_bonus_2: Decimal
    recent_matches_bonus: Decimal
    new_team_penalty: Decimal
    max_rating_points: Decimal


@dataclass(frozen=True)
class ExperienceBiasConfig:
    """Hidden effective-rating settings for prior match experience effects."""

    enabled: bool
    max_rating_points: Decimal
    log_multiplier: Decimal
    close_match_multiplier: Decimal
    close_match_competitiveness_threshold: Decimal


@dataclass(frozen=True)
class HiddenPerformanceBiasConfig:
    """Hidden effective-rating settings resolved from a configuration payload."""

    enabled: bool
    debug_enabled: bool
    total_max_rating_points: Decimal
    age_advantage: AgeAdvantageBiasConfig
    fatigue: FatigueBiasConfig
    regional_strength: RegionalStrengthBiasConfig
    partnership_affinity: PartnershipAffinityBiasConfig
    experience: ExperienceBiasConfig

    @classmethod
    def from_payload(
        cls,
        payload: Mapping[str, Any] | None,
    ) -> "HiddenPerformanceBiasConfig":
        defaults = DEFAULT_CONFIG_PAYLOAD["hidden_performance_bias"]
        section = _mapping_or_default(
            payload,
            defaults,
            "hidden_performance_bias",
        )

        return cls(
            enabled=_bool_setting(
                section,
                defaults,
                "enabled",
                "hidden_performance_bias.enabled",
            ),
            debug_enabled=_bool_setting(
                section,
                defaults,
                "debug_enabled",
                "hidden_performance_bias.debug_enabled",
            ),
            total_max_rating_points=_nonnegative_decimal(
                section.get(
                    "total_max_rating_points",
                    defaults["total_max_rating_points"],
                ),
                "hidden_performance_bias.total_max_rating_points",
            ),
            age_advantage=_age_advantage_config(section, defaults),
            fatigue=_fatigue_config(section, defaults),
            regional_strength=_regional_strength_config(section, defaults),
            partnership_affinity=_partnership_affinity_config(section, defaults),
            experience=_experience_config(section, defaults),
        )


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
    hidden_performance_bias: HiddenPerformanceBiasConfig

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
            hidden_performance_bias=HiddenPerformanceBiasConfig.from_payload(
                source.get("hidden_performance_bias")
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
    avg_age: Decimal | None
    player_ids: tuple[int, ...]
    club_ids: frozenset[int]
    primary_club_ids: frozenset[int]
    formation_date: date
    team_total_prior_matches: int
    recent_game_count: int
    recent_pair_counts: dict[tuple[int, int], int]
    region_name: str | None


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
        self._emit_progress(
            progress_listener,
            progress_current=0,
            progress_total=1,
            progress_unit="step",
            message=f"Loading active teams for batch {batch.batch_month}.",
            details={
                "phase": "load_active_teams",
                "batch_month": str(batch.batch_month),
            },
        )
        with _measure_runtime(
            runtime_recorder,
            "load_active_teams",
            metadata={"batch_month": batch.batch_month},
        ) as metric:
            teams = _active_teams(
                session,
                batch.generation_run_id,
                batch.batch_month,
                config=config,
                runtime_recorder=runtime_recorder,
                progress_callback=lambda message, details: self._emit_progress(
                    progress_listener,
                    progress_current=0,
                    progress_total=1,
                    progress_unit="step",
                    message=message,
                    details={
                        "phase": "load_active_teams",
                        "batch_month": str(batch.batch_month),
                        **details,
                    },
                ),
            )
            metric["output_count"] = len(teams)
            metric["metadata"]["active_team_count"] = len(teams)
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
        remaining_team_matches = {
            team_id: target
            for team_id, target in team_target_matches.items()
            if target > 0
        }
        under_target_ids = list(remaining_team_matches)
        under_target_set = set(under_target_ids)
        under_target_indexes = {
            team_id: index for index, team_id in enumerate(under_target_ids)
        }
        team_pool = MatchTeamPool(teams)
        matches: list[Match] = []
        pairings: list[tuple[Match, TeamCandidate, TeamCandidate, Decimal]] = []
        attempts = 0
        max_attempts = max(target_match_count * 40, 200)
        heartbeat_chunk_size = max(min(target_match_count // 20, 5_000), 500)
        planning_detail_seconds = {
            "planning_under_target_maintenance": 0.0,
            "planning_first_team_selection": 0.0,
            "planning_opponent_selection": 0.0,
            "planning_match_object_construction": 0.0,
        }
        planning_detail_counts = {
            "planning_under_target_maintenance": 0,
            "planning_first_team_selection": 0,
            "planning_opponent_selection": 0,
            "planning_match_object_construction": 0,
        }
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
                detail_start = perf_counter()
                under_target_count = len(under_target_ids)
                planning_detail_seconds["planning_under_target_maintenance"] += (
                    perf_counter() - detail_start
                )
                planning_detail_counts["planning_under_target_maintenance"] += 1
                if under_target_count < 2:
                    break
                match_date = date_sampler.choose(rng)
                match_type = str(match_type_sampler.choose(rng))
                detail_start = perf_counter()
                first_team = team_pool.choose_team(
                    rng,
                    source_ids=under_target_ids,
                    team_day_counts=team_day_counts,
                    match_date=match_date,
                    config=config,
                )
                planning_detail_seconds["planning_first_team_selection"] += (
                    perf_counter() - detail_start
                )
                planning_detail_counts["planning_first_team_selection"] += 1
                if first_team is None:
                    continue
                detail_start = perf_counter()
                second_team = team_pool.choose_opponent(
                    rng,
                    allowed_team_ids=under_target_set,
                    first_team=first_team,
                    match_date=match_date,
                    match_type=match_type,
                    recent_pair_dates=recent_pair_dates,
                    team_day_counts=team_day_counts,
                    config=config,
                )
                planning_detail_seconds["planning_opponent_selection"] += (
                    perf_counter() - detail_start
                )
                planning_detail_counts["planning_opponent_selection"] += 1
                if second_team is None:
                    continue

                detail_start = perf_counter()
                expected_win_probability = _hidden_adjusted_win_probability(
                    first_team,
                    second_team,
                    match_date=match_date,
                    config=config,
                    rng=rng,
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
                planning_detail_seconds["planning_match_object_construction"] += (
                    perf_counter() - detail_start
                )
                planning_detail_counts["planning_match_object_construction"] += 1
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
                detail_start = perf_counter()
                _consume_remaining_team_match(
                    first_team.id,
                    remaining_team_matches=remaining_team_matches,
                    under_target_ids=under_target_ids,
                    under_target_set=under_target_set,
                    under_target_indexes=under_target_indexes,
                )
                _consume_remaining_team_match(
                    second_team.id,
                    remaining_team_matches=remaining_team_matches,
                    under_target_ids=under_target_ids,
                    under_target_set=under_target_set,
                    under_target_indexes=under_target_indexes,
                )
                planning_detail_seconds["planning_under_target_maintenance"] += (
                    perf_counter() - detail_start
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
        for subphase_name, elapsed_seconds in planning_detail_seconds.items():
            _record_completed_runtime(
                runtime_recorder,
                subphase_name,
                elapsed_ms=int(elapsed_seconds * 1000),
                input_count=planning_detail_counts[subphase_name],
                output_count=len(matches),
                attempt_count=attempts,
                metadata={
                    "parent_subphase": "planning",
                    "target_match_count": target_match_count,
                    "active_team_count": len(teams),
                },
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
        scoring_detail_seconds = {
            "scoring_generate_games": 0.0,
            "scoring_build_match_teams": 0.0,
            "scoring_build_game_rows": 0.0,
        }
        scoring_detail_counts = {
            "scoring_generate_games": 0,
            "scoring_build_match_teams": 0,
            "scoring_build_game_rows": 0,
        }
        with _measure_runtime(
            runtime_recorder,
            "scoring",
            input_count=len(pairings),
        ) as metric:
            for index, (match, first_team, second_team, expected_prob) in enumerate(
                pairings,
                start=1,
            ):
                detail_start = perf_counter()
                generated_games = generate_match_games(
                    rng,
                    match=match,
                    expected_team_one_win_probability=expected_prob,
                    match_type=match.match_type,
                    config=config,
                )
                scoring_detail_seconds["scoring_generate_games"] += (
                    perf_counter() - detail_start
                )
                scoring_detail_counts["scoring_generate_games"] += 1
                detail_start = perf_counter()
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
                scoring_detail_seconds["scoring_build_match_teams"] += (
                    perf_counter() - detail_start
                )
                scoring_detail_counts["scoring_build_match_teams"] += 2
                detail_start = perf_counter()
                game_rows.extend(_match_game_rows(generated_games.games))
                match.total_points_played = sum(
                    game.team_one_score + game.team_two_score
                    for game in generated_games.games
                )
                scoring_detail_seconds["scoring_build_game_rows"] += (
                    perf_counter() - detail_start
                )
                scoring_detail_counts["scoring_build_game_rows"] += len(
                    generated_games.games
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
        for subphase_name, elapsed_seconds in scoring_detail_seconds.items():
            _record_completed_runtime(
                runtime_recorder,
                subphase_name,
                elapsed_ms=int(elapsed_seconds * 1000),
                input_count=scoring_detail_counts[subphase_name],
                output_count=len(game_rows),
                attempt_count=len(pairings),
                metadata={
                    "parent_subphase": "scoring",
                    "target_match_count": target_match_count,
                    "match_count": len(pairings),
                    "game_count": len(game_rows),
                    "match_team_count": len(match_teams),
                },
            )

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
            persist_detail_seconds = {
                "persist_match_team_players": 0.0,
                "persist_match_games": 0.0,
            }
            if match_team_player_rows:
                detail_start = perf_counter()
                session.execute(insert(MatchTeamPlayer), match_team_player_rows)
                persist_detail_seconds["persist_match_team_players"] += (
                    perf_counter() - detail_start
                )
            if game_rows:
                detail_start = perf_counter()
                session.execute(insert(MatchGame), game_rows)
                persist_detail_seconds["persist_match_games"] += (
                    perf_counter() - detail_start
                )
            session.flush()
            metric["output_count"] = len(match_team_player_rows) + len(game_rows)
        _record_completed_runtime(
            runtime_recorder,
            "persist_match_team_players",
            elapsed_ms=int(persist_detail_seconds["persist_match_team_players"] * 1000),
            input_count=len(match_team_player_rows),
            output_count=len(match_team_player_rows),
            metadata={
                "parent_subphase": "persist_match_related_rows",
                "match_team_player_count": len(match_team_player_rows),
            },
        )
        _record_completed_runtime(
            runtime_recorder,
            "persist_match_games",
            elapsed_ms=int(persist_detail_seconds["persist_match_games"] * 1000),
            input_count=len(game_rows),
            output_count=len(game_rows),
            metadata={
                "parent_subphase": "persist_match_related_rows",
                "game_count": len(game_rows),
            },
        )

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


def _record_completed_runtime(
    runtime_recorder: Any | None,
    subphase_name: str,
    *,
    elapsed_ms: int,
    input_count: int | None = None,
    output_count: int | None = None,
    attempt_count: int | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    if runtime_recorder is None:
        return
    runtime_recorder.record_completed(
        subphase_name,
        elapsed_ms=elapsed_ms,
        input_count=input_count,
        output_count=output_count,
        attempt_count=attempt_count,
        metadata=metadata,
    )


def _consume_remaining_team_match(
    team_id: int,
    *,
    remaining_team_matches: dict[int, int],
    under_target_ids: list[int],
    under_target_set: set[int],
    under_target_indexes: dict[int, int],
) -> None:
    remaining = remaining_team_matches.get(team_id, 0) - 1
    if remaining > 0:
        remaining_team_matches[team_id] = remaining
        return

    remaining_team_matches.pop(team_id, None)
    if team_id not in under_target_set:
        return

    under_target_set.remove(team_id)
    remove_index = under_target_indexes.pop(team_id)
    last_team_id = under_target_ids.pop()
    if remove_index == len(under_target_ids):
        return

    under_target_ids[remove_index] = last_team_id
    under_target_indexes[last_team_id] = remove_index


def _generation_payload(session: Session, batch: MonthlyBatch) -> dict[str, Any] | None:
    from app.models import GenerationRun

    generation_run = session.get(GenerationRun, batch.generation_run_id)
    return generation_run.parameter_snapshot if generation_run is not None else None


def _active_teams(
    session: Session,
    generation_run_id: int,
    batch_month: date,
    config: MatchGenerationConfig | None = None,
    runtime_recorder: Any | None = None,
    progress_callback: Callable[[str, dict[str, Any]], None] | None = None,
) -> list[TeamCandidate]:
    team_rows: dict[int, dict[str, Any]] = {}
    if progress_callback is not None:
        progress_callback(
            f"Loading active team rosters for batch {batch_month}.",
            {"subphase": "load_active_team_rosters"},
        )
    with _measure_runtime(
        runtime_recorder,
        "load_active_team_rosters",
        metadata={
            "parent_subphase": "load_active_teams",
            "batch_month": batch_month,
        },
    ) as metric:
        roster_rows = session.execute(
            select(
                Team.id,
                Team.team_type,
                Team.formation_date,
                TeamMembership.player_id,
                TeamMembership.player_position,
                Player.home_region_id,
                Player.birth_date,
            )
            .join(TeamMembership, TeamMembership.team_id == Team.id)
            .join(Player, Player.id == TeamMembership.player_id)
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
                Player.player_status == "ACTIVE",
            )
            .order_by(Team.id, TeamMembership.player_position)
        ).all()
        metric["output_count"] = len(roster_rows)

    for (
        team_id,
        team_type,
        formation_date,
        player_id,
        player_position,
        home_region_id,
        birth_date,
    ) in roster_rows:
        row = team_rows.setdefault(
            team_id,
            {
                "team_type": team_type,
                "region_id": home_region_id,
                "formation_date": formation_date,
                "birth_dates": [],
                "players": [],
            },
        )
        row["birth_dates"].append(birth_date)
        row["players"].append((player_id, player_position))

    if progress_callback is not None:
        progress_callback(
            f"Loading latest ratings for active team players in batch {batch_month}.",
            {"subphase": "load_latest_team_player_ratings"},
        )
    with _measure_runtime(
        runtime_recorder,
        "load_latest_team_player_ratings",
        metadata={
            "parent_subphase": "load_active_teams",
            "batch_month": batch_month,
        },
    ) as metric:
        latest_ratings_by_player = _latest_active_team_player_ratings(
            session,
            generation_run_id=generation_run_id,
            batch_month=batch_month,
        )
        metric["output_count"] = len(latest_ratings_by_player)

    player_ids_by_team: dict[int, tuple[int, ...]] = {}
    for team_id, row in team_rows.items():
        player_ids_by_team[team_id] = tuple(
            sorted(player_id for player_id, _ in row["players"])
        )

    fatigue_window_days = (
        config.hidden_performance_bias.fatigue.window_days
        if config is not None
        else int(
            DEFAULT_CONFIG_PAYLOAD["hidden_performance_bias"]["fatigue"][
                "window_days"
            ]
        )
    )
    recent_pair_window_days = (
        config.rematch_penalty_window_days
        if config is not None
        else int(DEFAULT_CONFIG_PAYLOAD["matchmaking"]["rematch_penalty_window_days"])
    )
    all_player_ids = {
        player_id for player_ids in player_ids_by_team.values() for player_id in player_ids
    }
    if progress_callback is not None:
        progress_callback(
            f"Loading club memberships for active teams in batch {batch_month}.",
            {"subphase": "load_active_team_club_memberships"},
        )
    with _measure_runtime(
        runtime_recorder,
        "load_active_team_club_memberships",
        metadata={
            "parent_subphase": "load_active_teams",
            "batch_month": batch_month,
        },
    ) as metric:
        club_ids_by_player, primary_club_ids_by_player = _club_membership_maps(
            session,
            player_ids=all_player_ids,
            batch_month=batch_month,
        )
        metric["output_count"] = len(club_ids_by_player)

    region_ids = {
        row["region_id"]
        for row in team_rows.values()
        if row["region_id"] is not None
    }
    if progress_callback is not None:
        progress_callback(
            f"Loading region names for active teams in batch {batch_month}.",
            {"subphase": "load_active_team_regions"},
        )
    with _measure_runtime(
        runtime_recorder,
        "load_active_team_regions",
        metadata={
            "parent_subphase": "load_active_teams",
            "batch_month": batch_month,
        },
    ) as metric:
        region_names = _region_name_map(
            session,
            region_ids=region_ids,
        )
        metric["output_count"] = len(region_names)

    if progress_callback is not None:
        progress_callback(
            f"Loading historical team activity for batch {batch_month}.",
            {"subphase": "load_active_team_history"},
        )
    with _measure_runtime(
        runtime_recorder,
        "load_active_team_history",
        metadata={
            "parent_subphase": "load_active_teams",
            "batch_month": batch_month,
        },
    ) as metric:
        prior_match_counts, recent_match_counts, recent_game_counts = (
            _historical_team_activity_maps(
                session,
                generation_run_id=generation_run_id,
                batch_month=batch_month,
                player_ids_by_team=player_ids_by_team,
                fatigue_window_days=fatigue_window_days,
                recent_pair_window_days=recent_pair_window_days,
            )
        )
        metric["output_count"] = len(prior_match_counts)

    candidates: list[TeamCandidate] = []
    if progress_callback is not None:
        progress_callback(
            f"Building active team candidates for batch {batch_month}.",
            {"subphase": "build_active_team_candidates"},
        )
    with _measure_runtime(
        runtime_recorder,
        "build_active_team_candidates",
        metadata={
            "parent_subphase": "load_active_teams",
            "batch_month": batch_month,
        },
    ) as metric:
        for team_id, row in team_rows.items():
            if len(row["players"]) != 2:
                continue
            player_ids = player_ids_by_team[team_id]
            player_ratings = []
            missing_rating = False
            for player_id, player_position in row["players"]:
                rating_value = latest_ratings_by_player.get(player_id)
                if rating_value is None:
                    missing_rating = True
                    break
                player_ratings.append((player_id, player_position, rating_value))
            if missing_rating:
                continue
            players = tuple(sorted(player_ratings, key=lambda player: player[1]))
            average_rating = (players[0][2] + players[1][2]) / Decimal("2")
            club_ids = frozenset(
                club_id
                for player_id in player_ids
                for club_id in club_ids_by_player.get(player_id, frozenset())
            )
            primary_club_ids = frozenset(
                club_id
                for player_id in player_ids
                for club_id in primary_club_ids_by_player.get(player_id, frozenset())
            )
            candidates.append(
                TeamCandidate(
                    id=team_id,
                    team_type=row["team_type"],
                    region_id=row["region_id"],
                    average_rating=average_rating,
                    players=players,
                    avg_age=_average_age(row["birth_dates"], as_of=batch_month),
                    player_ids=player_ids,
                    club_ids=club_ids,
                    primary_club_ids=primary_club_ids,
                    formation_date=row["formation_date"],
                    team_total_prior_matches=prior_match_counts.get(team_id, 0),
                    recent_game_count=recent_game_counts.get(team_id, 0),
                    recent_pair_counts={
                        player_ids: recent_match_counts.get(team_id, 0),
                    },
                    region_name=region_names.get(row["region_id"]),
                )
            )
        metric["output_count"] = len(candidates)
    return candidates


def _latest_active_team_player_ratings(
    session: Session,
    *,
    generation_run_id: int,
    batch_month: date,
) -> dict[int, Decimal]:
    active_player_ids = (
        select(TeamMembership.player_id.label("player_id"))
        .join(Team, Team.id == TeamMembership.team_id)
        .join(Player, Player.id == TeamMembership.player_id)
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
            Player.player_status == "ACTIVE",
        )
        .distinct()
        .subquery()
    )

    latest_ratings_by_player: dict[int, Decimal] = {}
    for player_id, rating_value in session.execute(
        select(
            PlayerRatingHistory.player_id,
            PlayerRatingHistory.rating_value,
        )
        .join(
            active_player_ids,
            active_player_ids.c.player_id == PlayerRatingHistory.player_id,
        )
        .where(PlayerRatingHistory.rating_date <= batch_month)
        .order_by(
            PlayerRatingHistory.player_id,
            PlayerRatingHistory.rating_date.desc(),
            PlayerRatingHistory.id.desc(),
        )
    ):
        if player_id not in latest_ratings_by_player:
            latest_ratings_by_player[player_id] = _decimal(rating_value)
    return latest_ratings_by_player


def _average_age(
    birth_dates: list[date],
    *,
    as_of: date,
) -> Decimal | None:
    if not birth_dates:
        return None
    total_years = Decimal("0")
    for birth_date in birth_dates:
        years = as_of.year - birth_date.year
        if (as_of.month, as_of.day) < (birth_date.month, birth_date.day):
            years -= 1
        total_years += Decimal(years)
    return (total_years / Decimal(len(birth_dates))).quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP,
    )


def _club_membership_maps(
    session: Session,
    *,
    player_ids: set[int],
    batch_month: date,
) -> tuple[dict[int, frozenset[int]], dict[int, frozenset[int]]]:
    if not player_ids or not _table_exists(session, "club_memberships"):
        return {}, {}

    club_ids_by_player: dict[int, set[int]] = {}
    primary_club_ids_by_player: dict[int, set[int]] = {}
    for player_id, club_id, is_primary in session.execute(
        select(
            ClubMembership.player_id,
            ClubMembership.club_id,
            ClubMembership.is_primary,
        )
        .where(
            ClubMembership.player_id.in_(player_ids),
            ClubMembership.start_date <= batch_month,
            or_(
                ClubMembership.end_date.is_(None),
                ClubMembership.end_date > batch_month,
            ),
        )
    ):
        club_ids_by_player.setdefault(player_id, set()).add(club_id)
        if is_primary:
            primary_club_ids_by_player.setdefault(player_id, set()).add(club_id)

    return (
        {
            player_id: frozenset(club_ids)
            for player_id, club_ids in club_ids_by_player.items()
        },
        {
            player_id: frozenset(club_ids)
            for player_id, club_ids in primary_club_ids_by_player.items()
        },
    )


def _region_name_map(
    session: Session,
    *,
    region_ids: set[int],
) -> dict[int, str]:
    if not region_ids or not _table_exists(session, "regions"):
        return {}

    return {
        region_id: region_name
        for region_id, region_name in session.execute(
            select(Region.id, Region.region_name).where(Region.id.in_(region_ids))
        )
    }


def _historical_team_activity_maps(
    session: Session,
    *,
    generation_run_id: int,
    batch_month: date,
    player_ids_by_team: dict[int, tuple[int, ...]],
    fatigue_window_days: int,
    recent_pair_window_days: int,
) -> tuple[dict[int, int], dict[int, int], dict[int, int]]:
    if not player_ids_by_team:
        return {}, {}, {}

    if not all(
        _table_exists(session, table_name)
        for table_name in (
            "monthly_batches",
            "matches",
            "match_teams",
            "match_team_players",
        )
    ):
        return {}, {}, {}

    team_id_by_player_ids = {
        player_ids: team_id for team_id, player_ids in player_ids_by_team.items()
    }
    active_player_ids = {
        player_id
        for player_ids in player_ids_by_team.values()
        for player_id in player_ids
    }
    game_counts_by_match = _game_counts_by_match(session)
    recent_pair_cutoff = batch_month - timedelta(days=recent_pair_window_days)
    fatigue_cutoff = batch_month - timedelta(days=fatigue_window_days)
    match_team_rows: dict[int, dict[str, Any]] = {}

    for match_team_id, match_id, match_date, player_id in session.execute(
        select(
            MatchTeam.id,
            Match.id,
            Match.match_date,
            MatchTeamPlayer.player_id,
        )
        .join(Match, Match.id == MatchTeam.match_id)
        .join(MonthlyBatch, MonthlyBatch.id == Match.batch_id)
        .join(MatchTeamPlayer, MatchTeamPlayer.match_team_id == MatchTeam.id)
        .where(
            MonthlyBatch.generation_run_id == generation_run_id,
            Match.match_date < batch_month,
            MatchTeamPlayer.player_id.in_(active_player_ids),
        )
    ):
        row = match_team_rows.setdefault(
            match_team_id,
            {
                "match_id": match_id,
                "match_date": match_date,
                "player_ids": [],
            },
        )
        row["player_ids"].append(player_id)

    prior_match_counts: dict[int, int] = {}
    recent_match_counts: dict[int, int] = {}
    recent_game_counts: dict[int, int] = {}
    for row in match_team_rows.values():
        player_ids = tuple(sorted(row["player_ids"]))
        team_id = team_id_by_player_ids.get(player_ids)
        if team_id is None:
            continue

        match_date = row["match_date"]
        prior_match_counts[team_id] = prior_match_counts.get(team_id, 0) + 1
        if match_date >= recent_pair_cutoff:
            recent_match_counts[team_id] = recent_match_counts.get(team_id, 0) + 1
        if match_date >= fatigue_cutoff:
            recent_game_counts[team_id] = recent_game_counts.get(
                team_id,
                0,
            ) + game_counts_by_match.get(row["match_id"], 0)

    return prior_match_counts, recent_match_counts, recent_game_counts


def _game_counts_by_match(session: Session) -> dict[int, int]:
    if not _table_exists(session, "match_games"):
        return {}

    return {
        match_id: game_count
        for match_id, game_count in session.execute(
            select(MatchGame.match_id, func.count(MatchGame.id)).group_by(
                MatchGame.match_id
            )
        )
    }


def _table_exists(session: Session, table_name: str) -> bool:
    bind = session.get_bind()
    return bind is not None and inspect(bind).has_table(table_name)


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


def _hidden_adjusted_win_probability(
    first_team: TeamCandidate,
    second_team: TeamCandidate,
    *,
    match_date: date,
    config: MatchGenerationConfig,
    rng: random.Random,
) -> Decimal:
    visible_probability = _expected_win_probability(
        first_team.average_rating,
        second_team.average_rating,
    )
    if not config.hidden_performance_bias.enabled:
        return visible_probability

    visible_competitiveness = _competitiveness(visible_probability)
    match_context = {
        "match_date": match_date,
        "visible_team_one_rating": first_team.average_rating,
        "visible_team_two_rating": second_team.average_rating,
        "visible_probability": visible_probability,
        "expected_competitiveness": visible_competitiveness,
    }
    first_breakdown = compute_hidden_team_adjustment_breakdown(
        first_team,
        second_team,
        match_context,
        config.hidden_performance_bias,
        rng,
    )
    second_breakdown = compute_hidden_team_adjustment_breakdown(
        second_team,
        first_team,
        match_context,
        config.hidden_performance_bias,
        rng,
    )
    team_one_effective_rating = first_team.average_rating + first_breakdown.total
    team_two_effective_rating = second_team.average_rating + second_breakdown.total
    adjusted_probability = _expected_win_probability(
        team_one_effective_rating,
        team_two_effective_rating,
    )
    if config.hidden_performance_bias.debug_enabled:
        _log_hidden_performance_bias_debug(
            first_team=first_team,
            second_team=second_team,
            match_date=match_date,
            visible_probability=visible_probability,
            final_probability=adjusted_probability,
            team_one_effective_rating=team_one_effective_rating,
            team_two_effective_rating=team_two_effective_rating,
            team_one_breakdown=first_breakdown,
            team_two_breakdown=second_breakdown,
        )
    return adjusted_probability


def _log_hidden_performance_bias_debug(
    *,
    first_team: TeamCandidate,
    second_team: TeamCandidate,
    match_date: date,
    visible_probability: Decimal,
    final_probability: Decimal,
    team_one_effective_rating: Decimal,
    team_two_effective_rating: Decimal,
    team_one_breakdown: Any,
    team_two_breakdown: Any,
) -> None:
    payload = {
        "match_date": match_date.isoformat(),
        "team_one_id": first_team.id,
        "team_two_id": second_team.id,
        "visible_team_ratings": {
            "team_one": _debug_decimal(first_team.average_rating),
            "team_two": _debug_decimal(second_team.average_rating),
        },
        "factor_adjustments": {
            "team_one": _debug_decimal_map(team_one_breakdown.factor_adjustments),
            "team_two": _debug_decimal_map(team_two_breakdown.factor_adjustments),
        },
        "total_adjustments": {
            "team_one_before_cap": _debug_decimal(team_one_breakdown.total_before_cap),
            "team_two_before_cap": _debug_decimal(team_two_breakdown.total_before_cap),
            "team_one": _debug_decimal(team_one_breakdown.total),
            "team_two": _debug_decimal(team_two_breakdown.total),
        },
        "effective_team_ratings": {
            "team_one": _debug_decimal(team_one_effective_rating),
            "team_two": _debug_decimal(team_two_effective_rating),
        },
        "visible_probability": _debug_decimal(visible_probability),
        "final_probability": _debug_decimal(final_probability),
    }
    logger.info(
        "Hidden performance bias adjustment computed %s",
        payload,
        extra={"hidden_performance_bias_debug": payload},
    )


def _debug_decimal_map(values: Mapping[str, Decimal]) -> dict[str, str]:
    return {key: _debug_decimal(value) for key, value in values.items()}


def _debug_decimal(value: Decimal) -> str:
    return format(value, "f")


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


def _age_advantage_config(
    parent: Mapping[str, Any],
    defaults: Mapping[str, Any],
) -> AgeAdvantageBiasConfig:
    factor_defaults = defaults["age_advantage"]
    section = _mapping_or_default(
        parent.get("age_advantage"),
        factor_defaults,
        "hidden_performance_bias.age_advantage",
    )
    return AgeAdvantageBiasConfig(
        enabled=_bool_setting(
            section,
            factor_defaults,
            "enabled",
            "hidden_performance_bias.age_advantage.enabled",
        ),
        max_rating_points=_nonnegative_decimal(
            section.get("max_rating_points", factor_defaults["max_rating_points"]),
            "hidden_performance_bias.age_advantage.max_rating_points",
        ),
        points_per_year_gap=_nonnegative_decimal(
            section.get("points_per_year_gap", factor_defaults["points_per_year_gap"]),
            "hidden_performance_bias.age_advantage.points_per_year_gap",
        ),
        close_match_multiplier=_nonnegative_decimal(
            section.get(
                "close_match_multiplier",
                factor_defaults["close_match_multiplier"],
            ),
            "hidden_performance_bias.age_advantage.close_match_multiplier",
        ),
        close_match_competitiveness_threshold=_probability(
            section.get(
                "close_match_competitiveness_threshold",
                factor_defaults["close_match_competitiveness_threshold"],
            ),
            (
                "hidden_performance_bias.age_advantage."
                "close_match_competitiveness_threshold"
            ),
        ),
    )


def _fatigue_config(
    parent: Mapping[str, Any],
    defaults: Mapping[str, Any],
) -> FatigueBiasConfig:
    factor_defaults = defaults["fatigue"]
    section = _mapping_or_default(
        parent.get("fatigue"),
        factor_defaults,
        "hidden_performance_bias.fatigue",
    )
    return FatigueBiasConfig(
        enabled=_bool_setting(
            section,
            factor_defaults,
            "enabled",
            "hidden_performance_bias.fatigue.enabled",
        ),
        window_days=_nonnegative_int(
            section.get("window_days", factor_defaults["window_days"]),
            "hidden_performance_bias.fatigue.window_days",
        ),
        points_per_recent_game=_nonnegative_decimal(
            section.get(
                "points_per_recent_game",
                factor_defaults["points_per_recent_game"],
            ),
            "hidden_performance_bias.fatigue.points_per_recent_game",
        ),
        max_rating_penalty=_nonnegative_decimal(
            section.get("max_rating_penalty", factor_defaults["max_rating_penalty"]),
            "hidden_performance_bias.fatigue.max_rating_penalty",
        ),
        recovery_days_threshold=_nonnegative_int(
            section.get(
                "recovery_days_threshold",
                factor_defaults["recovery_days_threshold"],
            ),
            "hidden_performance_bias.fatigue.recovery_days_threshold",
        ),
    )


def _regional_strength_config(
    parent: Mapping[str, Any],
    defaults: Mapping[str, Any],
) -> RegionalStrengthBiasConfig:
    factor_defaults = defaults["regional_strength"]
    section = _mapping_or_default(
        parent.get("regional_strength"),
        factor_defaults,
        "hidden_performance_bias.regional_strength",
    )
    return RegionalStrengthBiasConfig(
        enabled=_bool_setting(
            section,
            factor_defaults,
            "enabled",
            "hidden_performance_bias.regional_strength.enabled",
        ),
        max_rating_points=_nonnegative_decimal(
            section.get("max_rating_points", factor_defaults["max_rating_points"]),
            "hidden_performance_bias.regional_strength.max_rating_points",
        ),
        strength_map=_regional_strength_map(
            section.get("map", factor_defaults["map"]),
            "hidden_performance_bias.regional_strength.map",
        ),
    )


def _partnership_affinity_config(
    parent: Mapping[str, Any],
    defaults: Mapping[str, Any],
) -> PartnershipAffinityBiasConfig:
    factor_defaults = defaults["partnership_affinity"]
    section = _mapping_or_default(
        parent.get("partnership_affinity"),
        factor_defaults,
        "hidden_performance_bias.partnership_affinity",
    )
    threshold_1 = _nonnegative_int(
        section.get(
            "matches_together_threshold_1",
            factor_defaults["matches_together_threshold_1"],
        ),
        "hidden_performance_bias.partnership_affinity.matches_together_threshold_1",
    )
    threshold_2 = _nonnegative_int(
        section.get(
            "matches_together_threshold_2",
            factor_defaults["matches_together_threshold_2"],
        ),
        "hidden_performance_bias.partnership_affinity.matches_together_threshold_2",
    )
    if threshold_2 < threshold_1:
        raise ValueError(
            "hidden_performance_bias.partnership_affinity."
            "matches_together_threshold_2 must be greater than or equal to "
            "matches_together_threshold_1"
        )

    return PartnershipAffinityBiasConfig(
        enabled=_bool_setting(
            section,
            factor_defaults,
            "enabled",
            "hidden_performance_bias.partnership_affinity.enabled",
        ),
        same_club_bonus=_decimal_setting(
            section,
            factor_defaults,
            "same_club_bonus",
            "hidden_performance_bias.partnership_affinity.same_club_bonus",
        ),
        matches_together_threshold_1=threshold_1,
        matches_together_bonus_1=_decimal_setting(
            section,
            factor_defaults,
            "matches_together_bonus_1",
            "hidden_performance_bias.partnership_affinity.matches_together_bonus_1",
        ),
        matches_together_threshold_2=threshold_2,
        matches_together_bonus_2=_decimal_setting(
            section,
            factor_defaults,
            "matches_together_bonus_2",
            "hidden_performance_bias.partnership_affinity.matches_together_bonus_2",
        ),
        recent_matches_bonus=_decimal_setting(
            section,
            factor_defaults,
            "recent_matches_bonus",
            "hidden_performance_bias.partnership_affinity.recent_matches_bonus",
        ),
        new_team_penalty=_decimal_setting(
            section,
            factor_defaults,
            "new_team_penalty",
            "hidden_performance_bias.partnership_affinity.new_team_penalty",
        ),
        max_rating_points=_nonnegative_decimal(
            section.get("max_rating_points", factor_defaults["max_rating_points"]),
            "hidden_performance_bias.partnership_affinity.max_rating_points",
        ),
    )


def _experience_config(
    parent: Mapping[str, Any],
    defaults: Mapping[str, Any],
) -> ExperienceBiasConfig:
    factor_defaults = defaults["experience"]
    section = _mapping_or_default(
        parent.get("experience"),
        factor_defaults,
        "hidden_performance_bias.experience",
    )
    return ExperienceBiasConfig(
        enabled=_bool_setting(
            section,
            factor_defaults,
            "enabled",
            "hidden_performance_bias.experience.enabled",
        ),
        max_rating_points=_nonnegative_decimal(
            section.get("max_rating_points", factor_defaults["max_rating_points"]),
            "hidden_performance_bias.experience.max_rating_points",
        ),
        log_multiplier=_nonnegative_decimal(
            section.get("log_multiplier", factor_defaults["log_multiplier"]),
            "hidden_performance_bias.experience.log_multiplier",
        ),
        close_match_multiplier=_nonnegative_decimal(
            section.get(
                "close_match_multiplier",
                factor_defaults["close_match_multiplier"],
            ),
            "hidden_performance_bias.experience.close_match_multiplier",
        ),
        close_match_competitiveness_threshold=_probability(
            section.get(
                "close_match_competitiveness_threshold",
                factor_defaults["close_match_competitiveness_threshold"],
            ),
            (
                "hidden_performance_bias.experience."
                "close_match_competitiveness_threshold"
            ),
        ),
    )


def _mapping_or_default(
    value: Any,
    default: Mapping[str, Any],
    name: str,
) -> Mapping[str, Any]:
    if value is None:
        return default
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be an object")
    return value


def _bool_setting(
    section: Mapping[str, Any],
    defaults: Mapping[str, Any],
    key: str,
    name: str,
) -> bool:
    value = section.get(key, defaults[key])
    if not isinstance(value, bool):
        raise ValueError(f"{name} must be a boolean")
    return value


def _decimal_setting(
    section: Mapping[str, Any],
    defaults: Mapping[str, Any],
    key: str,
    name: str,
) -> Decimal:
    value = section.get(key, defaults[key])
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a number")
    return _decimal(value)


def _regional_strength_map(value: Any, name: str) -> dict[str, Decimal]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be an object")

    parsed: dict[str, Decimal] = {}
    for region_name, rating_points in value.items():
        if not isinstance(region_name, str):
            raise ValueError(f"{name} must use string region names")
        if isinstance(rating_points, bool):
            raise ValueError(f"{name} must contain only numeric rating-point values")
        try:
            parsed[region_name] = _decimal(rating_points)
        except ArithmeticError as exc:
            raise ValueError(
                f"{name} must contain only numeric rating-point values"
            ) from exc
    return parsed


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
