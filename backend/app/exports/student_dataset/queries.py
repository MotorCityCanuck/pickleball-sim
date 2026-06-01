"""Snapshot-aware source queries for student-facing dataset exports."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from sqlalchemy import Select, and_, case, or_, select
from sqlalchemy.sql.elements import ColumnElement

from app.models import (
    Club,
    ClubMembership,
    Match,
    MatchGame,
    MatchTeam,
    MatchTeamPlayer,
    MonthlyBatch,
    Player,
    PlayerAssessmentHistory,
    PlayerRatingHistory,
    PlayerRegistration,
    Region,
    Team,
    TeamMembership,
)

from .projection import PROJECTION_BY_TABLE, STUDENT_TABLE_ORDER, StudentTableProjection
from .release_windows import StudentDatasetReleaseWindow


class StudentDatasetQueryError(ValueError):
    """Raised when a student dataset source query cannot be built."""


@dataclass(frozen=True)
class StudentDatasetQueryContext:
    """Context required to build snapshot-aware source queries."""

    generation_run_id: int
    release_window: StudentDatasetReleaseWindow

    @property
    def batch_ids(self) -> tuple[int, ...]:
        """Return included monthly batch ids."""

        return self.release_window.batch_ids

    @property
    def snapshot_end_exclusive(self):
        """Return the exclusive upper bound for as-of event dates."""

        return self.release_window.snapshot_end_exclusive


def build_student_dataset_queries(
    context: StudentDatasetQueryContext,
) -> Mapping[str, Select]:
    """Build source queries for every student-facing table."""

    return {
        table_name: build_student_dataset_query(table_name, context)
        for table_name in STUDENT_TABLE_ORDER
    }


def build_student_dataset_query(
    table_name: str,
    context: StudentDatasetQueryContext,
) -> Select:
    """Build the source query for one student-facing table."""

    try:
        builder = _QUERY_BUILDERS[table_name]
    except KeyError as exc:
        raise StudentDatasetQueryError(
            f"No student dataset query builder for table: {table_name}"
        ) from exc
    return builder(context)


def _monthly_batches_query(context: StudentDatasetQueryContext) -> Select:
    projection = PROJECTION_BY_TABLE["monthly_batches"]
    return (
        _select_projection(projection)
        .where(
            MonthlyBatch.generation_run_id == context.generation_run_id,
            MonthlyBatch.id.in_(context.batch_ids),
        )
        .order_by(MonthlyBatch.batch_sequence, MonthlyBatch.id)
    )


def _players_query(context: StudentDatasetQueryContext) -> Select:
    projection = PROJECTION_BY_TABLE["players"]
    return (
        _select_projection(projection)
        .where(_included_player_predicate(context))
        .order_by(Player.id)
    )


def _player_registrations_query(context: StudentDatasetQueryContext) -> Select:
    projection = PROJECTION_BY_TABLE["player_registrations"]
    return (
        _select_projection(projection)
        .where(
            PlayerRegistration.batch_id.in_(context.batch_ids),
            PlayerRegistration.player_id.in_(_included_player_ids(context)),
        )
        .order_by(PlayerRegistration.id)
    )


def _player_rating_history_query(context: StudentDatasetQueryContext) -> Select:
    projection = PROJECTION_BY_TABLE["player_rating_history"]
    return (
        _select_projection(projection)
        .where(
            PlayerRatingHistory.batch_id.in_(context.batch_ids),
            PlayerRatingHistory.player_id.in_(_included_player_ids(context)),
        )
        .order_by(PlayerRatingHistory.id)
    )


def _player_assessment_history_query(context: StudentDatasetQueryContext) -> Select:
    projection = PROJECTION_BY_TABLE["player_assessment_history"]
    return (
        _select_projection(projection)
        .where(
            PlayerAssessmentHistory.batch_id.in_(context.batch_ids),
            PlayerAssessmentHistory.player_id.in_(_included_player_ids(context)),
        )
        .order_by(PlayerAssessmentHistory.id)
    )


def _matches_query(context: StudentDatasetQueryContext) -> Select:
    projection = PROJECTION_BY_TABLE["matches"]
    return (
        _select_projection(projection)
        .where(Match.batch_id.in_(context.batch_ids))
        .order_by(Match.id)
    )


def _match_teams_query(context: StudentDatasetQueryContext) -> Select:
    projection = PROJECTION_BY_TABLE["match_teams"]
    return (
        _select_projection(projection)
        .where(MatchTeam.match_id.in_(_included_match_ids(context)))
        .order_by(MatchTeam.id)
    )


def _match_team_players_query(context: StudentDatasetQueryContext) -> Select:
    projection = PROJECTION_BY_TABLE["match_team_players"]
    return (
        _select_projection(projection)
        .where(
            MatchTeamPlayer.match_team_id.in_(_included_match_team_ids(context)),
            MatchTeamPlayer.player_id.in_(_included_player_ids(context)),
        )
        .order_by(MatchTeamPlayer.id)
    )


def _match_games_query(context: StudentDatasetQueryContext) -> Select:
    projection = PROJECTION_BY_TABLE["match_games"]
    return (
        _select_projection(projection)
        .where(MatchGame.match_id.in_(_included_match_ids(context)))
        .order_by(MatchGame.id)
    )


def _teams_query(context: StudentDatasetQueryContext) -> Select:
    projection = PROJECTION_BY_TABLE["teams"]
    overrides = {
        "team_status": case(
            (
                and_(
                    Team.dissolution_date >= context.snapshot_end_exclusive,
                    Team.team_status.in_(("dormant", "retired")),
                ),
                "active",
            ),
            else_=Team.team_status,
        ).label("team_status"),
        "dissolution_date": case(
            (Team.dissolution_date >= context.snapshot_end_exclusive, None),
            else_=Team.dissolution_date,
        ).label("dissolution_date"),
    }
    return (
        _select_projection(projection, overrides)
        .where(
            Team.generation_run_id == context.generation_run_id,
            Team.formation_date < context.snapshot_end_exclusive,
        )
        .order_by(Team.id)
    )


def _team_memberships_query(context: StudentDatasetQueryContext) -> Select:
    projection = PROJECTION_BY_TABLE["team_memberships"]
    overrides = {
        "left_date": case(
            (TeamMembership.left_date >= context.snapshot_end_exclusive, None),
            else_=TeamMembership.left_date,
        ).label("left_date")
    }
    return (
        _select_projection(projection, overrides)
        .where(
            TeamMembership.team_id.in_(_included_team_ids(context)),
            TeamMembership.player_id.in_(_included_player_ids(context)),
            TeamMembership.joined_date < context.snapshot_end_exclusive,
        )
        .order_by(TeamMembership.id)
    )


def _clubs_query(context: StudentDatasetQueryContext) -> Select:
    projection = PROJECTION_BY_TABLE["clubs"]
    return (
        _select_projection(projection)
        .where(
            or_(
                and_(
                    Club.generation_run_id == context.generation_run_id,
                    or_(
                        Club.founding_date.is_(None),
                        Club.founding_date < context.snapshot_end_exclusive,
                    ),
                ),
                Club.id.in_(_included_club_ids_from_memberships(context)),
            )
        )
        .order_by(Club.id)
    )


def _club_memberships_query(context: StudentDatasetQueryContext) -> Select:
    projection = PROJECTION_BY_TABLE["club_memberships"]
    overrides = {
        "end_date": case(
            (ClubMembership.end_date >= context.snapshot_end_exclusive, None),
            else_=ClubMembership.end_date,
        ).label("end_date")
    }
    return (
        _select_projection(projection, overrides)
        .where(
            ClubMembership.player_id.in_(_included_player_ids(context)),
            ClubMembership.start_date < context.snapshot_end_exclusive,
            or_(
                ClubMembership.generation_run_id == context.generation_run_id,
                ClubMembership.generation_run_id.is_(None),
            ),
        )
        .order_by(ClubMembership.id)
    )


def _regions_query(context: StudentDatasetQueryContext) -> Select:
    projection = PROJECTION_BY_TABLE["regions"]
    return (
        _select_projection(projection)
        .where(
            Region.id.in_(
                _referenced_region_ids(context)
            )
        )
        .order_by(Region.id)
    )


def _select_projection(
    projection: StudentTableProjection,
    overrides: Mapping[str, ColumnElement] | None = None,
) -> Select:
    overrides = overrides or {}
    columns = tuple(
        overrides[column_name]
        if column_name in overrides
        else getattr(projection.model, column_name)
        for column_name in projection.included_columns
    )
    return select(*columns)


def _included_player_predicate(context: StudentDatasetQueryContext):
    return and_(
        Player.generation_run_id == context.generation_run_id,
        Player.registration_date < context.snapshot_end_exclusive,
    )


def _included_player_ids(context: StudentDatasetQueryContext) -> Select:
    return select(Player.id).where(_included_player_predicate(context))


def _included_match_ids(context: StudentDatasetQueryContext) -> Select:
    return select(Match.id).where(Match.batch_id.in_(context.batch_ids))


def _included_match_team_ids(context: StudentDatasetQueryContext) -> Select:
    return select(MatchTeam.id).where(MatchTeam.match_id.in_(_included_match_ids(context)))


def _included_team_ids(context: StudentDatasetQueryContext) -> Select:
    return select(Team.id).where(
        Team.generation_run_id == context.generation_run_id,
        Team.formation_date < context.snapshot_end_exclusive,
    )


def _included_club_membership_ids(context: StudentDatasetQueryContext) -> Select:
    return select(ClubMembership.id).where(
        ClubMembership.player_id.in_(_included_player_ids(context)),
        ClubMembership.start_date < context.snapshot_end_exclusive,
        or_(
            ClubMembership.generation_run_id == context.generation_run_id,
            ClubMembership.generation_run_id.is_(None),
        ),
    )


def _included_club_ids_from_memberships(context: StudentDatasetQueryContext) -> Select:
    return select(ClubMembership.club_id).where(
        ClubMembership.id.in_(_included_club_membership_ids(context))
    )


def _referenced_region_ids(context: StudentDatasetQueryContext) -> Select:
    player_regions = select(Player.home_region_id.label("region_id")).where(
        _included_player_predicate(context),
        Player.home_region_id.is_not(None),
    )
    club_regions = select(Club.region_id.label("region_id")).where(
        Club.id.in_(
            select(Club.id).where(
                or_(
                    and_(
                        Club.generation_run_id == context.generation_run_id,
                        or_(
                            Club.founding_date.is_(None),
                            Club.founding_date < context.snapshot_end_exclusive,
                        ),
                    ),
                    Club.id.in_(_included_club_ids_from_memberships(context)),
                )
            )
        )
    )
    registration_regions = select(
        PlayerRegistration.assigned_region_id.label("region_id")
    ).where(
        PlayerRegistration.batch_id.in_(context.batch_ids),
        PlayerRegistration.player_id.in_(_included_player_ids(context)),
        PlayerRegistration.assigned_region_id.is_not(None),
    )
    match_regions = select(Match.region_id.label("region_id")).where(
        Match.batch_id.in_(context.batch_ids),
        Match.region_id.is_not(None),
    )
    return player_regions.union(club_regions, registration_regions, match_regions)


_QUERY_BUILDERS = {
    "clubs": _clubs_query,
    "club_memberships": _club_memberships_query,
    "match_games": _match_games_query,
    "match_team_players": _match_team_players_query,
    "match_teams": _match_teams_query,
    "matches": _matches_query,
    "monthly_batches": _monthly_batches_query,
    "player_assessment_history": _player_assessment_history_query,
    "player_rating_history": _player_rating_history_query,
    "player_registrations": _player_registrations_query,
    "players": _players_query,
    "regions": _regions_query,
    "team_memberships": _team_memberships_query,
    "teams": _teams_query,
}
