"""Tests for reusable realism audit queries."""
import json
from pathlib import Path
import sys

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.generation import (  # noqa: E402
    REALISM_AUDIT_QUERIES,
    RealismAuditRunner,
    RealismAuditService,
    assess_realism_audit_payload,
    execution_to_json_ready,
    resolve_realism_audit_parameters,
    save_realism_audit_snapshot,
    snapshot_payload_to_markdown,
)


@pytest.fixture()
def session():
    engine = create_engine("sqlite:///:memory:", future=True)
    with engine.begin() as conn:
        conn.exec_driver_sql(
            """
            CREATE TABLE generation_runs (
                id integer primary key,
                generation_name varchar(255) not null,
                seed_value bigint not null,
                simulation_version varchar(100),
                parameter_snapshot json,
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
                batch_type varchar(30) not null default 'historical_initial',
                processing_status varchar(30) not null default 'succeeded',
                created_at datetime default current_timestamp not null,
                updated_at datetime default current_timestamp not null
            )
            """
        )
        conn.exec_driver_sql(
            """
            CREATE TABLE regions (
                id integer primary key,
                country_code varchar(10) not null,
                region_name varchar(255) not null,
                state_province_code varchar(10),
                selection_probability numeric(12, 8),
                latitude numeric(10, 6),
                longitude numeric(10, 6)
            )
            """
        )
        conn.exec_driver_sql(
            """
            CREATE TABLE players (
                id integer primary key,
                first_name varchar(100) not null,
                last_name varchar(100) not null,
                gender varchar(20),
                birth_date date not null,
                registration_date date not null,
                player_status varchar(30) not null,
                home_region_id bigint,
                generation_run_id bigint
            )
            """
        )
        conn.exec_driver_sql(
            """
            CREATE TABLE first_names (
                id integer primary key,
                country_code varchar(10) not null,
                state_province_code varchar(10),
                birth_year integer not null,
                gender varchar(20),
                first_name varchar(100) not null,
                normalized_probability numeric(12, 8)
            )
            """
        )
        conn.exec_driver_sql(
            """
            CREATE TABLE last_names (
                id integer primary key,
                country_code varchar(10) not null,
                state_province_code varchar(10),
                last_name varchar(100) not null,
                normalized_probability numeric(12, 8)
            )
            """
        )
        conn.exec_driver_sql(
            """
            CREATE TABLE player_registrations (
                id integer primary key,
                player_id bigint not null,
                batch_id bigint not null,
                registration_month date not null
            )
            """
        )
        conn.exec_driver_sql(
            """
            CREATE TABLE player_rating_history (
                id integer primary key,
                player_id bigint not null,
                rating_date date not null,
                rating_type varchar(50) not null,
                rating_value numeric(8, 3) not null,
                confidence_score numeric(8, 3),
                volatility_score numeric(8, 3),
                global_percentile numeric(5, 2),
                match_count_used integer,
                batch_id bigint not null
            )
            """
        )
        conn.exec_driver_sql(
            """
            CREATE TABLE clubs (
                id integer primary key,
                club_name varchar(255) not null,
                region_id bigint not null,
                member_capacity integer,
                generation_run_id bigint
            )
            """
        )
        conn.exec_driver_sql(
            """
            CREATE TABLE club_memberships (
                id integer primary key,
                player_id bigint not null,
                club_id bigint not null,
                start_date date not null,
                is_primary boolean,
                generation_run_id bigint
            )
            """
        )
        conn.exec_driver_sql(
            """
            CREATE TABLE teams (
                id integer primary key,
                team_type varchar(30) not null default 'competitive',
                team_division varchar(50) not null default 'open_doubles',
                team_status varchar(30) not null,
                country_code varchar(2),
                formation_date date not null,
                dissolution_date date,
                chemistry_score numeric(8, 4),
                persistence_probability numeric(5, 4),
                generation_run_id bigint
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
                left_date date
            )
            """
        )
        conn.exec_driver_sql(
            """
            CREATE TABLE team_lifecycle_events (
                id integer primary key,
                generation_run_id bigint not null,
                batch_id bigint not null,
                team_id bigint not null,
                event_date date not null,
                event_type varchar(30) not null
            )
            """
        )
        conn.exec_driver_sql(
            """
            CREATE TABLE audit_batch_team_rosters (
                generation_run_id bigint not null,
                batch_id bigint not null,
                batch_month date not null,
                team_id bigint not null,
                player_one_id bigint not null,
                player_two_id bigint not null,
                roster_key varchar(64) not null,
                created_at datetime default current_timestamp not null,
                updated_at datetime default current_timestamp not null,
                primary key (batch_id, team_id)
            )
            """
        )
        conn.exec_driver_sql(
            """
            CREATE TABLE matches (
                id integer primary key,
                match_date date not null,
                region_id bigint,
                match_type varchar(50) not null,
                winning_team_id bigint,
                predicted_winning_team_number integer,
                predicted_win_probability numeric(8, 4),
                batch_id bigint not null
            )
            """
        )
        conn.exec_driver_sql(
            """
            CREATE TABLE match_teams (
                id integer primary key,
                match_id bigint not null,
                team_number integer not null,
                team_score integer not null,
                pairing_source varchar(30),
                source_team_id bigint not null
            )
            """
        )
        conn.exec_driver_sql(
            """
            CREATE TABLE match_team_players (
                id integer primary key,
                match_team_id bigint not null,
                player_id bigint not null
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
                target_score integer not null,
                win_by integer not null
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
                calculation_version varchar(50)
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
                completed_at datetime
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
                row_count bigint,
                schema_hash varchar(128),
                checksum varchar(128)
            )
            """
        )

    db_session = sessionmaker(bind=engine, autoflush=False, future=True)()
    try:
        yield db_session
    finally:
        db_session.close()


