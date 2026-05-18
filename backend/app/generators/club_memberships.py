"""Assign generated players to primary and secondary clubs."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import random
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.default_configuration import DEFAULT_CONFIG_PAYLOAD
from app.db.session import session_scope
from app.models import Club, ClubMembership, GenerationRun, Player

from .players import WeightedSampler, _decimal


@dataclass(frozen=True)
class ClubMembershipGenerationConfig:
    """Club assignment settings resolved from a configuration payload."""

    unaffiliated_player_rate: Decimal
    multi_club_membership_rate: Decimal
    min_club_memberships_per_affiliated_player: int
    max_club_memberships_per_player: int
    secondary_membership_same_region_rate: Decimal
    cross_region_assignment_enabled: bool

    @classmethod
    def from_payload(
        cls,
        payload: dict[str, Any] | None,
    ) -> "ClubMembershipGenerationConfig":
        source = payload or DEFAULT_CONFIG_PAYLOAD
        club_config = source.get("club_generation", {})

        unaffiliated_rate = _decimal(club_config.get("unaffiliated_player_rate", 0.12))
        multi_club_rate = _decimal(club_config.get("multi_club_membership_rate", 0.06))
        same_region_rate = _decimal(
            club_config.get("secondary_membership_same_region_rate", 0.85)
        )
        _validate_probability(unaffiliated_rate, "unaffiliated_player_rate")
        _validate_probability(multi_club_rate, "multi_club_membership_rate")
        _validate_probability(
            same_region_rate,
            "secondary_membership_same_region_rate",
        )

        min_memberships = int(
            club_config.get("min_club_memberships_per_affiliated_player", 1)
        )
        max_memberships = int(club_config.get("max_club_memberships_per_player", 3))
        if min_memberships < 1:
            raise ValueError(
                "min_club_memberships_per_affiliated_player must be at least 1"
            )
        if max_memberships < min_memberships:
            raise ValueError(
                "max_club_memberships_per_player must be greater than or equal to "
                "min_club_memberships_per_affiliated_player"
            )

        return cls(
            unaffiliated_player_rate=unaffiliated_rate,
            multi_club_membership_rate=multi_club_rate,
            min_club_memberships_per_affiliated_player=min_memberships,
            max_club_memberships_per_player=max_memberships,
            secondary_membership_same_region_rate=same_region_rate,
            cross_region_assignment_enabled=bool(
                club_config.get("cross_region_assignment_enabled", False)
            ),
        )


@dataclass(frozen=True)
class ClubMembershipGenerationResult:
    """Summary of generated club membership rows."""

    generation_run_id: int
    players_evaluated: int
    affiliated_player_count: int
    unaffiliated_player_count: int
    multi_club_player_count: int
    rows_loaded: int


@dataclass(frozen=True)
class ClubCandidate:
    """Minimal club data needed for assignment."""

    id: int
    region_id: int
    member_capacity: int | None


class ClubIndex:
    """Cached weighted club samplers by region."""

    def __init__(self, session: Session) -> None:
        clubs = [
            ClubCandidate(
                id=club_id,
                region_id=region_id,
                member_capacity=member_capacity,
            )
            for club_id, region_id, member_capacity in session.execute(
                select(Club.id, Club.region_id, Club.member_capacity).order_by(Club.id)
            )
        ]
        self.clubs_by_region: dict[int, list[ClubCandidate]] = {}
        for club in clubs:
            self.clubs_by_region.setdefault(club.region_id, []).append(club)
        self.all_clubs = clubs
        self.region_samplers: dict[int, WeightedSampler[ClubCandidate]] = {}
        self.all_sampler = self._sampler(clubs)

    def choose_primary(self, rng: random.Random, region_id: int) -> ClubCandidate | None:
        return self.choose_in_region(rng, region_id, excluded_ids=set())

    def choose_secondary(
        self,
        rng: random.Random,
        *,
        region_id: int,
        excluded_ids: set[int],
        same_region: bool,
    ) -> ClubCandidate | None:
        if same_region:
            return self.choose_in_region(rng, region_id, excluded_ids=excluded_ids)
        candidates = [club for club in self.all_clubs if club.id not in excluded_ids]
        sampler = self._sampler(candidates)
        if sampler is None:
            return None
        return sampler.choose(rng)

    def choose_in_region(
        self,
        rng: random.Random,
        region_id: int,
        *,
        excluded_ids: set[int],
    ) -> ClubCandidate | None:
        candidates = [
            club
            for club in self.clubs_by_region.get(region_id, [])
            if club.id not in excluded_ids
        ]
        sampler = self._sampler(candidates)
        if sampler is None:
            return None
        return sampler.choose(rng)

    @staticmethod
    def _sampler(
        clubs: list[ClubCandidate],
    ) -> WeightedSampler[ClubCandidate] | None:
        if not clubs:
            return None
        return WeightedSampler(
            [(club, Decimal(club.member_capacity or 1)) for club in clubs]
        )


class ClubMembershipGenerator:
    """Generate primary and secondary club memberships for players."""

    def generate_for_run(
        self,
        *,
        generation_run_id: int,
        session: Session | None = None,
    ) -> ClubMembershipGenerationResult:
        """Generate club memberships for all players in a generation run."""
        if session is not None:
            return self._generate_for_run(
                generation_run_id=generation_run_id,
                session=session,
            )

        with session_scope() as active_session:
            return self._generate_for_run(
                generation_run_id=generation_run_id,
                session=active_session,
            )

    def _generate_for_run(
        self,
        *,
        generation_run_id: int,
        session: Session,
    ) -> ClubMembershipGenerationResult:
        generation_run = session.get(GenerationRun, generation_run_id)
        if generation_run is None:
            raise ValueError(f"Generation run {generation_run_id} does not exist")

        existing_memberships = session.scalar(
            select(func.count()).select_from(ClubMembership).where(
                ClubMembership.generation_run_id == generation_run_id
            )
        )
        if existing_memberships:
            raise ValueError(
                f"Generation run {generation_run_id} already has club memberships"
            )

        players = list(
            session.scalars(
                select(Player)
                .where(Player.generation_run_id == generation_run_id)
                .order_by(Player.id)
            )
        )
        if not players:
            raise ValueError(
                f"Generation run {generation_run_id} has no players to assign"
            )

        club_index = ClubIndex(session)
        if not club_index.all_clubs:
            raise ValueError("No clubs are available for club assignment")

        config = ClubMembershipGenerationConfig.from_payload(
            generation_run.parameter_snapshot
        )
        rng = random.Random(int(generation_run.seed_value) * 1_000_003 + 17)
        memberships: list[ClubMembership] = []
        affiliated_count = 0
        unaffiliated_count = 0
        multi_club_count = 0

        for player in players:
            if _random_probability(rng) < config.unaffiliated_player_rate:
                unaffiliated_count += 1
                continue

            primary_club = club_index.choose_primary(rng, player.home_region_id)
            if primary_club is None:
                unaffiliated_count += 1
                continue

            affiliated_count += 1
            selected_club_ids = {primary_club.id}
            memberships.append(
                _membership_row(
                    player=player,
                    club_id=primary_club.id,
                    generation_run_id=generation_run_id,
                    is_primary=True,
                )
            )

            target_membership_count = _target_membership_count(rng, config)
            if target_membership_count > 1:
                added_secondary = False
                while len(selected_club_ids) < target_membership_count:
                    same_region = (
                        not config.cross_region_assignment_enabled
                        or _random_probability(rng)
                        < config.secondary_membership_same_region_rate
                    )
                    secondary_club = club_index.choose_secondary(
                        rng,
                        region_id=player.home_region_id,
                        excluded_ids=selected_club_ids,
                        same_region=same_region,
                    )
                    if secondary_club is None:
                        break
                    selected_club_ids.add(secondary_club.id)
                    memberships.append(
                        _membership_row(
                            player=player,
                            club_id=secondary_club.id,
                            generation_run_id=generation_run_id,
                            is_primary=False,
                        )
                    )
                    added_secondary = True
                if added_secondary:
                    multi_club_count += 1

        session.add_all(memberships)
        session.flush()

        return ClubMembershipGenerationResult(
            generation_run_id=generation_run_id,
            players_evaluated=len(players),
            affiliated_player_count=affiliated_count,
            unaffiliated_player_count=unaffiliated_count,
            multi_club_player_count=multi_club_count,
            rows_loaded=len(memberships),
        )


def _target_membership_count(
    rng: random.Random,
    config: ClubMembershipGenerationConfig,
) -> int:
    if _random_probability(rng) >= config.multi_club_membership_rate:
        return config.min_club_memberships_per_affiliated_player
    lower_bound = max(2, config.min_club_memberships_per_affiliated_player)
    if config.max_club_memberships_per_player <= lower_bound:
        return lower_bound
    return rng.randint(lower_bound, config.max_club_memberships_per_player)


def _membership_row(
    *,
    player: Player,
    club_id: int,
    generation_run_id: int,
    is_primary: bool,
) -> ClubMembership:
    return ClubMembership(
        player_id=player.id,
        club_id=club_id,
        membership_type="member" if is_primary else "secondary",
        start_date=player.registration_date,
        is_primary=is_primary,
        generation_run_id=generation_run_id,
    )


def _random_probability(rng: random.Random) -> Decimal:
    return Decimal(str(rng.random()))


def _validate_probability(value: Decimal, name: str) -> None:
    if value < 0 or value > 1:
        raise ValueError(f"{name} must be between 0 and 1")
