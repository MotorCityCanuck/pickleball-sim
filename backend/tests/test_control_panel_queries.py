"""Tests for control panel read-side queries."""
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
import sys

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core import ConfigurationLifecycleService  # noqa: E402
from app.web import ControlPanelQueries  # noqa: E402


@pytest.fixture()
def session():
    engine = create_engine("sqlite:///:memory:", future=True)
    with engine.begin() as conn:
        conn.exec_driver_sql("PRAGMA foreign_keys = ON")
        conn.exec_driver_sql("ATTACH DATABASE ':memory:' AS ops")
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
        conn.exec_driver_sql(
            """
            CREATE TABLE student_dataset_comparisons (
                id integer primary key autoincrement,
                clean_export_path text not null,
                tainted_export_path text not null,
                clean_generation_run_id bigint,
                tainted_generation_run_id bigint,
                compared_release_count bigint not null default 0,
                total_issue_count bigint not null default 0,
                missing_clean_release_count bigint not null default 0,
                missing_tainted_release_count bigint not null default 0,
                status varchar(30) not null default 'succeeded',
                summary_payload text not null,
                error_message text,
                created_at datetime default current_timestamp not null,
                updated_at datetime default current_timestamp not null,
                foreign key(clean_generation_run_id) references generation_runs(id),
                foreign key(tainted_generation_run_id) references generation_runs(id)
            )
            """
        )
        conn.exec_driver_sql(
            """
            CREATE TABLE ops.background_workers (
                worker_id varchar(64) primary key,
                worker_type varchar(50) not null,
                host_name varchar(255),
                process_id integer,
                started_at datetime default current_timestamp not null,
                last_heartbeat_at datetime default current_timestamp not null,
                status varchar(30) default 'running' not null,
                metadata_json json,
                created_at datetime default current_timestamp not null,
                updated_at datetime default current_timestamp not null
            )
            """
        )
        conn.exec_driver_sql(
            """
            CREATE TABLE ops.background_job_leases (
                job_status_id bigint primary key,
                worker_id varchar(64) not null,
                lease_token varchar(64) not null,
                claimed_at datetime default current_timestamp not null,
                lease_expires_at datetime not null,
                last_heartbeat_at datetime default current_timestamp not null,
                attempt_count integer default 1 not null,
                metadata_json json,
                created_at datetime default current_timestamp not null,
                updated_at datetime default current_timestamp not null
            )
            """
        )
        conn.exec_driver_sql(
            """
            CREATE TABLE ops.realism_audit_query_runs (
                id integer primary key autoincrement,
                job_status_id bigint not null,
                generation_run_id bigint,
                batch_id bigint,
                query_index integer not null,
                query_name varchar(255) not null,
                status varchar(30) default 'pending' not null,
                started_at datetime,
                completed_at datetime,
                elapsed_ms bigint,
                row_count bigint,
                result_json json,
                error_message text,
                created_at datetime default current_timestamp not null,
                updated_at datetime default current_timestamp not null,
                unique (job_status_id, query_name)
            )
            """
        )
    session_factory = sessionmaker(bind=engine, autoflush=False, future=True)
    db_session = session_factory()
    try:
        yield db_session
    finally:
        db_session.close()


