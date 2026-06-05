"""Tests for tournament submission validation and team loading."""
from datetime import date
from decimal import Decimal
from pathlib import Path
import sys

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.models import (  # noqa: E402
    ClubMembership,
    GenerationRun,
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
from app.tournament_simulation import (  # noqa: E402
    PortfolioSlot,
    TeamSubmission,
    latest_completed_source_batch,
    load_validated_tournament_input,
)
from app.tournament_simulation.eligibility import team_active_as_of  # noqa: E402


@pytest.fixture()
def session_factory():
    engine = create_engine("sqlite:///:memory:", future=True)
    with engine.begin() as conn:
        for ddl in _schema_ddls():
            conn.exec_driver_sql(ddl)
    return sessionmaker(bind=engine, autoflush=False, future=True)


@pytest.fixture()
def session(session_factory):
    db_session = session_factory()
    try:
        yield db_session
    finally:
        db_session.close()


def test_latest_completed_source_batch_uses_latest_succeeded_batch(session):
    run = _generation_run(1)
    session.add(run)
    session.add_all(
        [
            _batch(1, run_id=1, month=date(2025, 1, 1), sequence=1),
            _batch(2, run_id=1, month=date(2025, 2, 1), sequence=2),
            _batch(3, run_id=1, month=date(2025, 3, 1), sequence=3, status="failed"),
        ]
    )
    session.commit()

    source = latest_completed_source_batch(session, generation_run_id=1)

    assert source.id == 2


def test_load_validated_tournament_input_builds_divisions_and_collapses_duplicates(session):
    _seed_valid_team(session, team_id=10, player_ids=(101, 102), ratings=(Decimal("1600"), Decimal("1700")))
    _seed_valid_team(session, team_id=20, player_ids=(201, 202), ratings=(Decimal("1500"), Decimal("1550")))
    slot = PortfolioSlot(country_code="US", division="mens_doubles")

    result = load_validated_tournament_input(
        session,
        submissions=(
            TeamSubmission(group_id=1, slot=slot, team_id=10),
            TeamSubmission(group_id=2, slot=slot, team_id=10),
            TeamSubmission(group_id=3, slot=slot, team_id=20),
        ),
        source_batch_id=2,
        tournament_date=date(2025, 3, 15),
    )

    assert result.is_valid
    assert result.source_batch_id == 2
    assert len(result.divisions) == 1
    entries = result.divisions[0].entries
    assert [entry.id for entry in entries] == [10, 20]
    assert entries[0].selected_by_group_ids == (1, 2)
    assert entries[0].average_rating == Decimal("1650")
    assert entries[0].avg_age == Decimal("35.00")
    assert entries[0].region_name == "Austin"


def test_validate_submissions_returns_field_specific_issues(session):
    _seed_valid_team(
        session,
        team_id=10,
        player_ids=(101, 102),
        ratings=(Decimal("1600"), Decimal("1700")),
        country_code="US",
        team_type="mens_doubles",
    )
    _seed_valid_team(
        session,
        team_id=20,
        player_ids=(201, 202),
        ratings=(Decimal("1500"), Decimal("1550")),
        country_code="CA",
        team_type="womens_doubles",
    )

    result = load_validated_tournament_input(
        session,
        submissions=(
            TeamSubmission(
                group_id=1,
                slot=PortfolioSlot(country_code="CA", division="mens_doubles"),
                team_id=10,
            ),
            TeamSubmission(
                group_id=2,
                slot=PortfolioSlot(country_code="CA", division="mens_doubles"),
                team_id=20,
            ),
            TeamSubmission(
                group_id=3,
                slot=PortfolioSlot(country_code="US", division="mens_doubles"),
                team_id=999,
            ),
        ),
        source_batch_id=2,
        tournament_date=date(2025, 3, 15),
    )

    assert not result.is_valid
    assert [(issue.group_id, issue.field, issue.code) for issue in result.issues] == [
        (1, "country_code", "country_mismatch"),
        (2, "division", "division_mismatch"),
        (3, "team_id", "team_not_found"),
    ]
    assert result.divisions == ()


def test_validation_rejects_missing_rating(session):
    _seed_valid_team(
        session,
        team_id=10,
        player_ids=(101, 102),
        ratings=(Decimal("1600"), None),
    )

    result = load_validated_tournament_input(
        session,
        submissions=(
            TeamSubmission(
                group_id=1,
                slot=PortfolioSlot(country_code="US", division="mens_doubles"),
                team_id=10,
            ),
        ),
        source_batch_id=2,
        tournament_date=date(2025, 3, 15),
    )

    assert [(issue.field, issue.code) for issue in result.issues] == [
        ("team_id", "missing_rating")
    ]


def test_lifecycle_events_prefer_reactivation_over_legacy_status(session):
    _seed_valid_team(
        session,
        team_id=10,
        player_ids=(101, 102),
        ratings=(Decimal("1600"), Decimal("1700")),
        team_status="retired",
    )
    session.add(
        TeamLifecycleEvent(
            id=2,
            generation_run_id=1,
            batch_id=2,
            team_id=10,
            event_date=date(2025, 3, 1),
            event_type="reactivated",
        )
    )
    session.commit()

    team = session.get(Team, 10)
    eligibility = team_active_as_of(
        session,
        team,
        tournament_date=date(2025, 3, 15),
    )

    assert eligibility.is_active
    assert eligibility.source == "team_lifecycle_events"


def test_legacy_fallback_handles_retired_team_without_lifecycle(session):
    _seed_valid_team(
        session,
        team_id=10,
        player_ids=(101, 102),
        ratings=(Decimal("1600"), Decimal("1700")),
        team_status="retired",
        lifecycle_event=False,
    )

    result = load_validated_tournament_input(
        session,
        submissions=(
            TeamSubmission(
                group_id=1,
                slot=PortfolioSlot(country_code="US", division="mens_doubles"),
                team_id=10,
            ),
        ),
        source_batch_id=2,
        tournament_date=date(2025, 3, 15),
    )

    assert [(issue.field, issue.code) for issue in result.issues] == [
        ("team_id", "team_not_active")
    ]


def _seed_valid_team(
    session,
    *,
    team_id: int,
    player_ids: tuple[int, int],
    ratings: tuple[Decimal | None, Decimal | None],
    country_code: str = "US",
    team_type: str = "mens_doubles",
    team_status: str = "active",
    lifecycle_event: bool = True,
) -> None:
    if session.get(GenerationRun, 1) is None:
        session.add(_generation_run(1))
        session.add_all(
            [
                _batch(1, run_id=1, month=date(2025, 1, 1), sequence=1),
                _batch(2, run_id=1, month=date(2025, 2, 1), sequence=2),
            ]
        )
    region_id = 1 if country_code == "US" else 2
    region_name = "Austin" if country_code == "US" else "Toronto"
    if session.get(Region, region_id) is None:
        session.add(
            Region(id=region_id, country_code=country_code, region_name=region_name)
        )
    session.add(
        Team(
            id=team_id,
            team_type=team_type,
            team_status=team_status,
            country_code=country_code,
            formation_date=date(2025, 1, 1),
            generation_run_id=1,
        )
    )
    if lifecycle_event:
        session.add(
            TeamLifecycleEvent(
                id=team_id,
                generation_run_id=1,
                batch_id=1,
                team_id=team_id,
                event_date=date(2025, 1, 1),
                event_type="formed",
            )
        )

    for index, player_id in enumerate(player_ids, start=1):
        session.add(
            Player(
                id=player_id,
                first_name=f"Player{player_id}",
                last_name="Test",
                gender="M",
                birth_date=date(1990, 3, 15),
                home_region_id=region_id,
                registration_date=date(2024, 1, 1),
                player_status="ACTIVE",
                generation_run_id=1,
            )
        )
        session.add(
            TeamMembership(
                id=team_id * 10 + index,
                team_id=team_id,
                player_id=player_id,
                player_position=index,
                joined_date=date(2025, 1, 1),
            )
        )
        session.add(
            ClubMembership(
                id=team_id * 10 + index,
                player_id=player_id,
                club_id=1,
                membership_type="member",
                start_date=date(2025, 1, 1),
                is_primary=True,
                generation_run_id=1,
            )
        )
        rating = ratings[index - 1]
        if rating is not None:
            session.add(
                PlayerRatingHistory(
                    id=team_id * 10 + index,
                    player_id=player_id,
                    rating_date=date(2025, 2, 1),
                    rating_type="doubles",
                    rating_value=rating,
                    batch_id=2,
                )
            )
    session.commit()


def _generation_run(run_id: int) -> GenerationRun:
    return GenerationRun(
        id=run_id,
        generation_name=f"run {run_id}",
        seed_value=1,
        simulation_version="test",
        status="succeeded",
    )


def _batch(
    batch_id: int,
    *,
    run_id: int,
    month: date,
    sequence: int,
    status: str = "succeeded",
) -> MonthlyBatch:
    return MonthlyBatch(
        id=batch_id,
        generation_run_id=run_id,
        batch_month=month,
        batch_sequence=sequence,
        batch_type="historical_initial",
        processing_status=status,
    )


def _schema_ddls() -> tuple[str, ...]:
    return (
        """
        CREATE TABLE generation_runs (
            id integer primary key,
            generation_name varchar(255) not null,
            seed_value bigint not null,
            simulation_version varchar(100),
            parameter_snapshot text,
            started_at datetime,
            completed_at datetime,
            status varchar(30) not null default 'succeeded',
            created_at datetime default current_timestamp not null,
            updated_at datetime default current_timestamp not null
        )
        """,
        """
        CREATE TABLE monthly_batches (
            id integer primary key,
            generation_run_id bigint not null,
            batch_month date not null,
            batch_sequence integer not null,
            batch_type varchar(30) not null default 'historical_initial',
            active_player_count_start integer,
            new_player_count integer,
            active_player_count_end integer,
            match_count_generated integer,
            rating_update_count integer,
            assessment_update_count integer,
            processing_status varchar(30) not null default 'succeeded',
            started_at datetime,
            completed_at datetime,
            error_message text,
            created_at datetime default current_timestamp not null,
            updated_at datetime default current_timestamp not null
        )
        """,
        """
        CREATE TABLE regions (
            id integer primary key,
            country_code varchar(10) not null,
            region_type varchar(20),
            region_name varchar(255) not null,
            state_province_code varchar(10),
            population bigint,
            selection_probability numeric(12, 8),
            competitiveness_multiplier numeric(8, 4) default 1.0,
            latitude numeric(10, 6),
            longitude numeric(10, 6),
            created_at datetime default current_timestamp not null,
            updated_at datetime default current_timestamp not null
        )
        """,
        """
        CREATE TABLE players (
            id integer primary key,
            external_player_key varchar(32) not null default (lower(hex(randomblob(16)))) unique,
            first_name varchar(100) not null,
            last_name varchar(100) not null,
            gender varchar(20),
            birth_date date not null,
            dominant_hand varchar(10),
            home_region_id bigint,
            registration_date date not null,
            initial_skill_seed numeric(8, 4),
            player_status varchar(30) not null default 'ACTIVE',
            generation_run_id bigint,
            created_at datetime default current_timestamp not null,
            updated_at datetime default current_timestamp not null
        )
        """,
        """
        CREATE TABLE teams (
            id integer primary key,
            team_type varchar(50) not null,
            team_status varchar(30) default 'active',
            country_code varchar(2),
            formation_date date not null,
            dissolution_date date,
            chemistry_score numeric(8, 4),
            persistence_probability numeric(5, 4),
            generation_run_id bigint,
            created_at datetime default current_timestamp not null,
            updated_at datetime default current_timestamp not null
        )
        """,
        """
        CREATE TABLE team_memberships (
            id integer primary key,
            team_id bigint not null,
            player_id bigint not null,
            player_position integer not null,
            joined_date date not null,
            left_date date,
            created_at datetime default current_timestamp not null,
            updated_at datetime default current_timestamp not null
        )
        """,
        """
        CREATE TABLE team_lifecycle_events (
            id integer primary key,
            generation_run_id bigint not null,
            batch_id bigint not null,
            team_id bigint not null,
            event_date date not null,
            event_type varchar(30) not null,
            created_at datetime default current_timestamp not null,
            updated_at datetime default current_timestamp not null
        )
        """,
        """
        CREATE TABLE player_rating_history (
            id integer primary key,
            player_id bigint not null,
            rating_date date not null,
            rating_type varchar(50) not null,
            rating_value numeric(8, 3) not null,
            confidence_score numeric(8, 3),
            volatility_score numeric(8, 3),
            expected_performance numeric(8, 3),
            regional_adjustment_factor numeric(8, 4),
            global_percentile numeric(5, 2),
            match_count_used integer,
            calculation_version varchar(50),
            batch_id bigint not null,
            created_at datetime default current_timestamp not null,
            updated_at datetime default current_timestamp not null
        )
        """,
        """
        CREATE TABLE club_memberships (
            id integer primary key,
            player_id bigint not null,
            club_id bigint not null,
            membership_type varchar(50),
            start_date date not null,
            end_date date,
            is_primary boolean default true,
            generation_run_id bigint,
            created_at datetime default current_timestamp not null,
            updated_at datetime default current_timestamp not null
        )
        """,
        """
        CREATE TABLE matches (
            id integer primary key,
            tournament_id bigint,
            match_date date not null,
            region_id bigint,
            match_type varchar(50) not null,
            court_type varchar(50),
            match_format varchar(50),
            winning_team_id bigint,
            predicted_winning_team_number integer,
            predicted_win_probability numeric(8, 4),
            total_points_played integer,
            expected_competitiveness numeric(8, 3),
            simulation_noise_factor numeric(8, 3),
            batch_id bigint not null,
            created_at datetime default current_timestamp not null,
            updated_at datetime default current_timestamp not null
        )
        """,
        """
        CREATE TABLE match_teams (
            id integer primary key,
            match_id bigint not null,
            team_number integer not null,
            team_score integer not null,
            expected_win_probability numeric(8, 4),
            average_team_rating numeric(8, 3),
            created_at datetime default current_timestamp not null,
            updated_at datetime default current_timestamp not null
        )
        """,
        """
        CREATE TABLE match_team_players (
            id integer primary key,
            match_team_id bigint not null,
            player_id bigint not null,
            player_position integer,
            player_rating_at_match numeric(8, 3),
            created_at datetime default current_timestamp not null,
            updated_at datetime default current_timestamp not null
        )
        """,
        """
        CREATE TABLE match_games (
            id integer primary key,
            match_id bigint not null,
            game_number integer not null,
            team_one_score integer not null,
            team_two_score integer not null,
            winning_team_number integer not null,
            target_score integer not null,
            win_by integer not null,
            expected_team_one_score_share numeric(8, 4),
            actual_team_one_score_share numeric(8, 4),
            expected_team_one_score numeric(8, 3),
            expected_team_two_score numeric(8, 3),
            score_noise_factor numeric(8, 3),
            created_at datetime default current_timestamp not null,
            updated_at datetime default current_timestamp not null
        )
        """,
    )