def seed_audit_dataset(session) -> None:
    session.execute(
        text(
            """
            INSERT INTO generation_runs (
                id, generation_name, seed_value, simulation_version, parameter_snapshot, status, created_at, updated_at
            ) VALUES (
                1,
                'Audit Run',
                77,
                'v1',
                '{
                    "validation": {
                        "weekend_concentration_min": 0.45,
                        "weekend_concentration_max": 0.55,
                        "regional_strength_min_rated_players": 1
                    },
                    "ratings": {
                        "rating_movement_warning_threshold": 250,
                        "initial_rating_elite_min": 2000
                    },
                    "player_generation": {
                        "player_status_weights": {
                            "active": 0.75,
                            "injured": 0.125,
                            "inactive": 0.125,
                            "retired": 0.0
                        },
                        "gender_weights": {
                            "male": 0.5,
                            "female": 0.5
                        },
                        "age_distribution": {
                            "under_18": 0.0,
                            "18_29": 0.25,
                            "30_44": 0.125,
                            "45_59": 0.25,
                            "60_74": 0.375,
                            "75_plus": 0.0
                        }
                    },
                    "club_generation": {
                        "unaffiliated_player_rate": 0.10,
                        "multi_club_membership_rate": 0.20,
                        "secondary_membership_same_region_rate": 0.75,
                        "cross_region_assignment_enabled": true,
                        "max_club_fill_ratio": 1.0
                    },
                    "match_scheduling": {
                        "monthly_matches_per_active_player_mean": 8.0,
                        "monthly_matches_per_active_player_std_dev": 2.0,
                        "match_volume_noise_factor": 0.25,
                        "max_daily_matches_per_team": 1
                    },
                    "match_types": {
                        "weights": {
                            "recreational": 0.5,
                            "league": 0.5
                        }
                    }
                }',
                'succeeded',
                '2026-01-01 00:00:00',
                '2026-01-01 00:00:00'
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
                (10, 1, '2026-01-01', 1, 'historical_initial', 'succeeded', '2026-01-15 12:00:00', '2026-01-15 12:00:00')
            """
        )
    )
    session.execute(
        text(
            """
            INSERT INTO regions (id, country_code, region_name, state_province_code, selection_probability, latitude, longitude) VALUES
                (1, 'US', 'North Metro', 'NY', 0.50, 40.7128, -74.0060),
                (2, 'US', 'South Metro', 'FL', 0.30, 25.7617, -80.1918),
                (3, 'CA', 'West Metro', 'BC', 0.20, 49.2827, -123.1207)
            """
        )
    )
    session.execute(
        text(
            """
            INSERT INTO players (
                id, first_name, last_name, gender, birth_date, registration_date, player_status, home_region_id, generation_run_id
            ) VALUES
                (1, 'Alex', 'Smith', 'M', '2000-01-01', '2026-01-01', 'ACTIVE', 1, 1),
                (2, 'Blair', 'Jones', 'F', '1998-01-01', '2026-01-01', 'ACTIVE', 1, 1),
                (3, 'Casey', 'Lee', 'M', '1988-01-01', '2026-01-01', 'ACTIVE', 1, 1),
                (4, 'Devon', 'Kim', 'F', '1976-01-01', '2026-01-01', 'ACTIVE', 2, 1),
                (5, 'Emery', 'Patel', 'M', '1970-01-01', '2026-01-01', 'ACTIVE', 2, 1),
                (6, 'Finley', 'Brown', 'F', '1960-01-01', '2026-01-01', 'ACTIVE', 2, 1),
                (7, 'Gray', 'Miller', 'M', '1962-01-01', '2026-01-01', 'INJURED', 1, 1),
                (8, 'Harper', 'Davis', 'F', '1964-01-01', '2026-01-01', 'INACTIVE', 3, 1)
            """
        )
    )
    session.execute(
        text(
            """
            INSERT INTO player_registrations (
                id, player_id, batch_id, registration_month
            ) VALUES
                (100, 1, 10, '2026-01-01'),
                (101, 2, 10, '2026-01-01'),
                (102, 3, 10, '2026-01-01'),
                (103, 4, 10, '2026-01-01'),
                (104, 5, 10, '2026-01-01'),
                (105, 6, 10, '2026-01-01'),
                (106, 7, 10, '2026-01-01'),
                (107, 8, 10, '2026-01-01')
            """
        )
    )
    session.execute(
        text(
            """
            INSERT INTO first_names (
                id, country_code, state_province_code, birth_year, gender, first_name, normalized_probability
            ) VALUES
                (1, 'US', 'NY', 2000, 'M', 'Alex', 1.0),
                (2, 'US', 'NY', 1997, 'F', 'Blair', 1.0),
                (3, 'US', 'CA', 1988, 'M', 'Casey', 1.0),
                (4, 'US', 'TX', 1975, 'F', 'Devon', 1.0),
                (5, 'US', 'FL', 1970, 'M', 'Emery', 1.0),
                (6, 'US', 'FL', 1960, 'F', 'Finley', 1.0),
                (7, 'US', 'NY', 1962, 'M', 'Gray', 1.0),
                (8, 'CA', 'BC', 1964, 'F', 'Harper', 1.0)
            """
        )
    )
    session.execute(
        text(
            """
            INSERT INTO last_names (
                id, country_code, state_province_code, last_name, normalized_probability
            ) VALUES
                (1, 'US', 'NY', 'Smith', 1.0),
                (2, 'US', 'CA', 'Jones', 1.0),
                (3, 'US', 'NY', 'Lee', 1.0),
                (4, 'US', 'TX', 'Kim', 1.0),
                (5, 'US', 'FL', 'Patel', 1.0),
                (6, 'US', 'FL', 'Brown', 1.0),
                (7, 'US', 'NY', 'Miller', 1.0),
                (8, 'CA', 'BC', 'Davis', 1.0)
            """
        )
    )
    session.execute(
        text(
            """
            INSERT INTO player_rating_history (
                id, player_id, rating_date, rating_type, rating_value, confidence_score, volatility_score, global_percentile, match_count_used, batch_id
            ) VALUES
                (200, 1, '2026-01-01', 'initial', 1500, 0.20, 0.35, 55.0, 2, 10),
                (201, 2, '2026-01-01', 'initial', 1600, 0.20, 0.34, 63.0, 2, 10),
                (202, 3, '2026-01-01', 'initial', 1700, 0.20, 0.30, 72.0, 4, 10),
                (203, 4, '2026-01-01', 'initial', 1800, 0.20, 0.28, 78.0, 4, 10),
                (204, 5, '2026-01-01', 'initial', 2100, 0.20, 0.22, 96.0, 8, 10),
                (205, 6, '2026-01-01', 'initial', 900, 0.20, 0.45, 18.0, 1, 10),
                (206, 7, '2026-01-01', 'initial', 1400, 0.20, 0.39, 48.0, 1, 10),
                (207, 8, '2026-01-01', 'initial', 1300, 0.20, 0.41, 35.0, 1, 10)
            """
        )
    )
    session.execute(
        text(
            """
            INSERT INTO clubs (id, club_name, region_id, member_capacity, generation_run_id) VALUES
                (100, 'North Club', 1, 1, NULL),
                (101, 'South Club', 2, 2, NULL),
                (102, 'West Club', 3, 10, NULL)
            """
        )
    )
    session.execute(
        text(
            """
            INSERT INTO club_memberships (
                id, player_id, club_id, start_date, is_primary, generation_run_id
            ) VALUES
                (1000, 1, 100, '2026-01-01', 1, 1),
                (1001, 2, 100, '2026-01-01', 1, 1),
                (1002, 2, 101, '2026-01-01', 0, 1),
                (1003, 4, 101, '2026-01-01', 1, 1),
                (1004, 5, 102, '2026-01-01', 1, 1),
                (1005, 6, 102, '2026-01-01', 1, 1),
                (1006, 8, 102, '2026-01-01', 1, 1)
            """
        )
    )
    session.execute(
        text(
            """
            INSERT INTO teams (
                id, team_type, team_division, team_status, country_code, formation_date, dissolution_date, chemistry_score, persistence_probability, generation_run_id
            ) VALUES
                (500, 'competitive', 'mens_doubles', 'active', 'US', '2026-01-01', NULL, 0.82, 0.91, 1),
                (501, 'competitive', 'mens_doubles', 'active', 'US', '2026-01-01', NULL, 0.48, 0.66, 1),
                (502, 'competitive', 'mixed_doubles', 'active', 'US', '2026-01-01', NULL, 0.73, 0.84, 1)
            """
        )
    )
    session.execute(
        text(
            """
            INSERT INTO team_memberships (
                id, team_id, player_id, joined_date, left_date
            ) VALUES
                (2000, 500, 1, '2026-01-01', NULL),
                (2001, 500, 2, '2026-01-01', NULL),
                (2002, 501, 3, '2026-01-01', NULL),
                (2003, 501, 4, '2026-01-01', NULL),
                (2004, 502, 5, '2026-01-01', NULL),
                (2005, 502, 6, '2026-01-01', NULL)
            """
        )
    )
    session.execute(
        text(
            """
            INSERT INTO team_lifecycle_events (
                id, generation_run_id, batch_id, team_id, event_date, event_type
            ) VALUES
                (4000, 1, 10, 500, '2026-01-01', 'formed'),
                (4001, 1, 10, 501, '2026-01-01', 'formed'),
                (4002, 1, 10, 502, '2026-01-01', 'formed'),
                (4003, 1, 11, 502, '2026-02-01', 'dormant'),
                (4004, 1, 12, 502, '2026-03-01', 'reactivated')
            """
        )
    )
    session.execute(
        text(
            """
            INSERT INTO audit_batch_team_rosters (
                generation_run_id, batch_id, batch_month, team_id, player_one_id, player_two_id, roster_key
            ) VALUES
                (1, 10, '2026-01-01', 500, 1, 2, '1:2'),
                (1, 10, '2026-01-01', 501, 3, 4, '3:4'),
                (1, 10, '2026-01-01', 502, 5, 6, '5:6'),
                (1, 11, '2026-02-01', 500, 1, 2, '1:2'),
                (1, 11, '2026-02-01', 501, 3, 4, '3:4'),
                (1, 12, '2026-03-01', 500, 1, 2, '1:2'),
                (1, 12, '2026-03-01', 501, 3, 4, '3:4'),
                (1, 12, '2026-03-01', 502, 5, 6, '5:6')
            """
        )
    )
    session.execute(
        text(
            """
            INSERT INTO matches (
                id, match_date, region_id, match_type, winning_team_id, predicted_winning_team_number,
                predicted_win_probability, batch_id
            ) VALUES
                (2000, '2026-01-03', 1, 'recreational', 500, 1, 0.75, 10),
                (2001, '2026-01-03', 1, 'league', 501, 1, 0.80, 10)
            """
        )
    )
    session.execute(
        text(
            """
            INSERT INTO match_teams (
                id, match_id, team_number, team_score, pairing_source, source_team_id
            ) VALUES
                (3000, 2000, 1, 1, 'competitive_team', 500),
                (3001, 2000, 2, 0, 'competitive_team', 501),
                (3002, 2001, 1, 0, 'competitive_team', 500),
                (3003, 2001, 2, 1, 'competitive_team', 501)
            """
        )
    )
    session.execute(
        text(
            """
            INSERT INTO match_team_players (
                id, match_team_id, player_id
            ) VALUES
                (3500, 3000, 1),
                (3501, 3000, 2),
                (3502, 3001, 3),
                (3503, 3001, 4),
                (3504, 3002, 1),
                (3505, 3002, 2),
                (3506, 3003, 3),
                (3507, 3003, 4)
            """
        )
    )
    session.execute(
        text(
            """
            INSERT INTO match_games (
                id, match_id, game_number, team_one_score, team_two_score, winning_team_number, target_score, win_by
            ) VALUES
                (3600, 2000, 1, 11, 6, 1, 11, 2),
                (3601, 2001, 1, 10, 12, 2, 11, 2)
            """
        )
    )
    session.execute(
        text(
            """
            INSERT INTO ratings_update_log (
                id, generation_run_id, batch_id, match_id, match_number, match_date, player_id,
                match_team_id, team_number, rating_type, rating_before, rating_after, rating_delta,
                expected_score_share, actual_score_share, expected_raw_points, actual_raw_points,
                games_played, games_won, match_won, k_factor, confidence_before, confidence_after, calculation_version
            ) VALUES
                (4000, 1, 10, 2000, 1, '2026-01-03', 1, 3000, 1, 'match_update', 1500, 1524, 24, 0.75, 0.65, 11, 6, 1, 1, 1, 24, 0.20, 0.22, 'v1'),
                (4001, 1, 10, 2000, 1, '2026-01-03', 2, 3000, 1, 'match_update', 1600, 1626, 26, 0.75, 0.65, 11, 6, 1, 1, 1, 24, 0.20, 0.22, 'v1'),
                (4002, 1, 10, 2000, 1, '2026-01-03', 3, 3001, 2, 'match_update', 1700, 1676, -24, 0.25, 0.35, 6, 11, 1, 0, 0, 24, 0.60, 0.62, 'v1'),
                (4003, 1, 10, 2000, 1, '2026-01-03', 4, 3001, 2, 'match_update', 1800, 1774, -26, 0.25, 0.35, 6, 11, 1, 0, 0, 24, 0.60, 0.62, 'v1'),
                (4004, 1, 10, 2001, 2, '2026-01-03', 1, 3002, 1, 'match_update', 1524, 1264, -260, 0.80, 0.45, 10, 12, 1, 0, 0, 24, 0.22, 0.24, 'v1'),
                (4005, 1, 10, 2001, 2, '2026-01-03', 2, 3002, 1, 'match_update', 1626, 1371, -255, 0.80, 0.45, 10, 12, 1, 0, 0, 24, 0.22, 0.24, 'v1'),
                (4006, 1, 10, 2001, 2, '2026-01-03', 3, 3003, 2, 'match_update', 1676, 1936, 260, 0.20, 0.55, 12, 10, 1, 1, 1, 24, 0.65, 0.67, 'v1'),
                (4007, 1, 10, 2001, 2, '2026-01-03', 4, 3003, 2, 'match_update', 1774, 2029, 255, 0.20, 0.55, 12, 10, 1, 1, 1, 24, 0.65, 0.67, 'v1')
            """
        )
    )
    session.commit()


