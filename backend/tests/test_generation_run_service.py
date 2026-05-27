"""Tests for operator-facing generation run orchestration."""
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
import re
import sys

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core import ConfigurationLifecycleService, SimulationSettings  # noqa: E402
from app.generation import run_service as run_service_module  # noqa: E402
from app.generation import (  # noqa: E402
    GenerationRunService,
    MonthlyPipelineResult,
    MultiMonthPipelineResult,
    PIPELINE_STEPS,
    PipelineProgressEvent,
    PipelineStepResult,
)
from app.models import ConfigurationProfileVersion, GenerationRun, JobStageProgress, JobStatus, MonthlyBatch  # noqa: E402


@pytest.fixture()
def session():
    engine = create_engine("sqlite:///:memory:", future=True)
    with engine.begin() as conn:
        conn.exec_driver_sql("PRAGMA foreign_keys = ON")
        conn.exec_driver_sql(
            """
            CREATE TABLE configuration_profiles (
                id integer primary key autoincrement,
                profile_name varchar(255) not null unique,
                description text,
                is_active boolean not null default true,
                created_at datetime default current_timestamp not null,
                updated_at datetime default current_timestamp not null
            )
            """
        )
        conn.exec_driver_sql(
            """
            CREATE TABLE configuration_profile_versions (
                id integer primary key autoincrement,
                profile_id bigint not null,
                version_number integer not null,
                title varchar(255) not null,
                notes text,
                config_schema_version varchar(50) not null,
                config_hash varchar(128),
                config_payload json not null,
                created_by varchar(255),
                lifecycle_status varchar(30) not null default 'valid',
                last_used_at datetime,
                deprecated_at datetime,
                created_at datetime default current_timestamp not null,
                updated_at datetime default current_timestamp not null,
                unique (profile_id, version_number),
                foreign key(profile_id) references configuration_profiles(id)
            )
            """
        )
        conn.exec_driver_sql(
            """
            CREATE TABLE generation_runs (
                id integer primary key autoincrement,
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
                id integer primary key autoincrement,
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
                unique (generation_run_id, batch_month),
                foreign key(generation_run_id) references generation_runs(id)
            )
            """
        )
        conn.exec_driver_sql(
            """
            CREATE TABLE job_status (
                id integer primary key autoincrement,
                job_type varchar(50) not null,
                job_id varchar(100) not null unique,
                status varchar(30) not null default 'pending',
                current_phase varchar(100),
                percent_complete numeric(5,2),
                current_message text,
                started_at datetime,
                completed_at datetime,
                error_message text,
                created_at datetime default current_timestamp not null,
                updated_at datetime default current_timestamp not null
            )
            """
        )
        conn.exec_driver_sql(
            """
            CREATE TABLE regions (
                id integer primary key,
                country_code varchar(2),
                region_name varchar(255)
            )
            """
        )
        conn.exec_driver_sql(
            """
            CREATE TABLE clubs (
                id integer primary key,
                club_name varchar(255) not null,
                region_id bigint not null,
                generation_run_id bigint,
                foreign key(region_id) references regions(id),
                foreign key(generation_run_id) references generation_runs(id)
            )
            """
        )
        conn.exec_driver_sql(
            """
            CREATE TABLE players (
                id integer primary key,
                first_name varchar(100) not null,
                last_name varchar(100) not null,
                birth_date date not null,
                registration_date date not null,
                generation_run_id bigint,
                foreign key(generation_run_id) references generation_runs(id)
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
                foreign key(player_id) references players(id),
                foreign key(batch_id) references monthly_batches(id)
            )
            """
        )
        conn.exec_driver_sql(
            """
            CREATE TABLE club_memberships (
                id integer primary key,
                player_id bigint not null,
                club_id bigint not null,
                generation_run_id bigint,
                start_date date not null,
                foreign key(player_id) references players(id),
                foreign key(club_id) references clubs(id),
                foreign key(generation_run_id) references generation_runs(id)
            )
            """
        )
        conn.exec_driver_sql(
            """
            CREATE TABLE teams (
                id integer primary key,
                team_type varchar(50) not null,
                formation_date date not null,
                generation_run_id bigint,
                foreign key(generation_run_id) references generation_runs(id)
            )
            """
        )
        conn.exec_driver_sql(
            """
            CREATE TABLE team_memberships (
                id integer primary key,
                team_id bigint not null,
                player_id bigint not null,
                joined_date date not null,
                player_position integer not null,
                foreign key(team_id) references teams(id),
                foreign key(player_id) references players(id)
            )
            """
        )
        conn.exec_driver_sql(
            """
            CREATE TABLE tournaments (
                id integer primary key,
                tournament_name varchar(255) not null,
                tournament_start_date date not null,
                tournament_end_date date not null,
                generation_run_id bigint,
                foreign key(generation_run_id) references generation_runs(id)
            )
            """
        )
        conn.exec_driver_sql(
            """
            CREATE TABLE matches (
                id integer primary key,
                tournament_id bigint,
                match_date date not null,
                match_type varchar(50) not null,
                batch_id bigint not null,
                foreign key(tournament_id) references tournaments(id),
                foreign key(batch_id) references monthly_batches(id)
            )
            """
        )
        conn.exec_driver_sql(
            """
            CREATE TABLE match_teams (
                id integer primary key,
                match_id bigint not null,
                team_number integer,
                team_score integer,
                foreign key(match_id) references matches(id)
            )
            """
        )
        conn.exec_driver_sql(
            """
            CREATE TABLE match_games (
                id integer primary key,
                match_id bigint not null,
                game_number integer not null,
                team_one_score integer not null,
                team_two_score integer not null,
                winning_team_number integer not null,
                target_score integer,
                win_by integer,
                foreign key(match_id) references matches(id)
            )
            """
        )
        conn.exec_driver_sql(
            """
            CREATE TABLE match_team_players (
                id integer primary key,
                match_team_id bigint not null,
                player_id bigint not null,
                foreign key(match_team_id) references match_teams(id),
                foreign key(player_id) references players(id)
            )
            """
        )
        conn.exec_driver_sql(
            """
            CREATE TABLE player_rating_history (
                id integer primary key,
                player_id bigint not null,
                batch_id bigint not null,
                rating_date date not null,
                rating_type varchar(50) not null,
                rating_value numeric(8,3) not null,
                foreign key(player_id) references players(id),
                foreign key(batch_id) references monthly_batches(id)
            )
            """
        )
        conn.exec_driver_sql(
            """
            CREATE TABLE player_assessment_history (
                id integer primary key,
                player_id bigint not null,
                batch_id bigint not null,
                assessment_date date not null,
                assessment_type varchar(100) not null,
                foreign key(player_id) references players(id),
                foreign key(batch_id) references monthly_batches(id)
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
                player_id bigint not null,
                match_team_id bigint not null,
                match_number integer not null,
                match_date date not null,
                team_number integer not null,
                rating_type varchar(50) not null,
                rating_before numeric(8,3) not null,
                rating_after numeric(8,3) not null,
                rating_delta numeric(8,3) not null,
                expected_score_share numeric(8,4) not null,
                actual_score_share numeric(8,4) not null,
                expected_raw_points numeric(8,3) not null,
                actual_raw_points numeric(8,3) not null,
                games_played integer not null,
                games_won integer not null,
                match_won integer not null,
                k_factor numeric(8,3) not null,
                foreign key(generation_run_id) references generation_runs(id),
                foreign key(batch_id) references monthly_batches(id),
                foreign key(match_id) references matches(id),
                foreign key(player_id) references players(id),
                foreign key(match_team_id) references match_teams(id)
            )
            """
        )
        conn.exec_driver_sql(
            """
            CREATE TABLE batch_runs (
                id integer primary key,
                batch_id bigint not null,
                run_status varchar(30) not null default 'pending',
                foreign key(batch_id) references monthly_batches(id)
            )
            """
        )
        conn.exec_driver_sql(
            """
            CREATE TABLE export_runs (
                id integer primary key,
                batch_id bigint,
                export_type varchar(50) not null,
                export_format varchar(50) not null,
                export_path text not null,
                foreign key(batch_id) references monthly_batches(id)
            )
            """
        )
        conn.exec_driver_sql(
            """
            CREATE TABLE validation_results (
                id integer primary key,
                batch_id bigint,
                validation_rule_id varchar(100) not null,
                validation_rule_name varchar(255) not null,
                severity varchar(30) not null,
                foreign key(batch_id) references monthly_batches(id)
            )
            """
        )
        conn.exec_driver_sql(
            """
            CREATE TABLE student_dataset_releases (
                id integer primary key,
                release_name varchar(255) not null,
                release_type varchar(50) not null,
                release_month date,
                generation_run_id bigint not null,
                data_quality_level varchar(50),
                output_path text not null,
                status varchar(30) not null default 'pending',
                created_at datetime default current_timestamp not null,
                completed_at datetime,
                error_message text,
                foreign key(generation_run_id) references generation_runs(id)
            )
            """
        )
        conn.exec_driver_sql(
            """
            CREATE TABLE student_dataset_release_files (
                id integer primary key,
                release_id bigint not null,
                table_name varchar(255) not null,
                file_path text not null,
                created_at datetime default current_timestamp not null,
                foreign key(release_id) references student_dataset_releases(id)
            )
            """
        )
        conn.exec_driver_sql(
            """
            CREATE TABLE job_stage_progress (
                id integer primary key autoincrement,
                job_status_id bigint not null,
                generation_run_id bigint,
                batch_id bigint,
                stage_name varchar(100) not null,
                stage_sequence integer,
                status varchar(30) not null default 'pending',
                progress_current bigint not null default 0,
                progress_total bigint,
                progress_unit varchar(100),
                progress_percent numeric(5,2),
                last_heartbeat_at datetime,
                progress_message text,
                started_at datetime,
                completed_at datetime,
                error_message text,
                metadata_json text,
                created_at datetime default current_timestamp not null,
                updated_at datetime default current_timestamp not null,
                unique(job_status_id, batch_id, stage_name),
                foreign key(job_status_id) references job_status(id),
                foreign key(generation_run_id) references generation_runs(id),
                foreign key(batch_id) references monthly_batches(id)
            )
            """
        )
        conn.exec_driver_sql("CREATE TABLE first_names (id integer primary key)")
        conn.exec_driver_sql("CREATE TABLE last_names (id integer primary key)")
        conn.exec_driver_sql(
            """
            CREATE TABLE uploaded_files (
                id integer primary key,
                validation_status varchar(30)
            )
            """
        )
    session_factory = sessionmaker(bind=engine, autoflush=False, future=True)
    db_session = session_factory()
    try:
        yield db_session
    finally:
        db_session.close()


