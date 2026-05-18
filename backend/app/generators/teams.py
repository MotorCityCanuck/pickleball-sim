"""Determine doubles teams for a generation run as of a monthly batch."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
import random
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.default_configuration import DEFAULT_CONFIG_PAYLOAD
from app.db.session import session_scope
from app.models import (
    ClubMembership,
    GenerationRun,
    MonthlyBatch,
    Player,
    PlayerRatingHistory,
    Team,
    TeamMembership,
)

from .players import WeightedSampler, _decimal


TEAM_TYPES = {"mens_doubles", "womens_doubles", "mixed_doubles", "open_doubles"}


@dataclass(frozen=True)
class TeamFormationConfig:
    """Team formation settings resolved from a configuration payload."""

    target_team_count: int | None
    player_team_participation_rate: Decimal
    multi_team_player_rate: Decimal
    max_active_teams_per_player: int
    same_club_team_rate: Decimal
    same_region_team_rate: Decimal
    rating_gap_mean: Decimal
    rating_gap_std_dev: Decimal
    rating_gap_max: Decimal
    team_type_weights: tuple[tuple[str, Decimal], ...]
    team_persistence_probability_recreational: Decimal
    team_persistence_probability_competitive: Decimal
    team_chemistry_weight: Decimal
    team_skill_balance_weight: Decimal
    team_club_proximity_weight: Decimal
    team_region_proximity_weight: Decimal
    team_prior_partnership_weight: Decimal
    team_noise_factor: Decimal
    monthly_team_dissolution_rate: Decimal
    allow_multiple_active_teams_per_scope: bool

    @classmethod
    def from_payload(cls, payload: dict[str, Any] | None) -> "TeamFormationConfig":
        source = payload or DEFAULT_CONFIG_PAYLOAD
        team_config = source.get("team_formation", {})

        target_team_count = team_config.get("target_team_count")
        if target_team_count is not None:
            target_team_count = int(target_team_count)
            if target_team_count < 1:
                raise ValueError("team_formation.target_team_count must be positive")

        team_type_weights = _team_type_weights(
            team_config.get(
                "team_type_weights",
                {
                    "mens_doubles": 0.30,
                    "womens_doubles": 0.30,
                    "mixed_doubles": 0.30,
                    "open_doubles": 0.10,
                },
            )
        )
        max_active_teams = int(team_config.get("max_active_teams_per_player", 2))
        if max_active_teams < 1:
            raise ValueError("max_active_teams_per_player must be at least 1")

        rating_gap_mean = _decimal(team_config.get("rating_gap_mean", 175))
        rating_gap_std_dev = _decimal(team_config.get("rating_gap_std_dev", 125))
        rating_gap_max = _decimal(team_config.get("rating_gap_max", 600))
        if rating_gap_mean < 0 or rating_gap_std_dev < 0 or rating_gap_max < 0:
            raise ValueError("rating gap settings cannot be negative")

        return cls(
            target_team_count=target_team_count,
            player_team_participation_rate=_probability(
                team_config.get("player_team_participation_rate", 0.70),
                "player_team_participation_rate",
            ),
            multi_team_player_rate=_probability(
                team_config.get("multi_team_player_rate", 0.08),
                "multi_team_player_rate",
            ),
            max_active_teams_per_player=max_active_teams,
            same_club_team_rate=_probability(
                team_config.get("same_club_team_rate", 0.78),
                "same_club_team_rate",
            ),
            same_region_team_rate=_probability(
                team_config.get("same_region_team_rate", 0.95),
                "same_region_team_rate",
            ),
            rating_gap_mean=rating_gap_mean,
            rating_gap_std_dev=rating_gap_std_dev,
            rating_gap_max=rating_gap_max,
            team_type_weights=team_type_weights,
            team_persistence_probability_recreational=_probability(
                team_config.get("team_persistence_probability_recreational", 0.72),
                "team_persistence_probability_recreational",
            ),
            team_persistence_probability_competitive=_probability(
                team_config.get("team_persistence_probability_competitive", 0.88),
                "team_persistence_probability_competitive",
            ),
            team_chemistry_weight=_probability(
                team_config.get("team_chemistry_weight", 0.35),
                "team_chemistry_weight",
            ),
            team_skill_balance_weight=_probability(
                team_config.get("team_skill_balance_weight", 0.25),
                "team_skill_balance_weight",
            ),
            team_club_proximity_weight=_probability(
                team_config.get("team_club_proximity_weight", 0.25),
                "team_club_proximity_weight",
            ),
            team_region_proximity_weight=_probability(
                team_config.get("team_region_proximity_weight", 0.10),
                "team_region_proximity_weight",
            ),
            team_prior_partnership_weight=_probability(
                team_config.get("team_prior_partnership_weight", 0.20),
                "team_prior_partnership_weight",
            ),
            team_noise_factor=_probability(
                team_config.get("team_noise_factor", 0.15),
                "team_noise_factor",
            ),
            monthly_team_dissolution_rate=_probability(
                team_config.get("monthly_team_dissolution_rate", 0.10),
                "monthly_team_dissolution_rate",
            ),
            allow_multiple_active_teams_per_scope=bool(
                team_config.get("allow_multiple_active_teams_per_scope", False)
            ),
        )


@dataclass(frozen=True)
class TeamGenerationResult:
    """Summary of generated team rows."""

    generation_run_id: int
    batch_id: int
    batch_month: date
    eligible_player_count: int
    target_team_count: int
    rows_loaded: int
    membership_rows_loaded: int
    leftover_player_count: int


@dataclass(frozen=True)
class PlayerCandidate:
    """Player attributes used for team formation."""

    id: int
    gender: str | None
    home_region_id: int | None
    rating_value: Decimal
    club_ids: frozenset[int]


class TeamGenerator:
    """Generate point-in-time doubles teams for a monthly batch."""

    def generate_for_batch(
        self,
        *,
        generation_run_id: int,
        batch_id: int,
        session: Session | None = None,
    ) -> TeamGenerationResult:
        """Create teams and team memberships for one monthly batch."""
        if session is not None:
            return self._generate_for_batch(
                generation_run_id=generation_run_id,
                batch_id=batch_id,
                session=session,
            )

        with session_scope() as active_session:
            return self._generate_for_batch(
                generation_run_id=generation_run_id,
                batch_id=batch_id,
                session=active_session,
            )

    def _generate_for_batch(
        self,
        *,
        generation_run_id: int,
        batch_id: int,
        session: Session,
    ) -> TeamGenerationResult:
        generation_run = session.get(GenerationRun, generation_run_id)
        if generation_run is None:
            raise ValueError(f"Generation run {generation_run_id} does not exist")
        batch = session.get(MonthlyBatch, batch_id)
        if batch is None:
            raise ValueError(f"Monthly batch {batch_id} does not exist")
        if batch.generation_run_id != generation_run_id:
            raise ValueError("Batch does not belong to the generation run")

        existing_teams = session.scalar(
            select(func.count()).select_from(Team).where(
                Team.generation_run_id == generation_run_id,
                Team.formation_date <= batch.batch_month,
                or_(Team.dissolution_date.is_(None), Team.dissolution_date > batch.batch_month),
            )
        )
        if existing_teams:
            raise ValueError(
                f"Generation run {generation_run_id} already has active teams"
            )

        config = TeamFormationConfig.from_payload(generation_run.parameter_snapshot)
        candidates = _eligible_players(session, generation_run_id, batch.batch_month)
        if len(candidates) < 2:
            raise ValueError("At least two eligible players are required")

        target_team_count = _target_team_count(config, len(candidates))
        rng = random.Random(
            int(generation_run.seed_value) * 1_000_003 + int(batch_id) * 10_007 + 29
        )
        team_type_sampler = WeightedSampler(config.team_type_weights)
        active_team_counts: dict[int, int] = {}
        available = {candidate.id: candidate for candidate in candidates}
        teams: list[Team] = []
        membership_pairs: list[tuple[Team, PlayerCandidate, PlayerCandidate]] = []

        attempts = 0
        max_attempts = max(target_team_count * 20, 100)
        while len(teams) < target_team_count and attempts < max_attempts:
            attempts += 1
            team_type = str(team_type_sampler.choose(rng))
            first_player = _choose_first_player(rng, available, team_type)
            if first_player is None:
                continue
            partner = _choose_partner(
                rng,
                first_player=first_player,
                available=available,
                team_type=team_type,
                config=config,
            )
            if partner is None:
                available.pop(first_player.id, None)
                continue

            team = Team(
                team_type=team_type,
                team_status="active",
                formation_date=batch.batch_month,
                chemistry_score=_initial_chemistry(rng, config),
                persistence_probability=config.team_persistence_probability_recreational,
                generation_run_id=generation_run_id,
            )
            teams.append(team)
            membership_pairs.append((team, first_player, partner))
            _mark_player_used(first_player, available, active_team_counts, config)
            _mark_player_used(partner, available, active_team_counts, config)

        session.add_all(teams)
        session.flush()

        team_memberships = [
            membership
            for team, first_player, second_player in membership_pairs
            for membership in (
                TeamMembership(
                    team_id=team.id,
                    player_id=first_player.id,
                    player_position=1,
                    joined_date=batch.batch_month,
                ),
                TeamMembership(
                    team_id=team.id,
                    player_id=second_player.id,
                    player_position=2,
                    joined_date=batch.batch_month,
                ),
            )
        ]
        session.add_all(team_memberships)
        session.flush()

        return TeamGenerationResult(
            generation_run_id=generation_run_id,
            batch_id=batch_id,
            batch_month=batch.batch_month,
            eligible_player_count=len(candidates),
            target_team_count=target_team_count,
            rows_loaded=len(teams),
            membership_rows_loaded=len(team_memberships),
            leftover_player_count=len(available),
        )


def _eligible_players(
    session: Session,
    generation_run_id: int,
    batch_month: date,
) -> list[PlayerCandidate]:
    ratings: dict[int, Decimal] = {}
    for player_id, rating_value in session.execute(
        select(PlayerRatingHistory.player_id, PlayerRatingHistory.rating_value)
        .where(PlayerRatingHistory.rating_date <= batch_month)
        .order_by(PlayerRatingHistory.player_id, PlayerRatingHistory.rating_date.desc())
    ):
        ratings.setdefault(player_id, rating_value)
    if not ratings:
        raise ValueError("No rating snapshots are available for team formation")

    club_ids_by_player: dict[int, set[int]] = {}
    for player_id, club_id in session.execute(
        select(ClubMembership.player_id, ClubMembership.club_id).where(
            ClubMembership.generation_run_id == generation_run_id,
            ClubMembership.start_date <= batch_month,
            or_(ClubMembership.end_date.is_(None), ClubMembership.end_date > batch_month),
        )
    ):
        club_ids_by_player.setdefault(player_id, set()).add(club_id)

    players = session.execute(
        select(Player.id, Player.gender, Player.home_region_id)
        .where(
            Player.generation_run_id == generation_run_id,
            Player.player_status == "ACTIVE",
            Player.id.in_(ratings.keys()),
        )
        .order_by(Player.id)
    )
    return [
        PlayerCandidate(
            id=player_id,
            gender=gender,
            home_region_id=home_region_id,
            rating_value=_decimal(ratings[player_id]),
            club_ids=frozenset(club_ids_by_player.get(player_id, set())),
        )
        for player_id, gender, home_region_id in players
    ]


def _target_team_count(config: TeamFormationConfig, eligible_player_count: int) -> int:
    max_without_reuse = eligible_player_count // 2
    if config.target_team_count is not None:
        return min(config.target_team_count, max_without_reuse)
    participating_players = int(
        (Decimal(eligible_player_count) * config.player_team_participation_rate)
        .to_integral_value(rounding=ROUND_HALF_UP)
    )
    return min(participating_players // 2, max_without_reuse)


def _choose_first_player(
    rng: random.Random,
    available: dict[int, PlayerCandidate],
    team_type: str,
) -> PlayerCandidate | None:
    candidates = [
        candidate
        for candidate in available.values()
        if _player_allowed_for_team_type(candidate, team_type)
    ]
    if not candidates:
        return None
    return candidates[rng.randrange(len(candidates))]


def _choose_partner(
    rng: random.Random,
    *,
    first_player: PlayerCandidate,
    available: dict[int, PlayerCandidate],
    team_type: str,
    config: TeamFormationConfig,
) -> PlayerCandidate | None:
    require_same_club = _random_probability(rng) < config.same_club_team_rate
    require_same_region = _random_probability(rng) < config.same_region_team_rate
    candidates = [
        candidate
        for candidate in available.values()
        if candidate.id != first_player.id
        and _team_type_pair_allowed(first_player, candidate, team_type)
        and (
            not require_same_region
            or first_player.home_region_id is None
            or candidate.home_region_id == first_player.home_region_id
        )
        and (
            not require_same_club
            or not first_player.club_ids
            or bool(first_player.club_ids.intersection(candidate.club_ids))
        )
    ]
    if not candidates and (require_same_club or require_same_region):
        candidates = [
            candidate
            for candidate in available.values()
            if candidate.id != first_player.id
            and _team_type_pair_allowed(first_player, candidate, team_type)
        ]
    if not candidates:
        return None
    preferred_candidates = [
        candidate
        for candidate in candidates
        if abs(first_player.rating_value - candidate.rating_value)
        <= config.rating_gap_max
    ]
    if not preferred_candidates:
        return None
    candidates = preferred_candidates

    weighted_candidates = [
        (candidate, _partner_weight(first_player, candidate, config, rng))
        for candidate in candidates
    ]
    return WeightedSampler(weighted_candidates).choose(rng)


def _partner_weight(
    first_player: PlayerCandidate,
    candidate: PlayerCandidate,
    config: TeamFormationConfig,
    rng: random.Random,
) -> Decimal:
    rating_gap = abs(first_player.rating_value - candidate.rating_value)
    rating_score = max(
        Decimal("0.01"),
        Decimal("1") - min(rating_gap, config.rating_gap_max) / (config.rating_gap_max or 1),
    )
    club_score = (
        Decimal("1")
        if first_player.club_ids and first_player.club_ids.intersection(candidate.club_ids)
        else Decimal("0.25")
    )
    region_score = (
        Decimal("1")
        if first_player.home_region_id == candidate.home_region_id
        else Decimal("0.25")
    )
    noise = Decimal(str(rng.random())) * config.team_noise_factor
    return (
        rating_score * config.team_skill_balance_weight
        + club_score * config.team_club_proximity_weight
        + region_score * config.team_region_proximity_weight
        + Decimal("0.01")
        + noise
    )


def _player_allowed_for_team_type(player: PlayerCandidate, team_type: str) -> bool:
    if team_type == "mens_doubles":
        return player.gender == "M"
    if team_type == "womens_doubles":
        return player.gender == "F"
    return True


def _team_type_pair_allowed(
    first_player: PlayerCandidate,
    second_player: PlayerCandidate,
    team_type: str,
) -> bool:
    if team_type == "mens_doubles":
        return first_player.gender == "M" and second_player.gender == "M"
    if team_type == "womens_doubles":
        return first_player.gender == "F" and second_player.gender == "F"
    if team_type == "mixed_doubles":
        return {first_player.gender, second_player.gender} == {"M", "F"}
    return True


def _mark_player_used(
    player: PlayerCandidate,
    available: dict[int, PlayerCandidate],
    active_team_counts: dict[int, int],
    config: TeamFormationConfig,
) -> None:
    active_team_counts[player.id] = active_team_counts.get(player.id, 0) + 1
    if (
        not config.allow_multiple_active_teams_per_scope
        or active_team_counts[player.id] >= config.max_active_teams_per_player
    ):
        available.pop(player.id, None)


def _initial_chemistry(
    rng: random.Random,
    config: TeamFormationConfig,
) -> Decimal:
    value = Decimal("0.20") + Decimal(str(rng.random())) * config.team_chemistry_weight
    return value.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def _team_type_weights(value: dict[str, Any]) -> tuple[tuple[str, Decimal], ...]:
    weights = tuple((team_type, _decimal(weight)) for team_type, weight in value.items())
    if not weights:
        raise ValueError("team_type_weights cannot be empty")
    unknown = {team_type for team_type, _ in weights} - TEAM_TYPES
    if unknown:
        raise ValueError(f"Unsupported team_type_weights keys: {sorted(unknown)}")
    total = sum(weight for _, weight in weights)
    if abs(total - Decimal("1")) > Decimal("0.01"):
        raise ValueError("team_type_weights must sum to 1.0")
    if any(weight < 0 for _, weight in weights):
        raise ValueError("team_type_weights cannot be negative")
    return weights


def _probability(value: Any, name: str) -> Decimal:
    parsed = _decimal(value)
    if parsed < 0 or parsed > 1:
        raise ValueError(f"{name} must be between 0 and 1")
    return parsed


def _random_probability(rng: random.Random) -> Decimal:
    return Decimal(str(rng.random()))