def test_realism_audit_runner_executes_expanded_queries_on_sqlite(session):
    seed_audit_dataset(session)
    runner = RealismAuditRunner(session)

    results = runner.run(
        query_names=[
            "player_status_distribution",
            "player_gender_distribution",
            "player_age_distribution",
            "club_fill_ratio_summary",
            "club_membership_geography",
            "match_type_distribution",
            "match_team_pairing_source_distribution",
            "matches_per_team_distribution",
            "matches_per_player_distribution",
            "daily_team_match_cap_violations",
            "upset_rate_summary",
            "rating_delta_summary",
            "rating_delta_by_confidence_band",
        ],
    )

    result_map = {result.query.name: result.rows for result in results}

    assert result_map["player_status_distribution"] == (
        {
            "player_status": "ACTIVE",
            "player_count": 6,
            "player_pct": 75.0,
            "configured_pct": 75.0,
            "pct_point_drift": 0.0,
        },
        {
            "player_status": "INJURED",
            "player_count": 1,
            "player_pct": 12.5,
            "configured_pct": 12.5,
            "pct_point_drift": 0.0,
        },
        {
            "player_status": "INACTIVE",
            "player_count": 1,
            "player_pct": 12.5,
            "configured_pct": 12.5,
            "pct_point_drift": 0.0,
        },
        {
            "player_status": "RETIRED",
            "player_count": 0,
            "player_pct": 0.0,
            "configured_pct": 0.0,
            "pct_point_drift": 0.0,
        },
    )
    assert result_map["player_gender_distribution"] == (
        {
            "gender": "M",
            "player_count": 4,
            "player_pct": 50.0,
            "configured_pct": 50.0,
            "pct_point_drift": 0.0,
        },
        {
            "gender": "F",
            "player_count": 4,
            "player_pct": 50.0,
            "configured_pct": 50.0,
            "pct_point_drift": 0.0,
        },
    )
    assert result_map["player_age_distribution"] == (
        {
            "age_bucket": "under_18",
            "player_count": 0,
            "player_pct": 0.0,
            "configured_pct": 0.0,
            "pct_point_drift": 0.0,
        },
        {
            "age_bucket": "18_29",
            "player_count": 2,
            "player_pct": 25.0,
            "configured_pct": 25.0,
            "pct_point_drift": 0.0,
        },
        {
            "age_bucket": "30_44",
            "player_count": 1,
            "player_pct": 12.5,
            "configured_pct": 12.5,
            "pct_point_drift": 0.0,
        },
        {
            "age_bucket": "45_59",
            "player_count": 2,
            "player_pct": 25.0,
            "configured_pct": 25.0,
            "pct_point_drift": 0.0,
        },
        {
            "age_bucket": "60_74",
            "player_count": 3,
            "player_pct": 37.5,
            "configured_pct": 37.5,
            "pct_point_drift": 0.0,
        },
        {
            "age_bucket": "75_plus",
            "player_count": 0,
            "player_pct": 0.0,
            "configured_pct": 0.0,
            "pct_point_drift": 0.0,
        },
    )
    assert result_map["club_fill_ratio_summary"] == (
        {
            "generation_run_id": 1,
            "club_count": 3,
            "capacity_tracked_club_count": 3,
            "zero_membership_club_count": 0,
            "avg_fill_ratio": 1.1,
            "max_fill_ratio": 2.0,
            "over_capacity_club_count": 1,
            "configured_max_fill_ratio": 1.0,
        },
    )
    assert result_map["club_membership_geography"] == (
        {
            "membership_count": 7,
            "primary_membership_count": 6,
            "secondary_membership_count": 1,
            "cross_region_membership_count": 3,
            "same_region_secondary_pct": 0.0,
            "configured_same_region_secondary_pct": 75.0,
        },
    )
    assert result_map["match_type_distribution"] == (
        {
            "batch_id": 10,
            "batch_month": "2026-01-01",
            "match_type": "recreational",
            "match_count": 1,
            "match_pct": 50.0,
            "configured_pct": 50.0,
            "pct_point_drift": 0.0,
        },
        {
            "batch_id": 10,
            "batch_month": "2026-01-01",
            "match_type": "league",
            "match_count": 1,
            "match_pct": 50.0,
            "configured_pct": 50.0,
            "pct_point_drift": 0.0,
        },
    )
    assert result_map["match_team_pairing_source_distribution"] == (
        {
            "pairing_source": "competitive_team",
            "match_team_count": 4,
            "match_team_pct": 100.0,
            "source_team_count": 4,
            "source_team_pct": 100.0,
        },
    )
    assert result_map["matches_per_team_distribution"] == (
        {
            "match_count_bucket": "0",
            "team_count": 1,
            "team_pct": 33.33,
        },
        {
            "match_count_bucket": "2",
            "team_count": 2,
            "team_pct": 66.67,
        },
    )
    assert result_map["matches_per_player_distribution"] == (
        {
            "match_count_bucket": "0",
            "player_count": 2,
            "player_pct": 33.33,
            "configured_match_mean": 8.0,
            "configured_match_std_dev": 2.0,
            "configured_match_volume_noise_factor": 0.25,
        },
        {
            "match_count_bucket": "1_2",
            "player_count": 4,
            "player_pct": 66.67,
            "configured_match_mean": 8.0,
            "configured_match_std_dev": 2.0,
            "configured_match_volume_noise_factor": 0.25,
        },
    )
    assert result_map["daily_team_match_cap_violations"] == (
        {
            "roster_key": "1:2",
            "player_one_id": 1,
            "player_two_id": 2,
            "match_date": "2026-01-03",
            "daily_match_count": 2,
            "configured_max_daily_matches": 1,
        },
        {
            "roster_key": "3:4",
            "player_one_id": 3,
            "player_two_id": 4,
            "match_date": "2026-01-03",
            "daily_match_count": 2,
            "configured_max_daily_matches": 1,
        },
    )
    assert result_map["upset_rate_summary"] == (
        {
            "batch_id": 10,
            "total_matches": 2,
            "upset_match_count": 1,
            "upset_match_pct": 50.0,
            "avg_predicted_win_probability": 0.775,
        },
    )
    assert result_map["rating_delta_summary"] == (
        {
            "batch_id": 10,
            "player_update_count": 8,
            "avg_abs_rating_delta": 141.25,
            "max_abs_rating_delta": 260,
            "large_delta_count": 4,
            "large_delta_pct": 50.0,
            "configured_warning_threshold": 250,
        },
    )
    assert result_map["rating_delta_by_confidence_band"] == (
        {
            "confidence_band": "0_24",
            "player_update_count": 4,
            "avg_abs_rating_delta": 141.25,
            "max_abs_rating_delta": 260,
        },
        {
            "confidence_band": "50_74",
            "player_update_count": 4,
            "avg_abs_rating_delta": 141.25,
            "max_abs_rating_delta": 260,
        },
    )


def test_player_age_distribution_uses_creation_month(session):
    seed_audit_dataset(session)
    session.execute(
        text(
            """
            UPDATE players
            SET registration_date = '2017-01-01'
            WHERE id = 1
            """
        )
    )
    session.commit()
    runner = RealismAuditRunner(session)

    results = runner.run(query_names=["player_age_distribution"])

    assert results[0].rows == (
        {
            "age_bucket": "under_18",
            "player_count": 0,
            "player_pct": 0.0,
            "configured_pct": 0.0,
            "pct_point_drift": 0.0,
        },
        {
            "age_bucket": "18_29",
            "player_count": 2,
            "player_pct": 25.0,
            "configured_pct": 25.0,
            "pct_point_drift": 0.0,
        },
        {
            "age_bucket": "30_44",
            "player_count": 1,
            "player_pct": 12.5,
            "configured_pct": 12.5,
            "pct_point_drift": 0.0,
        },
        {
            "age_bucket": "45_59",
            "player_count": 2,
            "player_pct": 25.0,
            "configured_pct": 25.0,
            "pct_point_drift": 0.0,
        },
        {
            "age_bucket": "60_74",
            "player_count": 3,
            "player_pct": 37.5,
            "configured_pct": 37.5,
            "pct_point_drift": 0.0,
        },
        {
            "age_bucket": "75_plus",
            "player_count": 0,
            "player_pct": 0.0,
            "configured_pct": 0.0,
            "pct_point_drift": 0.0,
        },
    )


def test_player_registration_age_distribution_uses_registration_date(session):
    seed_audit_dataset(session)
    session.execute(
        text(
            """
            UPDATE players
            SET registration_date = '2017-01-01'
            WHERE id = 1
            """
        )
    )
    session.commit()
    runner = RealismAuditRunner(session)

    results = runner.run(query_names=["player_registration_age_distribution"])

    assert results[0].rows == (
        {
            "age_bucket": "12_17",
            "player_count": 1,
            "player_pct": 12.5,
        },
        {
            "age_bucket": "18_29",
            "player_count": 1,
            "player_pct": 12.5,
        },
        {
            "age_bucket": "30_44",
            "player_count": 1,
            "player_pct": 12.5,
        },
        {
            "age_bucket": "45_59",
            "player_count": 2,
            "player_pct": 25.0,
        },
        {
            "age_bucket": "60_74",
            "player_count": 3,
            "player_pct": 37.5,
        },
    )