class FakePipeline:
    def run_months(
        self,
        *,
        generation_run_id,
        months,
        start_batch_id=None,
        player_count=None,
        skip_existing=True,
        progress_listener=None,
        session=None,
    ):
        del start_batch_id, player_count, skip_existing
        batches = list(
            session.query(MonthlyBatch)
            .filter(MonthlyBatch.generation_run_id == generation_run_id)
            .order_by(MonthlyBatch.batch_sequence)
        )
        batch_results = []
        for batch in batches[:months]:
            batch.started_at = datetime.now(UTC).replace(tzinfo=None)
            batch.processing_status = "running"
            step_results = []
            for step in PIPELINE_STEPS:
                if progress_listener is not None:
                    progress_listener(
                        PipelineProgressEvent(
                            generation_run_id=generation_run_id,
                            batch_id=batch.id,
                            batch_month=batch.batch_month,
                            step=step,
                            status="running",
                            details={},
                        )
                    )
                    progress_listener(
                        PipelineProgressEvent(
                            generation_run_id=generation_run_id,
                            batch_id=batch.id,
                            batch_month=batch.batch_month,
                            step=step,
                            status="succeeded",
                            details={"rows_loaded": 1},
                        )
                    )
                step_results.append(
                    PipelineStepResult(
                        step=step,
                        status="generated",
                        details={"rows_loaded": 1},
                    )
                )
            batch.processing_status = "succeeded"
            batch.completed_at = datetime.now(UTC).replace(tzinfo=None)
            batch_results.append(
                MonthlyPipelineResult(
                    generation_run_id=generation_run_id,
                    batch_id=batch.id,
                    batch_month=batch.batch_month,
                    step_results=tuple(step_results),
                )
            )
        session.flush()
        return MultiMonthPipelineResult(
            generation_run_id=generation_run_id,
            months_requested=months,
            batch_results=tuple(batch_results),
        )


