"""Tests for tournament service persistence workflows."""
from datetime import date
from decimal import Decimal
from pathlib import Path
import sys

import pytest
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import sessionmaker


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.models import (  # noqa: E402
    JobStatus,
    TournamentDivisionResult,
    TournamentGroupResult,
    TournamentOfficialGame,
    TournamentOfficialMatch,
    TournamentSimulationRun,
    TournamentSubmission,
    TournamentTeamResult,
)
from app.tournament_simulation import (  # noqa: E402
    PortfolioSlot,
    StudentGroup,
    TeamSubmission,
    TournamentService,
)
from app.tournament_simulation.monte_carlo import (  # noqa: E402
    MonteCarloGroupAggregate,
    MonteCarloResult,
    MonteCarloTeamAggregate,
)
import app.tournament_simulation.service as service_module  # noqa: E402
from test_tournament_team_loader import _schema_ddls, _seed_valid_team  # noqa: E402


@pytest.fixture()
def session_factory():
    engine = create_engine("sqlite:///:memory:", future=True)
    with engine.begin() as conn:
        for ddl in (*_schema_ddls(), *_service_schema_ddls()):
            conn.exec_driver_sql(ddl)
    return sessionmaker(bind=engine, autoflush=False, future=True)


@pytest.fixture()
def session(session_factory):
    db_session = session_factory()
    try:
        yield db_session
    finally:
        db_session.close()


def test_service_creates_event_and_validates_persisted_submissions(session):
    _seed_two_valid_teams(session)
    service = TournamentService()
    creation = _create_event(service, session)

    validation = service.validate_event(event_id=creation.event.id, session=session)

    assert validation.is_valid
    assert creation.event.id is not None
    assert session.scalar(select(func.count()).select_from(TournamentSubmission)) == 2
    statuses = session.execute(select(TournamentSubmission.validation_status)).all()
    assert {status for (status,) in statuses} == {"valid"}


def test_monte_carlo_run_persists_aggregate_results_and_summary(session):
    _seed_two_valid_teams(session)
    service = TournamentService()
    creation = _create_event(service, session)

    start = service.run_monte_carlo(
        event_id=creation.event.id,
        iterations=5,
        seed=22,
        session=session,
    )
    summary = service.latest_summary(event_id=creation.event.id, session=session)

    assert start.simulation_run.status == "succeeded"
    assert start.job_status.status == "succeeded"
    assert session.scalar(select(func.count()).select_from(TournamentTeamResult)) == 2
    assert session.scalar(select(func.count()).select_from(TournamentGroupResult)) == 2
    assert session.scalar(select(func.count()).select_from(TournamentDivisionResult)) == 1
    assert summary["simulation_run_id"] == start.simulation_run.id
    assert summary["run_type"] == "monte_carlo"
    assert summary["division_results"][0]["slot_country_code"] == "ALL"


def test_official_run_persists_match_and_game_results(session):
    _seed_two_valid_teams(session)
    service = TournamentService()
    creation = _create_event(service, session)

    start = service.run_official(
        event_id=creation.event.id,
        seed=22,
        session=session,
    )
    official_match = session.execute(select(TournamentOfficialMatch)).scalar_one()
    detail = service.official_match_detail(
        official_match_id=official_match.id,
        session=session,
    )

    assert start.simulation_run.status == "succeeded"
    assert official_match.simulation_run_id == start.simulation_run.id
    assert official_match.slot_country_code == "ALL"
    assert session.scalar(select(func.count()).select_from(TournamentOfficialGame)) == 3
    assert detail["match_number"] == 1
    assert detail["slot_country_code"] == "ALL"
    assert len(detail["games"]) == 3


def test_register_run_creates_pending_job_for_background_execution(session):
    _seed_two_valid_teams(session)
    service = TournamentService()
    creation = _create_event(service, session)

    start = service.register_monte_carlo_run(
        event_id=creation.event.id,
        iterations=10,
        seed=7,
        session=session,
    )

    assert start.simulation_run.status == "pending"
    assert start.job_status.status == "pending"
    assert session.get(TournamentSimulationRun, start.simulation_run.id) is not None
    assert session.get(JobStatus, start.job_status.id) is not None