def test_realism_audit_runner_executes_name_and_longitudinal_queries(session):
    seed_audit_dataset(session)
    session.execute(
        text(
            """
            INSERT INTO monthly_batches (
                id, generation_run_id, batch_month, batch_sequence, batch_type, processing_status, created_at, updated_at
            ) VALUES
                (11, 1, '2026-02-01', 2, 'historical_initial', 'succeeded', '2026-02-15 12:00:00', '2026-02-15 12:00:00'),
                (12, 1, '2026-03-01', 3, 'historical_initial', 'succeeded', '2026-03-15 12:00:00', '2026-03-15 12:00:00')
            """
        )
    )
    session.execute(
        text(
            """
            INSERT INTO matches (
                id, match_date, region_id, match_type, winning_team_id, predicted_winning_team_number,
                predicted_win_probability, batch_id
            ) VALUES
                (2002, '2026-02-03', 1, 'recreational', 500, 1, 0.65, 11),
                (2003, '2026-03-03', 1, 'league', 501, 2, 0.55, 12)
            """
        )
    )
    session.execute(
        text(
            """
            INSERT INTO match_teams (
                id, match_id, team_number, team_score, pairing_source, source_team_id
            ) VALUES
                (3004, 2002, 1, 1, 'competitive_team', 500),
                (3005, 2002, 2, 0, 'competitive_team', 501),
                (3006, 2003, 1, 0, 'competitive_team', 500),
                (3007, 2003, 2, 1, 'competitive_team', 501)
            """
        )
    )
    session.execute(
        text(
            """
            INSERT INTO match_team_players (
                id, match_team_id, player_id
            ) VALUES
                (3508, 3004, 1),
                (3509, 3004, 2),
                (3510, 3005, 3),
                (3511, 3005, 4),
                (3512, 3006, 1),
                (3513, 3006, 2),
                (3514, 3007, 3),
                (3515, 3007, 4)
            """
        )
    )
    session.execute(
        text(
            """
            INSERT INTO player_rating_history (
                id, player_id, rating_date, rating_type, rating_value, confidence_score, batch_id
            ) VALUES
                (208, 1, '2026-02-03', 'match_update', 1540, 0.24, 11),
                (209, 2, '2026-02-03', 'match_update', 1640, 0.24, 11),
                (210, 3, '2026-02-03', 'match_update', 1660, 0.67, 11),
                (211, 4, '2026-02-03', 'match_update', 1760, 0.67, 11),
                (212, 1, '2026-03-03', 'match_update', 1530, 0.26, 12),
                (213, 2, '2026-03-03', 'match_update', 1630, 0.26, 12),
                (214, 3, '2026-03-03', 'match_update', 1670, 0.69, 12),
                (215, 4, '2026-03-03', 'match_update', 1770, 0.69, 12)
            """
        )
    )
    session.commit()

    runner = RealismAuditRunner(session)
    results = runner.run(
        query_names=[
            "player_name_uniqueness_summary",
            "player_first_name_alignment",
            "player_last_name_alignment",
            "match_volume_by_batch",
            "team_partner_continuity_by_batch",
            "repeat_partner_match_distribution",
            "rating_summary_by_batch",
            "rating_band_distribution_by_batch",
        ]
    )

    result_map = {result.query.name: result.rows for result in results}

    assert result_map["player_name_uniqueness_summary"] == (
        {
            "generation_run_id": 1,
            "player_count": 8,
            "distinct_first_name_count": 8,
            "distinct_last_name_count": 8,
            "distinct_full_name_count": 8,
            "max_players_sharing_full_name": 1,
            "max_full_name_player_pct": 12.5,
        },
    )
    assert result_map["player_first_name_alignment"] == (
        {
            "alignment_bucket": "exact_state_year",
            "player_count": 5,
            "player_pct": 62.5,
        },
        {
            "alignment_bucket": "state_gender_other_year",
            "player_count": 1,
            "player_pct": 12.5,
        },
        {
            "alignment_bucket": "country_year_other_state",
            "player_count": 1,
            "player_pct": 12.5,
        },
        {
            "alignment_bucket": "country_gender_other_state_year",
            "player_count": 1,
            "player_pct": 12.5,
        },
    )
    assert result_map["player_last_name_alignment"] == (
        {
            "alignment_bucket": "exact_state",
            "player_count": 6,
            "player_pct": 75.0,
        },
        {
            "alignment_bucket": "country_other_state",
            "player_count": 2,
            "player_pct": 25.0,
        },
    )
    assert result_map["match_volume_by_batch"] == (
        {
            "batch_id": 10,
            "batch_month": "2026-01-01",
            "match_count": 2,
            "unique_match_days": 1,
            "avg_matches_per_match_day": 2.0,
            "distinct_match_regions": 1,
        },
        {
            "batch_id": 11,
            "batch_month": "2026-02-01",
            "match_count": 1,
            "unique_match_days": 1,
            "avg_matches_per_match_day": 1.0,
            "distinct_match_regions": 1,
        },
        {
            "batch_id": 12,
            "batch_month": "2026-03-01",
            "match_count": 1,
            "unique_match_days": 1,
            "avg_matches_per_match_day": 1.0,
            "distinct_match_regions": 1,
        },
    )
    assert result_map["team_partner_continuity_by_batch"] == (
        {
            "batch_id": 10,
            "batch_month": "2026-01-01",
            "active_roster_count": 3,
            "persisted_roster_count": 0,
            "new_roster_count": 3,
            "persisted_roster_pct": None,
        },
        {
            "batch_id": 11,
            "batch_month": "2026-02-01",
            "active_roster_count": 2,
            "persisted_roster_count": 2,
            "new_roster_count": 0,
            "persisted_roster_pct": 100.0,
        },
        {
            "batch_id": 12,
            "batch_month": "2026-03-01",
            "active_roster_count": 3,
            "persisted_roster_count": 2,
            "new_roster_count": 1,
            "persisted_roster_pct": 66.67,
        },
    )
    assert result_map["repeat_partner_match_distribution"] == (
            {
                "pairing_source": "competitive_team",
                "match_class": "competitive",
                "prior_match_count_bucket": "3_5",
                "match_team_count": 2,
            "match_team_pct_within_source_class": 100.0,
            "avg_prior_match_count": 3.0,
        },
    )
    assert result_map["rating_summary_by_batch"] == (
        {
            "batch_id": 10,
            "batch_month": "2026-01-01",
            "rated_player_count": 8,
            "avg_rating": 1537.5,
            "min_rating": 900,
            "max_rating": 2100,
            "rating_range": 1200.0,
            "sub_1000_count": 1,
            "rating_2000_plus_count": 1,
        },
        {
            "batch_id": 11,
            "batch_month": "2026-02-01",
            "rated_player_count": 8,
            "avg_rating": 1537.5,
            "min_rating": 900,
            "max_rating": 2100,
            "rating_range": 1200.0,
            "sub_1000_count": 1,
            "rating_2000_plus_count": 1,
        },
        {
            "batch_id": 12,
            "batch_month": "2026-03-01",
            "rated_player_count": 8,
            "avg_rating": 1537.5,
            "min_rating": 900,
            "max_rating": 2100,
            "rating_range": 1200.0,
            "sub_1000_count": 1,
            "rating_2000_plus_count": 1,
        },
    )
    assert result_map["rating_band_distribution_by_batch"] == (
        {
            "batch_id": 10,
            "batch_month": "2026-01-01",
            "rating_band": "sub_1000",
            "player_count": 1,
            "player_pct": 12.5,
        },
        {
            "batch_id": 10,
            "batch_month": "2026-01-01",
            "rating_band": "1000_1499",
            "player_count": 2,
            "player_pct": 25.0,
        },
        {
            "batch_id": 10,
            "batch_month": "2026-01-01",
            "rating_band": "1500_1999",
            "player_count": 4,
            "player_pct": 50.0,
        },
        {
            "batch_id": 10,
            "batch_month": "2026-01-01",
            "rating_band": "2000_plus",
            "player_count": 1,
            "player_pct": 12.5,
        },
        {
            "batch_id": 11,
            "batch_month": "2026-02-01",
            "rating_band": "sub_1000",
            "player_count": 1,
            "player_pct": 12.5,
        },
        {
            "batch_id": 11,
            "batch_month": "2026-02-01",
            "rating_band": "1000_1499",
            "player_count": 2,
            "player_pct": 25.0,
        },
        {
            "batch_id": 11,
            "batch_month": "2026-02-01",
            "rating_band": "1500_1999",
            "player_count": 4,
            "player_pct": 50.0,
        },
        {
            "batch_id": 11,
            "batch_month": "2026-02-01",
            "rating_band": "2000_plus",
            "player_count": 1,
            "player_pct": 12.5,
        },
        {
            "batch_id": 12,
            "batch_month": "2026-03-01",
            "rating_band": "sub_1000",
            "player_count": 1,
            "player_pct": 12.5,
        },
        {
            "batch_id": 12,
            "batch_month": "2026-03-01",
            "rating_band": "1000_1499",
            "player_count": 2,
            "player_pct": 25.0,
        },
        {
            "batch_id": 12,
            "batch_month": "2026-03-01",
            "rating_band": "1500_1999",
            "player_count": 4,
            "player_pct": 50.0,
        },
        {
            "batch_id": 12,
            "batch_month": "2026-03-01",
            "rating_band": "2000_plus",
            "player_count": 1,
            "player_pct": 12.5,
        },
    )


def test_zero_match_player_breakdowns_explain_team_and_registration_gaps(session):
    seed_audit_dataset(session)
    session.execute(
        text(
            """
            INSERT INTO monthly_batches (
                id, generation_run_id, batch_month, batch_sequence, batch_type, processing_status, created_at, updated_at
            ) VALUES
                (11, 1, '2026-02-01', 2, 'historical_incremental', 'succeeded', '2026-02-15 12:00:00', '2026-02-15 12:00:00')
            """
        )
    )
    session.execute(
        text(
            """
            INSERT INTO players (
                id, first_name, last_name, gender, birth_date, registration_date, player_status, home_region_id, generation_run_id
            ) VALUES
                (9, 'Indy', 'Wilson', 'F', '1995-06-01', '2026-02-01', 'ACTIVE', 3, 1),
                (10, 'No', 'Rating', 'M', '1990-06-01', '2026-02-01', 'ACTIVE', 3, 1)
            """
        )
    )
    session.execute(
        text(
            """
            INSERT INTO player_registrations (
                id, player_id, batch_id, registration_month
            ) VALUES
                (108, 9, 11, '2026-02-01'),
                (109, 10, 11, '2026-02-01')
            """
        )
    )
    session.execute(
        text(
            """
            INSERT INTO player_rating_history (
                id, player_id, rating_date, rating_type, rating_value, confidence_score, batch_id
            ) VALUES
                (208, 9, '2026-02-01', 'initial', 1450, 0.20, 11)
            """
        )
    )
    session.execute(
        text(
            """
            INSERT INTO matches (
                id, match_date, region_id, match_type, winning_team_id, predicted_winning_team_number,
                predicted_win_probability, batch_id
            ) VALUES
                (2002, '2026-02-03', 1, 'recreational', 500, 1, 0.65, 11)
            """
        )
    )
    session.execute(
        text(
            """
            INSERT INTO match_teams (
                id, match_id, team_number, team_score, pairing_source, source_team_id
            ) VALUES
                (3004, 2002, 1, 1, 'competitive_team', 500),
                (3005, 2002, 2, 0, 'competitive_team', 501)
            """
        )
    )
    session.execute(
        text(
            """
            INSERT INTO match_team_players (
                id, match_team_id, player_id
            ) VALUES
                (3508, 3004, 1),
                (3509, 3004, 2),
                (3510, 3005, 3),
                (3511, 3005, 4)
            """
        )
    )
    session.commit()

    runner = RealismAuditRunner(session)
    results = runner.run(
        query_names=[
            "zero_match_players_by_registration_cohort",
            "zero_match_players_by_team_membership",
            "zero_match_players_by_competitive_team_status",
            "zero_match_players_by_ad_hoc_eligibility",
            "zero_match_players_by_club_affiliation",
        ]
    )

    result_map = {result.query.name: result.rows for result in results}

    assert result_map["zero_match_players_by_registration_cohort"] == (
        {
            "registration_cohort": "initial_batch",
            "active_player_count": 6,
            "zero_match_player_count": 2,
            "zero_match_player_pct": 33.33,
        },
        {
            "registration_cohort": "later_batch",
            "active_player_count": 2,
            "zero_match_player_count": 2,
            "zero_match_player_pct": 100.0,
        },
    )
    assert result_map["zero_match_players_by_team_membership"] == (
        {
            "team_membership_status": "teamed",
            "active_player_count": 6,
            "zero_match_player_count": 2,
            "zero_match_player_pct": 33.33,
        },
        {
            "team_membership_status": "unteamed",
            "active_player_count": 2,
            "zero_match_player_count": 2,
            "zero_match_player_pct": 100.0,
        },
    )
    assert result_map["zero_match_players_by_competitive_team_status"] == (
        {
            "competitive_team_status": "on_competitive_team",
            "active_player_count": 6,
            "zero_match_player_count": 2,
            "zero_match_player_pct": 33.33,
        },
        {
            "competitive_team_status": "not_on_competitive_team",
            "active_player_count": 2,
            "zero_match_player_count": 2,
            "zero_match_player_pct": 100.0,
        },
    )
    assert result_map["zero_match_players_by_ad_hoc_eligibility"] == (
        {
            "ad_hoc_eligibility_status": "ad_hoc_eligible",
            "active_player_count": 7,
            "zero_match_player_count": 3,
            "zero_match_player_pct": 42.86,
        },
        {
            "ad_hoc_eligibility_status": "missing_current_rating",
            "active_player_count": 1,
            "zero_match_player_count": 1,
            "zero_match_player_pct": 100.0,
        },
    )
    assert result_map["zero_match_players_by_club_affiliation"] == (
        {
            "club_affiliation_status": "affiliated",
            "active_player_count": 5,
            "zero_match_player_count": 2,
            "zero_match_player_pct": 40.0,
        },
        {
            "club_affiliation_status": "unaffiliated",
            "active_player_count": 3,
            "zero_match_player_count": 2,
            "zero_match_player_pct": 66.67,
        },
    )