class FailingPipeline:
    def run_months(
        self,
        *,
        generation_run_id,
        months,
        start_batch_id=None,
        player_count=None,
        skip_existing=True,
        progress_listener=None,
        session=None,
    ):
        del (
            generation_run_id,
            months,
            start_batch_id,
            player_count,
            skip_existing,
            progress_listener,
            session,
        )
        raise RuntimeError("planned pipeline failure")


class RecordingPipeline:
    def __init__(self) -> None:
        self.last_skip_existing = None

    def run_months(
        self,
        *,
        generation_run_id,
        months,
        start_batch_id=None,
        player_count=None,
        skip_existing=True,
        progress_listener=None,
        session=None,
    ):
        del generation_run_id, months, start_batch_id, player_count, progress_listener, session
        self.last_skip_existing = skip_existing
        return MultiMonthPipelineResult(
            generation_run_id=1,
            months_requested=1,
            batch_results=(),
        )


def _seed_valid_config(session, *, seed=42, historical_months=2):
    lifecycle = ConfigurationLifecycleService()
    payload = {
        "runtime": {},
        "simulation": {
            "simulation_name": "service-run",
            "simulation_version": "service-v1",
            "master_seed": seed,
            "historical_batch_count": historical_months,
            "first_batch_month": "2026-01-01",
            "target_total_players": 1000,
        },
    }
    saved = lifecycle.save_new_version(
        session,
        title="Service config",
        notes=None,
        payload=payload,
    )
    session.commit()
    return saved.version


