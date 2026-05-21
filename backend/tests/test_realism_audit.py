"""Tests for reusable realism audit queries."""
from pathlib import Path
import sys

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.generation import RealismAuditRunner  # noqa: E402


def test_realism_audit_runner_executes_named_queries_on_sqlite():
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
                status varchar(30) not null default 'not_started'
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
                processing_status varchar(30) not null default 'succeeded'
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
                player_status varchar(30) not null,
                home_region_id bigint,
                generation_run_id bigint
            )
            """
        )
        conn.exec_driver_sql(
            """
            CREATE TABLE clubs (
                id integer primary key,
                club_name varchar(255) not null,
                region_id bigint not null
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
            CREATE TABLE matches (
                id integer primary key,
                match_date date not null,
                match_type varchar(50) not null,
                batch_id bigint not null
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

    session = sessionmaker(bind=engine, autoflush=False, future=True)()
    try:
        session.execute(
            text(
                """
                INSERT INTO generation_runs (
                    id, generation_name, seed_value, simulation_version, parameter_snapshot, status
                ) VALUES (
                    1,
                    'Audit Run',
                    77,
                    'v1',
                    '{"validation": {"weekend_concentration_min": 0.45, "weekend_concentration_max": 0.55}, "ratings": {"rating_movement_warning_threshold": 300}}',
                    'succeeded'
                )
                """
            )
        )
        session.execute(
            text(
                """
                INSERT INTO monthly_batches (
                    id, generation_run_id, batch_month, batch_sequence, batch_type, processing_status
                ) VALUES (10, 1, '2026-01-01', 1, 'historical_initial', 'succeeded')
                """
            )
        )
        session.execute(
            text(
                """
                INSERT INTO players (
                    id, first_name, last_name, birth_date, registration_date, player_status, home_region_id, generation_run_id
                ) VALUES
                    (1, 'Alex', 'Smith', '1990-01-01', '2026-01-01', 'ACTIVE', 1, 1),
                    (2, 'Blair', 'Jones', '1988-01-01', '2026-01-01', 'ACTIVE', 1, 1),
                    (3, 'Casey', 'Lee', '1992-01-01', '2026-01-01', 'INJURED', 2, 1)
                """
            )
        )
        session.execute(
            text(
                """
                INSERT INTO clubs (id, club_name, region_id) VALUES
                    (100, 'North Club', 1),
                    (101, 'South Club', 2)
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
                    (1002, 2, 101, '2026-01-01', 0, 1)
                """
            )
        )
        session.execute(
            text(
                """
                INSERT INTO matches (id, match_date, match_type, batch_id) VALUES
                    (2000, '2026-01-03', 'recreational', 10),
                    (2001, '2026-01-05', 'league', 10)
                """
            )
        )
        session.execute(
            text(
                """
                INSERT INTO match_games (
                    id, match_id, game_number, team_one_score, team_two_score, winning_team_number, target_score, win_by
                ) VALUES
                    (3000, 2000, 1, 11, 9, 1, 11, 2),
                    (3001, 2001, 1, 13, 11, 1, 11, 2)
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
                    (4000, 1, 10, 2000, 1, '2026-01-03', 1, 1, 1, 'match_update', 1500, 1525, 25, 0.6, 0.7, 11, 9, 1, 1, 1, 24, 0.2, 0.22, 'v1'),
                    (4001, 1, 10, 2001, 2, '2026-01-05', 2, 2, 2, 'match_update', 1700, 1350, -350, 0.4, 0.2, 11, 13, 1, 0, 0, 24, 0.2, 0.22, 'v1')
                """
            )
        )
        session.commit()

        runner = RealismAuditRunner(session)
        results = runner.run(
            generation_run_id=1,
            batch_id=10,
            query_names=[
                "player_roster_summary",
                "club_membership_geography",
                "match_type_distribution",
                "weekend_match_share",
                "game_competitiveness_summary",
                "rating_delta_summary",
            ],
        )
    finally:
        session.close()

    result_map = {result.query.name: result.rows for result in results}

    assert result_map["player_roster_summary"] == (
        {
            "generation_run_id": 1,
            "player_count": 3,
            "active_player_count": 2,
            "unaffiliated_player_count": 1,
            "multi_club_player_count": 1,
            "unaffiliated_player_pct": 33.33,
        },
    )
    assert result_map["club_membership_geography"] == (
        {
            "membership_count": 3,
            "primary_membership_count": 2,
            "secondary_membership_count": 1,
            "cross_region_membership_count": 1,
            "same_region_secondary_pct": 0.0,
        },
    )
    assert result_map["match_type_distribution"] == (
        {
            "batch_id": 10,
            "batch_month": "2026-01-01",
            "match_type": "league",
            "match_count": 1,
            "match_pct": 50.0,
        },
        {
            "batch_id": 10,
            "batch_month": "2026-01-01",
            "match_type": "recreational",
            "match_count": 1,
            "match_pct": 50.0,
        },
    )
    assert result_map["weekend_match_share"] == (
        {
            "batch_id": 10,
            "batch_month": "2026-01-01",
            "total_matches": 2,
            "weekend_match_count": 1,
            "weekend_match_pct": 50.0,
            "configured_weekend_min_pct": 45.0,
            "configured_weekend_max_pct": 55.0,
            "outside_config_range": 0,
        },
    )
    assert result_map["game_competitiveness_summary"] == (
        {
            "batch_id": 10,
            "game_count": 2,
            "avg_margin": 2.0,
            "extended_game_count": 1,
            "extended_game_pct": 50.0,
        },
    )
    assert result_map["rating_delta_summary"] == (
        {
            "batch_id": 10,
            "player_update_count": 2,
            "avg_abs_rating_delta": 187.5,
            "max_abs_rating_delta": 350,
            "large_delta_count": 1,
            "large_delta_pct": 50.0,
            "configured_warning_threshold": 300,
        },
    )