def test_team_assignment_delay_summary_measures_time_to_first_team(session):
    seed_audit_dataset(session)
    session.execute(
        text(
            """
            INSERT INTO monthly_batches (
                id, generation_run_id, batch_month, batch_sequence, batch_type, processing_status, created_at, updated_at
            ) VALUES
                (11, 1, '2026-02-01', 2, 'historical_incremental', 'succeeded', '2026-02-15 12:00:00', '2026-02-15 12:00:00'),
                (12, 1, '2026-03-01', 3, 'historical_incremental', 'succeeded', '2026-03-15 12:00:00', '2026-03-15 12:00:00')
            """
        )
    )
    session.execute(
        text(
            """
            INSERT INTO players (
                id, first_name, last_name, gender, birth_date, registration_date, player_status, home_region_id, generation_run_id
            ) VALUES
                (9, 'Indy', 'Wilson', 'F', '1995-06-01', '2026-01-20', 'ACTIVE', 3, 1),
                (10, 'Jordan', 'Moore', 'M', '1992-04-10', '2026-01-10', 'ACTIVE', 2, 1)
            """
        )
    )
    session.execute(
        text(
            """
            INSERT INTO player_registrations (
                id, player_id, batch_id, registration_month
            ) VALUES
                (108, 9, 11, '2026-02-01'),
                (109, 10, 11, '2026-02-01')
            """
        )
    )
    session.execute(
        text(
            """
            INSERT INTO teams (
                id, team_status, formation_date, dissolution_date, generation_run_id
            ) VALUES
                (503, 'active', '2026-01-01', NULL, 1)
            """
        )
    )
    session.execute(
        text(
            """
            INSERT INTO team_memberships (
                id, team_id, player_id, joined_date, left_date
            ) VALUES
                (2006, 503, 10, '2026-02-20', NULL)
            """
        )
    )
    session.commit()

    runner = RealismAuditRunner(session)
    params = resolve_realism_audit_parameters(session)
    params["batch_id"] = 12
    results = runner.run(
        query_names=["team_assignment_delay_summary"],
        params=params,
    )

    assert results[0].rows == (
        {
            "batch_id": 12,
            "batch_month": "2026-03-01",
            "player_count": 8,
            "ever_teamed_player_count": 7,
            "still_unteamed_player_count": 1,
            "avg_days_to_first_team": 2.71,
            "avg_days_unteamed_including_unresolved": 5.88,
            "max_days_unteamed_including_unresolved": 28,
        },
    )


def test_realism_audit_runner_uses_latest_batch_when_scope_is_omitted(session):
    seed_audit_dataset(session)
    session.execute(
        text(
            """
            INSERT INTO monthly_batches (
                id, generation_run_id, batch_month, batch_sequence, batch_type, processing_status, created_at, updated_at
            ) VALUES
                (11, 1, '2026-02-01', 2, 'future_increment', 'pending', '2026-02-15 12:00:00', '2026-02-15 12:00:00')
            """
        )
    )
    session.commit()
    runner = RealismAuditRunner(session)

    with pytest.raises(ValueError, match="Unknown audit query"):
        runner.run(query_names=["does_not_exist"])

    results = runner.run(query_names=["match_volume_summary"])

    assert results[0].rows == (
        {
            "batch_id": 11,
            "batch_month": "2026-02-01",
            "match_count": 0,
            "unique_match_days": 0,
            "avg_matches_per_match_day": None,
            "distinct_match_regions": 0,
        },
    )


def test_realism_audit_runner_executes_phase3_release_certification_queries(session):
    seed_audit_dataset(session)
    session.execute(
        text(
            """
            INSERT INTO generation_runs (
                id, generation_name, seed_value, simulation_version, parameter_snapshot, status, created_at, updated_at
            ) VALUES (
                2,
                'Prior Audit Run',
                55,
                'v0',
                '{}',
                'succeeded',
                '2025-12-31 12:00:00',
                '2025-12-31 12:00:00'
            )
            """
        )
    )
    session.execute(
        text(
            """
            INSERT INTO players (
                id, first_name, last_name, gender, birth_date, registration_date, player_status, home_region_id, generation_run_id
            ) VALUES
                (101, 'Prior', 'One', 'M', '1990-01-01', '2025-12-01', 'ACTIVE', 1, 2),
                (102, 'Prior', 'Two', 'F', '1991-01-01', '2025-12-01', 'ACTIVE', 2, 2)
            """
        )
    )
    session.execute(
        text(
            """
            INSERT INTO teams (
                id, team_type, team_division, team_status, country_code, formation_date, dissolution_date, chemistry_score, persistence_probability, generation_run_id
            ) VALUES
                (900, 'competitive', 'womens_doubles', 'active', 'CA', '2025-12-01', NULL, 0.61, 0.70, 2)
            """
        )
    )
    session.execute(
        text(
            """
            INSERT INTO monthly_batches (
                id, generation_run_id, batch_month, batch_sequence, batch_type, processing_status, created_at, updated_at
            ) VALUES
                (20, 2, '2025-12-01', 1, 'historical_initial', 'succeeded', '2025-12-15 12:00:00', '2025-12-15 12:00:00')
            """
        )
    )
    session.execute(
        text(
            """
            INSERT INTO matches (
                id, match_date, region_id, match_type, winning_team_id, predicted_winning_team_number, predicted_win_probability, batch_id
            ) VALUES
                (9000, '2025-12-10', 2, 'recreational', 900, 1, 0.60, 20)
            """
        )
    )
    session.execute(
        text(
            """
            INSERT INTO student_dataset_releases (
                id, release_name, release_type, release_month, generation_run_id, data_quality_level, output_path, status, completed_at
            ) VALUES
                (1, 'baseline_clean', 'initial_snapshot', '2026-01-01', 1, 'none', '/tmp/baseline_clean', 'succeeded', '2026-01-20 12:00:00')
            """
        )
    )
    session.execute(
        text(
            """
            INSERT INTO student_dataset_release_files (
                id, release_id, table_name, file_path, row_count, schema_hash, checksum
            ) VALUES
                (1, 1, 'players', '/tmp/baseline_clean/players.parquet', 8, 'abc', 'chk1'),
                (2, 1, 'teams', '/tmp/baseline_clean/teams.parquet', 3, 'def', 'chk2')
            """
        )
    )
    session.commit()
    runner = RealismAuditRunner(session)

    results = runner.run(
        query_names=[
            "chemistry_effectiveness",
            "fatigue_effectiveness",
            "confidence_stability",
            "regional_strength_balance",
            "candidate_depth_by_country_division",
            "elite_player_depth",
            "alternate_candidate_depth",
            "missing_gold_inputs",
            "division_balance",
            "repeat_opponent_rate",
            "historical_run_size_regression",
            "historical_release_file_coverage",
        ]
    )

    result_map = {result.query.name: result.rows for result in results}

    assert result_map["chemistry_effectiveness"] == (
        {
            "chemistry_band": "medium",
            "team_match_count": 2,
            "avg_chemistry_score": 0.48,
            "avg_expected_win_probability": 0.225,
            "actual_win_rate": 0.5,
            "win_rate_minus_expected": 0.275,
        },
        {
            "chemistry_band": "high",
            "team_match_count": 2,
            "avg_chemistry_score": 0.82,
            "avg_expected_win_probability": 0.775,
            "actual_win_rate": 0.5,
            "win_rate_minus_expected": -0.275,
        },
    )
    assert result_map["fatigue_effectiveness"] == (
        {
            "workload_band": "0",
            "player_update_count": 8,
            "avg_recent_match_count": 0.0,
            "avg_score_share_delta": 0.0,
            "met_or_exceeded_expected_rate": 0.5,
        },
    )
    assert result_map["confidence_stability"][0]["confidence_band"] == "0_24"
    assert result_map["regional_strength_balance"][0]["region_id"] == 2
    assert result_map["candidate_depth_by_country_division"] == (
        {
            "country_code": "US",
            "team_division": "mens_doubles",
            "candidate_team_count": 2,
            "candidate_player_count": 4,
            "avg_team_rating": 1650.0,
        },
        {
            "country_code": "US",
            "team_division": "mixed_doubles",
            "candidate_team_count": 1,
            "candidate_player_count": 2,
            "avg_team_rating": 1500.0,
        },
    )
    assert result_map["elite_player_depth"] == (
        {
            "country_code": "US",
            "team_division": "mens_doubles",
            "elite_player_count": 0,
            "rostered_player_count": 4,
            "elite_player_pct": 0.0,
        },
        {
            "country_code": "US",
            "team_division": "mixed_doubles",
            "elite_player_count": 1,
            "rostered_player_count": 2,
            "elite_player_pct": 50.0,
        },
    )
    assert result_map["alternate_candidate_depth"] == (
        {
            "country_code": "US",
            "team_division": "mens_doubles",
            "ranked_team_count": 2,
            "alternate_team_count": 1,
        },
        {
            "country_code": "US",
            "team_division": "mixed_doubles",
            "ranked_team_count": 1,
            "alternate_team_count": 0,
        },
    )
    missing_inputs = {row["table_name"]: row for row in result_map["missing_gold_inputs"]}
    assert missing_inputs["players"]["row_count"] == 8
    assert missing_inputs["matches"]["missing_flag"] == 0
    assert result_map["division_balance"] == (
        {
            "country_code": "US",
            "team_division": "mens_doubles",
            "team_count": 2,
            "team_pct_within_country": 66.67,
        },
        {
            "country_code": "US",
            "team_division": "mixed_doubles",
            "team_count": 1,
            "team_pct_within_country": 33.33,
        },
    )
    assert result_map["repeat_opponent_rate"] == (
        {
            "meeting_count": 2,
            "matchup_pair_count": 1,
            "matchup_pair_pct": 100.0,
        },
    )
    assert result_map["historical_run_size_regression"][0]["generation_run_id"] == 2
    assert result_map["historical_run_size_regression"][1]["generation_run_id"] == 1
    assert result_map["historical_run_size_regression"][0]["player_count"] == 2
    assert result_map["historical_run_size_regression"][0]["team_count"] == 1
    assert result_map["historical_run_size_regression"][0]["match_count"] == 1
    assert result_map["historical_release_file_coverage"] == (
        {
            "generation_run_id": 1,
            "release_name": "baseline_clean",
            "release_type": "initial_snapshot",
            "data_quality_level": "none",
            "status": "succeeded",
            "file_count": 2,
            "total_row_count": 11,
        },
    )

    baseline_results = runner.run(
        query_names=["historical_baseline_scale_regression"],
        params={"generation_run_id": 2},
    )
    baseline_row = baseline_results[0].rows[0]
    assert baseline_row["generation_run_id"] == 2
    assert baseline_row["baseline_generation_run_id"] == 1
    assert baseline_row["baseline_release_name"] == "baseline_clean"
    assert baseline_row["player_count"] == 2
    assert baseline_row["team_count"] == 1
    assert baseline_row["match_count"] == 1
    assert baseline_row["prior_run_count"] == 1