def _seed_old_generated_data(session):
    statements = [
        """
        INSERT INTO generation_runs (id, generation_name, seed_value, status, created_at, updated_at)
        VALUES (1, 'old-run', 1, 'succeeded', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """,
        """
        INSERT INTO monthly_batches (
            id, generation_run_id, batch_month, batch_sequence, batch_type, processing_status,
            created_at, updated_at
        )
        VALUES (1, 1, '2025-01-01', 1, 'historical_initial', 'succeeded', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """,
        "INSERT INTO regions (id, country_code, region_name) VALUES (1, 'US', 'Seed Region')",
        "INSERT INTO clubs (id, club_name, region_id, generation_run_id) VALUES (1, 'Seed Club', 1, 1)",
        "INSERT INTO players (id, first_name, last_name, birth_date, registration_date, generation_run_id) VALUES (1, 'Old', 'Player', '1990-01-01', '2025-01-01', 1)",
        "INSERT INTO player_registrations (id, player_id, batch_id, registration_month) VALUES (1, 1, 1, '2025-01-01')",
        "INSERT INTO club_memberships (id, player_id, club_id, generation_run_id, start_date) VALUES (1, 1, 1, 1, '2025-01-01')",
        "INSERT INTO teams (id, team_type, formation_date, generation_run_id) VALUES (1, 'open_doubles', '2025-01-01', 1)",
        "INSERT INTO team_memberships (id, team_id, player_id, joined_date, player_position) VALUES (1, 1, 1, '2025-01-01', 1)",
        "INSERT INTO tournaments (id, tournament_name, tournament_start_date, tournament_end_date, generation_run_id) VALUES (1, 'Old Tournament', '2025-01-01', '2025-01-02', 1)",
        "INSERT INTO matches (id, tournament_id, match_date, match_type, batch_id) VALUES (1, 1, '2025-01-02', 'recreational', 1)",
        "INSERT INTO match_teams (id, match_id, team_number, team_score) VALUES (1, 1, 1, 11)",
        "INSERT INTO match_games (id, match_id, game_number, team_one_score, team_two_score, winning_team_number, target_score, win_by) VALUES (1, 1, 1, 11, 9, 1, 11, 2)",
        "INSERT INTO match_team_players (id, match_team_id, player_id) VALUES (1, 1, 1)",
        "INSERT INTO player_rating_history (id, player_id, batch_id, rating_date, rating_type, rating_value) VALUES (1, 1, 1, '2025-01-02', 'match_update', 1500.0)",
        "INSERT INTO player_assessment_history (id, player_id, batch_id, assessment_date, assessment_type) VALUES (1, 1, 1, '2025-01-02', 'confidence')",
        "INSERT INTO ratings_update_log (id, generation_run_id, batch_id, match_id, player_id, match_team_id, match_number, match_date, team_number, rating_type, rating_before, rating_after, rating_delta, expected_score_share, actual_score_share, expected_raw_points, actual_raw_points, games_played, games_won, match_won, k_factor) VALUES (1, 1, 1, 1, 1, 1, 1, '2025-01-02', 1, 'match_update', 1500, 1501, 1, 0.5, 0.5, 10, 11, 1, 1, 1, 48)",
        "INSERT INTO batch_runs (id, batch_id, run_status) VALUES (1, 1, 'succeeded')",
        "INSERT INTO export_runs (id, batch_id, export_type, export_format, export_path) VALUES (1, 1, 'student', 'parquet', '/tmp/old')",
        "INSERT INTO validation_results (id, batch_id, validation_rule_id, validation_rule_name, severity) VALUES (1, 1, 'rule', 'rule', 'error')",
        "INSERT INTO student_dataset_releases (id, release_name, release_type, generation_run_id, output_path, status, created_at) VALUES (1, 'old release', 'historical_baseline', 1, '/tmp/release', 'succeeded', CURRENT_TIMESTAMP)",
        "INSERT INTO student_dataset_release_files (id, release_id, table_name, file_path, created_at) VALUES (1, 1, 'players', '/tmp/release/players.parquet', CURRENT_TIMESTAMP)",
        "INSERT INTO job_status (id, job_type, job_id, status, created_at, updated_at) VALUES (1, 'generation_run', 'old-job', 'succeeded', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
        "INSERT INTO job_stage_progress (id, job_status_id, generation_run_id, batch_id, stage_name, status, progress_current, progress_total, created_at, updated_at) VALUES (1, 1, 1, 1, 'players', 'succeeded', 1, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
    ]
    for statement in statements:
        session.execute(text(statement))
    session.commit()


