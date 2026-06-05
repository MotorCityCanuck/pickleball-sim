"""Eligibility checks for tournament team submissions."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Team, TeamLifecycleEvent


ACTIVE_LIFECYCLE_EVENTS = frozenset({"formed", "reactivated"})
INACTIVE_LIFECYCLE_EVENTS = frozenset({"dormant", "retired"})


@dataclass(frozen=True)
class TeamEligibility:
    """Point-in-time team eligibility result."""

    is_active: bool
    source: str
    reason: str | None = None


def team_active_as_of(
    session: Session,
    team: Team,
    *,
    tournament_date: date,
) -> TeamEligibility:
    """Return active-as-of status, preferring immutable lifecycle events."""
    latest_event = session.execute(
        select(TeamLifecycleEvent)
        .where(
            TeamLifecycleEvent.team_id == team.id,
            TeamLifecycleEvent.event_date <= tournament_date,
        )
        .order_by(
            TeamLifecycleEvent.event_date.desc(),
            TeamLifecycleEvent.id.desc(),
        )
        .limit(1)
    ).scalar_one_or_none()

    if latest_event is not None:
        if latest_event.event_type in ACTIVE_LIFECYCLE_EVENTS:
            return TeamEligibility(is_active=True, source="team_lifecycle_events")
        if latest_event.event_type in INACTIVE_LIFECYCLE_EVENTS:
            return TeamEligibility(
                is_active=False,
                source="team_lifecycle_events",
                reason=f"latest lifecycle event is {latest_event.event_type}",
            )
        return TeamEligibility(
            is_active=False,
            source="team_lifecycle_events",
            reason=f"unknown lifecycle event {latest_event.event_type}",
        )

    if team.formation_date > tournament_date:
        return TeamEligibility(
            is_active=False,
            source="teams",
            reason="team formation date is after tournament date",
        )
    if team.team_status != "active":
        return TeamEligibility(
            is_active=False,
            source="teams",
            reason=f"team status is {team.team_status}",
        )
    if team.dissolution_date is not None and team.dissolution_date <= tournament_date:
        return TeamEligibility(
            is_active=False,
            source="teams",
            reason="team dissolution date is on or before tournament date",
        )
    return TeamEligibility(is_active=True, source="teams")