def test_realism_audit_runner_executes_structural_integrity_queries(session):
    seed_audit_dataset(session)
    session.execute(
        text(
            """
            INSERT INTO teams (
                id, team_type, team_division, team_status, country_code, formation_date, dissolution_date, chemistry_score, persistence_probability, generation_run_id
            ) VALUES
                (610, 'competitive', 'mens_doubles', 'active', 'US', '2026-01-01', NULL, 0.55, 0.80, 1),
                (611, 'competitive', 'mixed_doubles', 'dissolved', 'US', '2026-01-01', '2026-01-15', 0.45, 0.40, 1)
            """
        )
    )
    session.execute(
        text(
            """
            INSERT INTO team_memberships (
                id, team_id, player_id, joined_date, left_date
            ) VALUES
                (2610, 610, 1, '2026-01-02', NULL),
                (2611, 611, 2, '2026-01-20', NULL)
            """
        )
    )
    session.execute(
        text(
            """
            INSERT INTO matches (
                id, match_date, region_id, match_type, winning_team_id, predicted_winning_team_number, predicted_win_probability, batch_id
            ) VALUES
                (6100, '2026-01-05', 1, 'league', 9999, 1, 0.65, 10)
            """
        )
    )
    session.execute(
        text(
            """
            INSERT INTO match_teams (
                id, match_id, team_number, team_score, pairing_source, source_team_id
            ) VALUES
                (61001, 6100, 1, 11, 'competitive', 1),
                (61002, 6100, 2, 9, 'competitive', 2)
            """
        )
    )
    session.execute(
        text(
            """
            INSERT INTO match_games (
                id, match_id, game_number, team_one_score, team_two_score, winning_team_number, target_score, win_by
            ) VALUES
                (610001, 6100, 1, 10, 10, 1, 11, 2)
            """
        )
    )
    session.commit()

    runner = RealismAuditRunner(session)
    results = runner.run(
        query_names=[
            "club_primary_membership_integrity",
            "team_current_roster_integrity",
            "team_membership_date_integrity",
            "match_winner_integrity",
            "match_game_score_integrity",
        ]
    )

    result_map = {result.query.name: result.rows for result in results}

    assert result_map["club_primary_membership_integrity"][0]["multi_primary_player_count"] == 0
    assert result_map["team_current_roster_integrity"] == (
        {
            "team_id": 610,
            "team_type": "competitive",
            "team_division": "mens_doubles",
            "team_status": "active",
            "country_code": "US",
            "formation_date": "2026-01-01",
            "dissolution_date": None,
            "current_member_count": 1,
        },
    )
    assert result_map["team_membership_date_integrity"] == (
        {
            "team_id": 611,
            "player_id": 2,
            "team_type": "competitive",
            "team_division": "mixed_doubles",
            "team_status": "dissolved",
            "formation_date": "2026-01-01",
            "dissolution_date": "2026-01-15",
            "joined_date": "2026-01-20",
            "left_date": None,
            "issue_type": "open_membership_on_dissolved_team",
        },
    )
    assert result_map["match_winner_integrity"] == (
        {
            "match_id": 6100,
            "match_date": "2026-01-05",
            "winning_team_id": 9999,
            "team_count": 2,
            "winning_team_row_count": 0,
            "winning_team_score": None,
            "opposing_team_score": 11,
            "issue_type": "winning_team_not_in_match",
        },
    )
    assert result_map["match_game_score_integrity"] == (
        {
            "match_id": 6100,
            "game_id": 610001,
            "game_number": 1,
            "team_one_score": 10,
            "team_two_score": 10,
            "winning_team_number": 1,
            "target_score": 11,
            "win_by": 2,
            "issue_type": "tied_score",
        },
    )


def test_realism_audit_parameter_resolution_uses_generation_run_snapshot(session):
    seed_audit_dataset(session)

    params = resolve_realism_audit_parameters(session)

    assert params["generation_run_id"] == 1
    assert params["batch_id"] == 10
    assert float(params["weekend_concentration_min"]) == pytest.approx(0.45)
    assert float(params["weekend_concentration_max"]) == pytest.approx(0.55)
    assert float(params["rating_delta_warning_threshold"]) == pytest.approx(250.0)
    assert float(params["initial_rating_elite_min"]) == pytest.approx(2000.0)
    assert params["regional_strength_min_rated_players"] == 1
    assert params["hidden_bias_enabled"] is False
    assert params["fatigue_bias_enabled"] is False
    assert params["regional_strength_bias_enabled"] is False
    assert params["partnership_affinity_bias_enabled"] is False
    assert params["age_advantage_bias_enabled"] is False
    assert params["experience_bias_enabled"] is False
    assert params["max_daily_matches_per_team"] == 1
    assert float(params["monthly_matches_per_active_player_mean"]) == pytest.approx(8.0)
    assert float(params["monthly_matches_per_active_player_std_dev"]) == pytest.approx(2.0)
    assert float(params["match_volume_noise_factor"]) == pytest.approx(0.25)
    assert params["player_status_target_pcts"] == {
        "ACTIVE": 75.0,
        "INJURED": 12.5,
        "INACTIVE": 12.5,
        "RETIRED": 0.0,
    }


def test_regional_strength_balance_uses_minimum_rated_player_threshold(session):
    seed_audit_dataset(session)
    runner = RealismAuditRunner(session)

    results = runner.run(
        query_names=["regional_strength_balance"],
        params={
            "generation_run_id": 1,
            "initial_rating_elite_min": 2000,
            "regional_strength_min_rated_players": 4,
        },
    )

    assert results[0].rows == (
        {
            "region_id": 1,
            "country_code": "US",
            "state_province_code": "NY",
            "region_name": "North Metro",
            "rated_player_count": 4,
            "avg_rating": 1550.0,
            "max_rating": 1700.0,
            "elite_player_pct": 0.0,
        },
    )


def test_realism_audit_parameter_resolution_defaults_to_latest_generation_run(session):
    seed_audit_dataset(session)
    session.execute(
        text(
            """
            INSERT INTO generation_runs (
                id, generation_name, seed_value, simulation_version, parameter_snapshot, status, created_at, updated_at
            ) VALUES (
                2,
                'Latest Audit Run',
                99,
                'v2',
                '{
                    "validation": {
                        "weekend_concentration_min": 0.52,
                        "weekend_concentration_max": 0.68
                    },
                    "ratings": {
                        "rating_movement_warning_threshold": 180
                    },
                    "match_scheduling": {
                        "monthly_matches_per_active_player_mean": 11.0,
                        "monthly_matches_per_active_player_std_dev": 3.5,
                        "match_volume_noise_factor": 0.05,
                        "max_daily_matches_per_team": 3
                    }
                }',
                'succeeded',
                '2026-02-01 00:00:00',
                '2026-02-01 00:00:00'
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
                (20, 2, '2026-03-01', 1, 'historical_initial', 'succeeded', '2026-03-15 12:00:00', '2026-03-15 12:00:00'),
                (21, 2, '2026-04-01', 2, 'future_increment', 'running', '2026-04-15 12:00:00', '2026-04-15 12:00:00')
            """
        )
    )
    session.commit()

    params = resolve_realism_audit_parameters(session)

    assert params["generation_run_id"] == 2
    assert params["batch_id"] == 21
    assert float(params["weekend_concentration_min"]) == pytest.approx(0.52)
    assert float(params["weekend_concentration_max"]) == pytest.approx(0.68)
    assert float(params["rating_delta_warning_threshold"]) == pytest.approx(180.0)
    assert params["max_daily_matches_per_team"] == 3
    assert float(params["monthly_matches_per_active_player_mean"]) == pytest.approx(11.0)
    assert float(params["monthly_matches_per_active_player_std_dev"]) == pytest.approx(3.5)
    assert float(params["match_volume_noise_factor"]) == pytest.approx(0.05)
    assert params["hidden_bias_enabled"] is False


def test_realism_audit_parameter_resolution_skips_newer_runs_without_batches(session):
    seed_audit_dataset(session)
    session.execute(
        text(
            """
            INSERT INTO generation_runs (
                id, generation_name, seed_value, simulation_version, parameter_snapshot, status, created_at, updated_at
            ) VALUES (
                2,
                'New Empty Run',
                99,
                'v2',
                '{
                    "validation": {
                        "weekend_concentration_min": 0.52,
                        "weekend_concentration_max": 0.68
                    }
                }',
                'running',
                '2026-03-01 00:00:00',
                '2026-03-01 00:00:00'
            )
            """
        )
    )
    session.commit()

    params = resolve_realism_audit_parameters(session)

    assert params["generation_run_id"] == 1
    assert params["batch_id"] == 10
    assert float(params["weekend_concentration_min"]) == pytest.approx(0.45)
    assert float(params["weekend_concentration_max"]) == pytest.approx(0.55)


def test_realism_audit_service_returns_scope_metadata(session):
    seed_audit_dataset(session)
    service = RealismAuditService(session)

    execution = service.run(query_names=["match_volume_summary"])

    assert execution.generation_run_id == 1
    assert execution.batch_id == 10
    assert str(execution.batch_month) == "2026-01-01"
    assert execution.results[0].query.name == "match_volume_summary"


def test_realism_audit_execution_json_ready_includes_scope_metadata(session):
    seed_audit_dataset(session)
    service = RealismAuditService(session)

    execution = service.run(query_names=["weekend_match_share"])
    payload = execution_to_json_ready(execution)

    assert payload["generation_run_id"] == 1
    assert payload["batch_id"] == 10
    assert payload["batch_month"] == "2026-01-01"
    assert payload["executed_at"].endswith("+00:00")
    assert payload["process_type"] == "release_certification"
    assert set(payload["implemented_pillars"]) == {
        "structural_integrity",
        "operational_realism",
        "simulation_fidelity",
        "assignment_readiness",
        "export_readiness",
        "historical_regression",
    }
    assert payload["planned_pillars"] == []
    assert payload["results"][0]["pillar"] == "operational_realism"
    assert payload["results"][0]["query"] == "weekend_match_share"
    assert payload["assessment"]["overall_status"] in {
        "no_material_issues",
        "review_recommended",
        "significant_realism_concerns",
    }
    assert payload["assessment"]["certification_decision"] in {
        "PASS",
        "PASS_WITH_WARNINGS",
        "FAIL",
    }
    assert payload["assessment"]["policy_version"] == "2026-07-27"
    assert isinstance(payload["assessment"]["certification_score"], float)
    assert payload["assessment"]["pillar_counts"]["operational_realism"] == 1


