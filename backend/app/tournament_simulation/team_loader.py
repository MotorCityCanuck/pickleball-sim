"""Load and validate student-submitted tournament teams."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models import (
    ClubMembership,
    Match,
    MatchGame,
    MatchTeam,
    MatchTeamPlayer,
    MonthlyBatch,
    Player,
    PlayerRatingHistory,
    Region,
    Team,
    TeamLifecycleEvent,
    TeamMembership,
)

from .dtos import PortfolioSlot, TournamentDivision, TournamentTeamEntry
from .eligibility import (
    ACTIVE_LIFECYCLE_EVENTS,
    INACTIVE_LIFECYCLE_EVENTS,
    TeamEligibility,
    team_active_as_of,
)
from .round_robin import build_division_from_submissions


@dataclass(frozen=True)
class TeamSubmission:
    """One student-group team selection for one portfolio slot."""

    group_id: int
    slot: PortfolioSlot
    team_id: int


@dataclass(frozen=True)
class SubmissionValidationIssue:
    """Field-specific validation issue suitable for UI display."""

    group_id: int
    slot: PortfolioSlot
    team_id: int
    field: str
    code: str
    message: str


@dataclass(frozen=True)
class ValidatedTournamentInput:
    """Validated in-memory tournament input loaded from submitted team IDs."""

    source_batch_id: int
    tournament_date: date
    divisions: tuple[TournamentDivision, ...]
    issues: tuple[SubmissionValidationIssue, ...]

    @property
    def is_valid(self) -> bool:
        return not self.issues


@dataclass(frozen=True)
class _LoadedTeam:
    entry: TournamentTeamEntry | None
    issues: tuple[SubmissionValidationIssue, ...]


@dataclass(frozen=True)
class _ValidationContext:
    source_batch: MonthlyBatch
    tournament_date: date
    teams_by_id: dict[int, Team]
    eligibility_by_team_id: dict[int, TeamEligibility]
    roster_rows_by_team_id: dict[int, tuple[dict[str, object], ...]]
    ratings_by_player_id: dict[int, Decimal]
    club_memberships_by_player_id: dict[int, tuple[tuple[int, bool], ...]]
    activity_counts_by_pair: dict[tuple[int, int], tuple[int, int, int]]


def latest_completed_source_batch(
    session: Session,
    *,
    generation_run_id: int | None = None,
) -> MonthlyBatch | None:
    """Return the latest succeeded batch available as a tournament source."""
    statement = select(MonthlyBatch).where(MonthlyBatch.processing_status == "succeeded")
    if generation_run_id is not None:
        statement = statement.where(MonthlyBatch.generation_run_id == generation_run_id)
    return session.execute(
        statement.order_by(
            MonthlyBatch.batch_month.desc(),
            MonthlyBatch.batch_sequence.desc(),
            MonthlyBatch.id.desc(),
        ).limit(1)
    ).scalar_one_or_none()


def load_validated_tournament_input(
    session: Session,
    *,
    submissions: tuple[TeamSubmission, ...],
    tournament_date: date,
    source_batch_id: int | None = None,
    generation_run_id: int | None = None,
) -> ValidatedTournamentInput:
    """Validate submissions and load runnable tournament divisions."""
    source_batch = _resolve_source_batch(
        session,
        source_batch_id=source_batch_id,
        generation_run_id=generation_run_id,
    )
    validation_context = _build_validation_context(
        session,
        submissions=submissions,
        source_batch=source_batch,
        tournament_date=tournament_date,
    )

    issues: list[SubmissionValidationIssue] = []
    entries_by_id: dict[int, TournamentTeamEntry] = {}
    for submission in submissions:
        loaded = _load_team_entry(
            submission=submission,
            validation_context=validation_context,
        )
        issues.extend(loaded.issues)
        if loaded.entry is not None:
            entries_by_id[loaded.entry.id] = loaded.entry

    divisions: list[TournamentDivision] = []
    issue_keys = {
        (issue.group_id, issue.slot, issue.team_id)
        for issue in issues
    }
    submissions_by_division: dict[str, list[tuple[int, int]]] = defaultdict(list)
    for submission in submissions:
        if (submission.group_id, submission.slot, submission.team_id) in issue_keys:
            continue
        submissions_by_division[submission.slot.division].append(
            (submission.group_id, submission.team_id)
        )

    for division, submitted_group_team_ids in sorted(
        submissions_by_division.items(),
        key=lambda item: item[0],
    ):
        divisions.append(
            build_division_from_submissions(
                slot=PortfolioSlot(country_code="ALL", division=division),
                submitted_group_team_ids=submitted_group_team_ids,
                teams_by_id=entries_by_id,
            )
        )

    return ValidatedTournamentInput(
        source_batch_id=source_batch.id,
        tournament_date=tournament_date,
        divisions=tuple(divisions),
        issues=tuple(issues),
    )


def validate_tournament_submission(
    session: Session,
    *,
    submission: TeamSubmission,
    tournament_date: date,
    source_batch_id: int | None = None,
    generation_run_id: int | None = None,
) -> tuple[SubmissionValidationIssue, ...]:
    """Validate a single submitted team against tournament rules."""
    source_batch = _resolve_source_batch(
        session,
        source_batch_id=source_batch_id,
        generation_run_id=generation_run_id,
    )
    validation_context = _build_validation_context(
        session,
        submissions=(submission,),
        source_batch=source_batch,
        tournament_date=tournament_date,
    )
    return _load_team_entry(
        submission=submission,
        validation_context=validation_context,
    ).issues


def _resolve_source_batch(
    session: Session,
    *,
    source_batch_id: int | None,
    generation_run_id: int | None,
) -> MonthlyBatch:
    if source_batch_id is not None:
        source_batch = session.get(MonthlyBatch, source_batch_id)
        if source_batch is None:
            raise ValueError(f"Monthly batch {source_batch_id} does not exist")
        if source_batch.processing_status != "succeeded":
            raise ValueError(f"Monthly batch {source_batch_id} is not succeeded")
        if (
            generation_run_id is not None
            and source_batch.generation_run_id != generation_run_id
        ):
            raise ValueError(
                f"Monthly batch {source_batch_id} does not belong to generation "
                f"run {generation_run_id}"
            )
        return source_batch

    source_batch = latest_completed_source_batch(
        session,
        generation_run_id=generation_run_id,
    )
    if source_batch is None:
        if generation_run_id is None:
            raise ValueError("No succeeded monthly batch is available")
        raise ValueError(
            f"No succeeded monthly batch is available for generation run {generation_run_id}"
        )
    return source_batch


def _build_validation_context(
    session: Session,
    *,
    submissions: tuple[TeamSubmission, ...],
    source_batch: MonthlyBatch,
    tournament_date: date,
) -> _ValidationContext:
    team_ids = {submission.team_id for submission in submissions}
    teams_by_id = (
        {
            team.id: team
            for team in session.execute(
                select(Team).where(Team.id.in_(team_ids))
            ).scalars()
        }
        if team_ids
        else {}
    )
    roster_rows_by_team_id = _active_roster_rows_by_team(
        session,
        team_ids=set(teams_by_id),
        source_batch=source_batch,
        tournament_date=tournament_date,
    )
    player_ids = {
        int(row["player_id"])
        for roster_rows in roster_rows_by_team_id.values()
        for row in roster_rows
    }
    player_pairs = {
        tuple(sorted(int(row["player_id"]) for row in roster_rows))
        for roster_rows in roster_rows_by_team_id.values()
        if len(roster_rows) == 2
    }
    return _ValidationContext(
        source_batch=source_batch,
        tournament_date=tournament_date,
        teams_by_id=teams_by_id,
        eligibility_by_team_id=_eligibility_by_team_id(
            session,
            teams_by_id=teams_by_id,
            tournament_date=tournament_date,
        ),
        roster_rows_by_team_id=roster_rows_by_team_id,
        ratings_by_player_id=_latest_ratings_by_player(
            session,
            player_ids=player_ids,
            source_batch=source_batch,
        ),
        club_memberships_by_player_id=_club_memberships_by_player(
            session,
            player_ids=player_ids,
            as_of=source_batch.batch_month,
        ),
        activity_counts_by_pair=_team_activity_counts_by_pair(
            session,
            player_pairs=player_pairs,
            source_batch=source_batch,
        ),
    )


def _load_team_entry(
    *,
    submission: TeamSubmission,
    validation_context: _ValidationContext,
) -> _LoadedTeam:
    source_batch = validation_context.source_batch
    team = validation_context.teams_by_id.get(submission.team_id)
    if team is None:
        return _LoadedTeam(
            entry=None,
            issues=(
                _issue(
                    submission,
                    field="team_id",
                    code="team_not_found",
                    message=f"Team {submission.team_id} does not exist.",
                ),
            ),
        )

    issues: list[SubmissionValidationIssue] = []
    if team.generation_run_id != source_batch.generation_run_id:
        issues.append(
            _issue(
                submission,
                field="team_id",
                code="wrong_generation_run",
                message=(
                    f"Team {team.id} does not belong to source generation run "
                    f"{source_batch.generation_run_id}."
                ),
            )
        )
    if team.country_code != submission.slot.country_code:
        issues.append(
            _issue(
                submission,
                field="country_code",
                code="country_mismatch",
                message=(
                    f"Team {team.id} is {team.country_code}, not "
                    f"{submission.slot.country_code}."
                ),
            )
        )
    if team.team_division != submission.slot.division:
        issues.append(
            _issue(
                submission,
                field="division",
                code="division_mismatch",
                message=(
                    f"Team {team.id} is {team.team_division}, not "
                    f"{submission.slot.division}."
                ),
            )
        )

    eligibility = validation_context.eligibility_by_team_id[team.id]
    if not eligibility.is_active:
        issues.append(
            _issue(
                submission,
                field="team_id",
                code="team_not_active",
                message=f"Team {team.id} is not active: {eligibility.reason}.",
            )
        )

    roster_rows = validation_context.roster_rows_by_team_id.get(team.id, ())
    if len(roster_rows) != 2:
        issues.append(
            _issue(
                submission,
                field="team_id",
                code="invalid_roster",
                message=f"Team {team.id} must have exactly two active members.",
            )
        )
        return _LoadedTeam(entry=None, issues=tuple(issues))

    player_ids = tuple(sorted(row["player_id"] for row in roster_rows))
    country_codes = {row["country_code"] for row in roster_rows}
    if country_codes != {team.country_code}:
        issues.append(
            _issue(
                submission,
                field="team_id",
                code="cross_country_team",
                message=f"Team {team.id} has member countries {sorted(country_codes)}.",
            )
        )

    missing_ratings = [
        player_id
        for player_id in player_ids
        if player_id not in validation_context.ratings_by_player_id
    ]
    if missing_ratings:
        issues.append(
            _issue(
                submission,
                field="team_id",
                code="missing_rating",
                message=(
                    f"Team {team.id} has players without ratings as of source "
                    f"batch {source_batch.id}: {missing_ratings}."
                ),
            )
        )

    if issues:
        return _LoadedTeam(entry=None, issues=tuple(issues))

    club_ids, primary_club_ids = _club_ids_for_players(
        player_ids=player_ids,
        memberships_by_player_id=validation_context.club_memberships_by_player_id,
    )
    prior_match_count, recent_match_count, recent_game_count = (
        validation_context.activity_counts_by_pair.get(player_ids, (0, 0, 0))
    )
    average_rating = (
        sum(validation_context.ratings_by_player_id[player_id] for player_id in player_ids)
        / Decimal("2")
    )
    entry = TournamentTeamEntry(
        id=team.id,
        country_code=team.country_code,
        division=team.team_division,
        average_rating=average_rating,
        avg_age=_average_age(
            [row["birth_date"] for row in roster_rows],
            as_of=validation_context.tournament_date,
        ),
        region_name=_team_region_name(roster_rows),
        primary_club_ids=primary_club_ids,
        club_ids=club_ids,
        team_total_prior_matches=prior_match_count,
        recent_pair_counts={player_ids: recent_match_count},
        recent_game_count=recent_game_count,
    )
    return _LoadedTeam(entry=entry, issues=())


def _eligibility_by_team_id(
    session: Session,
    *,
    teams_by_id: dict[int, Team],
    tournament_date: date,
) -> dict[int, TeamEligibility]:
    if not teams_by_id:
        return {}

    latest_events_by_team_id: dict[int, TeamLifecycleEvent] = {}
    for event in session.execute(
        select(TeamLifecycleEvent)
        .where(
            TeamLifecycleEvent.team_id.in_(set(teams_by_id)),
            TeamLifecycleEvent.event_date <= tournament_date,
        )
        .order_by(
            TeamLifecycleEvent.team_id,
            TeamLifecycleEvent.event_date.desc(),
            TeamLifecycleEvent.id.desc(),
        )
    ).scalars():
        latest_events_by_team_id.setdefault(event.team_id, event)

    results: dict[int, TeamEligibility] = {}
    for team_id, team in teams_by_id.items():
        latest_event = latest_events_by_team_id.get(team_id)
        if latest_event is not None:
            if latest_event.event_type in ACTIVE_LIFECYCLE_EVENTS:
                results[team_id] = TeamEligibility(
                    is_active=True,
                    source="team_lifecycle_events",
                )
                continue
            if latest_event.event_type in INACTIVE_LIFECYCLE_EVENTS:
                results[team_id] = TeamEligibility(
                    is_active=False,
                    source="team_lifecycle_events",
                    reason=f"latest lifecycle event is {latest_event.event_type}",
                )
                continue
            results[team_id] = TeamEligibility(
                is_active=False,
                source="team_lifecycle_events",
                reason=f"unknown lifecycle event {latest_event.event_type}",
            )
            continue

        results[team_id] = team_active_as_of(
            session,
            team,
            tournament_date=tournament_date,
        )

    return results


def _active_roster_rows_by_team(
    session: Session,
    *,
    team_ids: set[int],
    source_batch: MonthlyBatch,
    tournament_date: date,
) -> dict[int, tuple[dict[str, object], ...]]:
    if not team_ids:
        return {}

    rows_by_team_id: dict[int, list[dict[str, object]]] = defaultdict(list)
    for (
        team_id,
        player_id,
        player_position,
        birth_date,
        home_region_id,
        country_code,
        region_name,
    ) in session.execute(
        select(
            TeamMembership.team_id,
            TeamMembership.player_id,
            TeamMembership.player_position,
            Player.birth_date,
            Player.home_region_id,
            Region.country_code,
            Region.region_name,
        )
        .join(Player, Player.id == TeamMembership.player_id)
        .join(Region, Region.id == Player.home_region_id)
        .where(
            TeamMembership.team_id.in_(team_ids),
            TeamMembership.joined_date <= tournament_date,
            or_(
                TeamMembership.left_date.is_(None),
                TeamMembership.left_date > tournament_date,
            ),
            Player.player_status == "ACTIVE",
            Player.generation_run_id == source_batch.generation_run_id,
        )
        .order_by(TeamMembership.team_id, TeamMembership.player_position)
    ):
        rows_by_team_id[team_id].append(
            {
                "player_id": player_id,
                "player_position": player_position,
                "birth_date": birth_date,
                "home_region_id": home_region_id,
                "country_code": country_code,
                "region_name": region_name,
            }
        )
    return {
        team_id: tuple(rows)
        for team_id, rows in rows_by_team_id.items()
    }


def _latest_ratings_by_player(
    session: Session,
    *,
    player_ids: set[int],
    source_batch: MonthlyBatch,
) -> dict[int, Decimal]:
    if not player_ids:
        return {}

    latest: dict[int, Decimal] = {}
    for player_id, rating_value in session.execute(
        select(PlayerRatingHistory.player_id, PlayerRatingHistory.rating_value)
        .join(MonthlyBatch, MonthlyBatch.id == PlayerRatingHistory.batch_id)
        .where(
            PlayerRatingHistory.player_id.in_(player_ids),
            MonthlyBatch.generation_run_id == source_batch.generation_run_id,
            MonthlyBatch.batch_sequence <= source_batch.batch_sequence,
            PlayerRatingHistory.rating_date <= source_batch.batch_month,
        )
        .order_by(
            PlayerRatingHistory.player_id,
            PlayerRatingHistory.rating_date.desc(),
            PlayerRatingHistory.id.desc(),
        )
    ):
        if player_id not in latest:
            latest[player_id] = _decimal(rating_value)
    return latest


def _club_memberships_by_player(
    session: Session,
    *,
    player_ids: set[int],
    as_of: date,
) -> dict[int, tuple[tuple[int, bool], ...]]:
    if not player_ids:
        return {}
    memberships_by_player_id: dict[int, list[tuple[int, bool]]] = defaultdict(list)
    for player_id, club_id, is_primary in session.execute(
        select(
            ClubMembership.player_id,
            ClubMembership.club_id,
            ClubMembership.is_primary,
        ).where(
            ClubMembership.player_id.in_(player_ids),
            ClubMembership.start_date <= as_of,
            or_(ClubMembership.end_date.is_(None), ClubMembership.end_date > as_of),
        )
    ):
        memberships_by_player_id[player_id].append((club_id, bool(is_primary)))
    return {
        player_id: tuple(memberships)
        for player_id, memberships in memberships_by_player_id.items()
    }


def _club_ids_for_players(
    *,
    player_ids: tuple[int, ...],
    memberships_by_player_id: dict[int, tuple[tuple[int, bool], ...]],
) -> tuple[frozenset[int], frozenset[int]]:
    club_ids: set[int] = set()
    primary_club_ids: set[int] = set()
    for player_id in player_ids:
        for club_id, is_primary in memberships_by_player_id.get(player_id, ()):
            club_ids.add(club_id)
            if is_primary:
                primary_club_ids.add(club_id)
    return frozenset(club_ids), frozenset(primary_club_ids)


def _team_activity_counts_by_pair(
    session: Session,
    *,
    player_pairs: set[tuple[int, int]],
    source_batch: MonthlyBatch,
) -> dict[tuple[int, int], tuple[int, int, int]]:
    if not player_pairs:
        return {}

    player_ids = {player_id for player_pair in player_pairs for player_id in player_pair}
    rows: dict[int, dict[str, object]] = {}
    match_ids: set[int] = set()
    for match_team_id, match_id, _match_date, player_id in session.execute(
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
            MonthlyBatch.generation_run_id == source_batch.generation_run_id,
            MonthlyBatch.batch_sequence <= source_batch.batch_sequence,
            Match.match_date < source_batch.batch_month,
            MatchTeamPlayer.player_id.in_(set(player_ids)),
        )
    ):
        match_ids.add(match_id)
        row = rows.setdefault(
            match_team_id,
            {
                "match_id": match_id,
                "player_ids": [],
            },
        )
        row["player_ids"].append(player_id)

    game_counts = (
        dict(
            session.execute(
                select(MatchGame.match_id, func.count(MatchGame.id))
                .where(MatchGame.match_id.in_(match_ids))
                .group_by(MatchGame.match_id)
            ).all()
        )
        if match_ids
        else {}
    )

    counts_by_pair = {
        player_pair: [0, 0, 0]
        for player_pair in player_pairs
    }
    for row in rows.values():
        player_pair = tuple(sorted(row["player_ids"]))
        if player_pair not in counts_by_pair:
            continue
        counts_by_pair[player_pair][0] += 1
        counts_by_pair[player_pair][1] += 1
        counts_by_pair[player_pair][2] += int(game_counts.get(row["match_id"], 0))

    return {
        player_pair: (counts[0], counts[1], counts[2])
        for player_pair, counts in counts_by_pair.items()
    }


def _team_region_name(
    roster_rows: tuple[dict[str, object], ...],
) -> str | None:
    if not roster_rows:
        return None
    region_name = roster_rows[0]["region_name"]
    return None if region_name is None else str(region_name)


def _average_age(birth_dates: list[date], *, as_of: date) -> Decimal | None:
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


def _decimal(value: object) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _issue(
    submission: TeamSubmission,
    *,
    field: str,
    code: str,
    message: str,
) -> SubmissionValidationIssue:
    return SubmissionValidationIssue(
        group_id=submission.group_id,
        slot=submission.slot,
        team_id=submission.team_id,
        field=field,
        code=code,
        message=message,
    )
