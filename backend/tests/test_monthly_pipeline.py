"""Tests for end-to-end monthly pipeline orchestration."""
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

from app.generation import MonthlyGenerationPipeline  # noqa: E402
from app.generators import (  # noqa: E402
    ClubMembershipGenerationResult,
    MatchGenerationResult,
    PlayerGenerationResult,
    RatingUpdateResult,
    TeamGenerationResult,
)
from app.models import (  # noqa: E402
    ClubMembership,
    GenerationRun,
    Match,
    MonthlyBatch,
    Player,
    PlayerRegistration,
    RatingsUpdateLog,
    Team,
)


@pytest.fixture()
def session_factory():
    engine = create_engine("sqlite:///:memory:", future=True)
    with engine.begin() as conn:
        conn.exec_driver_sql(
            """
            CREATE TABLE generation_runs (
                id integer primary key,
                generation_name varchar(255) not null,
                seed_value bigint not null,
                simulation_version varchar(100),
                parameter_snapshot text,
                started_at datetime,
                completed_at datetime,
                status varchar(30) not null default 'not_started',
                created_at datetime default current_timestamp not null,
                updated_at datetime default current_timestamp not null
            )
            """
        )
        conn.exec_driver_sql(
            """
            CREATE TABLE monthly_batches (
                id integer primary key,
                generation_run_id bigint not null,
                batch_month date not null,
                batch_sequence integer not null,
                batch_type varchar(30) not null default 'future_increment',
                active_player_count_start integer,
                new_player_count integer,
                active_player_count_end integer,
                match_count_generated integer,
                rating_update_count integer,
                assessment_update_count integer,
                processing_status varchar(30) not null default 'pending',
                started_at datetime,
                completed_at datetime,
                error_message text,
                created_at datetime default current_timestamp not null,
                updated_at datetime default current_timestamp not null,
                unique (generation_run_id, batch_month)
            )
            """
        )
        conn.exec_driver_sql(
            """
            CREATE TABLE players (
                id integer primary key,
                external_player_key varchar(32),
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
            """
        )
        conn.exec_driver_sql(
            """
            CREATE TABLE player_registrations (
                id integer primary key,
                player_id bigint not null,
                batch_id bigint not null,
                registration_month date not null,
                registration_source varchar(50) not null default 'synthetic',
                assigned_region_id bigint,
                initial_rating_value numeric(8, 3),
                initial_confidence_score numeric(8, 3),
                created_at datetime default current_timestamp not null,
                updated_at datetime default current_timestamp not null
            )
            """
        )
        conn.exec_driver_sql(
            """
            CREATE TABLE club_memberships (
                id integer primary key,
                player_id bigint not null,
                club_id bigint not null,
                membership_type varchar(50),
                start_date date not null,
                end_date date,
                is_primary boolean,
                generation_run_id bigint,
                created_at datetime default current_timestamp not null,
                updated_at datetime default current_timestamp not null
            )
            """
        )
        conn.exec_driver_sql(
            """
            CREATE TABLE teams (
                id integer primary key,
                team_type varchar(50) not null,
                team_status varchar(30),
                formation_date date not null,
                dissolution_date date,
                chemistry_score numeric(8, 4),
                persistence_probability numeric(5, 4),
                generation_run_id bigint,
                created_at datetime default current_timestamp not null,
                updated_at datetime default current_timestamp not null
            )
            """
        )
        conn.exec_driver_sql(
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
            """
        )
        conn.exec_driver_sql(
            """
            CREATE TABLE ratings_update_log (
                id integer primary key,
                generation_run_id bigint not null,
                batch_id bigint not null,
                match_id bigint not null,
                match_number integer not null,
                match_date date not null,
                player_id bigint not null,
                match_team_id bigint not null,
                team_number integer not null,
                rating_type varchar(50) not null,
                rating_before numeric(8, 3) not null,
                rating_after numeric(8, 3) not null,
                rating_delta numeric(8, 3) not null,
                expected_score_share numeric(8, 4) not null,
                actual_score_share numeric(8, 4) not null,
                expected_raw_points numeric(8, 3) not null,
                actual_raw_points numeric(8, 3) not null,
                games_played integer not null,
                games_won integer not null,
                match_won integer not null,
                k_factor numeric(8, 3) not null,
                confidence_before numeric(8, 3),
                confidence_after numeric(8, 3),
                calculation_version varchar(50),
                created_at datetime default current_timestamp not null,
                updated_at datetime default current_timestamp not null
            )
            """
        )
    return sessionmaker(bind=engine, autoflush=False, future=True)


@pytest.fixture()
def session(session_factory):
    db_session = session_factory()
    try:
        yield db_session
    finally:
        db_session.close()


def seed_run(session):
    session.add(
        GenerationRun(
            id=1,
            generation_name="pipeline",
            seed_value=42,
            simulation_version="test",
            status="not_started",
        )
    )
    session.add_all(
        [
            MonthlyBatch(
                id=1,
                generation_run_id=1,
                batch_month=date(2024, 1, 1),
                batch_sequence=1,
                batch_type="historical_initial",
                processing_status="pending",
            ),
            MonthlyBatch(
                id=2,
                generation_run_id=1,
                batch_month=date(2024, 2, 1),
                batch_sequence=2,
                batch_type="future_increment",
                processing_status="pending",
            ),
        ]
    )
    session.commit()


class FakePlayerGenerator:
    def generate_initial_population(self, *, generation_run_id, batch_id, player_count, session):
        rows_loaded = player_count or 2
        session.add_all(
            [
                Player(
                    id=index,
                    first_name=f"Player{index}",
                    last_name="Pipeline",
                    birth_date=date(1990, 1, 1),
                    registration_date=date(2024, 1, 1),
                    player_status="ACTIVE",
                    generation_run_id=generation_run_id,
                )
                for index in range(1, rows_loaded + 1)
            ]
        )
        session.add_all(
            [
                PlayerRegistration(
                    player_id=index,
                    batch_id=batch_id,
                    registration_month=date(2024, 1, 1),
                )
                for index in range(1, rows_loaded + 1)
            ]
        )
        session.flush()
        return PlayerGenerationResult(
            generation_run_id=generation_run_id,
            batch_id=batch_id,
            rows_loaded=rows_loaded,
            active_player_count_start=0,
            active_player_count_end=rows_loaded,
        )

    def generate_incremental_population(self, *, generation_run_id, batch_id, session):
        next_player_id = session.query(Player).count() + 1
        session.add(
            Player(
                id=next_player_id,
                first_name=f"Player{next_player_id}",
                last_name="Pipeline",
                birth_date=date(1990, 1, 1),
                registration_date=date(2024, batch_id, 1),
                player_status="ACTIVE",
                generation_run_id=generation_run_id,
            )
        )
        session.add(
            PlayerRegistration(
                player_id=next_player_id,
                batch_id=batch_id,
                registration_month=date(2024, batch_id, 1),
            )
        )
        session.flush()
        return PlayerGenerationResult(
            generation_run_id=generation_run_id,
            batch_id=batch_id,
            rows_loaded=1,
            active_player_count_start=next_player_id - 1,
            active_player_count_end=next_player_id,
        )


class FakeClubMembershipGenerator:
    def generate_for_run(self, *, generation_run_id, session):
        session.add(
            ClubMembership(
                player_id=1,
                club_id=1,
                membership_type="member",
                start_date=date(2024, 1, 1),
                is_primary=True,
                generation_run_id=generation_run_id,
            )
        )
        session.flush()
        return ClubMembershipGenerationResult(
            generation_run_id=generation_run_id,
            players_evaluated=2,
            affiliated_player_count=1,
            unaffiliated_player_count=1,
            multi_club_player_count=0,
            rows_loaded=1,
        )

    def generate_for_batch_registrations(self, *, generation_run_id, batch_id, session):
        latest_player_id = session.query(Player.id).order_by(Player.id.desc()).first()[0]
        session.add(
            ClubMembership(
                player_id=latest_player_id,
                club_id=1,
                membership_type="member",
                start_date=date(2024, batch_id, 1),
                is_primary=True,
                generation_run_id=generation_run_id,
            )
        )
        session.flush()
        return ClubMembershipGenerationResult(
            generation_run_id=generation_run_id,
            players_evaluated=1,
            affiliated_player_count=1,
            unaffiliated_player_count=0,
            multi_club_player_count=0,
            rows_loaded=1,
        )


class FakeTeamGenerator:
    def generate_for_batch(self, *, generation_run_id, batch_id, session):
        session.add(
            Team(
                team_type="open_doubles",
                team_status="active",
                formation_date=date(2024, 1, 1),
                generation_run_id=generation_run_id,
            )
        )
        session.flush()
        return TeamGenerationResult(
            generation_run_id=generation_run_id,
            batch_id=batch_id,
            batch_month=date(2024, 1, 1),
            eligible_player_count=2,
            target_team_count=1,
            rows_loaded=1,
            membership_rows_loaded=2,
            leftover_player_count=0,
        )


class FakeMatchGenerator:
    def generate_for_batch(self, *, batch_id, session):
        session.add(
            Match(
                match_date=date(2024, batch_id, 15),
                match_type="recreational",
                batch_id=batch_id,
            )
        )
        session.flush()
        return MatchGenerationResult(
            batch_id=batch_id,
            match_count=1,
            match_team_count=2,
            match_team_player_count=4,
            game_count=1,
        )


class FakeRatingGenerator:
    def generate_for_batch(self, *, batch_id, session):
        session.add(
            RatingsUpdateLog(
                generation_run_id=1,
                batch_id=batch_id,
                match_id=batch_id,
                match_number=1,
                match_date=date(2024, batch_id, 15),
                player_id=1,
                match_team_id=1,
                team_number=1,
                rating_type="match_update",
                rating_before=Decimal("1500.000"),
                rating_after=Decimal("1501.000"),
                rating_delta=Decimal("1.000"),
                expected_score_share=Decimal("0.5000"),
                actual_score_share=Decimal("0.5200"),
                expected_raw_points=Decimal("10.000"),
                actual_raw_points=Decimal("11.000"),
                games_played=1,
                games_won=1,
                match_won=1,
                k_factor=Decimal("48.000"),
            )
        )
        session.flush()
        return RatingUpdateResult(
            batch_id=batch_id,
            match_count=1,
            player_update_count=1,
            rating_history_count=1,
            log_count=1,
        )


def fake_pipeline():
    return MonthlyGenerationPipeline(
        player_generator=FakePlayerGenerator(),
        club_membership_generator=FakeClubMembershipGenerator(),
        team_generator=FakeTeamGenerator(),
        match_generator=FakeMatchGenerator(),
        rating_update_generator=FakeRatingGenerator(),
    )


def test_pipeline_runs_successive_months_and_skips_run_setup_after_first(session):
    seed_run(session)

    result = fake_pipeline().run_months(
        generation_run_id=1,
        months=2,
        player_count=2,
        session=session,
    )

    assert len(result.batch_results) == 2
    assert [batch.batch_id for batch in result.batch_results] == [1, 2]
    assert [
        step.status for step in result.batch_results[0].step_results
    ] == ["generated", "generated", "generated", "generated", "generated"]
    assert [
        step.status for step in result.batch_results[1].step_results
    ] == ["generated", "generated", "generated", "generated", "generated"]
    assert session.query(Match).count() == 2
    assert session.query(RatingsUpdateLog).count() == 2
    assert session.query(Player).count() == 3
    assert session.query(PlayerRegistration).count() == 3
    assert session.query(ClubMembership).count() == 2
    assert {
        batch.processing_status for batch in session.query(MonthlyBatch).all()
    } == {"succeeded"}


def test_pipeline_rejects_more_than_twelve_months(session):
    seed_run(session)

    with pytest.raises(ValueError, match="between 1 and 12"):
        fake_pipeline().run_months(
            generation_run_id=1,
            months=13,
            session=session,
        )


def test_pipeline_creates_missing_successive_batches(session):
    seed_run(session)

    result = fake_pipeline().run_months(
        generation_run_id=1,
        months=3,
        session=session,
    )

    assert [batch.batch_month for batch in result.batch_results] == [
        date(2024, 1, 1),
        date(2024, 2, 1),
        date(2024, 3, 1),
    ]
    created_batch = session.get(MonthlyBatch, 3)
    assert created_batch.batch_type == "future_increment"
    assert created_batch.batch_sequence == 3


def test_pipeline_skips_succeeded_batch_when_skip_existing_is_enabled(session):
    seed_run(session)
    session.get(MonthlyBatch, 1).processing_status = "succeeded"
    session.commit()

    result = fake_pipeline().run_months(
        generation_run_id=1,
        months=1,
        session=session,
    )

    assert result.batch_results[0].step_results[0].step == "batch"
    assert result.batch_results[0].step_results[0].status == "skipped"