def test_realism_audit_assessment_flags_threshold_findings():
    payload = {
        "results": [
            {
                "query": "player_gender_distribution",
                "category": "players",
                "pillar": "operational_realism",
                "rows": [
                    {
                        "gender": "female",
                        "player_pct": 62.0,
                        "configured_pct": 50.0,
                        "pct_point_drift": 12.0,
                    }
                ],
            },
            {
                "query": "daily_team_match_cap_violations",
                "category": "matches",
                "pillar": "operational_realism",
                "rows": [{"team_id": 12, "match_date": "2026-01-04"}],
            },
        ]
    }

    assessment = assess_realism_audit_payload(payload)

    assert assessment["overall_status"] == "significant_realism_concerns"
    assert assessment["certification_decision"] == "FAIL"
    assert assessment["certification_score"] == 75.0
    assert assessment["policy_reasons"]
    assert assessment["finding_count"] == 2
    assert assessment["severity_counts"]["blocker"] == 1
    assert assessment["severity_counts"]["error"] == 1
    assert assessment["pillar_counts"]["operational_realism"] == 2
    assert assessment["finding_pillar_counts"]["operational_realism"] == 2
    operational_realism = next(
        pillar
        for pillar in assessment["pillar_assessments"]
        if pillar["pillar"] == "operational_realism"
    )
    assert operational_realism["score"] == 75.0
    assert operational_realism["decision"] == "FAIL"
    assert [finding["query"] for finding in assessment["findings"]] == [
        "player_gender_distribution",
        "daily_team_match_cap_violations",
    ]


def test_realism_audit_assessment_allows_unaffiliated_zero_primary_players():
    zero_primary_payload = {
        "results": [
            {
                "query": "club_primary_membership_integrity",
                "category": "clubs",
                "pillar": "operational_realism",
                "rows": [
                    {
                        "zero_primary_player_count": 25,
                        "multi_primary_player_count": 0,
                    }
                ],
            }
        ]
    }

    zero_primary_assessment = assess_realism_audit_payload(zero_primary_payload)

    assert zero_primary_assessment["overall_status"] == "no_material_issues"
    assert zero_primary_assessment["finding_count"] == 0

    multi_primary_payload = {
        "results": [
            {
                "query": "club_primary_membership_integrity",
                "category": "clubs",
                "pillar": "operational_realism",
                "rows": [
                    {
                        "zero_primary_player_count": 25,
                        "multi_primary_player_count": 2,
                    }
                ],
            }
        ]
    }

    multi_primary_assessment = assess_realism_audit_payload(multi_primary_payload)

    assert multi_primary_assessment["overall_status"] == "significant_realism_concerns"
    assert multi_primary_assessment["finding_count"] == 1
    assert multi_primary_assessment["findings"][0]["severity"] == "blocker"


def test_realism_audit_assessment_computes_cross_pillar_certification_score():
    payload = {
        "results": [
            {
                "query": "chemistry_effectiveness",
                "category": "simulation",
                "pillar": "simulation_fidelity",
                "rows": [
                    {
                        "chemistry_band": "high",
                        "team_match_count": 8,
                        "avg_chemistry_score": 0.81,
                        "avg_expected_win_probability": 0.52,
                        "actual_win_rate": 0.52,
                        "win_rate_minus_expected": 0.0,
                    }
                ],
            },
            {
                "query": "team_assignment_delay_summary",
                "category": "teams",
                "pillar": "operational_realism",
                "rows": [
                    {
                        "player_count": 120,
                        "ever_teamed_player_count": 118,
                        "still_unteamed_player_count": 2,
                        "avg_days_to_first_team": 45.0,
                        "avg_days_unteamed_including_unresolved": 18.0,
                        "max_days_unteamed_including_unresolved": 45,
                    }
                ],
            },
            {
                "query": "historical_run_size_regression",
                "category": "historical",
                "pillar": "historical_regression",
                "rows": [
                    {
                        "generation_run_id": 2,
                        "player_count": 1000,
                        "team_count": 500,
                        "match_count": 2500,
                    },
                    {
                        "generation_run_id": 1,
                        "player_count": 800,
                        "team_count": 400,
                        "match_count": 2000,
                    },
                ],
            },
        ]
    }

    assessment = assess_realism_audit_payload(payload)

    assert assessment["certification_decision"] == "PASS_WITH_WARNINGS"
    assert assessment["certification_score"] == 96.7
    assert assessment["finding_count"] == 1
    by_pillar = {
        pillar["pillar"]: pillar
        for pillar in assessment["pillar_assessments"]
        if pillar["query_count"] > 0
    }
    assert by_pillar["simulation_fidelity"]["decision"] == "PASS"
    assert by_pillar["simulation_fidelity"]["score"] == 100.0
    assert by_pillar["operational_realism"]["decision"] == "PASS_WITH_WARNINGS"
    assert by_pillar["operational_realism"]["score"] == 90.0
    assert by_pillar["historical_regression"]["decision"] == "PASS"
    assert by_pillar["historical_regression"]["score"] == 100.0


def test_realism_audit_assessment_scores_structural_integrity_findings():
    payload = {
        "results": [
            {
                "query": "match_winner_integrity",
                "category": "matches",
                "pillar": "structural_integrity",
                "rows": [{"match_id": 99, "issue_type": "winning_team_not_in_match"}],
            }
        ]
    }

    assessment = assess_realism_audit_payload(payload)

    structural = next(
        pillar
        for pillar in assessment["pillar_assessments"]
        if pillar["pillar"] == "structural_integrity"
    )
    assert structural["query_count"] == 1
    assert structural["implementation_status"] == "implemented"
    assert structural["decision"] == "FAIL"
    assert structural["score"] == 75.0
    assert assessment["certification_score"] == 75.0
    assert assessment["certification_decision"] == "FAIL"


def test_realism_audit_assessment_expands_simulation_assignment_export_and_regression_rules():
    payload = {
        "results": [
            {
                "query": "chemistry_effectiveness",
                "category": "simulation_fidelity",
                "pillar": "simulation_fidelity",
                "rows": [
                    {
                        "chemistry_band": "high",
                        "team_match_count": 12,
                        "avg_chemistry_score": 0.82,
                        "avg_expected_win_probability": 0.70,
                        "actual_win_rate": 0.25,
                        "win_rate_minus_expected": -0.45,
                    }
                ],
            },
            {
                "query": "candidate_depth_by_country_division",
                "category": "assignment_readiness",
                "pillar": "assignment_readiness",
                "rows": [
                    {
                        "country_code": "US",
                        "team_division": "mens_doubles",
                        "candidate_team_count": 1,
                        "candidate_player_count": 2,
                        "avg_team_rating": 1600.0,
                    }
                ],
            },
            {
                "query": "missing_gold_inputs",
                "category": "export_readiness",
                "pillar": "export_readiness",
                "rows": [
                    {"table_name": "players", "row_count": 1000, "missing_flag": 0},
                    {"table_name": "matches", "row_count": 0, "missing_flag": 1},
                ],
            },
            {
                "query": "historical_run_size_regression",
                "category": "historical_regression",
                "pillar": "historical_regression",
                "rows": [
                    {
                        "generation_run_id": 10,
                        "generation_name": "Current",
                        "player_count": 1000,
                        "team_count": 500,
                        "match_count": 3000,
                        "player_growth_pct": 55.0,
                        "team_growth_pct": 20.0,
                        "match_growth_pct": 10.0,
                    }
                ],
            },
            {
                "query": "historical_baseline_scale_regression",
                "category": "historical_regression",
                "pillar": "historical_regression",
                "rows": [
                    {
                        "generation_run_id": 10,
                        "baseline_generation_run_id": 8,
                        "baseline_release_name": "baseline_clean",
                        "player_delta_vs_baseline_pct": 42.0,
                        "team_delta_vs_baseline_pct": 18.0,
                        "match_delta_vs_baseline_pct": 12.0,
                        "prior_run_count": 3,
                        "player_delta_vs_trend_pct": 28.0,
                        "team_delta_vs_trend_pct": 8.0,
                        "match_delta_vs_trend_pct": 4.0,
                    }
                ],
            },
        ]
    }

    assessment = assess_realism_audit_payload(payload)
    by_query = {finding["query"]: finding for finding in assessment["findings"]}

    assert by_query["chemistry_effectiveness"]["severity"] == "error"
    assert by_query["candidate_depth_by_country_division"]["severity"] == "warning"
    assert by_query["missing_gold_inputs"]["severity"] == "blocker"
    assert by_query["historical_run_size_regression"]["severity"] == "error"
    assert by_query["historical_baseline_scale_regression"]["severity"] == "error"
    assert assessment["certification_decision"] == "FAIL"
    assert assessment["finding_count"] == 5


def test_realism_audit_assessment_expands_additional_phase3_query_coverage():
    payload = {
        "results": [
            {
                "query": "fatigue_effectiveness",
                "category": "simulation_fidelity",
                "pillar": "simulation_fidelity",
                "rows": [
                    {"workload_band": "0", "avg_score_share_delta": -0.01, "met_or_exceeded_expected_rate": 0.51},
                    {"workload_band": "2_plus", "avg_score_share_delta": 0.08, "met_or_exceeded_expected_rate": 0.62},
                ],
            },
            {
                "query": "elite_team_depth",
                "category": "assignment_readiness",
                "pillar": "assignment_readiness",
                "rows": [
                    {"country_code": "US", "team_division": "mens_doubles", "candidate_team_count": 3, "elite_team_count": 0, "elite_team_pct": 0.0},
                ],
            },
            {
                "query": "student_candidate_availability",
                "category": "export_readiness",
                "pillar": "export_readiness",
                "rows": [
                    {"country_code": "US", "team_division": "mens_doubles", "candidate_team_count": 3, "fully_rated_team_count": 2, "fully_rated_team_pct": 66.67},
                ],
            },
            {
                "query": "historical_release_file_coverage",
                "category": "historical_regression",
                "pillar": "historical_regression",
                "rows": [
                    {
                        "generation_run_id": 1,
                        "release_name": "baseline",
                        "release_type": "initial_snapshot",
                        "data_quality_level": "none",
                        "status": "failed",
                        "file_count": 0,
                        "total_row_count": 0,
                    }
                ],
            },
        ]
    }

    assessment = assess_realism_audit_payload(payload)
    by_query = {finding["query"]: finding for finding in assessment["findings"]}

    assert by_query["fatigue_effectiveness"]["severity"] == "warning"
    assert by_query["elite_team_depth"]["severity"] == "warning"
    assert by_query["student_candidate_availability"]["severity"] == "warning"
    assert by_query["historical_release_file_coverage"]["severity"] == "error"
    assert assessment["certification_decision"] == "FAIL"
    assert any("clean pass threshold" in reason for reason in assessment["policy_reasons"])