def test_launch_generation_run_resets_generated_data_and_tracks_progress(session):
    _seed_valid_config(session, seed=77, historical_months=2)
    _seed_old_generated_data(session)

    service = GenerationRunService(
        settings=SimulationSettings(config_payload=None),
        pipeline=FakePipeline(),
    )

    result = service.launch_generation_run("new run", session=session)
    session.commit()

    assert result.configuration_version.last_used_at is not None
    assert result.generation_run.status == "succeeded"
    assert result.generation_run.seed_value == 77
    assert result.job_status.status == "succeeded"
    assert result.job_status.percent_complete == Decimal("100.00")
    assert len(result.monthly_batches) == 2
    assert {batch.processing_status for batch in result.monthly_batches} == {"succeeded"}

    assert session.query(GenerationRun).count() == 2
    assert session.query(JobStatus).count() == 2
    assert session.query(MonthlyBatch).count() == 3
    assert session.query(JobStageProgress).count() == (len(PIPELINE_STEPS) * 2) + 2
    assert session.execute(text("SELECT COUNT(*) FROM players")).scalar_one() == 0
    assert session.execute(text("SELECT COUNT(*) FROM matches")).scalar_one() == 0
    assert session.execute(text("SELECT COUNT(*) FROM validation_results")).scalar_one() == 1
    assert session.execute(text("SELECT COUNT(*) FROM export_runs")).scalar_one() == 1
    assert session.execute(text("SELECT COUNT(*) FROM student_dataset_releases")).scalar_one() == 1


