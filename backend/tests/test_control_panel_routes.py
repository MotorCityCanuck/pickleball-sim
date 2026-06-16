"""Route tests for the read-only control panel shell."""
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
import asyncio
import json
import re
import sys

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.requests import Request


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core import ConfigurationLifecycleService  # noqa: E402
from app.exports.student_dataset.service import StudentDatasetExportService  # noqa: E402
from app.main import create_app  # noqa: E402
from app.web.routes import get_configuration_lifecycle  # noqa: E402
import app.web.routes as routes_module  # noqa: E402
from app.web.control_panel_queries import ControlPanelQueries  # noqa: E402


@pytest.fixture()
def session_factory():
    engine = create_engine(
        "sqlite://",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.begin() as conn:
        conn.exec_driver_sql("PRAGMA foreign_keys = ON")
        conn.exec_driver_sql(
            """
            CREATE TABLE raw_seed_load_runs (
                id integer primary key autoincrement,
                job_status_id bigint,
                dataset_type varchar(80) not null,
                source_path varchar(1000) not null,
                source_file_count integer not null default 0,
                source_checksum varchar(128),
                started_at datetime,
                completed_at datetime,
                status varchar(30) not null default 'pending',
                rows_read integer not null default 0,
                rows_loaded integer not null default 0,
                rows_rejected integer not null default 0,
                error_message text,
                created_at datetime default current_timestamp not null,
                updated_at datetime default current_timestamp not null
            )
            """
        )
        conn.exec_driver_sql(
            """
            CREATE TABLE regions (
                id integer primary key autoincrement,
                country_code varchar(10) not null,
                region_type varchar(20),
                region_name varchar(255) not null,
                state_province_code varchar(10),
                population bigint,
                selection_probability numeric(12,8),
                competitiveness_multiplier numeric(8,4) default 1.0,
                latitude numeric(10,6),
                longitude numeric(10,6),
                created_at datetime default current_timestamp not null,
                updated_at datetime default current_timestamp not null
            )
            """
        )
        conn.exec_driver_sql(
            """
            CREATE TABLE clubs (
                id integer primary key,
                club_name varchar(255) not null,
                region_id bigint not null,
                club_type varchar(50),
                competitiveness_level varchar(50),
                member_capacity integer,
                founding_date date,
                indoor_court_count integer default 0,
                outdoor_court_count integer default 0,
                generation_run_id bigint,
                created_at datetime default current_timestamp not null,
                updated_at datetime default current_timestamp not null,
                foreign key(region_id) references regions(id),
                foreign key(generation_run_id) references generation_runs(id)
            )
            """
        )
        conn.exec_driver_sql(
            """
            CREATE TABLE first_names (
                id integer primary key,
                country_code varchar(2) not null,
                state_province_code varchar(2) not null,
                birth_year integer not null,
                gender varchar(1) not null,
                first_name varchar(100) not null,
                frequency_count integer not null,
                normalized_probability numeric(12,8),
                source_dataset varchar(255),
                created_at datetime default current_timestamp not null,
                updated_at datetime default current_timestamp not null
            )
            """
        )
        conn.exec_driver_sql(
            """
            CREATE TABLE last_names (
                id integer primary key,
                country_code varchar(2) not null,
                state_province_code varchar(2) not null,
                last_name varchar(100) not null,
                frequency_count integer not null,
                bias_multiplier numeric(10,4),
                adjusted_frequency_count numeric(18,4),
                normalized_probability numeric(12,8),
                source_dataset varchar(255),
                created_at datetime default current_timestamp not null,
                updated_at datetime default current_timestamp not null
            )
            """
        )
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
        conn.exec_driver_sql(
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
            """
        )
        conn.exec_driver_sql(
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
            """
        )
        conn.exec_driver_sql(
            """
            CREATE TABLE tournament_student_groups (
                id integer primary key autoincrement,
                event_id bigint not null,
                group_name varchar(255) not null,
                external_group_key varchar(255),
                created_at datetime default current_timestamp not null,
                updated_at datetime default current_timestamp not null
            )
            """
        )
        conn.exec_driver_sql(
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
            """
        )
        conn.exec_driver_sql(
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
            """
        )
        conn.exec_driver_sql(
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
            """
        )
        conn.exec_driver_sql(
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
            """
        )
        conn.exec_driver_sql(
            """
            CREATE TABLE student_dataset_releases (
                id integer primary key autoincrement,
                release_name varchar(255) not null,
                release_type varchar(50) not null,
                release_month date,
                generation_run_id bigint not null,
                data_quality_level varchar(50),
                output_path text not null,
                status varchar(30) not null default 'pending',
                created_at datetime default current_timestamp not null,
                updated_at datetime default current_timestamp not null,
                completed_at datetime,
                error_message text,
                foreign key(generation_run_id) references generation_runs(id)
            )
            """
        )
        conn.exec_driver_sql(
            """
            CREATE TABLE student_dataset_release_files (
                id integer primary key autoincrement,
                release_id bigint not null,
                table_name varchar(255) not null,
                file_path text not null,
                row_count bigint,
                schema_hash varchar(128),
                checksum varchar(128),
                created_at datetime default current_timestamp not null,
                foreign key(release_id) references student_dataset_releases(id)
            )
            """
        )
    yield sessionmaker(bind=engine, autoflush=False, future=True)


def _seed_snapshot_state(session_factory):
    session = session_factory()
    try:
        lifecycle = ConfigurationLifecycleService()
        lifecycle.save_new_version(
            session,
            title="Read only config",
            notes=None,
            payload={
                "runtime": {},
                "simulation": {
                    "simulation_name": "Route Test",
                    "simulation_version": "v1",
                    "master_seed": 11,
                    "historical_batch_count": 2,
                    "first_batch_month": "2026-01-01",
                },
                "player_generation": {
                    "player_count": 1000,
                },
            },
        )
        _seed_ready_reference_data(session)
        session.execute(
            text(
                """
                INSERT INTO generation_runs (
                    id, generation_name, seed_value, simulation_version, status, started_at, created_at, updated_at
                ) VALUES (
                    1, 'UI run', 11, 'v1', 'running', '2026-05-20 09:00:00', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                )
                """
            )
        )
        session.execute(
            text(
                """
                INSERT INTO monthly_batches (
                    id, generation_run_id, batch_month, batch_sequence, batch_type, processing_status, created_at, updated_at
                ) VALUES
                    (1, 1, '2026-01-01', 1, 'historical_initial', 'succeeded', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
                    (2, 1, '2026-02-01', 2, 'historical_initial', 'running', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """
            )
        )
        session.execute(
            text(
                """
                INSERT INTO job_status (
                    id, job_type, job_id, status, current_phase, percent_complete, current_message, created_at, updated_at
                ) VALUES (
                    1, 'generation_run', 'generation-run-1-test', 'running', 'matches', 40.00, 'matches running',
                    CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                )
                """
            )
        )
        session.execute(
            text(
                """
                INSERT INTO job_stage_progress (
                    id, job_status_id, generation_run_id, batch_id, stage_name, stage_sequence, status,
                    progress_current, progress_total, progress_unit, progress_percent, progress_message,
                    metadata_json, started_at, completed_at, created_at, updated_at
                ) VALUES
                    (1, 1, 1, 1, 'players', 1, 'succeeded', 1, 1, 'stage', 100.00, 'players succeeded', '{"rows_loaded": 1250}', '2026-05-20 11:00:00', '2026-05-20 11:01:00', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
                    (2, 1, 1, 2, 'matches', 4, 'running', 0, 1, 'stage', 0.00, 'matches running', NULL, '2026-05-20 11:15:00', NULL, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """
            )
        )
        session.commit()
    finally:
        session.close()


def _seed_completed_generation_state(session_factory):
    session = session_factory()
    try:
        lifecycle = ConfigurationLifecycleService()
        lifecycle.save_new_version(
            session,
            title="Completed config",
            notes=None,
            payload={
                "runtime": {},
                "simulation": {
                    "simulation_name": "Completed Route Test",
                    "simulation_version": "v1",
                    "master_seed": 11,
                    "historical_batch_count": 2,
                    "first_batch_month": "2026-01-01",
                },
                "player_generation": {
                    "player_count": 1000,
                },
            },
        )
        _seed_ready_reference_data(session)
        session.execute(
            text(
                """
                INSERT INTO generation_runs (
                    id, generation_name, seed_value, simulation_version, status, started_at, completed_at, created_at, updated_at
                ) VALUES (
                    2, 'Completed UI run', 11, 'v1', 'succeeded', '2026-05-20 09:00:00', '2026-05-20 10:00:00', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                )
                """
            )
        )
        session.execute(
            text(
                """
                INSERT INTO monthly_batches (
                    id, generation_run_id, batch_month, batch_sequence, batch_type, active_player_count_end,
                    match_count_generated, processing_status, completed_at, created_at, updated_at
                ) VALUES
                    (21, 2, '2026-01-01', 1, 'historical_initial', 1000, 480, 'succeeded', '2026-05-20 09:30:00', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
                    (22, 2, '2026-02-01', 2, 'historical_initial', 1020, 520, 'succeeded', '2026-05-20 10:00:00', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """
            )
        )
        session.execute(
            text(
                """
                INSERT INTO job_status (
                    id, job_type, job_id, status, current_phase, percent_complete, current_message, started_at, completed_at, created_at, updated_at
                ) VALUES (
                    2, 'generation_run', 'generation-run-2-test', 'succeeded', 'completed', 100.00, 'Generation run completed successfully.',
                    '2026-05-20 09:00:00', '2026-05-20 10:00:00', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                )
                """
            )
        )
        session.execute(
            text(
                """
                INSERT INTO job_stage_progress (
                    id, job_status_id, generation_run_id, batch_id, stage_name, stage_sequence, status,
                    progress_current, progress_total, progress_unit, progress_percent, progress_message,
                    created_at, updated_at
                ) VALUES
                    (201, 2, 2, 21, 'players', 1, 'succeeded', 1, 1, 'stage', 100.00, 'players succeeded', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
                    (202, 2, 2, 22, 'matches', 4, 'succeeded', 1, 1, 'stage', 100.00, 'matches succeeded', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """
            )
        )
        session.commit()
    finally:
        session.close()


def _seed_tournament_event_state(session_factory):
    _seed_completed_generation_state(session_factory)
    session = session_factory()
    try:
        session.execute(
            text(
                """
                INSERT INTO tournament_events (
                    id, event_name, generation_run_id, source_batch_id,
                    tournament_date, config_snapshot, status, created_at, updated_at
                ) VALUES (
                    301, 'Saved Class Tournament', 2, 22,
                    '2026-02-01', '{}', 'ready', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                )
                """
            )
        )
        session.execute(
            text(
                """
                INSERT INTO job_status (
                    id, job_type, job_id, status, current_phase, percent_complete,
                    current_message, started_at, completed_at, created_at, updated_at
                ) VALUES (
                    302, 'tournament_monte_carlo', 'tournament-mc-302',
                    'succeeded', 'completed', 100.00,
                    'Monte Carlo completed.', '2026-02-01 09:00:00', '2026-02-01 09:03:15',
                    CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                )
                """
            )
        )
        session.execute(
            text(
                """
                INSERT INTO tournament_simulation_runs (
                    id, event_id, run_type, status, seed, iteration_count,
                    config_snapshot, job_status_id, created_at, updated_at
                ) VALUES (
                    303, 301, 'monte_carlo', 'succeeded', 7, 250,
                    '{}', 302, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                )
                """
            )
        )
        session.execute(
            text(
                """
                INSERT INTO tournament_student_groups (
                    id, event_id, group_name, external_group_key, created_at, updated_at
                ) VALUES
                    (401, 301, 'Group 1', '1', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
                    (402, 301, 'Group 2', '2', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """
            )
        )
        session.execute(
            text(
                """
                INSERT INTO tournament_submissions (
                    id, event_id, student_group_id, slot_country_code, slot_division,
                    team_id, validation_status, created_at, updated_at
                ) VALUES
                    (501, 301, 401, 'CA', 'mens_doubles', 9001, 'valid', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
                    (502, 301, 402, 'CA', 'mens_doubles', 9001, 'valid', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
                    (503, 301, 401, 'US', 'mixed_doubles', 9002, 'valid', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """
            )
        )
        session.execute(
            text(
                """
                INSERT INTO tournament_division_results (
                    id, simulation_run_id, slot_country_code, slot_division,
                    iteration_count, unique_team_count, match_count, created_at, updated_at
                ) VALUES
                    (601, 303, 'ALL', 'mens_doubles', 250, 5, 10, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
                    (602, 303, 'ALL', 'mixed_doubles', 250, 4, 6, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """
            )
        )
        session.execute(
            text(
                """
                INSERT INTO tournament_team_results (
                    id, simulation_run_id, slot_country_code, slot_division, team_id,
                    championship_probability, top_three_probability, average_finish,
                    win_percentage, created_at, updated_at
                ) VALUES
                    (701, 303, 'CA', 'mens_doubles', 9001, 0.42000, 0.78000, 1.850, 0.62000, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
                    (702, 303, 'US', 'mens_doubles', 9002, 0.33000, 0.74000, 2.100, 0.56000, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
                    (703, 303, 'US', 'mens_doubles', 9003, 0.25000, 0.68000, 2.700, 0.51000, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
                    (704, 303, 'US', 'mixed_doubles', 9004, 0.18000, 0.51000, 3.200, 0.48000, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """
            )
        )
        session.execute(
            text(
                """
                INSERT INTO tournament_group_results (
                    id, simulation_run_id, student_group_id, expected_score,
                    average_rank, rank_distribution, created_at, updated_at
                ) VALUES
                    (801, 303, 401, 31.250, 1.400, '{}', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
                    (802, 303, 402, 28.500, 2.100, '{}', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """
            )
        )
        session.commit()
    finally:
        session.close()


def _seed_idle_config_state(session_factory):
    session = session_factory()
    try:
        lifecycle = ConfigurationLifecycleService()
        lifecycle.save_new_version(
            session,
            title="Editable config",
            notes="base",
            payload={
                "runtime": {},
                "simulation": {
                    "simulation_name": "Editable Route Test",
                    "simulation_version": "v1",
                    "master_seed": 21,
                    "historical_batch_count": 2,
                    "first_batch_month": "2026-03-01",
                },
                "player_generation": {
                    "player_count": 1000,
                },
            },
        )
        _seed_ready_reference_data(session)
        session.commit()
    finally:
        session.close()


def _seed_stale_seed_job_state(session_factory):
    _seed_idle_config_state(session_factory)
    session = session_factory()
    try:
        session.execute(
            text(
                """
                INSERT INTO job_status (
                    id, job_type, job_id, status, current_phase, percent_complete,
                    current_message, started_at, created_at, updated_at
                ) VALUES (
                    31, 'seed_refresh', 'seed-refresh-stale', 'running',
                    'seed_normalization', 50.00, 'Stale seed job.',
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
                    31, 31, NULL, NULL, 'seed_normalization', 2, 'pending',
                    0, 4, 'dataset', 0.00, NULL,
                    'Pending execution.', NULL,
                    '2026-05-20 09:00:00', '2026-05-20 09:00:00'
                )
                """
            )
        )
        session.commit()
    finally:
        session.close()


def _seed_stale_generation_job_state(session_factory):
    _seed_idle_config_state(session_factory)
    session = session_factory()
    try:
        session.execute(
            text(
                """
                INSERT INTO generation_runs (
                    id, generation_name, seed_value, simulation_version, status,
                    started_at, created_at, updated_at
                ) VALUES (
                    41, 'Stale generation run', 11, 'v1', 'running',
                    '2026-05-20 09:00:00', '2026-05-20 09:00:00',
                    '2026-05-20 09:00:00'
                )
                """
            )
        )
        session.execute(
            text(
                """
                INSERT INTO monthly_batches (
                    id, generation_run_id, batch_month, batch_sequence,
                    batch_type, processing_status, created_at, updated_at
                ) VALUES (
                    41, 41, '2026-01-01', 1, 'historical_initial',
                    'running', '2026-05-20 09:00:00', '2026-05-20 09:00:00'
                )
                """
            )
        )
        session.execute(
            text(
                """
                INSERT INTO job_status (
                    id, job_type, job_id, status, current_phase, percent_complete,
                    current_message, started_at, created_at, updated_at
                ) VALUES (
                    41, 'generation_run', 'generation-run-stale', 'running',
                    'matches', 20.00, 'Stale generation job.',
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
                    41, 41, 41, 41, 'matches', 4, 'running',
                    0, 1, 'stage', 0.00, '2026-05-20 09:01:00',
                    'Stale generation job.', '2026-05-20 09:00:00',
                    '2026-05-20 09:00:00', '2026-05-20 09:00:00'
                )
                """
            )
        )
        session.commit()
    finally:
        session.close()


def _seed_ready_reference_data(session):
    session.execute(
        text(
            """
            INSERT INTO regions (
                id, country_code, region_type, region_name, state_province_code, created_at, updated_at
            ) VALUES (1, 'US', 'MSA', 'Phoenix, AZ', 'AZ', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """
        )
    )
    session.execute(
        text(
            """
            INSERT INTO clubs (
                id, club_name, region_id, club_type, created_at, updated_at
            ) VALUES (1, 'Phoenix Pickleball Club', 1, 'public_park', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """
        )
    )
    session.execute(
        text(
            """
            INSERT INTO first_names (
                id, country_code, state_province_code, birth_year, gender, first_name, frequency_count, created_at, updated_at
            ) VALUES (1, 'US', 'AZ', 1990, 'M', 'Alex', 10, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """
        )
    )
    session.execute(
        text(
            """
            INSERT INTO last_names (
                id, country_code, state_province_code, last_name, frequency_count, created_at, updated_at
            ) VALUES (1, 'US', 'AZ', 'Smith', 10, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """
        )
    )
    session.execute(
        text(
            """
            INSERT INTO raw_seed_load_runs (
                id, dataset_type, source_path, source_file_count, status, rows_read, rows_loaded, rows_rejected, created_at, updated_at
            ) VALUES (
                1, 'metro_areas_us', 'data/raw/metro_areas/us.csv', 1, 'completed', 100, 100, 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
            """
        )
    )


def _request(path: str, *, method: str = "GET") -> Request:
    return Request({"type": "http", "method": method, "path": path, "headers": []})


def _route_map(app):
    return {route.path: route.endpoint for route in app.router.routes if hasattr(route, "path")}


class FakeGenerationRunService:
    def __init__(self, *, error: str | None = None) -> None:
        self.error = error
        self.calls: list[str] = []

    def register_generation_run(self, generation_name: str, *, session=None):
        del session
        self.calls.append(generation_name)
        if self.error is not None:
            raise ValueError(self.error)
        return type(
            "Registration",
            (),
            {
                "configuration_version": type("ConfigVersion", (), {"id": 1})(),
                "generation_run": type("GenerationRun", (), {"id": 2})(),
                "job_status": type("JobStatus", (), {"id": 3})(),
            },
        )()

    def execute_registered_generation_run_in_background(self, **kwargs):
        return kwargs


class FakeSeedRefreshService:
    def __init__(self, *, error: str | None = None) -> None:
        self.error = error
        self.calls: list[str] = []

    def register_raw_seed_ingest(self, *, session=None):
        del session
        self.calls.append("load")
        if self.error is not None:
            raise ValueError(self.error)
        return type(
            "Registration",
            (),
            {
                "configuration_version": type("ConfigVersion", (), {"id": 10})(),
                "job_status": type("JobStatus", (), {"id": 11})(),
                "mode": "load",
            },
        )()

    def register_seed_normalization(self, *, session=None):
        del session
        self.calls.append("normalize")
        if self.error is not None:
            raise ValueError(self.error)
        return type(
            "Registration",
            (),
            {
                "configuration_version": type("ConfigVersion", (), {"id": 10})(),
                "job_status": type("JobStatus", (), {"id": 11})(),
                "mode": "normalize",
            },
        )()

    def register_seed_refresh(self, *, session=None):
        del session
        self.calls.append("refresh")
        if self.error is not None:
            raise ValueError(self.error)
        return type(
            "Registration",
            (),
            {
                "configuration_version": type("ConfigVersion", (), {"id": 10})(),
                "job_status": type("JobStatus", (), {"id": 11})(),
                "mode": "refresh",
            },
        )()

    def execute_registered_seed_job_in_background(self, **kwargs):
        return kwargs


class FakeStudentDatasetExportService:
    def __init__(self, *, error: str | None = None) -> None:
        self.error = error
        self.calls: list[dict[str, object]] = []

    def register_export_job(self, **kwargs):
        self.calls.append(kwargs)
        if self.error is not None:
            raise ValueError(self.error)
        return type(
            "Registration",
            (),
            {"job_status": type("JobStatus", (), {"id": 91})()},
        )()

    def execute_registered_export_in_background(self, **kwargs):
        return kwargs


class FakeBackgroundRunner:
    def __init__(self) -> None:
        self.submissions: list[tuple[object, tuple[object, ...], dict[str, object]]] = []

    def submit(self, fn, /, *args, **kwargs):
        self.submissions.append((fn, args, kwargs))
        return object()


class _FakeTournamentService:
    def __init__(self) -> None:
        self.created_event_name: str | None = None
        self.submission_count = 0
        self.registered_event_id: int | None = None
        self.registered_iterations: int | None = None
        self.registered_seed: int | None = None

    def create_event(self, **kwargs):
        self.created_event_name = kwargs["event_name"]
        self.submission_count = len(kwargs["submissions"])
        return SimpleNamespace(event=SimpleNamespace(id=777))

    def validate_event(self, **kwargs):
        return SimpleNamespace(is_valid=True, issues=())

    def register_monte_carlo_run(self, **kwargs):
        self.registered_event_id = kwargs["event_id"]
        self.registered_iterations = kwargs["iterations"]
        self.registered_seed = kwargs["seed"]
        return SimpleNamespace(
            simulation_run=SimpleNamespace(id=888),
            job_status=SimpleNamespace(id=889),
        )

    def execute_run_in_background(self, **kwargs):
        return kwargs


def _full_tournament_payload_json() -> str:
    team_ids = {}
    team_id = 100
    for group_index in range(1, routes_module.TOURNAMENT_GROUP_COUNT + 1):
        for slot in routes_module.TOURNAMENT_PORTFOLIO_SLOTS:
            team_ids[
                f"group_{group_index}_{slot.country_code}_{slot.division}"
            ] = str(team_id)
            team_id += 1
    return json.dumps(
        {
            "group_names": {
                str(index): f"Group {index}"
                for index in range(1, routes_module.TOURNAMENT_GROUP_COUNT + 1)
            },
            "team_ids": team_ids,
        }
    )


def test_control_panel_shell_renders_tabs_and_initial_content(session_factory):
    _seed_snapshot_state(session_factory)
    app = create_app()
    routes = _route_map(app)
    session = session_factory()
    try:
        response = routes["/control"](
            request=_request("/control"),
            session=session,
            queries=ControlPanelQueries(),
        )
    finally:
        session.close()

    body = response.body.decode()
    assert response.status_code == 200
    assert "/control" in routes
    assert "/control/partials/config" in routes
    assert "/control/partials/config/seed" in routes
    assert "/control/partials/config/player-match" in routes
    assert "/control/partials/config/export" in routes
    assert "/control/partials/config/tournament" in routes
    assert "/control/partials/tournament" in routes
    assert "/control/partials/tournament/simulation" in routes
    assert "/control/tournaments/submissions/save" in routes
    assert "/control/tournaments/monte-carlo/start" in routes
    assert "/control/partials/overall-progress" in routes
    assert "Simulation Control Panel" in body
    assert "Seed Data Config" in body
    assert "Player and Match Config" in body
    assert "Export Configuration" in body
    assert "Orchestration" in body
    assert "Tournament Config" in body
    assert "Tournament" in body
    assert 'data-tab-url="/control/partials/config/seed"' in body
    assert 'data-tab-url="/control/partials/config/player-match"' in body
    assert 'data-tab-url="/control/partials/config/export"' in body
    assert 'data-tab-url="/control/partials/orchestration"' in body
    assert 'data-tab-url="/control/partials/config/tournament"' in body
    assert 'data-tab-url="/control/partials/tournament"' in body
    assert "window.loadControlPanelTab" in body
    assert "window.htmx?.process?.(target)" in body
    assert "Read only config" in body


def test_control_panel_partials_render_run_status_batch_table_and_progress(session_factory):
    _seed_snapshot_state(session_factory)
    app = create_app()
    routes = _route_map(app)
    session = session_factory()
    try:
        run_status = routes["/control/partials/run-status"](
            request=_request("/control/partials/run-status"),
            session=session,
            queries=ControlPanelQueries(),
        )
        batch_table = routes["/control/partials/batch-table"](
            request=_request("/control/partials/batch-table"),
            session=session,
            queries=ControlPanelQueries(),
        )
        overall_progress = routes["/control/partials/overall-progress"](
            request=_request("/control/partials/overall-progress"),
            session=session,
            queries=ControlPanelQueries(),
        )
        progress = routes["/control/partials/progress-bars"](
            request=_request("/control/partials/progress-bars"),
            session=session,
            queries=ControlPanelQueries(),
        )
        orchestration = routes["/control/partials/orchestration"](
            request=_request("/control/partials/orchestration"),
            session=session,
            queries=ControlPanelQueries(),
        )
        export_config = routes["/control/partials/config/export"](
            request=_request("/control/partials/config/export"),
            session=session,
            queries=ControlPanelQueries(),
        )
        tournament_config = routes["/control/partials/config/tournament"](
            request=_request("/control/partials/config/tournament"),
            session=session,
            queries=ControlPanelQueries(),
        )
        tournament = routes["/control/partials/tournament"](
            request=_request("/control/partials/tournament"),
            session=session,
            queries=ControlPanelQueries(),
        )
    finally:
        session.close()

    assert run_status.status_code == 200
    assert "UI run" in run_status.body.decode()
    assert "running" in run_status.body.decode()

    assert batch_table.status_code == 200
    assert "Monthly Batches" in batch_table.body.decode()
    assert "2026-02-01" in batch_table.body.decode()
    assert "Total Duration" in batch_table.body.decode()
    assert "Type" not in batch_table.body.decode()
    assert "Stages" not in batch_table.body.decode()
    assert 'hx-get="/control/partials/batch-table"' in batch_table.body.decode()
    assert 'hx-trigger="every 10s"' in batch_table.body.decode()

    assert overall_progress.status_code == 200
    assert "Overall Progress" in overall_progress.body.decode()
    assert "1 of 2 stages completed" in overall_progress.body.decode()
    assert 'hx-get="/control/partials/overall-progress"' in overall_progress.body.decode()
    assert 'hx-trigger="every 10s"' in overall_progress.body.decode()

    assert progress.status_code == 200
    assert "Stage Progress" in progress.body.decode()
    assert "matches" in progress.body.decode()
    assert "Rows created: 1,250 | Duration 1m 00s" in progress.body.decode()

    assert orchestration.status_code == 200
    assert "Raw Ingest &amp; Normalization" in orchestration.body.decode()
    assert "Player &amp; Match Generation" in orchestration.body.decode()
    assert "Data Export" in orchestration.body.decode()
    assert "<details open" not in orchestration.body.decode()
    assert "Generate seed data" in orchestration.body.decode()
    assert "Generate player and match data" in orchestration.body.decode()
    assert "Start Student Dataset Baseline + Incremental Export" in orchestration.body.decode()
    assert "Start Generation Run" in orchestration.body.decode()
    assert "Estimated Dataset Size" in orchestration.body.decode()
    assert "Estimated Players" in orchestration.body.decode()
    assert "1,020" in orchestration.body.decode()
    assert "Estimated Teams" in orchestration.body.decode()
    assert "982" in orchestration.body.decode()
    assert "Estimated Matches" in orchestration.body.decode()
    assert "1,964" in orchestration.body.decode()
    assert "Estimated Games" in orchestration.body.decode()
    assert "2,750" in orchestration.body.decode()
    assert "Overall Progress" in orchestration.body.decode()
    assert "1 of 2 stages completed" in orchestration.body.decode()
    assert 'id="seed-destructive-confirm"' in orchestration.body.decode()
    assert 'hx-include="#seed-destructive-confirm"' in orchestration.body.decode()
    assert 'hx-post="/control/seed/load"' in orchestration.body.decode()
    assert 'hx-post="/control/seed/normalize"' in orchestration.body.decode()
    assert 'hx-post="/control/seed/refresh"' in orchestration.body.decode()
    assert 'hx-get="/control/partials/orchestration"' in orchestration.body.decode()
    assert 'hx-trigger="every 10s"' in orchestration.body.decode()
    assert 'data-orchestration-section="raw-ingest"' in orchestration.body.decode()
    assert (
        'data-orchestration-section="player-match-generation"'
        in orchestration.body.decode()
    )
    assert 'data-orchestration-section="data-export"' in orchestration.body.decode()
    assert 'id="generation-run-name"' in orchestration.body.decode()
    assert "hx-preserve" in orchestration.body.decode()
    assert "control-panel-orchestration-section:" in orchestration.body.decode()

    assert export_config.status_code == 200
    assert "Export Configuration" in export_config.body.decode()
    assert "Student dataset baseline and incremental export" in export_config.body.decode()
    assert 'hx-post="/control/export/student-dataset/start"' in export_config.body.decode()
    assert "Start Student Dataset Baseline + Incremental Export" in export_config.body.decode()
    assert "copyControlPanelText" in export_config.body.decode()

    assert tournament_config.status_code == 200
    assert "Tournament Configuration" in tournament_config.body.decode()
    assert "Tournament Simulation Rules" in tournament_config.body.decode()
    assert "Student Leaderboard Scoring" in tournament_config.body.decode()
    assert "Tournament Match Structure" in tournament_config.body.decode()
    assert "Tournament Hidden Performance Bias" in tournament_config.body.decode()

    assert tournament.status_code == 200
    assert "Instructor tournament workflow" in tournament.body.decode()
    assert "No completed generated history is available" in tournament.body.decode()
    assert "Open Orchestration" in tournament.body.decode()


def test_tournament_partial_renders_empty_state_without_generation_run(session_factory):
    _seed_idle_config_state(session_factory)
    app = create_app()
    routes = _route_map(app)
    session = session_factory()
    try:
        response = routes["/control/partials/tournament"](
            request=_request("/control/partials/tournament"),
            session=session,
            queries=ControlPanelQueries(),
        )
    finally:
        session.close()

    body = response.body.decode()
    assert response.status_code == 200
    assert "No completed generated history is available" in body
    assert "Open Orchestration" in body


def test_tournament_partial_renders_ready_state_for_completed_generation(session_factory):
    _seed_completed_generation_state(session_factory)
    app = create_app()
    routes = _route_map(app)
    session = session_factory()
    try:
        response = routes["/control/partials/tournament"](
            request=_request("/control/partials/tournament"),
            session=session,
            queries=ControlPanelQueries(),
        )
    finally:
        session.close()

    body = response.body.decode()
    assert response.status_code == 200
    assert "Source Run" in body
    assert "Completed UI run" in body
    assert "Submission form" in body
    assert 'hx-post="/control/tournaments/submissions/save"' in body
    assert "Validate and Save Submissions" in body
    assert "Student Group 6" in body
    assert 'data-tournament-team-id="group_1_CA_mens_doubles"' in body
    assert 'id="tournament-save-status"' in body
    assert 'id="tournament-team-grid-shell"' in body
    assert 'data-tournament-dirty="false"' in body
    assert 'name="group_1_CA_mens_doubles"' in body
    assert 'hx-include="closest .tournament-team-field, #tournament-submission-form [name=' in body
    assert "field_key,group_index,country_code,division" in body
    assert 'hx-sync="closest form:replace"' in body
    assert 'data-tournament-team-id="group_6_US_mixed_doubles"' in body
    assert 'value="39134"' not in body
    assert 'value="34722"' not in body
    assert "serializeTournamentSubmissionForm" in body
    assert "Simulation controls" in body
    assert "Save and validate submissions" in body
    assert 'id="tournament-monte-carlo-panel"' in body
    assert 'data-tournament-locked="false"' in body


def test_tournament_partial_renders_monte_carlo_controls_for_saved_event(session_factory):
    _seed_tournament_event_state(session_factory)
    app = create_app()
    routes = _route_map(app)
    session = session_factory()
    try:
        response = routes["/control/partials/tournament"](
            request=_request("/control/partials/tournament"),
            session=session,
            queries=ControlPanelQueries(),
        )
    finally:
        session.close()

    body = response.body.decode()
    assert response.status_code == 200
    assert "Saved Class Tournament" in body
    assert "Start Monte Carlo" in body
    assert 'id="tournament-monte-carlo-button"' in body
    assert 'hx-post="/control/tournaments/monte-carlo/start"' in body
    assert 'name="event_id" value="301"' in body
    assert "Run 303" in body
    assert "250 iterations | seed 7" in body
    assert "Monte Carlo completed. Elapsed time: 3m 15s." in body
    assert 'value="9001"' in body
    assert 'value="9002"' in body
    assert 'value="39134"' not in body
    assert "Tournament summary" in body
    assert "Championship and Medal Probabilities" in body
    assert "Team 9001" in body
    assert "Student Group" in body
    assert "Group 1, Group 2" in body
    assert body.index("Team 9001") < body.index("Team 9002")
    assert "42.0%" in body
    assert "78.0%" in body
    assert "#fff6d6" in body
    assert "#e5e7eb" in body
    assert "#f6e3d3" in body
    assert "Student Leaderboard" in body
    assert "Student Group Scoring Outcome" in body
    assert 'id="tournament-results-content"' in body
    assert 'data-tournament-results-stale="false"' in body
    assert "31.250" in body
    assert body.index("Group 1") < body.index("Group 2")
    assert "Aggregate score 31.250 | Avg rank 1.400" in body
    assert "Duplicate-Team Credit" in body
    assert "Team 9001 in CA mens doubles credits 2 groups: Group 1, Group 2." in body


def test_tournament_running_monte_carlo_polling_is_pinned_to_event(session_factory):
    _seed_tournament_event_state(session_factory)
    app = create_app()
    routes = _route_map(app)
    session = session_factory()
    try:
        session.execute(
            text(
                """
                INSERT INTO job_status (
                    id, job_type, job_id, status, current_phase, percent_complete,
                    current_message, created_at, updated_at
                ) VALUES (
                    309, 'tournament_monte_carlo', 'tournament-mc-309',
                    'running', 'simulating', 50.00,
                    'Tournament simulation running.', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                )
                """
            )
        )
        session.execute(
            text(
                """
                INSERT INTO tournament_simulation_runs (
                    id, event_id, run_type, status, seed, iteration_count,
                    config_snapshot, job_status_id, created_at, updated_at
                ) VALUES (
                    309, 301, 'monte_carlo', 'running', 8, 500,
                    '{}', 309, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                )
                """
            )
        )
        session.commit()
        response = routes["/control/partials/tournament"](
            request=_request("/control/partials/tournament"),
            session=session,
            queries=ControlPanelQueries(),
        )
    finally:
        session.close()

    body = response.body.decode()
    assert response.status_code == 200
    assert 'hx-get="/control/partials/tournament/simulation?event_id=301"' in body


def test_tournament_team_field_validation_shows_error_for_invalid_team_id(session_factory):
    _seed_completed_generation_state(session_factory)
    app = create_app()
    routes = _route_map(app)
    session = session_factory()
    try:
        response = asyncio.run(
            routes["/control/tournaments/submissions/validate-field"](
                request=_request(
                    "/control/tournaments/submissions/validate-field",
                    method="POST",
                ),
                team_id="not-a-number",
                tournament_date="2026-02-01",
                group_index=1,
                country_code="CA",
                division="mens_doubles",
                session=session,
                queries=ControlPanelQueries(),
            )
        )
    finally:
        session.close()

    body = response.body.decode()
    assert response.status_code == 200
    assert 'data-tournament-team-id="group_1_CA_mens_doubles"' in body
    assert 'value="not-a-number"' in body
    assert "Team ID must be a whole number." in body
    assert "#b42318" in body


def test_tournament_team_field_validation_is_silent_for_valid_team(session_factory, monkeypatch):
    _seed_completed_generation_state(session_factory)
    app = create_app()
    routes = _route_map(app)

    def _fake_validation(*args, **kwargs):
        return ()

    monkeypatch.setattr(routes_module, "validate_tournament_submission", _fake_validation)

    session = session_factory()
    try:
        response = asyncio.run(
            routes["/control/tournaments/submissions/validate-field"](
                request=_request(
                    "/control/tournaments/submissions/validate-field",
                    method="POST",
                ),
                team_id="39134",
                tournament_date="2026-02-01",
                group_index=1,
                country_code="CA",
                division="mens_doubles",
                session=session,
                queries=ControlPanelQueries(),
            )
        )
    finally:
        session.close()

    body = response.body.decode()
    assert response.status_code == 200
    assert 'data-tournament-team-id="group_1_CA_mens_doubles"' in body
    assert 'value="39134"' in body
    assert "Team ID must be a whole number." not in body
    assert "#b42318" not in body


def test_tournament_monte_carlo_start_queues_background_run(session_factory):
    _seed_tournament_event_state(session_factory)
    app = create_app()
    routes = _route_map(app)
    fake_service = _FakeTournamentService()
    background_runner = FakeBackgroundRunner()
    session = session_factory()
    try:
        response = routes["/control/tournaments/monte-carlo/start"](
            request=_request("/control/tournaments/monte-carlo/start", method="POST"),
            event_id=301,
            iterations=500,
            seed=42,
            session=session,
            queries=ControlPanelQueries(),
            tournament_service=fake_service,
            background_runner=background_runner,
        )
    finally:
        session.close()

    body = response.body.decode()
    assert response.status_code == 200
    assert 'id="tournament-simulation-panels"' in body
    assert 'id="tournament-submission-form"' not in body
    assert "Monte Carlo run 888 queued." in body
    assert fake_service.registered_event_id == 301
    assert fake_service.registered_iterations == 500
    assert fake_service.registered_seed == 42
    assert len(background_runner.submissions) == 1
    assert background_runner.submissions[0][2] == {"simulation_run_id": 888}


def test_tournament_submission_save_renders_field_errors(session_factory, monkeypatch):
    _seed_completed_generation_state(session_factory)
    app = create_app()
    routes = _route_map(app)
    slot = routes_module.PortfolioSlot(country_code="CA", division="mens_doubles")

    monkeypatch.setattr(
        routes_module,
        "load_validated_tournament_input",
        lambda *args, **kwargs: SimpleNamespace(
            is_valid=False,
            issues=(
                SimpleNamespace(
                    group_id=1,
                    slot=slot,
                    team_id=999,
                    field="team_id",
                    code="team_not_found",
                    message="Team 999 does not exist.",
                ),
            ),
        ),
    )

    session = session_factory()
    try:
        response = routes["/control/tournaments/submissions/save"](
            request=_request("/control/tournaments/submissions/save", method="POST"),
            event_name="Class Tournament",
            tournament_date="2026-02-01",
            tournament_payload_json=_full_tournament_payload_json(),
            session=session,
            queries=ControlPanelQueries(),
            tournament_service=_FakeTournamentService(),
        )
    finally:
        session.close()

    body = response.body.decode()
    assert response.status_code == 200
    assert "Fix the highlighted team submissions" in body
    assert "Team 999 does not exist." in body
    assert 'data-tournament-dirty="true"' in body


def test_tournament_submission_save_clears_saved_results_when_revalidation_is_required(
    session_factory,
    monkeypatch,
):
    _seed_tournament_event_state(session_factory)
    app = create_app()
    routes = _route_map(app)
    slot = routes_module.PortfolioSlot(country_code="CA", division="mens_doubles")

    monkeypatch.setattr(
        routes_module,
        "load_validated_tournament_input",
        lambda *args, **kwargs: SimpleNamespace(
            is_valid=False,
            issues=(
                SimpleNamespace(
                    group_id=1,
                    slot=slot,
                    team_id=999,
                    field="team_id",
                    code="team_not_found",
                    message="Team 999 does not exist.",
                ),
            ),
        ),
    )

    session = session_factory()
    try:
        response = routes["/control/tournaments/submissions/save"](
            request=_request("/control/tournaments/submissions/save", method="POST"),
            event_name="Saved Class Tournament",
            tournament_date="2026-02-01",
            tournament_payload_json=_full_tournament_payload_json(),
            session=session,
            queries=ControlPanelQueries(),
            tournament_service=_FakeTournamentService(),
        )
    finally:
        session.close()

    body = response.body.decode()
    assert response.status_code == 200
    assert 'data-tournament-results-stale="true"' in body
    assert "Validate and save the updated team submissions before reviewing Monte Carlo results." in body
    assert "Student Leaderboard" not in body
    assert "Student Group Scoring Outcome" not in body


def test_tournament_submission_save_persists_valid_event(session_factory, monkeypatch):
    _seed_completed_generation_state(session_factory)
    app = create_app()
    routes = _route_map(app)
    fake_service = _FakeTournamentService()

    monkeypatch.setattr(
        routes_module,
        "load_validated_tournament_input",
        lambda *args, **kwargs: SimpleNamespace(is_valid=True, issues=()),
    )

    session = session_factory()
    try:
        response = routes["/control/tournaments/submissions/save"](
            request=_request("/control/tournaments/submissions/save", method="POST"),
            event_name="Class Tournament",
            tournament_date="2026-02-01",
            tournament_payload_json=_full_tournament_payload_json(),
            session=session,
            queries=ControlPanelQueries(),
            tournament_service=fake_service,
        )
    finally:
        session.close()

    body = response.body.decode()
    assert response.status_code == 200
    assert "Validation complete. Tournament event 777 saved." in body
    assert 'data-tournament-dirty="false"' in body
    assert fake_service.created_event_name == "Class Tournament"
    assert fake_service.submission_count == 36


def test_orchestration_partial_renders_raw_load_duration_column(session_factory):
    _seed_idle_config_state(session_factory)
    app = create_app()
    routes = _route_map(app)
    session = session_factory()
    try:
        session.execute(
            text(
                """
                INSERT INTO job_status (
                    id, job_type, job_id, status, current_phase, percent_complete, current_message,
                    started_at, completed_at, created_at, updated_at
                ) VALUES (
                    71, 'seed_refresh', 'seed-refresh-71', 'succeeded', 'completed', 100.00,
                    'Seed refresh completed successfully.',
                    '2026-05-20 08:00:00', '2026-05-20 08:10:00', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                )
                """
            )
        )
        session.execute(
            text(
                """
                INSERT INTO raw_seed_load_runs (
                    id, job_status_id, dataset_type, source_path, source_file_count, status,
                    rows_read, rows_loaded, rows_rejected, started_at, completed_at, created_at, updated_at
                ) VALUES (
                    71, 71, 'metro_areas_us', 'data/raw/metro/us.csv', 1, 'completed',
                    100, 98, 2, '2026-05-20 08:01:00', '2026-05-20 08:06:30', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                )
                """
            )
        )
        session.commit()

        orchestration = routes["/control/partials/orchestration"](
            request=_request("/control/partials/orchestration"),
            session=session,
            queries=ControlPanelQueries(now_fn=lambda: datetime(2026, 5, 20, 8, 11, 0)),
        )
    finally:
        session.close()

    body = orchestration.body.decode()
    assert orchestration.status_code == 200
    assert "Total Duration" in body
    assert "5m 30s" in body


def test_completed_generation_run_renders_completion_popup_script(session_factory):
    _seed_completed_generation_state(session_factory)
    app = create_app()
    routes = _route_map(app)
    session = session_factory()
    try:
        orchestration = routes["/control/partials/orchestration"](
            request=_request("/control/partials/orchestration"),
            session=session,
            queries=ControlPanelQueries(),
        )
    finally:
        session.close()

    body = orchestration.body.decode()
    assert orchestration.status_code == 200
    assert "Generation run finished." in body
    assert 'const isComplete = true;' in body
    assert "2 of 2 stages completed - Duration 1:00:00" in body
    assert 'const runId = 2;' in body
    assert 'const playerCount = 1020;' in body
    assert 'const matchCount = 1000;' in body
    assert 'popupState.pendingRunId === String(runId)' in body
    assert '`Run ID: ${runId}`' in body
    assert '`Elapsed time: ${elapsedTime || "n/a"}`' in body


def test_completed_generation_run_marks_student_dataset_export_ready(session_factory):
    _seed_completed_generation_state(session_factory)
    app = create_app()
    routes = _route_map(app)
    session = session_factory()
    try:
        orchestration = routes["/control/partials/orchestration"](
            request=_request("/control/partials/orchestration"),
            session=session,
            queries=ControlPanelQueries(),
        )
    finally:
        session.close()

    body = orchestration.body.decode()
    assert orchestration.status_code == 200
    assert "Data Export" in body
    assert "Ready to export" in body
    assert "Open Export Configuration" in body
    assert "Delete the expected release folder first if it already exists" in body
    assert "Generate Student Dataset (coming soon)" not in body


def test_student_dataset_export_start_route_queues_background_job(session_factory):
    _seed_completed_generation_state(session_factory)
    app = create_app()
    routes = _route_map(app)
    session = session_factory()
    export_service = FakeStudentDatasetExportService()
    background_runner = FakeBackgroundRunner()
    try:
        response = routes["/control/export/student-dataset/start"](
            request=_request("/control/export/student-dataset/start", method="POST"),
            generation_run_id=2,
            initial_history_month_count=2,
            subsequent_month_count=0,
            output_root="data/student_dataset_exports",
            release_name="ui_export",
            data_quality_level="none",
            overwrite_existing=None,
            session=session,
            queries=ControlPanelQueries(),
            export_service=export_service,
            background_runner=background_runner,
        )
    finally:
        session.close()

    body = response.body.decode()
    assert response.status_code == 200
    assert "ui_export" in body
    assert "baseline and incremental export" in body
    assert "started in background" in body
    assert export_service.calls[0]["generation_run_id"] == 2
    assert export_service.calls[0]["release_name"] == "ui_export"
    assert export_service.calls[0]["overwrite_existing"] is False
    assert len(background_runner.submissions) == 1
    assert background_runner.submissions[0][2]["job_status_id"] == 91
    assert background_runner.submissions[0][2]["release_name"] == "ui_export"


def test_student_dataset_export_start_route_can_return_orchestration_partial(session_factory):
    _seed_completed_generation_state(session_factory)
    app = create_app()
    routes = _route_map(app)
    session = session_factory()
    export_service = FakeStudentDatasetExportService()
    background_runner = FakeBackgroundRunner()
    try:
        response = routes["/control/export/student-dataset/start"](
            request=_request("/control/export/student-dataset/start", method="POST"),
            generation_run_id=2,
            initial_history_month_count=2,
            subsequent_month_count=0,
            output_root="data/student_dataset_exports",
            release_name="ui_export",
            data_quality_level="none",
            overwrite_existing=None,
            return_target="orchestration",
            session=session,
            queries=ControlPanelQueries(),
            export_service=export_service,
            background_runner=background_runner,
        )
    finally:
        session.close()

    body = response.body.decode()
    assert response.status_code == 200
    assert "Data Export" in body
    assert "Start Student Dataset Baseline + Incremental Export" in body
    assert "ui_export" in body
    assert "started in background" in body


def test_student_dataset_export_start_route_passes_delete_confirmation(session_factory):
    _seed_completed_generation_state(session_factory)
    app = create_app()
    routes = _route_map(app)
    session = session_factory()
    export_service = FakeStudentDatasetExportService()
    background_runner = FakeBackgroundRunner()
    try:
        response = routes["/control/export/student-dataset/start"](
            request=_request("/control/export/student-dataset/start", method="POST"),
            generation_run_id=2,
            initial_history_month_count=2,
            subsequent_month_count=0,
            output_root="data/student_dataset_exports",
            release_name="ui_export",
            data_quality_level="none",
            overwrite_existing="yes",
            session=session,
            queries=ControlPanelQueries(),
            export_service=export_service,
            background_runner=background_runner,
        )
    finally:
        session.close()

    assert response.status_code == 200
    assert export_service.calls[0]["overwrite_existing"] is True
    assert background_runner.submissions[0][2]["overwrite_existing"] is True


def test_export_progress_shows_elapsed_time_for_completed_export(session_factory):
    _seed_completed_generation_state(session_factory)
    session = session_factory()
    try:
        session.execute(
            text(
                """
                INSERT INTO job_status (
                    id, job_type, job_id, status, current_phase, percent_complete, current_message,
                    started_at, completed_at, created_at, updated_at
                ) VALUES (
                    81, 'student_dataset_export', 'student-dataset-export-81', 'succeeded', 'completed', 100.00,
                    'Student dataset baseline and incremental export completed successfully.',
                    '2026-05-20 10:00:00', '2026-05-20 10:07:30', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                )
                """
            )
        )
        session.commit()
        app = create_app()
        routes = _route_map(app)
        response = routes["/control/partials/config/export"](
            request=_request("/control/partials/config/export"),
            session=session,
            queries=ControlPanelQueries(),
        )
    finally:
        session.close()

    body = response.body.decode()
    assert response.status_code == 200
    assert "Student dataset baseline and incremental export completed successfully." in body
    assert "Duration 7m 30s" in body


def test_export_progress_renders_release_actions(session_factory):
    _seed_completed_generation_state(session_factory)
    session = session_factory()
    try:
        session.execute(
            text(
                """
                INSERT INTO student_dataset_releases (
                    id, release_name, release_type, release_month, generation_run_id,
                    data_quality_level, output_path, status, created_at, updated_at, completed_at
                ) VALUES (
                    61, 'student_release_initial_history', 'historical_baseline', '2026-05-01', 2,
                    'none', 'data/student_dataset_exports/student_release/student_release_initial_history',
                    'succeeded', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                )
                """
            )
        )
        session.execute(
            text(
                """
                INSERT INTO student_dataset_release_files (
                    release_id, table_name, file_path, row_count, schema_hash, checksum, created_at
                ) VALUES
                    (61, 'player_master', 'data/student_dataset_exports/student_release/student_release_initial_history/player_master.parquet', 1000, 'abc', 'def', CURRENT_TIMESTAMP)
                """
            )
        )
        session.commit()
        app = create_app()
        routes = _route_map(app)
        response = routes["/control/partials/config/export"](
            request=_request("/control/partials/config/export"),
            session=session,
            queries=ControlPanelQueries(),
        )
    finally:
        session.close()

    body = response.body.decode()
    assert response.status_code == 200
    assert "Download Package" in body
    assert "Open Folder" in body
    assert "Run QC" in body
    assert "Copy Path" in body


def test_default_export_config_prefers_twelve_month_baseline():
    snapshot = SimpleNamespace(
        generation_run_summary=SimpleNamespace(
            generation_run_id=9,
            generation_name="QA Export Run",
            succeeded_batch_count=18,
        ),
        config_summary=SimpleNamespace(historical_batch_count=4),
    )

    config = routes_module._default_export_config(snapshot)

    assert config["generation_run_id"] == 9
    assert config["initial_history_month_count"] == 12
    assert config["subsequent_month_count"] == 6
    assert config["release_name"] == "qa_export_run"


def test_student_dataset_export_start_route_records_incremental_export_metadata(
    session_factory,
):
    _seed_completed_generation_state(session_factory)
    app = create_app()
    routes = _route_map(app)
    session = session_factory()
    background_runner = FakeBackgroundRunner()
    try:
        response = routes["/control/export/student-dataset/start"](
            request=_request("/control/export/student-dataset/start", method="POST"),
            generation_run_id=2,
            initial_history_month_count=12,
            subsequent_month_count=3,
            output_root="data/student_dataset_exports",
            release_name="ui_export",
            data_quality_level="none",
            overwrite_existing=None,
            session=session,
            queries=ControlPanelQueries(),
            export_service=StudentDatasetExportService(),
            background_runner=background_runner,
        )

        queued_job_id = background_runner.submissions[0][2]["job_status_id"]
        stage_rows = session.execute(
            text(
                """
                SELECT stage_name, metadata_json
                FROM job_stage_progress
                WHERE job_status_id = :job_status_id
                ORDER BY stage_sequence
                """
            ),
            {"job_status_id": queued_job_id},
        ).mappings().all()
        job_row = session.execute(
            text(
                """
                SELECT current_message
                FROM job_status
                WHERE id = :job_status_id
                """
            ),
            {"job_status_id": queued_job_id},
        ).mappings().one()
    finally:
        session.close()

    assert response.status_code == 200
    assert len(background_runner.submissions) == 1
    assert job_row["current_message"] == "Queued student dataset baseline and incremental export."
    assert len(stage_rows) == 3
    for row in stage_rows:
        metadata = (
            row["metadata_json"]
            if isinstance(row["metadata_json"], dict)
            else json.loads(row["metadata_json"])
        )
        assert metadata["release_family_mode"] == "baseline_plus_monthly_incrementals"
        assert metadata["baseline_month_count"] == 12
        assert metadata["incremental_month_count"] == 3


def test_copy_path_route_uses_windows_clipboard_helper(monkeypatch):
    app = create_app()
    routes = _route_map(app)
    captured: dict[str, str] = {}

    def fake_copy(value: str) -> None:
        captured["value"] = value

    monkeypatch.setattr(routes_module, "_copy_to_windows_clipboard", fake_copy)

    response = routes["/control/system/copy-path"](path="C:/exports/release")

    assert response.status_code == 200
    assert response.body.decode() == '{"ok":true}'
    assert captured["value"] == "C:/exports/release"


def test_open_folder_route_uses_host_folder_helper(monkeypatch):
    app = create_app()
    routes = _route_map(app)
    captured: dict[str, object] = {}

    def fake_resolve(value: str):
        captured["raw"] = value
        return Path("/tmp/student-release")

    def fake_open(path: Path) -> None:
        captured["path"] = path

    monkeypatch.setattr(routes_module, "_resolve_control_panel_path", fake_resolve)
    monkeypatch.setattr(routes_module, "_open_folder_in_host", fake_open)

    response = routes["/control/system/open-folder"](path="data/student_dataset_exports/release")

    assert response.status_code == 200
    assert captured["raw"] == "data/student_dataset_exports/release"
    assert captured["path"] == Path("/tmp/student-release")
    assert "Opened folder: /tmp/student-release" in response.body.decode()


def test_run_qc_route_returns_qc_summary(monkeypatch):
    app = create_app()
    routes = _route_map(app)
    captured: dict[str, object] = {}

    def fake_resolve(value: str):
        captured["raw"] = value
        return Path("/tmp/student-release")

    def fake_qc(path: Path):
        captured["path"] = path
        return {
            "ok": True,
            "message": "QC passed for student-release. Executed 88 checks with 0 failures.",
            "check_count": 88,
            "failed_check_count": 0,
        }

    monkeypatch.setattr(routes_module, "_resolve_control_panel_path", fake_resolve)
    monkeypatch.setattr(routes_module, "_run_student_dataset_qc", fake_qc)

    response = routes["/control/export/student-dataset/run-qc"](
        path="data/student_dataset_exports/release"
    )

    assert response.status_code == 200
    assert captured["raw"] == "data/student_dataset_exports/release"
    assert captured["path"] == Path("/tmp/student-release")
    assert "QC passed for student-release" in response.body.decode()


def test_run_qc_route_returns_422_for_failed_qc(monkeypatch):
    app = create_app()
    routes = _route_map(app)

    monkeypatch.setattr(
        routes_module,
        "_resolve_control_panel_path",
        lambda value: Path("/tmp/student-release"),
    )
    monkeypatch.setattr(
        routes_module,
        "_run_student_dataset_qc",
        lambda path: {
            "ok": False,
            "message": "QC failed for student-release. 2 of 88 checks failed.",
            "check_count": 88,
            "failed_check_count": 2,
            "failed_checks": [
                {"check_name": "row_count:players", "details": "manifest=10 actual=9"},
            ],
        },
    )

    response = routes["/control/export/student-dataset/run-qc"](
        path="data/student_dataset_exports/release"
    )

    assert response.status_code == 422
    assert "QC failed for student-release" in response.body.decode()


def test_download_package_route_returns_zip_attachment(monkeypatch, tmp_path):
    app = create_app()
    routes = _route_map(app)
    archive_path = tmp_path / "student_release_initial_history.zip"
    archive_path.write_bytes(b"zip-bytes")
    captured: dict[str, object] = {}

    def fake_resolve(value: str):
        captured["raw"] = value
        return Path("/tmp/student_release_initial_history")

    def fake_build(path: Path):
        captured["path"] = path
        return archive_path

    monkeypatch.setattr(routes_module, "_resolve_control_panel_path", fake_resolve)
    monkeypatch.setattr(routes_module, "_build_student_dataset_release_package", fake_build)

    response = routes["/control/export/student-dataset/download-package"](
        path="data/student_dataset_exports/student_release_initial_history"
    )

    assert response.status_code == 200
    assert captured["raw"] == "data/student_dataset_exports/student_release_initial_history"
    assert captured["path"] == Path("/tmp/student_release_initial_history")
    assert response.media_type == "application/zip"
    assert (
        response.headers["content-disposition"]
        == 'attachment; filename="student_release_initial_history.zip"'
    )


def test_clear_stalled_seed_job_route_marks_job_failed(session_factory):
    _seed_stale_seed_job_state(session_factory)
    app = create_app()
    routes = _route_map(app)
    session = session_factory()
    try:
        before = routes["/control/partials/orchestration"](
            request=_request("/control/partials/orchestration"),
            session=session,
            queries=ControlPanelQueries(),
        )
        response = routes["/control/jobs/clear-stalled"](
            request=_request("/control/jobs/clear-stalled", method="POST"),
            job_status_id=31,
            session=session,
            queries=ControlPanelQueries(),
        )
        job_status = session.execute(
            text("SELECT status, current_phase FROM job_status WHERE id = 31")
        ).one()
        stage_status = session.execute(
            text("SELECT status FROM job_stage_progress WHERE id = 31")
        ).scalar_one()
    finally:
        session.close()

    assert before.status_code == 200
    assert "Clear stalled job" in before.body.decode()
    assert response.status_code == 200
    assert "Cleared stalled seed_refresh job seed-refresh-stale." in response.body.decode()
    assert job_status == ("failed", "failed")
    assert stage_status == "failed"


def test_clear_stalled_generation_job_route_marks_run_and_batch_failed(session_factory):
    _seed_stale_generation_job_state(session_factory)
    app = create_app()
    routes = _route_map(app)
    session = session_factory()
    try:
        before = routes["/control/partials/orchestration"](
            request=_request("/control/partials/orchestration"),
            session=session,
            queries=ControlPanelQueries(),
        )
        response = routes["/control/jobs/clear-stalled"](
            request=_request("/control/jobs/clear-stalled", method="POST"),
            job_status_id=41,
            session=session,
            queries=ControlPanelQueries(),
        )
        run_status = session.execute(
            text("SELECT status FROM generation_runs WHERE id = 41")
        ).scalar_one()
        batch_status = session.execute(
            text("SELECT processing_status FROM monthly_batches WHERE id = 41")
        ).scalar_one()
        job_status = session.execute(
            text("SELECT status FROM job_status WHERE id = 41")
        ).scalar_one()
    finally:
        session.close()

    assert before.status_code == 200
    assert "Clear stalled job" in before.body.decode()
    assert response.status_code == 200
    assert "Cleared stalled generation_run job generation-run-stale." in response.body.decode()
    assert run_status == "failed"
    assert batch_status == "failed"
    assert job_status == "failed"


def test_clear_stalled_job_route_refuses_active_job(session_factory):
    _seed_idle_config_state(session_factory)
    app = create_app()
    routes = _route_map(app)
    session = session_factory()
    try:
        session.execute(
            text(
                """
                INSERT INTO job_status (
                    id, job_type, job_id, status, current_phase, percent_complete,
                    current_message, started_at, created_at, updated_at
                ) VALUES (
                    51, 'seed_refresh', 'seed-refresh-active', 'running',
                    'raw_seed_ingest', 0.00, 'Fresh seed job.',
                    CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
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
                    51, 51, NULL, NULL, 'raw_seed_ingest', 1, 'running',
                    0, 4, 'dataset', 0.00, CURRENT_TIMESTAMP,
                    'Fresh seed job.', CURRENT_TIMESTAMP,
                    CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                )
                """
            )
        )
        session.commit()
        response = routes["/control/jobs/clear-stalled"](
            request=_request("/control/jobs/clear-stalled", method="POST"),
            job_status_id=51,
            session=session,
            queries=ControlPanelQueries(),
        )
        job_status = session.execute(
            text("SELECT status FROM job_status WHERE id = 51")
        ).scalar_one()
    finally:
        session.close()

    assert response.status_code == 200
    assert "still has a fresh activity signal" in response.body.decode()
    assert job_status == "running"


def test_dismiss_failed_job_route_removes_failed_seed_job_from_snapshot(session_factory):
    _seed_idle_config_state(session_factory)
    app = create_app()
    routes = _route_map(app)
    session = session_factory()
    try:
        session.execute(
            text(
                """
                INSERT INTO job_status (
                    id, job_type, job_id, status, current_phase, percent_complete,
                    current_message, started_at, completed_at, error_message, created_at, updated_at
                ) VALUES (
                    61, 'seed_refresh', 'seed-refresh-failed', 'failed',
                    'failed', 0.00, 'Seed refresh failed.',
                    '2026-05-20 09:00:00', '2026-05-20 09:05:00', 'Seed refresh failed.',
                    CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
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
                    progress_message, error_message, started_at, completed_at, created_at, updated_at
                ) VALUES (
                    61, 61, NULL, NULL, 'seed_normalization', 2, 'failed',
                    0, 4, 'dataset', 0.00, CURRENT_TIMESTAMP,
                    'Seed refresh failed.', 'Seed refresh failed.',
                    '2026-05-20 09:00:00', '2026-05-20 09:05:00', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                )
                """
            )
        )
        session.execute(
            text(
                """
                INSERT INTO raw_seed_load_runs (
                    id, job_status_id, dataset_type, source_path, source_file_count, status,
                    rows_read, rows_loaded, rows_rejected, error_message,
                    started_at, completed_at, created_at, updated_at
                ) VALUES (
                    61, 61, 'first_names_us', 'data/raw/first_names/us.txt', 1, 'failed',
                    100, 0, 100, 'parse failed',
                    '2026-05-20 09:00:00', '2026-05-20 09:01:00', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                )
                """
            )
        )
        session.commit()

        before = routes["/control/partials/orchestration"](
            request=_request("/control/partials/orchestration"),
            session=session,
            queries=ControlPanelQueries(),
        )
        response = routes["/control/jobs/dismiss-failed"](
            request=_request("/control/jobs/dismiss-failed", method="POST"),
            job_status_id=61,
            session=session,
            queries=ControlPanelQueries(),
        )
        remaining_job_count = session.execute(
            text("SELECT COUNT(*) FROM job_status WHERE id = 61")
        ).scalar_one()
        orphaned_load_job_id = session.execute(
            text("SELECT job_status_id FROM raw_seed_load_runs WHERE id = 61")
        ).scalar_one()
    finally:
        session.close()

    assert before.status_code == 200
    assert "Dismiss failed job" in before.body.decode()
    assert response.status_code == 200
    assert "Dismissed failed seed_refresh job seed-refresh-failed." in response.body.decode()
    assert remaining_job_count == 0
    assert orphaned_load_job_id is None


def test_control_panel_config_validate_renders_validation_success(session_factory):
    _seed_idle_config_state(session_factory)
    app = create_app()
    routes = _route_map(app)
    session = session_factory()
    lifecycle = get_configuration_lifecycle()
    try:
        response = routes["/control/config/validate"](
            request=_request("/control/config/validate", method="POST"),
            config_title="March tuning",
            config_notes="adjusted player count",
            active_config_scope="synthetic",
            seed_config_json='{"raw_seed_data": {"raw_data_root": "data/raw", "supported_datasets": ["metro_areas_us"]}}',
            synthetic_config_json='{"runtime": {}, "simulation": {"simulation_name": "Editable Route Test", "simulation_version": "v2", "master_seed": 21, "historical_batch_count": 3, "first_batch_month": "2026-03-01"}, "player_generation": {"player_count": 1200}}',
            session=session,
            queries=ControlPanelQueries(),
            lifecycle=lifecycle,
        )
    finally:
        session.close()

    body = response.body.decode()
    assert response.status_code == 200
    assert "Validation passed." in body
    assert "Draft validated successfully and is ready to save." in body
    assert "Validate and Save" in body
    assert "March tuning" in body
    assert "Synthetic Workload Configuration" in body
    assert "Player and Match Generation" in body
    assert 'type="date"' in body
    assert 'value="v2"' in body
    assert "Valid input: whole number." in body
    assert "Monthly player growth rate" in body
    assert "Monthly player inactivation rate" in body
    assert 'data-config-section="synthetic:synthetic_simulation_identity"' in body


def test_control_panel_config_save_highlights_invalid_fields_without_persisting(session_factory):
    _seed_idle_config_state(session_factory)
    app = create_app()
    routes = _route_map(app)
    session = session_factory()
    lifecycle = get_configuration_lifecycle()
    try:
        response = routes["/control/config/save"](
            request=_request("/control/config/save", method="POST"),
            config_title="Broken tuning",
            config_notes="invalid month count",
            active_config_scope="synthetic",
            seed_config_json='{"raw_seed_data": {"raw_data_root": "data/raw", "supported_datasets": ["metro_areas_us"]}}',
            synthetic_config_json='{"runtime": {}, "simulation": {"simulation_name": "Editable Route Test", "simulation_version": "v2", "master_seed": 21, "historical_batch_count": 13, "first_batch_month": "2026-03-01"}, "player_generation": {"player_count": 1200}}',
            session=session,
            queries=ControlPanelQueries(),
            lifecycle=lifecycle,
        )
        current_version = lifecycle.load_current_valid_version(session)
    finally:
        session.close()

    body = response.body.decode()
    assert response.status_code == 200
    assert "Validation failed" in body
    assert "Validate and Save again" in body
    assert re.search(
        r'data-config-control[^>]*data-config-path="simulation.historical_batch_count"[^>]*data-config-invalid="true"',
        body,
    )
    assert re.search(
        r'data-config-section="synthetic:synthetic_simulation_identity"[^>]*data-config-section-invalid="true"',
        body,
    )
    assert "live monthly pipeline" in body
    assert current_version.title == "Editable config"
    assert current_version.version_number == 1


def test_control_panel_config_save_persists_new_version_when_idle(session_factory):
    _seed_idle_config_state(session_factory)
    app = create_app()
    routes = _route_map(app)
    session = session_factory()
    lifecycle = get_configuration_lifecycle()
    try:
        response = routes["/control/config/save"](
            request=_request("/control/config/save", method="POST"),
            config_title="April tuning",
            config_notes="saved",
            active_config_scope="synthetic",
            seed_config_json='{"raw_seed_data": {"raw_data_root": "data/raw", "supported_datasets": ["metro_areas_us", "first_names_us"]}}',
            synthetic_config_json='{"runtime": {}, "simulation": {"simulation_name": "Editable Route Test", "simulation_version": "v3", "master_seed": 21, "historical_batch_count": 4, "first_batch_month": "2026-03-01"}, "player_generation": {"player_count": 1400}}',
            session=session,
            queries=ControlPanelQueries(),
            lifecycle=lifecycle,
        )
        current_version = lifecycle.load_current_valid_version(session)
    finally:
        session.close()

    body = response.body.decode()
    assert response.status_code == 200
    assert "Configuration validated and saved as the current valid version." in body
    assert "April tuning" in body
    assert "Simulation Scale and Determinism" in body
    assert current_version.title == "April tuning"
    assert current_version.version_number == 2
    assert current_version.config_payload["simulation"]["simulation_version"] == "v3"


def test_control_panel_config_save_requires_title_and_marks_title_field(session_factory):
    _seed_idle_config_state(session_factory)
    app = create_app()
    routes = _route_map(app)
    session = session_factory()
    lifecycle = get_configuration_lifecycle()
    try:
        response = routes["/control/config/save"](
            request=_request("/control/config/save", method="POST"),
            config_title="",
            config_notes="missing title",
            active_config_scope="synthetic",
            seed_config_json='{"raw_seed_data": {"raw_data_root": "data/raw", "supported_datasets": ["metro_areas_us"]}}',
            synthetic_config_json='{"runtime": {}, "simulation": {"simulation_name": "Editable Route Test", "simulation_version": "v3", "master_seed": 21, "historical_batch_count": 4, "first_batch_month": "2026-03-01"}, "player_generation": {"player_count": 1400}}',
            session=session,
            queries=ControlPanelQueries(),
            lifecycle=lifecycle,
        )
        current_version = lifecycle.load_current_valid_version(session)
    finally:
        session.close()

    body = response.body.decode()
    assert response.status_code == 200
    assert "Configuration version title is required." in body
    assert re.search(
        r'<input[^>]*name="config_title"[^>]*border:1px solid #e07a75',
        body,
    )
    assert current_version.title == "Editable config"
    assert current_version.version_number == 1


def test_control_panel_config_save_is_blocked_while_run_active(session_factory):
    _seed_snapshot_state(session_factory)
    app = create_app()
    routes = _route_map(app)
    session = session_factory()
    lifecycle = get_configuration_lifecycle()
    try:
        response = routes["/control/config/save"](
            request=_request("/control/config/save", method="POST"),
            config_title="Blocked save",
            config_notes="should not persist",
            active_config_scope="seed",
            seed_config_json='{"raw_seed_data": {"raw_data_root": "data/raw"}}',
            synthetic_config_json='{"runtime": {}, "simulation": {"simulation_name": "Route Test", "simulation_version": "v2", "master_seed": 11, "historical_batch_count": 2, "first_batch_month": "2026-01-01"}, "player_generation": {"player_count": 1000}}',
            session=session,
            queries=ControlPanelQueries(),
            lifecycle=lifecycle,
        )
        current_version = lifecycle.load_current_valid_version(session)
    finally:
        session.close()

    body = response.body.decode()
    assert response.status_code == 200
    assert "Configuration editing is blocked while a generation run is active." in body
    assert "Seed Data Ingest and Preparation" in body
    assert current_version.title == "Read only config"


def test_control_panel_seed_config_partial_renders_current_values_in_controls(session_factory):
    _seed_idle_config_state(session_factory)
    app = create_app()
    routes = _route_map(app)
    session = session_factory()
    try:
        response = routes["/control/partials/config/seed"](
            request=_request("/control/partials/config/seed"),
            session=session,
            queries=ControlPanelQueries(),
        )
    finally:
        session.close()

    body = response.body.decode()
    assert response.status_code == 200
    assert "Seed Data Configuration" in body
    assert "Current draft matches the saved configuration." in body
    assert 'name="config_title"' in body
    assert 'value="Editable config"' in body
    assert "Supported raw seed datasets" in body
    assert "Club Facilities and Membership Policy" in body
    assert "Club size distribution and capacity ranges" in body
    assert "Distribution" in body
    assert "Club court ranges" in body
    assert "Allow cross-region club assignment" in body
    assert "Multi-club membership rate" in body
    assert "Name Assignment" not in body
    assert 'data-config-section="seed:seed_raw_ingest"' in body
    assert re.search(
        r'<details[^>]*data-config-section="seed:seed_raw_ingest"[^>]*open',
        body,
    )
    assert "Raw seed data root" not in body
    assert "Player and Match Generation" not in body


def test_control_panel_player_match_config_partial_renders_current_values_in_controls(session_factory):
    _seed_idle_config_state(session_factory)
    app = create_app()
    routes = _route_map(app)
    session = session_factory()
    try:
        response = routes["/control/partials/config/player-match"](
            request=_request("/control/partials/config/player-match"),
            session=session,
            queries=ControlPanelQueries(),
        )
    finally:
        session.close()

    body = response.body.decode()
    assert response.status_code == 200
    assert "Synthetic Workload Configuration" in body
    assert "Simulation Scale and Determinism" in body
    assert 'value="v1"' in body
    assert 'value="2026-03-01"' in body
    assert "Player Traits and Skill Seeding" in body
    assert "Dominant hand weights" in body
    assert "Player status weights" in body
    assert "Initial skill mean" in body
    assert "Games and Score Dynamics" in body
    assert "Games per match" in body
    assert "Win-by-two extension rate" not in body
    assert "Upset probability boost" not in body
    assert "Rating Initialization and Updates" in body
    assert "New-player K factor" in body
    assert "Confidence increment per match" in body
    assert "Matchmaking locality weight" in body
    assert "Match Scheduling" in body
    assert "Matches per team per month" in body
    assert "Saturday scheduling weight" in body
    assert "Max daily matches per team" in body
    assert "Generation run mode" not in body
    assert "Commit strategy" not in body
    assert "Batch retry max attempts" not in body
    assert "Allow destructive rerun" not in body
    assert "Multi-team player rate" not in body
    assert "Rating gap max" in body
    assert "Monthly team dissolution rate" not in body
    assert re.search(
        r'<details[^>]*data-config-section="synthetic:synthetic_simulation_identity"[^>]*open',
        body,
    )
    assert "Simulation version" in body
    assert "Supported raw seed datasets" not in body


def test_control_panel_tournament_config_partial_renders_current_values_in_controls(session_factory):
    _seed_idle_config_state(session_factory)
    app = create_app()
    routes = _route_map(app)
    session = session_factory()
    try:
        response = routes["/control/partials/config/tournament"](
            request=_request("/control/partials/config/tournament"),
            session=session,
            queries=ControlPanelQueries(),
        )
    finally:
        session.close()

    body = response.body.decode()
    assert response.status_code == 200
    assert "Tournament Configuration" in body
    assert "Tournament Simulation Rules" in body
    assert "Tournament Match Structure" in body
    assert "Tournament games per match" in body
    assert "Student Leaderboard Scoring" in body
    assert "Champion points" in body
    assert "Match win points" in body
    assert "Tournament Hidden Performance Bias" in body
    assert "Enable hidden performance bias" in body
    assert 'data-config-section="tournament:tournament_match_structure"' in body
    assert re.search(
        r'<details[^>]*data-config-section="tournament:tournament_match_structure"[^>]*open',
        body,
    )


def test_control_panel_generation_start_requires_destructive_confirmation(session_factory):
    _seed_idle_config_state(session_factory)
    app = create_app()
    routes = _route_map(app)
    session = session_factory()
    fake_service = FakeGenerationRunService()
    fake_runner = FakeBackgroundRunner()
    try:
        response = routes["/control/generation/start"](
            request=_request("/control/generation/start", method="POST"),
            generation_name="UI launch",
            destructive_confirm=None,
            session=session,
            queries=ControlPanelQueries(),
            run_service=fake_service,
            background_runner=fake_runner,
        )
    finally:
        session.close()

    body = response.body.decode()
    assert response.status_code == 200
    assert "Destructive reset confirmation is required before starting a generation run." in body
    assert fake_service.calls == []


def test_control_panel_seed_refresh_requires_destructive_confirmation(session_factory):
    _seed_idle_config_state(session_factory)
    app = create_app()
    routes = _route_map(app)
    session = session_factory()
    fake_service = FakeSeedRefreshService()
    fake_runner = FakeBackgroundRunner()
    try:
        response = routes["/control/seed/refresh"](
            request=_request("/control/seed/refresh", method="POST"),
            destructive_confirm=None,
            session=session,
            queries=ControlPanelQueries(),
            seed_service=fake_service,
            background_runner=fake_runner,
        )
    finally:
        session.close()

    body = response.body.decode()
    assert response.status_code == 200
    assert "Destructive reset confirmation is required before starting a seed data load." in body
    assert fake_service.calls == []
    assert fake_runner.submissions == []


def test_control_panel_seed_refresh_launches_when_allowed(session_factory):
    _seed_idle_config_state(session_factory)
    app = create_app()
    routes = _route_map(app)
    session = session_factory()
    fake_service = FakeSeedRefreshService()
    fake_runner = FakeBackgroundRunner()
    try:
        response = routes["/control/seed/refresh"](
            request=_request("/control/seed/refresh", method="POST"),
            destructive_confirm="yes",
            session=session,
            queries=ControlPanelQueries(),
            seed_service=fake_service,
            background_runner=fake_runner,
        )
    finally:
        session.close()

    body = response.body.decode()
    assert response.status_code == 200
    assert "Full seed refresh started in background." in body
    assert fake_service.calls == ["refresh"]
    assert len(fake_runner.submissions) == 1


def test_control_panel_seed_refresh_surfaces_service_failure(session_factory):
    _seed_idle_config_state(session_factory)
    app = create_app()
    routes = _route_map(app)
    session = session_factory()
    fake_service = FakeSeedRefreshService(error="seed refresh failed")
    fake_runner = FakeBackgroundRunner()
    try:
        response = routes["/control/seed/normalize"](
            request=_request("/control/seed/normalize", method="POST"),
            destructive_confirm="yes",
            session=session,
            queries=ControlPanelQueries(),
            seed_service=fake_service,
            background_runner=fake_runner,
        )
    finally:
        session.close()

    body = response.body.decode()
    assert response.status_code == 200
    assert "seed refresh failed" in body
    assert fake_service.calls == ["normalize"]


def test_control_panel_generation_start_launches_run_when_allowed(session_factory):
    _seed_idle_config_state(session_factory)
    app = create_app()
    routes = _route_map(app)
    session = session_factory()
    fake_service = FakeGenerationRunService()
    fake_runner = FakeBackgroundRunner()
    try:
        response = routes["/control/generation/start"](
            request=_request("/control/generation/start", method="POST"),
            generation_name="UI launch",
            destructive_confirm="yes",
            session=session,
            queries=ControlPanelQueries(),
            run_service=fake_service,
            background_runner=fake_runner,
        )
    finally:
        session.close()

    body = response.body.decode()
    assert response.status_code == 200
    assert "started in background" in body
    assert "UI launch" in body
    assert fake_service.calls == ["UI launch"]
    assert len(fake_runner.submissions) == 1


def test_control_panel_generation_start_surfaces_service_failure(session_factory):
    _seed_idle_config_state(session_factory)
    app = create_app()
    routes = _route_map(app)
    session = session_factory()
    fake_service = FakeGenerationRunService(error="pipeline failed")
    fake_runner = FakeBackgroundRunner()
    try:
        response = routes["/control/generation/start"](
            request=_request("/control/generation/start", method="POST"),
            generation_name="UI launch",
            destructive_confirm="yes",
            session=session,
            queries=ControlPanelQueries(),
            run_service=fake_service,
            background_runner=fake_runner,
        )
    finally:
        session.close()

    body = response.body.decode()
    assert response.status_code == 200
    assert "pipeline failed" in body
    assert fake_service.calls == ["UI launch"]
