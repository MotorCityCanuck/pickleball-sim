"""Persistent team identity helpers for unordered player pairs."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Iterable

from sqlalchemy import inspect, select
from sqlalchemy.orm import Session

from app.models import Region, Team, TeamMembership


TEAM_IDENTITY_TYPES = {"competitive", "ad_hoc"}


def player_pair_key(first_player_id: int, second_player_id: int) -> tuple[int, int]:
    """Return the canonical identity key for an unordered two-player team."""
    if int(first_player_id) == int(second_player_id):
        raise ValueError("A team identity pair requires two distinct players")
    return tuple(sorted((int(first_player_id), int(second_player_id))))


@dataclass(frozen=True)
class TeamIdentityRecord:
    """Resolved persistent team identity for one unordered player pair."""

    team_id: int
    player_ids: tuple[int, int]
    team_type: str
    team_identity_type: str


@dataclass(frozen=True)
class TeamIdentityResolution:
    """Result of resolving or creating a team identity."""

    record: TeamIdentityRecord
    team: Team
    created: bool


class TeamIdentityRegistry:
    """Generation-run scoped registry keyed by unordered player pair."""

    def __init__(
        self,
        *,
        session: Session,
        generation_run_id: int,
        records_by_pair: dict[tuple[int, int], TeamIdentityRecord] | None = None,
    ) -> None:
        self.session = session
        self.generation_run_id = int(generation_run_id)
        self._records_by_pair = dict(records_by_pair or {})

    @classmethod
    def load(
        cls,
        session: Session,
        *,
        generation_run_id: int,
    ) -> "TeamIdentityRegistry":
        """Load existing two-player team identities for a generation run."""
        rows = session.execute(
            select(
                Team.id,
                Team.team_type,
                Team.team_identity_type,
                TeamMembership.player_id,
            )
            .join(TeamMembership, TeamMembership.team_id == Team.id)
            .where(Team.generation_run_id == generation_run_id)
            .order_by(Team.id, TeamMembership.player_position, TeamMembership.player_id)
        )

        team_rows: dict[int, dict[str, object]] = {}
        for team_id, team_type, team_identity_type, player_id in rows:
            row = team_rows.setdefault(
                int(team_id),
                {
                    "team_type": str(team_type),
                    "team_identity_type": str(team_identity_type),
                    "player_ids": [],
                },
            )
            player_ids = row["player_ids"]
            assert isinstance(player_ids, list)
            player_ids.append(int(player_id))

        records_by_pair: dict[tuple[int, int], TeamIdentityRecord] = {}
        for team_id, row in team_rows.items():
            player_ids = row["player_ids"]
            if not isinstance(player_ids, list) or len(player_ids) != 2:
                continue
            pair_key = player_pair_key(player_ids[0], player_ids[1])
            existing = records_by_pair.get(pair_key)
            if existing is not None and existing.team_id != team_id:
                raise ValueError(
                    "Duplicate team identity for player pair "
                    f"{pair_key}: teams {existing.team_id} and {team_id}"
                )
            records_by_pair[pair_key] = TeamIdentityRecord(
                team_id=team_id,
                player_ids=pair_key,
                team_type=str(row["team_type"]),
                team_identity_type=str(row["team_identity_type"]),
            )

        return cls(
            session=session,
            generation_run_id=generation_run_id,
            records_by_pair=records_by_pair,
        )

    def get(
        self,
        first_player_id: int,
        second_player_id: int,
    ) -> TeamIdentityRecord | None:
        """Return the existing team identity for a pair, if any."""
        return self._records_by_pair.get(
            player_pair_key(first_player_id, second_player_id)
        )

    def has_pair(self, first_player_id: int, second_player_id: int) -> bool:
        """Return whether a persistent team already exists for a pair."""
        return self.get(first_player_id, second_player_id) is not None

    def get_or_create_team(
        self,
        *,
        players: tuple[tuple[int, int], tuple[int, int]],
        team_type: str,
        team_identity_type: str,
        formation_date: date,
        country_code: str | None = None,
        chemistry_score: Decimal | None = None,
        persistence_probability: Decimal | None = None,
    ) -> TeamIdentityResolution:
        """Resolve an existing team or create one persistent team for the pair."""
        if team_identity_type not in TEAM_IDENTITY_TYPES:
            raise ValueError(f"Unsupported team_identity_type: {team_identity_type}")

        pair_key = player_pair_key(players[0][0], players[1][0])
        existing = self._records_by_pair.get(pair_key)
        if existing is not None:
            team = self.session.get(Team, existing.team_id)
            if team is None:
                raise ValueError(f"Team identity {existing.team_id} no longer exists")
            return TeamIdentityResolution(record=existing, team=team, created=False)

        team = Team(
            team_type=team_type,
            team_identity_type=team_identity_type,
            team_status="active",
            country_code=country_code,
            formation_date=formation_date,
            chemistry_score=chemistry_score,
            persistence_probability=persistence_probability,
            generation_run_id=self.generation_run_id,
        )
        self.session.add(team)
        self.session.flush()

        memberships = [
            TeamMembership(
                team_id=team.id,
                player_id=player_id,
                player_position=position,
                joined_date=formation_date,
            )
            for player_id, position in _ordered_membership_players(players)
        ]
        self.session.add_all(memberships)
        self.session.flush()

        record = TeamIdentityRecord(
            team_id=int(team.id),
            player_ids=pair_key,
            team_type=team_type,
            team_identity_type=team_identity_type,
        )
        self._records_by_pair[pair_key] = record
        return TeamIdentityResolution(record=record, team=team, created=True)


def _ordered_membership_players(
    players: Iterable[tuple[int, int]],
) -> tuple[tuple[int, int], tuple[int, int]]:
    ordered = tuple(sorted(players, key=lambda item: item[1]))
    if len(ordered) != 2:
        raise ValueError("A team identity requires exactly two membership players")
    return (ordered[0], ordered[1])


def country_code_for_region(
    session: Session,
    region_id: int | None,
) -> str | None:
    """Return a region country code for generated ad hoc teams."""
    if region_id is None:
        return None
    if not inspect(session.get_bind()).has_table("regions"):
        return None
    return session.scalar(select(Region.country_code).where(Region.id == region_id))