def test_launch_generation_run_rejects_multiple_valid_configs(session):
    first_version = _seed_valid_config(session, seed=1, historical_months=1)
    session.add(
        ConfigurationProfileVersion(
            profile_id=first_version.profile_id,
            version_number=99,
            title="Forced duplicate valid version",
            notes=None,
            config_schema_version=first_version.config_schema_version,
            config_hash="forced-duplicate",
            config_payload=first_version.config_payload,
            lifecycle_status="valid",
        )
    )
    session.commit()

    service = GenerationRunService(
        settings=SimulationSettings(config_payload=None),
        pipeline=FakePipeline(),
    )

    with pytest.raises(ValueError, match="exactly one valid configuration"):
        service.launch_generation_run("bad run", session=session)


def test_launch_generation_run_rejects_active_generation_run(session):
    _seed_valid_config(session, seed=1, historical_months=1)
    session.add(
        GenerationRun(
            generation_name="already running",
            seed_value=1,
            simulation_version="service-v1",
            status="running",
        )
    )
    session.commit()

    service = GenerationRunService(
        settings=SimulationSettings(config_payload=None),
        pipeline=FakePipeline(),
    )

    with pytest.raises(ValueError, match="already running"):
        service.launch_generation_run("blocked run", session=session)


def test_launch_generation_run_ignores_stale_running_generation_job(session):
    _seed_valid_config(session, seed=1, historical_months=1)
    session.add(
        GenerationRun(
            id=90,
            generation_name="stale running",
            seed_value=1,
            simulation_version="service-v1",
            status="running",
            started_at=datetime(2026, 5, 20, 9, 0, 0),
        )
    )
    session.flush()
    session.execute(
        text(
            """
            INSERT INTO job_status (
                id, job_type, job_id, status, current_phase, percent_complete,
                current_message, started_at, created_at, updated_at
            ) VALUES (
                90, 'generation_run', 'generation-run-stale', 'running',
                'destructive_reset', 0.00, 'Stale reset.',
                '2026-05-20 09:00:00', '2026-05-20 09:00:00',
                '2026-05-20 09:00:00'
            )
            """
        )
    )
    session.execute(
        text(
                """
                INSERT INTO job_stage_progress (
                    id, job_status_id, generation_run_id, batch_id, stage_name,
                    stage_sequence, status, progress_current, progress_total,
                    progress_unit, progress_percent, last_heartbeat_at,
                progress_message, started_at, created_at, updated_at
            ) VALUES (
                90, 90, 90, NULL, 'destructive_reset', 0, 'running',
                0, 1, 'stage', 0.00, '2026-05-20 09:01:00',
                'Stale reset.', '2026-05-20 09:00:00',
                '2026-05-20 09:00:00', '2026-05-20 09:00:00'
            )
            """
        )
    )
    session.commit()

    service = GenerationRunService(
        settings=SimulationSettings(config_payload=None),
        pipeline=FakePipeline(),
    )

    result = service.launch_generation_run("fresh run", session=session)

    assert result.generation_run.id != 90
    assert result.generation_run.status == "succeeded"


