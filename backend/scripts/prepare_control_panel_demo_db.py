"""Create a SQLite demo database for the control panel mock-up."""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path


DEMO_PAYLOAD = {
    "runtime": {},
    "simulation": {
        "simulation_name": "NAPA Demo Workload",
        "simulation_version": "demo-v1",
        "master_seed": 42,
        "historical_batch_count": 3,
        "first_batch_month": "2026-01-01",
        "target_total_players": 100,
    },
}


SCHEMA_STATEMENTS = (
    """
    CREATE TABLE raw_seed_load_runs (
        id integer primary key autoincrement,
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
    """,
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
    """,
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
    """,
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
    """,
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
    """,
    """
    CREATE TABLE configuration_profiles (
        id integer primary key autoincrement,
        profile_name varchar(255) not null unique,
        description text,
        is_active boolean not null default true,
        created_at datetime default current_timestamp not null,
        updated_at datetime default current_timestamp not null
    )
    """,
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
    """,
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
    """,
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
    """,
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
    """,
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
    """,
)


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: prepare_control_panel_demo_db.py /path/to/demo.db")
        return 2

    db_path = Path(sys.argv[1]).expanduser().resolve()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()

    with sqlite3.connect(db_path) as connection:
        for statement in SCHEMA_STATEMENTS:
            connection.execute(statement)

        connection.executemany(
            """
            INSERT INTO raw_seed_load_runs (
                id, dataset_type, source_path, source_file_count, status,
                rows_read, rows_loaded, rows_rejected, started_at, completed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                (1, "metro_areas_us", "data/raw/metro_areas/us.csv", 1, "completed", 120, 120, 0, "2026-05-20 08:00:00", "2026-05-20 08:03:00"),
                (2, "first_names_us", "data/raw/first_names/us.csv", 1, "completed", 500, 500, 0, "2026-05-20 08:03:00", "2026-05-20 08:06:00"),
                (3, "last_names_us", "data/raw/last_names/us.csv", 1, "completed", 300, 300, 0, "2026-05-20 08:06:00", "2026-05-20 08:08:00"),
                (4, "pickleball_club_distributions", "data/raw/pickleball_clubs/distributions.csv", 1, "completed", 50, 50, 0, "2026-05-20 08:08:00", "2026-05-20 08:10:00"),
            ),
        )
        connection.execute(
            """
            INSERT INTO regions (
                id, country_code, region_type, region_name, state_province_code, population, selection_probability
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (1, "US", "MSA", "Phoenix, AZ", "AZ", 5000000, 1.0),
        )
        connection.execute(
            """
            INSERT INTO clubs (
                id, club_name, region_id, club_type, competitiveness_level, member_capacity,
                indoor_court_count, outdoor_court_count
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (1, "Phoenix Pickleball Club", 1, "public_park", "recreational", 120, 0, 8),
        )
        connection.execute(
            """
            INSERT INTO first_names (
                id, country_code, state_province_code, birth_year, gender, first_name, frequency_count, normalized_probability, source_dataset
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (1, "US", "AZ", 1990, "M", "Alex", 25, 1.0, "demo_first_names_us"),
        )
        connection.execute(
            """
            INSERT INTO last_names (
                id, country_code, state_province_code, last_name, frequency_count, bias_multiplier,
                adjusted_frequency_count, normalized_probability, source_dataset
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (1, "US", "AZ", "Smith", 25, 1.0, 25.0, 1.0, "demo_last_names_us"),
        )

        connection.execute(
            """
            INSERT INTO configuration_profiles (
                id, profile_name, description, is_active
            ) VALUES (?, ?, ?, ?)
            """,
            (1, "default", "Demo configuration profile", 1),
        )
        connection.execute(
            """
            INSERT INTO configuration_profile_versions (
                id, profile_id, version_number, title, notes, config_schema_version, config_hash,
                config_payload, created_by, lifecycle_status, last_used_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                1,
                1,
                1,
                "May Demo Configuration",
                "Mock-up control panel dataset",
                "1.0",
                "demohash001",
                json.dumps(DEMO_PAYLOAD),
                "demo-seed",
                "valid",
                "2026-05-20 08:55:00",
            ),
        )
        connection.execute(
            """
            INSERT INTO generation_runs (
                id, generation_name, seed_value, simulation_version, parameter_snapshot,
                started_at, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                1,
                "May 2026 Full Refresh",
                42,
                "demo-v1",
                json.dumps(DEMO_PAYLOAD),
                "2026-05-20 09:00:00",
                "running",
            ),
        )
        connection.executemany(
            """
            INSERT INTO monthly_batches (
                id, generation_run_id, batch_month, batch_sequence, batch_type,
                active_player_count_start, new_player_count, active_player_count_end,
                match_count_generated, rating_update_count, assessment_update_count,
                processing_status, started_at, completed_at, error_message
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                (10, 1, "2026-01-01", 1, "historical_initial", 0, 40, 40, 160, 160, 40, "succeeded", "2026-05-20 09:01:00", "2026-05-20 09:06:00", None),
                (11, 1, "2026-02-01", 2, "historical_initial", 40, 30, 70, 220, 220, 70, "succeeded", "2026-05-20 09:06:00", "2026-05-20 09:13:00", None),
                (12, 1, "2026-03-01", 3, "historical_initial", 70, 30, 100, None, None, None, "running", "2026-05-20 09:13:00", None, None),
            ),
        )
        connection.execute(
            """
            INSERT INTO job_status (
                id, job_type, job_id, status, current_phase, percent_complete, current_message, started_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                100,
                "generation_run",
                "generation-run-1-demo",
                "running",
                "matches",
                73.33,
                "2026-03-01: matches running",
                "2026-05-20 09:00:00",
            ),
        )
        connection.executemany(
            """
            INSERT INTO job_stage_progress (
                id, job_status_id, generation_run_id, batch_id, stage_name, stage_sequence, status,
                progress_current, progress_total, progress_unit, progress_percent, last_heartbeat_at,
                progress_message, metadata_json, started_at, completed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                (1000, 100, 1, 10, "players", 1, "succeeded", 1, 1, "stage", 100.00, "2026-05-20 09:02:00", "players succeeded", '{"rows_loaded": 40}', "2026-05-20 09:01:00", "2026-05-20 09:02:00"),
                (1001, 100, 1, 10, "club_memberships", 2, "succeeded", 1, 1, "stage", 100.00, "2026-05-20 09:03:00", "club_memberships succeeded", '{"rows_loaded": 32}', "2026-05-20 09:02:00", "2026-05-20 09:03:00"),
                (1002, 100, 1, 10, "teams", 3, "succeeded", 1, 1, "stage", 100.00, "2026-05-20 09:04:00", "teams succeeded", '{"rows_loaded": 16, "membership_rows_loaded": 32}', "2026-05-20 09:03:00", "2026-05-20 09:04:00"),
                (1003, 100, 1, 10, "matches", 4, "succeeded", 1, 1, "stage", 100.00, "2026-05-20 09:05:00", "matches succeeded", '{"match_count": 160, "game_count": 240}', "2026-05-20 09:04:00", "2026-05-20 09:05:00"),
                (1004, 100, 1, 10, "ratings", 5, "succeeded", 1, 1, "stage", 100.00, "2026-05-20 09:06:00", "ratings succeeded", '{"rating_history_count": 160, "log_count": 160}', "2026-05-20 09:05:00", "2026-05-20 09:06:00"),
                (1010, 100, 1, 11, "players", 1, "succeeded", 1, 1, "stage", 100.00, "2026-05-20 09:07:00", "players succeeded", '{"rows_loaded": 30}', "2026-05-20 09:06:00", "2026-05-20 09:07:00"),
                (1011, 100, 1, 11, "club_memberships", 2, "succeeded", 1, 1, "stage", 100.00, "2026-05-20 09:08:00", "club_memberships succeeded", '{"rows_loaded": 56}', "2026-05-20 09:07:00", "2026-05-20 09:08:00"),
                (1012, 100, 1, 11, "teams", 3, "succeeded", 1, 1, "stage", 100.00, "2026-05-20 09:09:00", "teams succeeded", '{"rows_loaded": 28, "membership_rows_loaded": 56}', "2026-05-20 09:08:00", "2026-05-20 09:09:00"),
                (1013, 100, 1, 11, "matches", 4, "succeeded", 1, 1, "stage", 100.00, "2026-05-20 09:11:00", "matches succeeded", '{"match_count": 220, "game_count": 330}', "2026-05-20 09:09:00", "2026-05-20 09:11:00"),
                (1014, 100, 1, 11, "ratings", 5, "succeeded", 1, 1, "stage", 100.00, "2026-05-20 09:13:00", "ratings succeeded", '{"rating_history_count": 220, "log_count": 220}', "2026-05-20 09:11:00", "2026-05-20 09:13:00"),
                (1020, 100, 1, 12, "players", 1, "succeeded", 1, 1, "stage", 100.00, "2026-05-20 09:14:00", "players succeeded", '{"rows_loaded": 30}', "2026-05-20 09:13:00", "2026-05-20 09:14:00"),
                (1021, 100, 1, 12, "club_memberships", 2, "succeeded", 1, 1, "stage", 100.00, "2026-05-20 09:15:00", "club_memberships succeeded", '{"rows_loaded": 80}', "2026-05-20 09:14:00", "2026-05-20 09:15:00"),
                (1022, 100, 1, 12, "teams", 3, "succeeded", 1, 1, "stage", 100.00, "2026-05-20 09:16:00", "teams succeeded", '{"rows_loaded": 40, "membership_rows_loaded": 80}', "2026-05-20 09:15:00", "2026-05-20 09:16:00"),
                (1023, 100, 1, 12, "matches", 4, "running", 0, 1, "stage", 0.00, "2026-05-20 09:17:00", "matches running", None, "2026-05-20 09:16:00", None),
                (1024, 100, 1, 12, "ratings", 5, "pending", 0, 1, "stage", 0.00, None, "Pending execution.", None, None, None),
            ),
        )
        connection.commit()

    print(db_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
