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
    RealismAuditRunner,
    RealismAuditService,
    execution_to_json_ready,
    resolve_realism_audit_parameters,
    save_realism_audit_snapshot,
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
                selection_probability numeric(12, 8)
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
                team_status varchar(30) not null,
                formation_date date not null,
                dissolution_date date,
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
                team_score integer not null
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
                        "weekend_concentration_max": 0.55
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
            INSERT INTO regions (id, country_code, region_name, state_province_code, selection_probability) VALUES
                (1, 'US', 'North Metro', 'NY', 0.50),
                (2, 'US', 'South Metro', 'FL', 0.30),
                (3, 'CA', 'West Metro', 'BC', 0.20)
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
            INSERT INTO player_rating_history (
                id, player_id, rating_date, rating_type, rating_value, confidence_score, batch_id
            ) VALUES
                (200, 1, '2026-01-01', 'initial', 1500, 0.20, 10),
                (201, 2, '2026-01-01', 'initial', 1600, 0.20, 10),
                (202, 3, '2026-01-01', 'initial', 1700, 0.20, 10),
                (203, 4, '2026-01-01', 'initial', 1800, 0.20, 10),
                (204, 5, '2026-01-01', 'initial', 2100, 0.20, 10),
                (205, 6, '2026-01-01', 'initial', 900, 0.20, 10),
                (206, 7, '2026-01-01', 'initial', 1400, 0.20, 10),
                (207, 8, '2026-01-01', 'initial', 1300, 0.20, 10)
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
                id, team_status, formation_date, dissolution_date, generation_run_id
            ) VALUES
                (500, 'active', '2026-01-01', NULL, 1),
                (501, 'active', '2026-01-01', NULL, 1),
                (502, 'active', '2026-01-01', NULL, 1)
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
            INSERT INTO matches (
                id, match_date, region_id, match_type, winning_team_id, predicted_winning_team_number,
                predicted_win_probability, batch_id
            ) VALUES
                (2000, '2026-01-03', 1, 'recreational', 3000, 1, 0.75, 10),
                (2001, '2026-01-03', 1, 'league', 3003, 1, 0.80, 10)
            """
        )
    )
    session.execute(
        text(
            """
            INSERT INTO match_teams (
                id, match_id, team_number, team_score
            ) VALUES
                (3000, 2000, 1, 1),
                (3001, 2000, 2, 0),
                (3002, 2001, 1, 0),
                (3003, 2001, 2, 1)
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


def test_player_age_distribution_uses_batch_created_at_instead_of_registration_date(session):
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


def test_realism_audit_parameter_resolution_uses_generation_run_snapshot(session):
    seed_audit_dataset(session)

    params = resolve_realism_audit_parameters(session)

    assert params["generation_run_id"] == 1
    assert params["batch_id"] == 10
    assert float(params["weekend_concentration_min"]) == pytest.approx(0.45)
    assert float(params["weekend_concentration_max"]) == pytest.approx(0.55)
    assert float(params["rating_delta_warning_threshold"]) == pytest.approx(250.0)
    assert float(params["initial_rating_elite_min"]) == pytest.approx(2000.0)
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
    assert payload["results"][0]["query"] == "weekend_match_share"


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