def test_launch_generation_run_respects_quiet_match_stage_as_active(session):
    _seed_valid_config(session, seed=1, historical_months=1)
    now = datetime.now(UTC).replace(tzinfo=None)
    started_at = now.replace(second=0, microsecond=0) - timedelta(hours=1)
    quiet_heartbeat_at = now.replace(second=0, microsecond=0) - timedelta(minutes=20)
    session.add(
        GenerationRun(
            id=91,
            generation_name="quiet running",
            seed_value=1,
            simulation_version="service-v1",
            status="running",
            started_at=started_at,
        )
    )
    session.flush()
    session.execute(
        text(
            """
            INSERT INTO job_status (
                id, job_type, job_id, status, current_phase, percent_complete,
                current_message, started_at, created_at, updated_at
            ) VALUES (
                91, 'generation_run', 'generation-run-quiet', 'running',
                'matches', 45.00, 'Quiet match generation.',
                :started_at, :started_at, :started_at
            )
            """
        ),
        {"started_at": started_at},
    )
    session.execute(
        text(
            """
            INSERT INTO job_stage_progress (
                id, job_status_id, generation_run_id, batch_id, stage_name,
                stage_sequence, status, progress_current, progress_total,
                progress_unit, progress_percent, last_heartbeat_at,
                progress_message, metadata_json, started_at, created_at, updated_at
                ) VALUES (
                91, 91, 91, NULL, 'matches', 4, 'running',
                5000, 12000, 'match', 41.67, :heartbeat_at,
                'Quiet match generation.',
                '{"heartbeat_quiet_after_seconds": 1200, "heartbeat_likely_stalled_after_seconds": 3600}',
                :started_at, :started_at, :heartbeat_at
            )
            """
        ),
        {
            "started_at": started_at,
            "heartbeat_at": quiet_heartbeat_at,
        },
    )
    session.commit()

    service = GenerationRunService(
        settings=SimulationSettings(config_payload=None),
        pipeline=FakePipeline(),
    )

    with pytest.raises(ValueError, match="already running"):
        service.launch_generation_run("blocked by quiet run", session=session)


def test_background_generation_run_persists_failed_status(session, monkeypatch):
    _seed_valid_config(session, historical_months=2)
    local_session_factory = sessionmaker(
        bind=session.bind,
        autoflush=False,
        expire_on_commit=False,
        future=True,
    )
    monkeypatch.setattr(run_service_module, "SessionLocal", local_session_factory)

    service = GenerationRunService(
        settings=SimulationSettings(config_payload=None),
        pipeline=FailingPipeline(),
    )
    registration = service.register_generation_run("Background failure", session=session)
    session.commit()

    service.execute_registered_generation_run_in_background(
        config_version_id=registration.configuration_version.id,
        generation_run_id=registration.generation_run.id,
        job_status_id=registration.job_status.id,
    )

    session.expire_all()
    job = session.get(JobStatus, registration.job_status.id)
    run = session.get(GenerationRun, registration.generation_run.id)
    assert job is not None
    assert run is not None
    assert job.status == "failed"
    assert job.current_phase == "failed"
    assert "planned pipeline failure" in job.current_message
    assert run.status == "failed"

    stage_rows = session.query(JobStageProgress).filter_by(job_status_id=job.id).all()
    assert stage_rows
    assert any(row.status == "failed" for row in stage_rows)


def test_launch_generation_run_uses_skip_existing_for_successive_months(session):
    _seed_valid_config(session, historical_months=2)
    pipeline = RecordingPipeline()
    service = GenerationRunService(
        settings=SimulationSettings(config_payload=None),
        pipeline=pipeline,
    )

    service.launch_generation_run("skip existing run", session=session)

    assert pipeline.last_skip_existing is True


def test_launch_generation_run_logs_job_and_stage_lifecycle(session, caplog):
    _seed_valid_config(session, historical_months=1)
    service = GenerationRunService(
        settings=SimulationSettings(config_payload=None),
        pipeline=FakePipeline(),
    )

    with caplog.at_level("INFO", logger="uvicorn.error"):
        service.launch_generation_run("logged run", session=session)

    messages = [record.getMessage() for record in caplog.records]
    assert any(
        "Generation job started" in message and "phase=destructive_reset" in message
        for message in messages
    )
    assert any(
        "Generation stage completed" in message
        and "stage_name=destructive_reset" in message
        for message in messages
    )
    assert any(
        "Generation stage completed" in message
        and "stage_name=players" in message
        and "batch_month=2026-01-01" in message
        for message in messages
    )
    assert any(
        "Generation job completed" in message and "phase=completed" in message
        for message in messages
    )
    assert all(
        re.search(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} UTC", message)
        for message in messages
        if "Generation job" in message or "Generation stage completed" in message
    )
