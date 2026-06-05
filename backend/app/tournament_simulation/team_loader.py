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
    TeamMembership,
)

from .dtos import PortfolioSlot, TournamentDivision, TournamentTeamEntry
from .eligibility import team_active_as_of
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

    issues: list[SubmissionValidationIssue] = []
    entries_by_id: dict[int, TournamentTeamEntry] = {}
    for submission in submissions:
        loaded = _load_team_entry(
            session,
            submission=submission,
            source_batch=source_batch,
            tournament_date=tournament_date,
        )
        issues.extend(loaded.issues)
        if loaded.entry is not None:
            entries_by_id[loaded.entry.id] = loaded.entry

    divisions: list[TournamentDivision] = []
    submissions_by_slot: dict[PortfolioSlot, dict[int, int]] = defaultdict(dict)
    for submission in submissions:
        if any(
            issue.group_id == submission.group_id
            and issue.slot == submission.slot
            and issue.team_id == submission.team_id
            for issue in issues
        ):
            continue
        submissions_by_slot[submission.slot][submission.group_id] = submission.team_id

    for slot, group_submissions in sorted(
        submissions_by_slot.items(),
        key=lambda item: item[0],
    ):
        divisions.append(
            build_division_from_submissions(
                slot=slot,
                submissions_by_group_id=group_submissions,
                teams_by_id=entries_by_id,
            )
        )

    return ValidatedTournamentInput(
        source_batch_id=source_batch.id,
        tournament_date=tournament_date,
        divisions=tuple(divisions),
        issues=tuple(issues),
    )


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


def _load_team_entry(
    session: Session,
    *,
    submission: TeamSubmission,
    source_batch: MonthlyBatch,
    tournament_date: date,
) -> _LoadedTeam:
    team = session.get(Team, submission.team_id)
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
    if team.team_type != submission.slot.division:
        issues.append(
            _issue(
                submission,
                field="division",
                code="division_mismatch",
                message=(
                    f"Team {team.id} is {team.team_type}, not "
                    f"{submission.slot.division}."
                ),
            )
        )

    eligibility = team_active_as_of(
        session,
        team,
        tournament_date=tournament_date,
    )
    if not eligibility.is_active:
        issues.append(
            _issue(
                submission,
                field="team_id",
                code="team_not_active",
                message=f"Team {team.id} is not active: {eligibility.reason}.",
            )
        )

    roster_rows = _active_roster_rows(
        session,
        team_id=team.id,
        source_batch=source_batch,
        tournament_date=tournament_date,
    )
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

    ratings = _latest_ratings_by_player(
        session,
        player_ids=set(player_ids),
        source_batch=source_batch,
    )
    missing_ratings = [player_id for player_id in player_ids if player_id not in ratings]
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
        session,
        player_ids=set(player_ids),
        as_of=source_batch.batch_month,
    )
    prior_match_count, recent_match_count, recent_game_count = _team_activity_counts(
        session,
        player_ids=player_ids,
        source_batch=source_batch,
    )
    average_rating = sum(ratings[player_id] for player_id in player_ids) / Decimal("2")
    entry = TournamentTeamEntry(
        id=team.id,
        country_code=team.country_code,
        division=team.team_type,
        average_rating=average_rating,
        avg_age=_average_age([row["birth_date"] for row in roster_rows], as_of=tournament_date),
        region_name=_team_region_name(session, roster_rows),
        primary_club_ids=primary_club_ids,
        club_ids=club_ids,
        team_total_prior_matches=prior_match_count,
        recent_pair_counts={player_ids: recent_match_count},
        recent_game_count=recent_game_count,
    )
    return _LoadedTeam(entry=entry, issues=())


def _active_roster_rows(
    session: Session,
    *,
    team_id: int,
    source_batch: MonthlyBatch,
    tournament_date: date,
) -> list[dict[str, object]]:
    rows = session.execute(
        select(
            TeamMembership.player_id,
            TeamMembership.player_position,
            Player.birth_date,
            Player.home_region_id,
            Region.country_code,
        )
        .join(Player, Player.id == TeamMembership.player_id)
        .join(Region, Region.id == Player.home_region_id)
        .where(
            TeamMembership.team_id == team_id,
            TeamMembership.joined_date <= tournament_date,
            or_(
                TeamMembership.left_date.is_(None),
                TeamMembership.left_date > tournament_date,
            ),
            Player.player_status == "ACTIVE",
            Player.generation_run_id == source_batch.generation_run_id,
        )
        .order_by(TeamMembership.player_position)
    ).all()
    return [
        {
            "player_id": player_id,
            "player_position": player_position,
            "birth_date": birth_date,
            "home_region_id": home_region_id,
            "country_code": country_code,
        }
        for player_id, player_position, birth_date, home_region_id, country_code in rows
    ]


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


def _club_ids_for_players(
    session: Session,
    *,
    player_ids: set[int],
    as_of: date,
) -> tuple[frozenset[int], frozenset[int]]:
    if not player_ids:
        return frozenset(), frozenset()
    club_ids: set[int] = set()
    primary_club_ids: set[int] = set()
    for _player_id, club_id, is_primary in session.execute(
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
        club_ids.add(club_id)
        if is_primary:
            primary_club_ids.add(club_id)
    return frozenset(club_ids), frozenset(primary_club_ids)


def _team_activity_counts(
    session: Session,
    *,
    player_ids: tuple[int, ...],
    source_batch: MonthlyBatch,
) -> tuple[int, int, int]:
    prior_match_count = 0
    recent_match_count = 0
    recent_game_count = 0
    game_counts = dict(
        session.execute(
            select(MatchGame.match_id, func.count(MatchGame.id)).group_by(
                MatchGame.match_id
            )
        ).all()
    )
    rows: dict[int, dict[str, object]] = {}
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
            MonthlyBatch.generation_run_id == source_batch.generation_run_id,
            MonthlyBatch.batch_sequence <= source_batch.batch_sequence,
            Match.match_date < source_batch.batch_month,
            MatchTeamPlayer.player_id.in_(set(player_ids)),
        )
    ):
        row = rows.setdefault(
            match_team_id,
            {
                "match_id": match_id,
                "match_date": match_date,
                "player_ids": [],
            },
        )
        row["player_ids"].append(player_id)

    for row in rows.values():
        if tuple(sorted(row["player_ids"])) != player_ids:
            continue
        prior_match_count += 1
        recent_match_count += 1
        recent_game_count += int(game_counts.get(row["match_id"], 0))

    return prior_match_count, recent_match_count, recent_game_count


def _team_region_name(
    session: Session,
    roster_rows: list[dict[str, object]],
) -> str | None:
    region_ids = [row["home_region_id"] for row in roster_rows]
    if not region_ids or region_ids[0] is None:
        return None
    region = session.get(Region, region_ids[0])
    return None if region is None else region.region_name


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
