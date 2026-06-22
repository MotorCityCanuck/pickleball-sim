"""Snapshot-aware source queries for student-facing dataset exports."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Mapping

from sqlalchemy import Select, and_, case, func, literal, or_, select
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
        """Return snapshot-scope monthly batch ids."""

        return self.release_window.batch_ids

    @property
    def snapshot_batch_ids(self) -> tuple[int, ...]:
        """Return snapshot-scope monthly batch ids."""

        return self.release_window.snapshot_batch_ids

    @property
    def fact_batch_ids(self) -> tuple[int, ...]:
        """Return fact-scope monthly batch ids."""

        return self.release_window.fact_batch_ids

    @property
    def snapshot_end_exclusive(self):
        """Return the exclusive upper bound for as-of event dates."""

        return self.release_window.snapshot_end_exclusive

    @property
    def prior_snapshot_end_exclusive(self):
        """Return the previous snapshot upper bound, if any."""

        return self.release_window.prior_snapshot_end_exclusive

    @property
    def is_incremental(self) -> bool:
        """Return whether the release window represents an incremental export."""

        return self.release_window.release_type == "monthly_incremental"

    @property
    def has_prior_snapshot(self) -> bool:
        """Return whether a prior snapshot exists for delta comparisons."""

        return bool(self.release_window.prior_snapshot_batches)

    def prior_snapshot_context(self) -> "StudentDatasetQueryContext":
        """Return a query context pinned to the previous snapshot."""

        if not self.has_prior_snapshot:
            raise StudentDatasetQueryError("Prior snapshot context is unavailable.")
        prior_release_window = replace(
            self.release_window,
            batches=self.release_window.prior_snapshot_batches,
            fact_batches=self.release_window.prior_snapshot_batches,
            prior_snapshot_batches=(),
        )
        return StudentDatasetQueryContext(
            generation_run_id=self.generation_run_id,
            release_window=prior_release_window,
        )


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
    if table_name in _INCREMENTAL_DELTA_TABLES and context.is_incremental and context.has_prior_snapshot:
        return _build_incremental_delta_query(
            table_name=table_name,
            context=context,
            snapshot_builder=builder,
        )
    return builder(context)


def _monthly_batches_query(context: StudentDatasetQueryContext) -> Select:
    projection = PROJECTION_BY_TABLE["monthly_batches"]
    return (
        _select_projection(projection)
        .where(
            MonthlyBatch.generation_run_id == context.generation_run_id,
            MonthlyBatch.id.in_(context.fact_batch_ids),
        )
        .order_by(MonthlyBatch.batch_sequence, MonthlyBatch.id)
    )


def _player_registrations_query(context: StudentDatasetQueryContext) -> Select:
    projection = PROJECTION_BY_TABLE["player_registrations"]
    return (
        _select_projection(projection)
        .where(
            PlayerRegistration.batch_id.in_(context.fact_batch_ids),
            PlayerRegistration.player_id.in_(_included_player_ids(context)),
        )
        .order_by(PlayerRegistration.id)
    )


def _players_snapshot_query(context: StudentDatasetQueryContext) -> Select:
    latest_ratings = (
        select(
            PlayerRatingHistory.player_id.label("player_id"),
            PlayerRatingHistory.rating_value.label("rating_value"),
            PlayerRatingHistory.confidence_score.label("confidence_score"),
            PlayerRatingHistory.volatility_score.label("volatility_score"),
            PlayerRatingHistory.global_percentile.label("global_percentile"),
            PlayerRatingHistory.match_count_used.label("match_count_used"),
            PlayerRatingHistory.rating_date.label("rating_date"),
            PlayerRatingHistory.batch_id.label("rating_batch_id"),
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
        .where(
            PlayerRatingHistory.batch_id.in_(context.snapshot_batch_ids),
            PlayerRatingHistory.player_id.in_(_included_player_ids(context)),
            PlayerRatingHistory.rating_date < context.snapshot_end_exclusive,
        )
        .subquery()
    )
    query = (
        select(
            Player.id.label("player_id"),
            Player.external_player_key.label("external_player_key"),
            Player.first_name.label("first_name"),
            Player.last_name.label("last_name"),
            Player.gender.label("gender"),
            Player.birth_date.label("birth_date"),
            Player.dominant_hand.label("dominant_hand"),
            Player.home_region_id.label("home_region_id"),
            Player.registration_date.label("registration_date"),
            Player.player_status.label("player_status"),
            latest_ratings.c.rating_value.label("rating_value"),
            latest_ratings.c.confidence_score.label("confidence_score"),
            latest_ratings.c.volatility_score.label("volatility_score"),
            latest_ratings.c.global_percentile.label("global_percentile"),
            latest_ratings.c.match_count_used.label("match_count_used"),
            latest_ratings.c.rating_date.label("rating_date"),
            latest_ratings.c.rating_batch_id.label("rating_batch_id"),
            literal(context.release_window.snapshot_month).label("snapshot_month"),
        )
        .select_from(Player)
        .outerjoin(
            latest_ratings,
            and_(
                latest_ratings.c.player_id == Player.id,
                latest_ratings.c.rating_rank == 1,
            ),
        )
        .where(_included_player_predicate(context))
        .order_by(Player.id)
    )
    return query


def _players_query(context: StudentDatasetQueryContext) -> Select:
    query = _players_snapshot_query(context)
    if context.is_incremental and context.has_prior_snapshot:
        query = query.where(Player.id.in_(_incremental_player_ids(context)))
    return query


def _player_assessment_history_query(context: StudentDatasetQueryContext) -> Select:
    projection = PROJECTION_BY_TABLE["player_assessment_history"]
    return (
        _select_projection(projection)
        .where(
            PlayerAssessmentHistory.batch_id.in_(context.fact_batch_ids),
            PlayerAssessmentHistory.player_id.in_(_included_player_ids(context)),
        )
        .order_by(PlayerAssessmentHistory.id)
    )


def _matches_query(context: StudentDatasetQueryContext) -> Select:
    projection = PROJECTION_BY_TABLE["matches"]
    return (
        _select_projection(projection)
        .where(Match.batch_id.in_(context.fact_batch_ids))
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


def _teams_snapshot_query(context: StudentDatasetQueryContext) -> Select:
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
    query = (
        _select_projection(projection, overrides)
        .where(
            Team.generation_run_id == context.generation_run_id,
            Team.formation_date < context.snapshot_end_exclusive,
        )
        .order_by(Team.id)
    )
    return query


def _teams_query(context: StudentDatasetQueryContext) -> Select:
    query = _teams_snapshot_query(context)
    if context.is_incremental and context.has_prior_snapshot:
        query = query.where(Team.id.in_(_incremental_team_ids(context)))
    return query


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


def _clubs_snapshot_query(context: StudentDatasetQueryContext) -> Select:
    projection = PROJECTION_BY_TABLE["clubs"]
    query = (
        _select_projection(projection)
        .where(
            or_(
                Club.founding_date.is_(None),
                Club.founding_date < context.snapshot_end_exclusive,
            ),
            or_(
                and_(
                    Club.generation_run_id == context.generation_run_id,
                ),
                Club.id.in_(_included_club_ids_from_memberships(context)),
            )
        )
        .order_by(Club.id)
    )
    return query


def _clubs_query(context: StudentDatasetQueryContext) -> Select:
    query = _clubs_snapshot_query(context)
    if context.is_incremental and context.has_prior_snapshot:
        query = query.where(Club.id.in_(_incremental_club_ids(context)))
    return query


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
            ClubMembership.club_id.in_(_clubs_as_of_snapshot_ids(context)),
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
    query = (
        _select_projection(projection)
        .where(Region.id.in_(_referenced_region_ids(context)))
        .order_by(Region.id)
    )
    if context.is_incremental and context.has_prior_snapshot:
        query = query.where(Region.id.in_(_incremental_region_ids(context)))
    return query


def _build_incremental_delta_query(
    *,
    table_name: str,
    context: StudentDatasetQueryContext,
    snapshot_builder,
) -> Select:
    projection = PROJECTION_BY_TABLE[table_name]
    current_rows = snapshot_builder(context).subquery(f"{table_name}_current")
    prior_rows = snapshot_builder(context.prior_snapshot_context()).subquery(
        f"{table_name}_prior"
    )
    primary_key = _export_primary_key_column(table_name)
    changed_columns = tuple(
        column_name
        for column_name in projection.included_columns
        if column_name != primary_key
        and column_name not in _DELTA_COMPARISON_IGNORED_COLUMNS.get(table_name, ())
    )
    change_predicate = or_(
        prior_rows.c[primary_key].is_(None),
        *(
            current_rows.c[column_name].is_distinct_from(prior_rows.c[column_name])
            for column_name in changed_columns
        ),
    )
    return (
        select(*(current_rows.c[column_name] for column_name in projection.included_columns))
        .select_from(
            current_rows.outerjoin(
                prior_rows,
                prior_rows.c[primary_key] == current_rows.c[primary_key],
            )
        )
        .where(change_predicate)
        .order_by(current_rows.c[primary_key])
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
    return select(Match.id).where(Match.batch_id.in_(context.fact_batch_ids))


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


def _clubs_as_of_snapshot_ids(context: StudentDatasetQueryContext) -> Select:
    return select(Club.id).where(
        or_(
            Club.founding_date.is_(None),
            Club.founding_date < context.snapshot_end_exclusive,
        ),
        or_(
            Club.generation_run_id == context.generation_run_id,
            Club.id.in_(_included_club_ids_from_memberships(context)),
        ),
    )


def _referenced_region_ids(context: StudentDatasetQueryContext) -> Select:
    player_regions = select(Player.home_region_id.label("region_id")).where(
        _included_player_predicate(context),
        Player.home_region_id.is_not(None),
    )
    club_regions = select(Club.region_id.label("region_id")).where(
        Club.id.in_(_clubs_as_of_snapshot_ids(context))
    )
    registration_regions = select(
        PlayerRegistration.assigned_region_id.label("region_id")
    ).where(
        PlayerRegistration.batch_id.in_(context.fact_batch_ids),
        PlayerRegistration.player_id.in_(_included_player_ids(context)),
        PlayerRegistration.assigned_region_id.is_not(None),
    )
    match_regions = select(Match.region_id.label("region_id")).where(
        Match.batch_id.in_(context.fact_batch_ids),
        Match.region_id.is_not(None),
    )
    return player_regions.union(club_regions, registration_regions, match_regions)


def _incremental_player_ids(context: StudentDatasetQueryContext) -> Select:
    changed_player_ids = _delta_primary_keys("players", context)
    registration_players = select(PlayerRegistration.player_id).where(
        PlayerRegistration.batch_id.in_(context.fact_batch_ids),
        PlayerRegistration.player_id.in_(_included_player_ids(context)),
    )
    assessment_players = select(PlayerAssessmentHistory.player_id).where(
        PlayerAssessmentHistory.batch_id.in_(context.fact_batch_ids),
        PlayerAssessmentHistory.player_id.in_(_included_player_ids(context)),
    )
    match_players = select(MatchTeamPlayer.player_id).where(
        MatchTeamPlayer.match_team_id.in_(_included_match_team_ids(context))
    )
    club_membership_players = select(ClubMembership.player_id).where(
        ClubMembership.id.in_(_delta_primary_keys("club_memberships", context))
    )
    team_membership_players = select(TeamMembership.player_id).where(
        TeamMembership.id.in_(_delta_primary_keys("team_memberships", context))
    )
    return changed_player_ids.union(
        registration_players,
        assessment_players,
        match_players,
        club_membership_players,
        team_membership_players,
    )


def _incremental_team_ids(context: StudentDatasetQueryContext) -> Select:
    changed_team_ids = _delta_primary_keys("teams", context)
    membership_team_ids = select(TeamMembership.team_id).where(
        TeamMembership.id.in_(_delta_primary_keys("team_memberships", context))
    )
    return changed_team_ids.union(membership_team_ids)


def _incremental_club_ids(context: StudentDatasetQueryContext) -> Select:
    changed_club_ids = _delta_primary_keys("clubs", context)
    membership_club_ids = select(ClubMembership.club_id).where(
        ClubMembership.id.in_(_delta_primary_keys("club_memberships", context))
    )
    return changed_club_ids.union(membership_club_ids)


def _incremental_region_ids(context: StudentDatasetQueryContext) -> Select:
    player_regions = select(Player.home_region_id.label("region_id")).where(
        Player.id.in_(_incremental_player_ids(context)),
        Player.home_region_id.is_not(None),
    )
    club_regions = select(Club.region_id.label("region_id")).where(
        Club.id.in_(_incremental_club_ids(context)),
        Club.region_id.is_not(None),
    )
    registration_regions = select(
        PlayerRegistration.assigned_region_id.label("region_id")
    ).where(
        PlayerRegistration.batch_id.in_(context.fact_batch_ids),
        PlayerRegistration.player_id.in_(_included_player_ids(context)),
        PlayerRegistration.assigned_region_id.is_not(None),
    )
    match_regions = select(Match.region_id.label("region_id")).where(
        Match.batch_id.in_(context.fact_batch_ids),
        Match.region_id.is_not(None),
    )
    return player_regions.union(club_regions, registration_regions, match_regions)


def _delta_primary_keys(table_name: str, context: StudentDatasetQueryContext) -> Select:
    delta_query = _build_incremental_delta_query(
        table_name=table_name,
        context=context,
        snapshot_builder=_SNAPSHOT_QUERY_BUILDERS[table_name],
    ).subquery(f"{table_name}_delta")
    primary_key = _export_primary_key_column(table_name)
    return select(delta_query.c[primary_key])


def _export_primary_key_column(table_name: str) -> str:
    return "player_id" if table_name == "players" else "id"


_INCREMENTAL_DELTA_TABLES = frozenset(
    {
        "club_memberships",
        "team_memberships",
    }
)

_DELTA_COMPARISON_IGNORED_COLUMNS = {
    "players": ("snapshot_month",),
}


_QUERY_BUILDERS = {
    "clubs": _clubs_query,
    "club_memberships": _club_memberships_query,
    "match_games": _match_games_query,
    "match_team_players": _match_team_players_query,
    "match_teams": _match_teams_query,
    "matches": _matches_query,
    "monthly_batches": _monthly_batches_query,
    "player_assessment_history": _player_assessment_history_query,
    "players": _players_query,
    "player_registrations": _player_registrations_query,
    "regions": _regions_query,
    "team_memberships": _team_memberships_query,
    "teams": _teams_query,
}

_SNAPSHOT_QUERY_BUILDERS = {
    **_QUERY_BUILDERS,
    "clubs": _clubs_snapshot_query,
    "players": _players_snapshot_query,
    "teams": _teams_snapshot_query,
}