def test_execute_run_commits_intermediate_monte_carlo_progress(session, session_factory, monkeypatch):
    _seed_two_valid_teams(session)
    service = TournamentService()
    creation = _create_event(service, session)
    start = service.register_monte_carlo_run(
        event_id=creation.event.id,
        iterations=10,
        seed=7,
        session=session,
    )
    session.commit()

    observed_progress: list[tuple[str, str | None]] = []

    def fake_run_monte_carlo(
        divisions,
        *,
        simulation_config,
        scoring_config,
        iterations,
        progress_callback=None,
    ):
        assert iterations == 10
        assert progress_callback is not None
        progress_callback(5, 10)
        probe_session = session_factory()
        try:
            job = probe_session.get(JobStatus, start.job_status.id)
            observed_progress.append((str(job.percent_complete), job.current_message))
        finally:
            probe_session.close()
        return MonteCarloResult(
            iterations=10,
            team_results=(
                MonteCarloTeamAggregate(
                    team_id=10,
                    championship_probability=Decimal("0.500"),
                    top_three_probability=Decimal("1.000"),
                    average_finish=Decimal("1.500"),
                    win_percentage=Decimal("0.600"),
                    upset_count=0,
                ),
                MonteCarloTeamAggregate(
                    team_id=20,
                    championship_probability=Decimal("0.500"),
                    top_three_probability=Decimal("1.000"),
                    average_finish=Decimal("1.500"),
                    win_percentage=Decimal("0.400"),
                    upset_count=0,
                ),
            ),
            group_results=(
                MonteCarloGroupAggregate(
                    group_id=1,
                    expected_score=Decimal("10.000"),
                    average_rank=Decimal("1.000"),
                    rank_distribution={1: 10},
                ),
                MonteCarloGroupAggregate(
                    group_id=2,
                    expected_score=Decimal("8.000"),
                    average_rank=Decimal("2.000"),
                    rank_distribution={2: 10},
                ),
            ),
        )

    monkeypatch.setattr(service_module, "run_monte_carlo", fake_run_monte_carlo)

    service._execute_run(simulation_run_id=start.simulation_run.id, session=session)

    assert observed_progress == [
        ("52.50", "Monte Carlo iteration 5/10 completed.")
    ]


def _seed_two_valid_teams(session) -> None:
    _seed_valid_team(
        session,
        team_id=10,
        player_ids=(101, 102),
        ratings=(Decimal("1600"), Decimal("1700")),
    )
    _seed_valid_team(
        session,
        team_id=20,
        player_ids=(201, 202),
        ratings=(Decimal("1500"), Decimal("1550")),
        country_code="CA",
    )


def _create_event(service: TournamentService, session):
    return service.create_event(
        event_name="Class Tournament",
        source_batch_id=2,
        tournament_date=date(2025, 3, 15),
        student_groups=(
            StudentGroup(id=1, name="Group 1"),
            StudentGroup(id=2, name="Group 2"),
        ),
        submissions=(
            TeamSubmission(
                group_id=1,
                slot=PortfolioSlot(country_code="US", division="mens_doubles"),
                team_id=10,
            ),
            TeamSubmission(
                group_id=2,
                slot=PortfolioSlot(country_code="CA", division="mens_doubles"),
                team_id=20,
            ),
        ),
        session=session,
    )