def test_realism_audit_assessment_applies_bias_aware_simulation_thresholds():
    payload = {
        "parameters": {
            "hidden_bias_enabled": True,
            "fatigue_bias_enabled": True,
            "regional_strength_bias_enabled": True,
            "partnership_affinity_bias_enabled": True,
            "age_advantage_bias_enabled": False,
            "experience_bias_enabled": False,
        },
        "results": [
            {
                "query": "chemistry_effectiveness",
                "category": "simulation_fidelity",
                "pillar": "simulation_fidelity",
                "rows": [
                    {
                        "chemistry_band": "high",
                        "team_match_count": 12,
                        "avg_chemistry_score": 0.82,
                        "avg_expected_win_probability": 0.70,
                        "actual_win_rate": 0.40,
                        "win_rate_minus_expected": -0.30,
                    }
                ],
            },
            {
                "query": "fatigue_effectiveness",
                "category": "simulation_fidelity",
                "pillar": "simulation_fidelity",
                "rows": [
                    {"workload_band": "0", "avg_score_share_delta": 0.00},
                    {"workload_band": "2_plus", "avg_score_share_delta": 0.04},
                ],
            },
            {
                "query": "rating_predictiveness",
                "category": "simulation_fidelity",
                "pillar": "simulation_fidelity",
                "rows": [
                    {"prediction_bucket": "80_plus", "predicted_match_count": 100, "favorite_win_rate": 0.62},
                ],
            },
            {
                "query": "regional_strength_balance",
                "category": "simulation_fidelity",
                "pillar": "simulation_fidelity",
                "rows": [
                    {"region_id": 1, "avg_rating": 1700.0},
                    {"region_id": 2, "avg_rating": 900.0},
                ],
            },
        ],
    }

    assessment = assess_realism_audit_payload(payload)
    by_query = {item["query"]: item for item in assessment["query_assessments"]}

    assert by_query["chemistry_effectiveness"]["severity"] == "info"
    assert by_query["fatigue_effectiveness"]["severity"] == "warning"
    assert by_query["rating_predictiveness"]["severity"] == "info"
    assert by_query["regional_strength_balance"]["severity"] == "warning"
    assert assessment["bias_context"]["hidden_bias_enabled"] is True
    assert assessment["thresholds"]["chemistry_gap_warning"] == pytest.approx(0.35)
    assert assessment["thresholds"]["fatigue_reverse_gap_warning"] == pytest.approx(0.03)
    assert assessment["thresholds"]["rating_predictiveness_warning_min"] == pytest.approx(0.60)
    assert assessment["thresholds"]["regional_strength_spread_error"] == pytest.approx(850.0)


def test_realism_audit_query_registry_maps_phase3_queries_to_certification_pillars():
    pillar_map = {
        query.name: query.pillar
        for query in REALISM_AUDIT_QUERIES
        if query.name
        in {
            "match_winner_integrity",
            "chemistry_effectiveness",
            "candidate_depth_by_country_division",
            "missing_gold_inputs",
            "historical_run_size_regression",
            "historical_baseline_scale_regression",
        }
    }

    assert pillar_map == {
        "match_winner_integrity": "structural_integrity",
        "chemistry_effectiveness": "simulation_fidelity",
        "candidate_depth_by_country_division": "assignment_readiness",
        "missing_gold_inputs": "export_readiness",
        "historical_run_size_regression": "historical_regression",
        "historical_baseline_scale_regression": "historical_regression",
    }


def test_last_name_alignment_query_avoids_full_reference_materialization():
    query = next(
        query
        for query in REALISM_AUDIT_QUERIES
        if query.name == "player_last_name_alignment"
    )

    assert "EXISTS (" in query.sql
    assert "exact_reference AS" not in query.sql
    assert "country_reference AS" not in query.sql


def test_realism_audit_snapshot_is_saved_with_batch_metadata(session, tmp_path):
    seed_audit_dataset(session)
    service = RealismAuditService(session)

    execution = service.run(query_names=["weekend_match_share"])
    snapshot_path = save_realism_audit_snapshot(execution, snapshot_dir=tmp_path)
    payload = json.loads(snapshot_path.read_text())

    assert snapshot_path.parent.name == "generation_run_000001"
    assert "run_000001_batch_000010_2026-01-01_" in snapshot_path.name
    assert payload["generation_run_id"] == 1
    assert payload["batch_id"] == 10
    assert payload["batch_month"] == "2026-01-01"
    assert payload["query_count"] == 1
    assert payload["results"][0]["query"] == "weekend_match_share"
    assert payload["results"][0]["pillar"] == "operational_realism"
    assert "assessment" in payload
    assert payload["pillars"][0]["key"] == "structural_integrity"


def test_realism_audit_markdown_includes_assessment_findings():
    payload = {
        "executed_at": "2026-06-18T12:00:00+00:00",
        "generation_run_id": 2,
        "batch_id": 22,
        "batch_month": "2026-02-01",
        "release_comparison": [
            {
                "label": "Previous approved release",
                "summary": "Player and team counts stayed within tolerance.",
            }
        ],
        "results": [
            {
                "query": "club_fill_ratio_summary",
                "scope": "generation_run",
                "category": "clubs",
                "pillar": "operational_realism",
                "description": "Club fill summary.",
                "rows": [
                    {
                        "club_count": 8,
                        "over_capacity_club_count": 2,
                        "configured_max_fill_ratio": 1.1,
                    }
                ],
            }
        ],
    }

    markdown = snapshot_payload_to_markdown(payload)

    assert "## Executive Summary" in markdown
    assert "## Certification Dashboard" in markdown
    assert "## Findings by Pillar" in markdown
    assert "## Recommendations" in markdown
    assert "## Release Comparison" in markdown
    assert "## Certification Decision" in markdown
    assert "## Query Results" in markdown
    assert "### Pillar Coverage" in markdown
    assert "Operational Realism" in markdown
    assert "## Assessment Summary" in markdown
    assert "Certification decision" in markdown
    assert "Certification score" in markdown
    assert "Policy version" in markdown
    assert "## Assessment Findings" in markdown
    assert "Previous approved release" in markdown
    assert "Club Fill Ratio Summary" in markdown
    assert "over capacity" in markdown


def test_realism_audit_markdown_uses_historical_findings_for_release_comparison():
    payload = {
        "executed_at": "2026-06-18T12:00:00+00:00",
        "generation_run_id": 2,
        "batch_id": 22,
        "batch_month": "2026-02-01",
        "results": [
            {
                "query": "historical_run_size_regression",
                "scope": "generation_run",
                "category": "historical",
                "pillar": "historical_regression",
                "description": "Run-size regression summary.",
                "rows": [
                    {
                        "generation_run_id": 2,
                        "player_count": 1000,
                        "team_count": 500,
                        "match_count": 2500,
                    }
                ],
            }
        ],
        "assessment": {
            "overall_status": "review_recommended",
            "finding_count": 1,
            "severity_counts": {"info": 0, "warning": 1, "error": 0, "blocker": 0},
            "certification_score": 90.0,
            "certification_decision": "PASS_WITH_WARNINGS",
            "findings": [
                {
                    "query": "historical_run_size_regression",
                    "pillar": "historical_regression",
                    "category": "historical",
                    "severity": "warning",
                    "title": "Historical Run Size Regression",
                    "summary": "Current release is larger than the previous certified baseline.",
                    "evidence": "Player count increased by 25.0%.",
                    "recommendation": "Review whether release growth remains within approved tolerances.",
                }
            ],
            "pillar_assessments": [
                {
                    "pillar": "historical_regression",
                    "label": "Historical Regression",
                    "implementation_status": "implemented",
                    "query_count": 1,
                    "finding_count": 1,
                    "severity_counts": {"info": 0, "warning": 1, "error": 0, "blocker": 0},
                    "score": 90.0,
                    "decision": "PASS_WITH_WARNINGS",
                }
            ],
            "query_assessments": [
                {
                    "query": "historical_run_size_regression",
                    "pillar": "historical_regression",
                    "severity": "warning",
                    "summary": "Current release is larger than the previous certified baseline.",
                }
            ],
        },
    }

    markdown = snapshot_payload_to_markdown(payload)

    assert "## Release Comparison" in markdown
    assert "Historical Run Size Regression" in markdown
    assert "Current release is larger than the previous certified baseline." in markdown
    assert "## Recommendations" in markdown
    assert "Review whether release growth remains within approved tolerances." in markdown


def test_realism_audit_markdown_synthesizes_release_comparison_from_baseline_query():
    payload = {
        "executed_at": "2026-06-18T12:00:00+00:00",
        "generation_run_id": 2,
        "batch_id": 22,
        "batch_month": "2026-02-01",
        "results": [
            {
                "query": "historical_baseline_scale_regression",
                "scope": "generation_run",
                "category": "historical",
                "pillar": "historical_regression",
                "description": "Baseline regression summary.",
                "rows": [
                    {
                        "generation_run_id": 2,
                        "baseline_generation_run_id": 1,
                        "baseline_release_name": "baseline_clean",
                        "player_delta_vs_baseline_pct": 12.5,
                        "team_delta_vs_baseline_pct": 8.0,
                        "match_delta_vs_baseline_pct": -2.5,
                        "prior_run_count": 3,
                        "player_delta_vs_trend_pct": 10.0,
                        "team_delta_vs_trend_pct": 6.0,
                        "match_delta_vs_trend_pct": -1.0,
                    }
                ],
            }
        ],
        "assessment": {
            "overall_status": "no_material_issues",
            "finding_count": 0,
            "severity_counts": {"info": 1, "warning": 0, "error": 0, "blocker": 0},
            "certification_score": 100.0,
            "certification_decision": "PASS",
            "findings": [],
            "pillar_assessments": [
                {
                    "pillar": "historical_regression",
                    "label": "Historical Regression",
                    "implementation_status": "implemented",
                    "query_count": 1,
                    "finding_count": 0,
                    "severity_counts": {"info": 1, "warning": 0, "error": 0, "blocker": 0},
                    "score": 100.0,
                    "decision": "PASS",
                }
            ],
            "query_assessments": [
                {
                    "query": "historical_baseline_scale_regression",
                    "pillar": "historical_regression",
                    "severity": "info",
                    "summary": "Current release scale remains within configured historical regression tolerances.",
                }
            ],
        },
    }

    markdown = snapshot_payload_to_markdown(payload)

    assert "## Release Comparison" in markdown
    assert "Previous baseline release" in markdown
    assert "baseline_clean (run 1)" in markdown
    assert "Scale delta vs baseline" in markdown
    assert "players 12.5%" in markdown
    assert "Scale delta vs recent trend" in markdown