def _seed_valid_config(session):
    lifecycle = ConfigurationLifecycleService()
    payload = {
        "runtime": {},
        "simulation": {
            "simulation_name": "Control Panel Test",
            "simulation_version": "v1",
            "master_seed": 77,
            "historical_batch_count": 2,
            "first_batch_month": "2026-01-01",
        },
        "player_generation": {
            "player_count": 1000,
        },
    }
    lifecycle.save_new_version(
        session,
        title="Current config",
        notes=None,
        payload=payload,
    )
    session.commit()


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
                id, dataset_type, source_path, source_file_count, status, rows_read, rows_loaded, rows_rejected, started_at, completed_at, created_at, updated_at
            ) VALUES (
                1, 'metro_areas_us', 'data/raw/metro_areas/us.csv', 1, 'completed', 100, 100, 0,
                '2026-05-20 08:00:00', '2026-05-20 08:05:00', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
            """
        )
    )


def test_get_config_editor_state_uses_current_valid_version_title(session):
    _seed_valid_config(session)

    editor = ControlPanelQueries().get_config_editor_state(session)

    assert editor.title == "Current config"


def test_seed_raw_load_summary_includes_elapsed_duration(session):
    _seed_valid_config(session)
    session.execute(
        text(
            """
            INSERT INTO job_status (
                id, job_type, job_id, status, current_phase, percent_complete, current_message,
                started_at, completed_at, created_at, updated_at
            ) VALUES (
                901, 'seed_refresh', 'seed-refresh-901', 'succeeded', 'completed', 100.00,
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
                901, 901, 'metro_areas_us', 'data/raw/metro/us.csv', 1, 'completed',
                100, 98, 2, '2026-05-20 08:01:00', '2026-05-20 08:06:30', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
            """
        )
    )
    session.commit()

    snapshot = ControlPanelQueries(
        now_fn=lambda: datetime(2026, 5, 20, 8, 11, 0)
    ).get_control_panel_snapshot(session)

    assert len(snapshot.seed_data_summary.latest_raw_loads) == 1
    assert snapshot.seed_data_summary.latest_raw_loads[0].elapsed_label == "5m 30s"


def test_get_control_panel_snapshot_returns_ui_ready_state(session):
    _seed_valid_config(session)
    _seed_ready_reference_data(session)
    now = datetime(2026, 5, 20, 12, 0, 0)
    quiet_at = now - timedelta(minutes=25)
    stalled_at = now - timedelta(minutes=61)
    session.execute(
        text(
            """
            INSERT INTO generation_runs (
                id, generation_name, seed_value, simulation_version, status, started_at, created_at, updated_at
            ) VALUES (
                1, 'May generation', 77, 'v1', 'running', '2026-05-20 11:00:00', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
            """
        )
    )
    session.execute(
        text(
            """
            INSERT INTO monthly_batches (
                id, generation_run_id, batch_month, batch_sequence, batch_type, processing_status, started_at, created_at, updated_at
            ) VALUES
                (10, 1, '2026-01-01', 1, 'historical_initial', 'succeeded', '2026-05-20 11:01:00', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
                (11, 1, '2026-02-01', 2, 'historical_initial', 'running', '2026-05-20 11:15:00', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """
        )
    )
    session.execute(
        text(
            """
            INSERT INTO job_status (
                id, job_type, job_id, status, current_phase, percent_complete, current_message, started_at, created_at, updated_at
            ) VALUES (
                100, 'generation_run', 'generation-run-1-aaaa1111', 'running', 'matches', 60.00,
                '2026-02-01: matches running', '2026-05-20 11:00:00', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
            """
        )
    )
    session.execute(
        text(
            """
            INSERT INTO job_stage_progress (
                id, job_status_id, generation_run_id, batch_id, stage_name, stage_sequence, status,
                progress_current, progress_total, progress_unit, progress_percent, last_heartbeat_at,
                progress_message, metadata_json, started_at, completed_at, created_at, updated_at
            ) VALUES
                (1000, 100, 1, 10, 'players', 1, 'succeeded', 1, 1, 'stage', 100.00, '2026-05-20 11:02:00', 'players succeeded', '{"rows_loaded": 1250}', '2026-05-20 11:01:00', '2026-05-20 11:02:00', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
                (1003, 100, 1, 10, 'ratings', 5, 'succeeded', 1, 1, 'stage', 100.00, '2026-05-20 11:04:00', 'ratings succeeded', '{"match_count": 320, "rating_history_count": 2500, "log_count": 2500}', '2026-05-20 11:03:00', '2026-05-20 11:04:00', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
                (1001, 100, 1, 11, 'players', 1, 'succeeded', 1, 1, 'stage', 100.00, '2026-05-20 11:16:00', 'players succeeded', '{"rows_loaded": 1400}', '2026-05-20 11:15:00', '2026-05-20 11:16:00', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
                (1002, 100, 1, 11, 'matches', 4, 'running', 4800, 12000, 'match', 40.00, '2026-05-20 11:58:00', 'matches running', '{"heartbeat_quiet_after_seconds": 1200, "heartbeat_likely_stalled_after_seconds": 3600}', '2026-05-20 11:20:00', NULL, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """
        )
    )
    session.commit()

    queries = ControlPanelQueries(now_fn=lambda: now)
    snapshot = queries.get_control_panel_snapshot(session)

    assert snapshot.config_summary is not None
    assert snapshot.config_summary.title == "Current config"
    assert snapshot.config_summary.first_batch_month.isoformat() == "2026-01-01"
    assert snapshot.config_summary.player_count == 1000
    assert snapshot.config_summary.estimated_total_players == 1020
    assert snapshot.config_summary.estimated_total_teams == 982
    assert snapshot.config_summary.estimated_total_matches == 1964
    assert snapshot.config_summary.estimated_total_games == 2750
    assert snapshot.seed_data_summary.is_ready is True
    assert snapshot.generation_run_summary is not None
    assert snapshot.generation_run_summary.generation_run_id == 1
    assert snapshot.generation_run_summary.running_batch_count == 1
    assert snapshot.generation_run_summary.succeeded_batch_count == 1
    assert snapshot.generation_run_summary.overall_progress_percent == 60
    assert snapshot.generation_run_summary.completed_stage_count == 3
    assert snapshot.generation_run_summary.total_stage_count == 4
    assert snapshot.generation_run_summary.stage_progress_percent == 75
    assert snapshot.generation_run_summary.total_elapsed_label is None
    assert snapshot.active_job_summary is not None
    assert snapshot.active_job_summary.status == "running"
    assert snapshot.active_job_stage_progress == ()
    assert snapshot.allowed_actions.can_start_generation_run is False
    assert "A generation run is already running." in snapshot.allowed_actions.start_generation_blockers
    assert len(snapshot.batch_summaries) == 2
    second_batch = snapshot.batch_summaries[1]
    assert second_batch.batch_id == 11
    assert len(second_batch.stage_progress) == 2
    assert snapshot.batch_summaries[0].stage_progress[0].completion_message == "Rows created: 1,250"
    assert snapshot.batch_summaries[0].stage_progress[1].completion_message == "Ratings updated: 2,500"
    assert snapshot.batch_summaries[0].stage_progress[0].elapsed_label == "1m 00s"
    assert snapshot.batch_summaries[0].stage_progress[1].elapsed_label == "1m 00s"
    assert snapshot.batch_summaries[0].elapsed_label == "3m 00s"
    assert snapshot.batch_summaries[1].elapsed_label is None
    assert second_batch.stage_progress[1].stage_name == "matches"
    assert second_batch.stage_progress[1].is_stale is False
    assert second_batch.stage_progress[1].liveness_state == "active"
    assert snapshot.warnings == ()

    session.execute(
        text("UPDATE job_stage_progress SET last_heartbeat_at = :quiet_at WHERE id = 1002"),
        {"quiet_at": quiet_at},
    )
    session.commit()

    quiet_snapshot = queries.get_control_panel_snapshot(session)
    assert "One or more long-running stages have gone heartbeat-quiet." in quiet_snapshot.warnings
    assert quiet_snapshot.batch_summaries[1].stage_progress[1].liveness_state == "quiet"
    assert quiet_snapshot.batch_summaries[1].stage_progress[1].is_stale is False

    session.execute(
        text("UPDATE job_stage_progress SET last_heartbeat_at = :stalled_at WHERE id = 1002"),
        {"stalled_at": stalled_at},
    )
    session.commit()

    stalled_snapshot = queries.get_control_panel_snapshot(session)
    assert "One or more running stages now look likely stalled." in stalled_snapshot.warnings
    assert stalled_snapshot.batch_summaries[1].stage_progress[1].is_stale is True


def test_completed_generation_run_reports_total_elapsed_duration(session):
    _seed_valid_config(session)
    _seed_ready_reference_data(session)
    session.execute(
        text(
            """
            INSERT INTO generation_runs (
                id, generation_name, seed_value, simulation_version, status, started_at, completed_at, created_at, updated_at
            ) VALUES (
                2, 'Completed generation', 11, 'v1', 'succeeded',
                '2026-05-20 09:00:00', '2026-05-20 10:00:00', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
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
                200, 'generation_run', 'generation-run-200', 'succeeded', 'completed', 100.00,
                'Generation run completed successfully.',
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
                (2001, 200, 2, 21, 'players', 1, 'succeeded', 1, 1, 'stage', 100.00, 'players succeeded', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
                (2002, 200, 2, 22, 'matches', 4, 'succeeded', 1, 1, 'stage', 100.00, 'matches succeeded', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """
        )
    )
    session.commit()

    snapshot = ControlPanelQueries(
        now_fn=lambda: datetime(2026, 5, 20, 10, 1, 0)
    ).get_control_panel_snapshot(session)

    assert snapshot.generation_run_summary is not None
    assert snapshot.generation_run_summary.player_count == 1020
    assert snapshot.generation_run_summary.match_count == 1000
    assert snapshot.generation_run_summary.completed_stage_count == 2
    assert snapshot.generation_run_summary.total_stage_count == 2
    assert snapshot.generation_run_summary.total_elapsed_label == "1:00:00"


def test_get_control_panel_snapshot_reports_missing_valid_config(session):
    _seed_ready_reference_data(session)
    session.execute(
        text(
            """
            INSERT INTO generation_runs (
                id, generation_name, seed_value, simulation_version, status, completed_at, created_at, updated_at
            ) VALUES (
                2, 'Completed run', 99, 'v2', 'succeeded', '2026-05-19 12:00:00', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
            """
        )
    )
    session.execute(
        text(
            """
            INSERT INTO monthly_batches (
                id, generation_run_id, batch_month, batch_sequence, batch_type, processing_status, completed_at, created_at, updated_at
            ) VALUES (
                20, 2, '2026-03-01', 1, 'historical_initial', 'succeeded', '2026-05-19 11:00:00', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
            """
        )
    )
    session.commit()

    snapshot = ControlPanelQueries(now_fn=lambda: datetime(2026, 5, 20, 12, 0, 0)).get_control_panel_snapshot(session)

    assert snapshot.config_summary is None
    assert "No valid configuration is available." in snapshot.warnings
    assert snapshot.generation_run_summary is not None
    assert snapshot.generation_run_summary.status == "succeeded"
    assert snapshot.allowed_actions.can_start_generation_run is False
    assert "A single valid configuration is required." in snapshot.allowed_actions.start_generation_blockers
    assert snapshot.allowed_actions.can_generate_student_dataset is True


def test_student_dataset_export_summary_marks_stale_export_job_clearable(session):
    _seed_valid_config(session)
    _seed_ready_reference_data(session)
    session.execute(
        text(
            """
            INSERT INTO generation_runs (
                id, generation_name, seed_value, simulation_version, status, completed_at, created_at, updated_at
            ) VALUES (
                12, 'Export run', 42, 'v1', 'succeeded', '2026-05-20 10:00:00', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
            """
        )
    )
    session.execute(
        text(
            """
            INSERT INTO monthly_batches (
                id, generation_run_id, batch_month, batch_sequence, batch_type, processing_status, completed_at, created_at, updated_at
            ) VALUES (
                120, 12, '2026-03-01', 1, 'historical_initial', 'succeeded',
                '2026-05-20 10:00:00', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
            """
        )
    )
    session.execute(
        text(
            """
            INSERT INTO job_status (
                id, job_type, job_id, status, current_phase, percent_complete, current_message,
                started_at, created_at, updated_at
            ) VALUES (
                812, 'student_dataset_export', 'student-dataset-export-812', 'running',
                'write_validate_parquet', 33.33, 'Executing source query for release: clubs.',
                '2026-05-20 10:00:00', '2026-05-20 10:00:00', '2026-05-20 10:00:00'
            )
            """
        )
    )
    session.execute(
        text(
            """
            INSERT INTO job_stage_progress (
                job_status_id, generation_run_id, batch_id, stage_name, stage_sequence,
                status, progress_current, progress_total, progress_unit, progress_percent,
                progress_message, last_heartbeat_at, started_at, created_at, updated_at
            ) VALUES (
                812, 12, NULL, 'write_validate_parquet', 2,
                'running', 1, 7, 'release_family', 14.29,
                'Executing source query for release: clubs.',
                '2026-05-20 10:10:00', '2026-05-20 10:00:05', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
            """
        )
    )
    session.commit()

    summary = ControlPanelQueries(
        now_fn=lambda: datetime(2026, 5, 20, 11, 0, 0)
    ).get_student_dataset_export_summary(session)

    assert summary.latest_export_job is not None
    assert summary.latest_export_job_is_active is False
    assert summary.clearable_job is not None
    assert summary.clearable_job.job_status_id == 812


def test_student_dataset_export_job_prefers_newer_completed_job_over_older_running_job(session):
    session.execute(
        text(
            """
            INSERT INTO job_status (
                id, job_type, job_id, status, current_phase, percent_complete, current_message,
                started_at, completed_at, created_at, updated_at
            ) VALUES
                (
                    821, 'student_dataset_export', 'student-dataset-export-821', 'running',
                    'write_validate_parquet', 14.29, 'Older export still marked running.',
                    '2026-05-20 10:00:00', NULL, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                ),
                (
                    822, 'student_dataset_export', 'student-dataset-export-822', 'succeeded',
                    'completed', 100.00, 'Newest export completed successfully.',
                    '2026-05-20 11:00:00', '2026-05-20 11:30:00', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                )
            """
        )
    )
    session.commit()

    job = ControlPanelQueries(
        now_fn=lambda: datetime(2026, 5, 20, 12, 0, 0)
    ).get_student_dataset_export_job(session)

    assert job is not None
    assert job.job_status_id == 822
    assert job.status == "succeeded"


def test_get_control_panel_snapshot_includes_student_dataset_comparison_history(session):
    _seed_valid_config(session)
    _seed_ready_reference_data(session)
    session.execute(
        text(
            """
            INSERT INTO generation_runs (
                id, generation_name, seed_value, simulation_version, status, completed_at, created_at, updated_at
            ) VALUES (
                8, 'Comparison clean run', 12, 'v1', 'succeeded', '2026-05-20 10:00:00', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            ), (
                9, 'Comparison tainted run', 12, 'v1', 'succeeded', '2026-05-20 10:05:00', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
            """
        )
    )
    session.execute(
        text(
            """
            INSERT INTO student_dataset_releases (
                id, release_name, release_type, release_month, generation_run_id, data_quality_level,
                output_path, status, created_at, updated_at, completed_at
            ) VALUES
                (81, 'clean_snapshot', 'initial_snapshot', '2026-05-01', 8, 'none',
                 'data/student_dataset_exports/clean_snapshot', 'succeeded',
                 CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, '2026-05-20 10:10:00'),
                (82, 'tainted_snapshot', 'initial_snapshot', '2026-05-01', 9, 'medium',
                 'data/student_dataset_exports/tainted_snapshot', 'succeeded',
                 CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, '2026-05-20 10:12:00')
            """
        )
    )
    session.execute(
        text(
            """
            INSERT INTO student_dataset_comparisons (
                id, clean_export_path, tainted_export_path, clean_generation_run_id, tainted_generation_run_id,
                compared_release_count, total_issue_count, missing_clean_release_count, missing_tainted_release_count,
                status, summary_payload, error_message, created_at, updated_at
            ) VALUES (
                1,
                'data/student_dataset_exports/clean_snapshot',
                'data/student_dataset_exports/tainted_snapshot',
                8,
                9,
                1,
                3,
                0,
                0,
                'succeeded',
                :summary_payload,
                NULL,
                '2026-05-20 12:00:00',
                '2026-05-20 12:00:00'
            )
            """
        ),
        {
            "summary_payload": json.dumps(
                {
                    "releases": [
                        {
                            "release_type": "initial_snapshot",
                            "release_month": None,
                            "clean_release": {
                                "generation_run_id": 8,
                                "generation_name": "Comparison clean run",
                            },
                            "tainted_release": {
                                "generation_run_id": 9,
                                "generation_name": "Comparison tainted run",
                            },
                        }
                    ],
                    "missing_clean_releases": [],
                    "missing_tainted_releases": [],
                }
            )
        },
    )
    session.commit()

    snapshot = ControlPanelQueries(
        now_fn=lambda: datetime(2026, 5, 20, 12, 30, 0)
    ).get_control_panel_snapshot(session)

    assert len(snapshot.student_dataset_export_summary.comparison_history) == 1
    comparison = snapshot.student_dataset_export_summary.comparison_history[0]
    assert comparison.status == "succeeded"
    assert comparison.clean_generation_context == "#8 Comparison clean run"
    assert comparison.tainted_generation_context == "#9 Comparison tainted run"
    assert comparison.release_context == "initial_snapshot"
    assert comparison.total_issue_count == 3
    assert comparison.clean_export_path == "data/student_dataset_exports/clean_snapshot"


def test_get_control_panel_snapshot_tolerates_missing_comparison_history_table(session):
    _seed_valid_config(session)
    _seed_ready_reference_data(session)
    session.execute(text("DROP TABLE student_dataset_comparisons"))
    session.commit()

    snapshot = ControlPanelQueries(
        now_fn=lambda: datetime(2026, 5, 20, 12, 30, 0)
    ).get_control_panel_snapshot(session)

    assert snapshot.student_dataset_export_summary.comparison_history == ()


def test_realism_audit_summary_reports_active_lease_and_last_completed_query(session):
    now = datetime(2026, 6, 21, 12, 0, 0)
    session.execute(
        text(
            """
            INSERT INTO job_status (
                id, job_type, job_id, status, current_phase, percent_complete,
                current_message, started_at, created_at, updated_at
            ) VALUES (
                701, 'realism_audit', 'realism-audit-701', 'running',
                'run_realism_audit', 33.33, 'Running audit query.',
                '2026-06-21 11:55:00', '2026-06-21 11:55:00', '2026-06-21 11:55:00'
            )
            """
        )
    )
    session.execute(
        text(
            """
            INSERT INTO ops.background_workers (
                worker_id, worker_type, host_name, process_id, started_at,
                last_heartbeat_at, status, created_at, updated_at
            ) VALUES (
                'realism-worker-1', 'realism_audit', 'worker-host', 4242,
                '2026-06-21 11:54:00', '2026-06-21 11:59:00', 'running',
                '2026-06-21 11:54:00', '2026-06-21 11:59:00'
            )
            """
        )
    )
    session.execute(
        text(
            """
            INSERT INTO ops.background_job_leases (
                job_status_id, worker_id, lease_token, claimed_at, lease_expires_at,
                last_heartbeat_at, attempt_count, created_at, updated_at
            ) VALUES (
                701, 'realism-worker-1', 'token-701', '2026-06-21 11:55:00',
                '2026-06-21 12:10:00', '2026-06-21 11:59:00', 1,
                '2026-06-21 11:55:00', '2026-06-21 11:59:00'
            )
            """
        )
    )
    session.execute(
        text(
            """
            INSERT INTO ops.realism_audit_query_runs (
                id, job_status_id, generation_run_id, batch_id, query_index,
                query_name, status, completed_at, created_at, updated_at
            ) VALUES
                (1, 701, 2, 22, 1, 'player_roster_summary', 'succeeded',
                 '2026-06-21 11:56:00', '2026-06-21 11:55:00', '2026-06-21 11:56:00'),
                (2, 701, 2, 22, 2, 'match_volume_summary', 'succeeded',
                 '2026-06-21 11:58:00', '2026-06-21 11:56:00', '2026-06-21 11:58:00'),
                (3, 701, 2, 22, 3, 'rating_distribution', 'running',
                 NULL, '2026-06-21 11:58:00', '2026-06-21 11:58:00')
            """
        )
    )
    session.commit()

    summary = ControlPanelQueries(now_fn=lambda: now).get_realism_audit_summary(
        session,
        generation_run_id=2,
        batch_id=22,
    )

    assert summary.latest_incomplete_job_is_active is True
    assert summary.display_state == "running"
    assert summary.display_label == "Audit running"
    assert summary.clearable_job is None
    assert summary.lease_state is not None
    assert summary.lease_state.active_worker_id == "realism-worker-1"
    assert summary.lease_state.active_worker_label == "realism-worker-1 on worker-host"
    assert summary.lease_state.lease_is_active is True
    assert summary.lease_state.recoverable_stale_job is False
    assert summary.lease_state.last_completed_query == "match_volume_summary"


def test_realism_audit_summary_reports_recoverable_expired_lease(session):
    now = datetime(2026, 6, 21, 12, 30, 0)
    session.execute(
        text(
            """
            INSERT INTO job_status (
                id, job_type, job_id, status, current_phase, percent_complete,
                current_message, started_at, created_at, updated_at
            ) VALUES (
                702, 'realism_audit', 'realism-audit-702', 'running',
                'run_realism_audit', 53.33, 'Audit worker lease expired.',
                '2026-06-21 11:55:00', '2026-06-21 11:55:00', '2026-06-21 11:55:00'
            )
            """
        )
    )
    session.execute(
        text(
            """
            INSERT INTO ops.background_job_leases (
                job_status_id, worker_id, lease_token, claimed_at, lease_expires_at,
                last_heartbeat_at, attempt_count, created_at, updated_at
            ) VALUES (
                702, 'realism-worker-2', 'token-702', '2026-06-21 11:55:00',
                '2026-06-21 12:00:00', '2026-06-21 11:59:00', 1,
                '2026-06-21 11:55:00', '2026-06-21 11:59:00'
            )
            """
        )
    )
    session.commit()

    summary = ControlPanelQueries(now_fn=lambda: now).get_realism_audit_summary(
        session,
        generation_run_id=2,
        batch_id=22,
    )

    assert summary.latest_incomplete_job_is_active is False
    assert summary.display_state == "recoverable"
    assert summary.display_label == "Audit recoverable"
    assert summary.clearable_job is not None
    assert summary.lease_state is not None
    assert summary.lease_state.lease_is_active is False
    assert summary.lease_state.recoverable_stale_job is True


def test_realism_audit_summary_reports_queued_pending_job(session):
    session.execute(
        text(
            """
            INSERT INTO job_status (
                id, job_type, job_id, status, current_phase, percent_complete,
                current_message, created_at, updated_at
            ) VALUES (
                703, 'realism_audit', 'realism-audit-703', 'pending',
                'queued', 0.00, 'Audit queued for durable worker.',
                '2026-06-21 12:00:00', '2026-06-21 12:00:00'
            )
            """
        )
    )
    session.commit()

    summary = ControlPanelQueries(
        now_fn=lambda: datetime(2026, 6, 21, 12, 1, 0)
    ).get_realism_audit_summary(
        session,
        generation_run_id=2,
        batch_id=22,
    )

    assert summary.latest_incomplete_job_is_active is True
    assert summary.display_state == "queued"
    assert summary.display_label == "Audit queued"
    assert summary.lease_state is not None
    assert summary.lease_state.recoverable_stale_job is False


def test_get_control_panel_snapshot_blocks_generation_when_seed_data_missing(session):
    _seed_valid_config(session)

    snapshot = ControlPanelQueries(now_fn=lambda: datetime(2026, 5, 20, 12, 0, 0)).get_control_panel_snapshot(session)

    assert snapshot.seed_data_summary.is_ready is False
    assert snapshot.allowed_actions.can_start_generation_run is False
    assert (
        "Seed/reference data must be prepared before synthetic generation can start."
        in snapshot.allowed_actions.start_generation_blockers
    )


def test_stale_running_generation_run_does_not_block_config_editing(session):
    _seed_valid_config(session)
    _seed_ready_reference_data(session)
    session.execute(
        text(
            """
            INSERT INTO generation_runs (
                id, generation_name, seed_value, simulation_version, status, started_at, created_at, updated_at
            ) VALUES (
                4, 'Stale running run', 88, 'v1', 'running', '2026-05-20 09:00:00', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
            """
        )
    )
    session.execute(
        text(
            """
            INSERT INTO monthly_batches (
                id, generation_run_id, batch_month, batch_sequence, batch_type, processing_status, completed_at, created_at, updated_at
            ) VALUES (
                40, 4, '2026-01-01', 1, 'historical_initial', 'succeeded', '2026-05-20 09:30:00', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
            """
        )
    )
    session.execute(
        text(
            """
            INSERT INTO job_status (
                id, job_type, job_id, status, current_phase, percent_complete, current_message,
                started_at, completed_at, created_at, updated_at
            ) VALUES (
                400, 'generation_run', 'generation-run-400', 'succeeded', 'completed', 100.00,
                'Generation run completed successfully.',
                '2026-05-20 09:00:00', '2026-05-20 09:30:00', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
            """
        )
    )
    session.execute(
        text(
            """
            INSERT INTO job_stage_progress (
                id, job_status_id, generation_run_id, batch_id, stage_name, stage_sequence, status,
                progress_current, progress_total, progress_unit, progress_percent, last_heartbeat_at,
                progress_message, started_at, completed_at, created_at, updated_at
            ) VALUES (
                4000, 400, 4, 40, 'matches', 4, 'succeeded', 1, 1, 'stage', 100.00,
                '2026-05-20 09:30:00', 'matches succeeded',
                '2026-05-20 09:10:00', '2026-05-20 09:30:00', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
            """
        )
    )
    session.commit()

    snapshot = ControlPanelQueries(
        now_fn=lambda: datetime(2026, 5, 20, 12, 0, 0)
    ).get_control_panel_snapshot(session)

    assert snapshot.generation_run_summary is not None
    assert snapshot.generation_run_summary.generation_run_id == 4
    assert snapshot.generation_run_summary.status == "running"
    assert snapshot.generation_run_summary.display_status == "completed"
    assert snapshot.generation_run_summary.status_detail is not None
    assert snapshot.allowed_actions.can_edit_config is True
    assert snapshot.allowed_actions.can_start_generation_run is True
    assert "A generation run is already running." not in snapshot.allowed_actions.start_generation_blockers


def test_get_control_panel_snapshot_includes_seed_job_stage_progress(session):
    _seed_valid_config(session)
    session.execute(
        text(
            """
            INSERT INTO job_status (
                id, job_type, job_id, status, current_phase, percent_complete, current_message,
                started_at, created_at, updated_at
            ) VALUES (
                200, 'seed_refresh', 'seed-refresh-200', 'running', 'seed_normalization', 50.00,
                'Normalizing staged seed datasets into reference tables.',
                '2026-05-20 09:00:00', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
            """
        )
    )
    session.execute(
        text(
            """
            INSERT INTO job_stage_progress (
                id, job_status_id, generation_run_id, batch_id, stage_name, stage_sequence, status,
                progress_current, progress_total, progress_unit, progress_percent, last_heartbeat_at,
                progress_message, metadata_json, started_at, completed_at, created_at, updated_at
            ) VALUES
                (2000, 200, NULL, NULL, 'raw_seed_ingest', 1, 'succeeded', 6, 6, 'dataset', 100.00, '2026-05-20 09:10:00', 'Loaded 6 raw seed datasets.', '{"completed_datasets": 6}', '2026-05-20 09:00:00', '2026-05-20 09:10:00', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
                (2001, 200, NULL, NULL, 'seed_normalization', 2, 'running', 2, 4, 'dataset', 50.00, '2026-05-20 09:12:00', 'Normalizing last_names (3/4)', '{"completed_datasets": 2}', '2026-05-20 09:10:00', NULL, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """
        )
    )
    session.commit()

    snapshot = ControlPanelQueries(now_fn=lambda: datetime(2026, 5, 20, 9, 13, 0)).get_control_panel_snapshot(session)

    assert snapshot.seed_data_summary.latest_seed_job is not None
    assert snapshot.seed_data_summary.latest_seed_job.job_type == "seed_refresh"
    assert snapshot.seed_data_summary.latest_seed_job_is_active is True
    assert len(snapshot.seed_data_summary.latest_seed_stage_progress) == 2
    assert snapshot.seed_data_summary.latest_seed_stage_progress[0].stage_name == "raw_seed_ingest"
    assert snapshot.seed_data_summary.latest_seed_stage_progress[0].completion_message == "Datasets completed: 6"
    assert snapshot.seed_data_summary.latest_seed_stage_progress[0].elapsed_label == "10m 00s"
    assert snapshot.seed_data_summary.latest_seed_stage_progress[1].stage_name == "seed_normalization"
    assert snapshot.seed_data_summary.latest_seed_stage_progress[1].progress_percent == 50


def test_get_control_panel_snapshot_includes_generation_setup_stage_progress(session):
    _seed_valid_config(session)
    _seed_ready_reference_data(session)
    session.execute(
        text(
            """
            INSERT INTO generation_runs (
                id, generation_name, seed_value, simulation_version, status, started_at, created_at, updated_at
            ) VALUES (
                3, 'Setup run', 77, 'v1', 'running', '2026-05-20 09:00:00', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
            """
        )
    )
    session.execute(
        text(
            """
            INSERT INTO job_status (
                id, job_type, job_id, status, current_phase, percent_complete, current_message,
                started_at, created_at, updated_at
            ) VALUES (
                300, 'generation_run', 'generation-run-300', 'running', 'destructive_reset', 0.00,
                'Resetting generated data from previous runs.',
                '2026-05-20 09:00:00', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
            """
        )
    )
    session.execute(
        text(
            """
            INSERT INTO job_stage_progress (
                id, job_status_id, generation_run_id, batch_id, stage_name, stage_sequence, status,
                progress_current, progress_total, progress_unit, progress_percent, last_heartbeat_at,
                progress_message, started_at, created_at, updated_at
            ) VALUES (
                3000, 300, 3, NULL, 'destructive_reset', 0, 'running', 0, 1, 'stage', 0.00,
                '2026-05-20 09:01:00', 'Resetting generated data from previous runs.',
                '2026-05-20 09:00:00', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
            """
        )
    )
    session.commit()

    snapshot = ControlPanelQueries(now_fn=lambda: datetime(2026, 5, 20, 9, 2, 0)).get_control_panel_snapshot(session)

    assert snapshot.active_job_summary is not None
    assert snapshot.active_job_summary.current_phase == "destructive_reset"
    assert len(snapshot.active_job_stage_progress) == 1
    assert snapshot.active_job_stage_progress[0].stage_name == "destructive_reset"
    assert snapshot.active_job_stage_progress[0].status == "running"


def test_stale_running_generation_setup_job_does_not_block_config_editing(session):
    _seed_valid_config(session)
    _seed_ready_reference_data(session)
    session.execute(
        text(
            """
            INSERT INTO generation_runs (
                id, generation_name, seed_value, simulation_version, status, started_at, created_at, updated_at
            ) VALUES (
                5, 'Stale setup run', 77, 'v1', 'running', '2026-05-20 09:00:00', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
            """
        )
    )
    session.execute(
        text(
            """
            INSERT INTO job_status (
                id, job_type, job_id, status, current_phase, percent_complete, current_message,
                started_at, created_at, updated_at
            ) VALUES (
                500, 'generation_run', 'generation-run-500', 'running', 'destructive_reset', 0.00,
                'Resetting generated data from previous runs.',
                '2026-05-20 09:00:00', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
            """
        )
    )
    session.execute(
        text(
            """
            INSERT INTO job_stage_progress (
                id, job_status_id, generation_run_id, batch_id, stage_name, stage_sequence, status,
                progress_current, progress_total, progress_unit, progress_percent, last_heartbeat_at,
                progress_message, started_at, created_at, updated_at
            ) VALUES (
                5000, 500, 5, NULL, 'destructive_reset', 0, 'running', 0, 1, 'stage', 0.00,
                '2026-05-20 09:01:00', 'Resetting generated data from previous runs.',
                '2026-05-20 09:00:00', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
            """
        )
    )
    session.commit()

    snapshot = ControlPanelQueries(
        now_fn=lambda: datetime(2026, 5, 20, 12, 0, 0)
    ).get_control_panel_snapshot(session)

    assert snapshot.generation_run_summary is not None
    assert snapshot.generation_run_summary.generation_run_id == 5
    assert snapshot.generation_run_summary.display_status == "stalled"
    assert snapshot.active_job_summary is None
    assert snapshot.allowed_actions.can_edit_config is True
    assert snapshot.allowed_actions.can_start_generation_run is True
    assert "A generation run is already running." not in snapshot.allowed_actions.start_generation_blockers


def test_seed_readiness_ignores_stale_failed_raw_load_when_reference_data_is_ready(session):
    _seed_valid_config(session)
    _seed_ready_reference_data(session)
    session.execute(
        text(
            """
            INSERT INTO raw_seed_load_runs (
                id, dataset_type, source_path, source_file_count, status, rows_read, rows_loaded, rows_rejected,
                error_message, started_at, completed_at, created_at, updated_at
            ) VALUES (
                2, 'first_names_us', 'data/raw/first_names/us.csv', 1, 'failed', 100, 0, 100,
                'parse failed', '2026-05-21 10:00:00', '2026-05-21 10:01:00', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
            """
        )
    )
    session.execute(
        text(
            """
            INSERT INTO job_status (
                id, job_type, job_id, status, current_phase, percent_complete, current_message,
                started_at, completed_at, created_at, updated_at
            ) VALUES (
                201, 'seed_refresh', 'seed-refresh-201', 'succeeded', 'completed', 100.00,
                'Seed refresh completed successfully.',
                '2026-05-21 09:00:00', '2026-05-21 09:30:00', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
            """
        )
    )
    session.commit()

    snapshot = ControlPanelQueries(
        now_fn=lambda: datetime(2026, 5, 21, 10, 5, 0)
    ).get_control_panel_snapshot(session)

    assert snapshot.seed_data_summary.is_ready is True
    assert "The latest raw seed ingest failed." not in snapshot.seed_data_summary.readiness_blockers
    assert snapshot.seed_data_summary.latest_raw_loads == ()


def test_seed_raw_loads_are_scoped_to_latest_seed_job_cycle(session):
    _seed_valid_config(session)
    _seed_ready_reference_data(session)
    session.execute(
        text(
            """
            INSERT INTO job_status (
                id, job_type, job_id, status, current_phase, percent_complete, current_message,
                started_at, completed_at, created_at, updated_at
            ) VALUES (
                211, 'seed_refresh', 'seed-refresh-211', 'succeeded', 'completed', 100.00,
                'Seed refresh completed successfully.',
                '2026-05-21 11:00:00', '2026-05-21 11:30:00', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
            """
        )
    )
    session.execute(
        text(
            """
            INSERT INTO raw_seed_load_runs (
                id, job_status_id, dataset_type, source_path, source_file_count, status, rows_read, rows_loaded, rows_rejected,
                started_at, completed_at, created_at, updated_at
            ) VALUES
                (11, 211, 'metro_areas_us', 'data/raw/metro/us.csv', 1, 'completed', 10, 10, 0,
                 '2026-05-21 11:00:00', '2026-05-21 11:01:00', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
                (12, 211, 'first_names_us', 'data/raw/first_names/us.txt', 1, 'completed', 20, 20, 0,
                 '2026-05-21 11:01:00', '2026-05-21 11:10:00', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
                (13, NULL, 'last_names_us', 'data/raw/last_names/us.csv', 1, 'failed', 30, 0, 30,
                 '2026-05-20 10:00:00', '2026-05-20 10:01:00', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """
        )
    )
    session.commit()

    snapshot = ControlPanelQueries(
        now_fn=lambda: datetime(2026, 5, 21, 11, 35, 0)
    ).get_control_panel_snapshot(session)

    assert [load.dataset_type for load in snapshot.seed_data_summary.latest_raw_loads] == [
        "metro_areas_us",
        "first_names_us",
    ]


def test_seed_job_prefers_newer_succeeded_job_over_older_failed_job_without_started_at(session):
    _seed_valid_config(session)
    _seed_ready_reference_data(session)
    session.execute(
        text(
            """
            INSERT INTO job_status (
                id, job_type, job_id, status, current_phase, percent_complete, current_message,
                completed_at, created_at, updated_at
            ) VALUES (
                301, 'raw_seed_ingest', 'raw-seed-ingest-301', 'failed', 'failed', 0.00,
                'Cleared stale pending job before retest.',
                '2026-05-20 12:06:48', '2026-05-20 12:06:48', CURRENT_TIMESTAMP
            )
            """
        )
    )
    session.execute(
        text(
            """
            INSERT INTO job_status (
                id, job_type, job_id, status, current_phase, percent_complete, current_message,
                started_at, completed_at, created_at, updated_at
            ) VALUES (
                302, 'seed_normalization', 'seed-normalization-302', 'succeeded', 'completed', 100.00,
                'Seed normalization completed for 4 datasets.',
                '2026-05-20 20:33:49', '2026-05-20 20:38:59', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
            """
        )
    )
    session.commit()

    snapshot = ControlPanelQueries(
        now_fn=lambda: datetime(2026, 5, 20, 20, 40, 0)
    ).get_control_panel_snapshot(session)

    assert snapshot.seed_data_summary.latest_seed_job is not None
    assert snapshot.seed_data_summary.latest_seed_job.job_status_id == 302
    assert snapshot.seed_data_summary.latest_seed_job.status == "succeeded"
    assert snapshot.seed_data_summary.is_ready is True


def test_stale_running_seed_job_does_not_block_config_editing(session):
    _seed_valid_config(session)
    _seed_ready_reference_data(session)
    session.execute(
        text(
            """
            INSERT INTO job_status (
                id, job_type, job_id, status, current_phase, percent_complete, current_message,
                started_at, created_at, updated_at
            ) VALUES (
                401, 'seed_refresh', 'seed-refresh-401', 'running', 'seed_normalization', 50.00,
                'Seed normalization appears stuck.',
                '2026-05-20 09:00:00', '2026-05-20 09:00:00', CURRENT_TIMESTAMP
            )
            """
        )
    )
    session.execute(
        text(
            """
            INSERT INTO job_stage_progress (
                id, job_status_id, generation_run_id, batch_id, stage_name, stage_sequence, status,
                progress_current, progress_total, progress_unit, progress_percent, last_heartbeat_at,
                progress_message, started_at, created_at, updated_at
            ) VALUES (
                4010, 401, NULL, NULL, 'seed_normalization', 2, 'running', 2, 4, 'dataset', 50.00,
                '2026-05-20 09:05:00', 'Seed normalization appears stuck.',
                '2026-05-20 09:00:00', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
            """
        )
    )
    session.commit()

    snapshot = ControlPanelQueries(
        now_fn=lambda: datetime(2026, 5, 20, 12, 0, 0)
    ).get_control_panel_snapshot(session)

    assert snapshot.seed_data_summary.latest_seed_job is not None
    assert snapshot.seed_data_summary.latest_seed_job.status == "running"
    assert snapshot.seed_data_summary.latest_seed_job_is_active is False
    assert snapshot.allowed_actions.can_edit_config is True
    assert snapshot.allowed_actions.can_start_generation_run is True
    assert "A seed preparation job is already running." not in snapshot.allowed_actions.seed_refresh_blockers