def _service_schema_ddls() -> tuple[str, ...]:
    return (
        """
        CREATE TABLE job_status (
            id integer primary key autoincrement,
            job_type varchar(50) not null,
            job_id varchar(100) not null unique,
            status varchar(30) not null default 'pending',
            current_phase varchar(100),
            percent_complete numeric(5, 2),
            current_message text,
            started_at datetime,
            completed_at datetime,
            error_message text,
            created_at datetime default current_timestamp not null,
            updated_at datetime default current_timestamp not null
        )
        """,
        """
        CREATE TABLE tournament_events (
            id integer primary key autoincrement,
            event_name varchar(255) not null,
            generation_run_id bigint not null,
            source_batch_id bigint not null,
            tournament_date date not null,
            config_snapshot json not null,
            status varchar(30) not null default 'draft',
            created_at datetime default current_timestamp not null,
            updated_at datetime default current_timestamp not null
        )
        """,
        """
        CREATE TABLE tournament_student_groups (
            id integer primary key autoincrement,
            event_id bigint not null,
            group_name varchar(255) not null,
            external_group_key varchar(255),
            created_at datetime default current_timestamp not null,
            updated_at datetime default current_timestamp not null
        )
        """,
        """
        CREATE TABLE tournament_submissions (
            id integer primary key autoincrement,
            event_id bigint not null,
            student_group_id bigint not null,
            slot_country_code varchar(2) not null,
            slot_division varchar(50) not null,
            team_id bigint not null,
            validation_status varchar(30) not null default 'pending',
            validation_message text,
            created_at datetime default current_timestamp not null,
            updated_at datetime default current_timestamp not null
        )
        """,
        """
        CREATE TABLE tournament_simulation_runs (
            id integer primary key autoincrement,
            event_id bigint not null,
            run_type varchar(30) not null,
            status varchar(30) not null default 'pending',
            seed bigint,
            iteration_count integer,
            config_snapshot json not null,
            job_status_id bigint,
            started_at datetime,
            completed_at datetime,
            error_message text,
            created_at datetime default current_timestamp not null,
            updated_at datetime default current_timestamp not null
        )
        """,
        """
        CREATE TABLE tournament_team_results (
            id integer primary key autoincrement,
            simulation_run_id bigint not null,
            slot_country_code varchar(2) not null,
            slot_division varchar(50) not null,
            team_id bigint not null,
            championship_probability numeric(8, 5),
            top_three_probability numeric(8, 5),
            average_finish numeric(8, 3),
            win_percentage numeric(8, 5),
            upset_count integer,
            final_rank integer,
            match_wins integer,
            match_losses integer,
            games_won integer,
            games_lost integer,
            point_differential integer,
            created_at datetime default current_timestamp not null,
            updated_at datetime default current_timestamp not null
        )
        """,
        """
        CREATE TABLE tournament_group_results (
            id integer primary key autoincrement,
            simulation_run_id bigint not null,
            student_group_id bigint not null,
            expected_score numeric(10, 3),
            official_score numeric(10, 3),
            average_rank numeric(8, 3),
            final_rank integer,
            champion_count integer,
            runner_up_count integer,
            top_four_count integer,
            match_wins integer,
            rank_distribution json,
            created_at datetime default current_timestamp not null,
            updated_at datetime default current_timestamp not null
        )
        """,
        """
        CREATE TABLE tournament_division_results (
            id integer primary key autoincrement,
            simulation_run_id bigint not null,
            slot_country_code varchar(2) not null,
            slot_division varchar(50) not null,
            iteration_count integer,
            unique_team_count integer not null,
            match_count integer not null,
            champion_team_id bigint,
            summary_payload json,
            created_at datetime default current_timestamp not null,
            updated_at datetime default current_timestamp not null
        )
        """,
        """
        CREATE TABLE tournament_official_matches (
            id integer primary key autoincrement,
            simulation_run_id bigint not null,
            slot_country_code varchar(2) not null,
            slot_division varchar(50) not null,
            match_number integer not null,
            team_one_id bigint not null,
            team_two_id bigint not null,
            winning_team_id bigint not null,
            team_one_games_won integer not null,
            team_two_games_won integer not null,
            team_one_points integer not null,
            team_two_points integer not null,
            visible_team_one_win_probability numeric(8, 4),
            final_team_one_win_probability numeric(8, 4),
            created_at datetime default current_timestamp not null,
            updated_at datetime default current_timestamp not null
        )
        """,
        """
        CREATE TABLE tournament_official_games (
            id integer primary key autoincrement,
            official_match_id bigint not null,
            game_number integer not null,
            team_one_score integer not null,
            team_two_score integer not null,
            winning_team_number integer not null,
            target_score integer not null default 11,
            win_by integer not null default 2,
            expected_team_one_score_share numeric(8, 4),
            actual_team_one_score_share numeric(8, 4),
            created_at datetime default current_timestamp not null,
            updated_at datetime default current_timestamp not null
        )
        """,
    )
