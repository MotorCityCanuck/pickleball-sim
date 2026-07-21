"""Tests for snapshot-aware student dataset source queries."""

from datetime import date
from pathlib import Path
import sys

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.exports.student_dataset import (  # noqa: E402
    PROJECTION_BY_TABLE,
    STUDENT_TABLE_ORDER,
    ReleaseBatch,
    StudentDatasetQueryContext,
    StudentDatasetQueryError,
    StudentDatasetReleaseWindow,
    build_student_dataset_queries,
    build_student_dataset_query,
)


@pytest.fixture()
def session_factory():
    engine = create_engine("sqlite:///:memory:", future=True)
    with engine.begin() as conn:
        for statement in STUDENT_SOURCE_TABLES_SQL:
            conn.exec_driver_sql(statement)
    return sessionmaker(bind=engine, autoflush=False, future=True)


@pytest.fixture()
def session(session_factory):
    db_session = session_factory()
    try:
        yield db_session
    finally:
        db_session.close()


@pytest.fixture()
def release_window():
    return StudentDatasetReleaseWindow(
        release_index=0,
        release_type="initial_snapshot",
        folder_suffix="_initial_history",
        batch_sequence_start=1,
        batch_sequence_end=2,
        batches=(
            ReleaseBatch(id=101, batch_sequence=1, batch_month=date(2025, 1, 1)),
            ReleaseBatch(id=102, batch_sequence=2, batch_month=date(2025, 2, 1)),
        ),
    )


@pytest.fixture()
def query_context(release_window):
    return StudentDatasetQueryContext(
        generation_run_id=1,
        release_window=release_window,
    )


@pytest.fixture()
def incremental_release_window():
    return StudentDatasetReleaseWindow(
        release_index=1,
        release_type="monthly_incremental",
        folder_suffix="_snapshot_2025_03",
        batch_sequence_start=1,
        batch_sequence_end=3,
        batches=(
            ReleaseBatch(id=101, batch_sequence=1, batch_month=date(2025, 1, 1)),
            ReleaseBatch(id=102, batch_sequence=2, batch_month=date(2025, 2, 1)),
            ReleaseBatch(id=103, batch_sequence=3, batch_month=date(2025, 3, 1)),
        ),
        fact_batches=(
            ReleaseBatch(id=103, batch_sequence=3, batch_month=date(2025, 3, 1)),
        ),
        prior_snapshot_batches=(
            ReleaseBatch(id=101, batch_sequence=1, batch_month=date(2025, 1, 1)),
            ReleaseBatch(id=102, batch_sequence=2, batch_month=date(2025, 2, 1)),
        ),
    )


@pytest.fixture()
def incremental_query_context(incremental_release_window):
    return StudentDatasetQueryContext(
        generation_run_id=1,
        release_window=incremental_release_window,
    )


def seed_snapshot_query_data(session):
    session.execute(
        text(
            """
            INSERT INTO monthly_batches (
                id, generation_run_id, batch_month, batch_sequence, batch_type,
                processing_status
            )
            VALUES
                (101, 1, '2025-01-01', 1, 'historical_initial', 'succeeded'),
                (102, 1, '2025-02-01', 2, 'historical_initial', 'succeeded'),
                (103, 1, '2025-03-01', 3, 'future_increment', 'succeeded'),
                (201, 2, '2025-01-01', 1, 'historical_initial', 'succeeded')
            """
        )
    )
    session.execute(
        text(
            """
            INSERT INTO regions (
                id, country_code, region_type, region_name, state_province_code,
                population, latitude, longitude
            )
            VALUES
                (1, 'US', 'metro', 'Included Home', 'CA', 1000, 1.0, 2.0),
                (2, 'US', 'metro', 'Included Club', 'CA', 2000, 3.0, 4.0),
                (3, 'US', 'metro', 'Included Match', 'CA', 3000, 5.0, 6.0),
                (4, 'US', 'metro', 'Included Registration', 'CA', 4000, 7.0, 8.0),
                (9, 'US', 'metro', 'Unreferenced', 'CA', 9000, 9.0, 9.0)
            """
        )
    )
    session.execute(
        text(
            """
            INSERT INTO players (
                id, external_player_key, first_name, last_name, gender,
                birth_date, dominant_hand, home_region_id, registration_date,
                initial_skill_seed, player_status, generation_run_id
            )
            VALUES
                (1, '00000000-0000-0000-0000-000000000001', 'Ada', 'Ace', 'F', '1990-01-01', 'RIGHT', 1,
                 '2025-01-05', 0.1000, 'ACTIVE', 1),
                (2, '00000000-0000-0000-0000-000000000002', 'Ben', 'Backhand', 'M', '1991-01-01', 'LEFT', 1,
                 '2025-03-01', 0.2000, 'ACTIVE', 1),
                (3, '00000000-0000-0000-0000-000000000003', 'Cy', 'Crosscourt', 'M', '1992-01-01', 'RIGHT', 1,
                 '2025-01-01', 0.3000, 'ACTIVE', 2)
            """
        )
    )
    session.execute(
        text(
            """
            INSERT INTO player_registrations (
                id, player_id, batch_id, registration_month, registration_source,
                assigned_region_id, initial_rating_value, initial_confidence_score
            )
            VALUES
                (1, 1, 101, '2025-01-01', 'synthetic', 4, 1400.0, 0.1),
                (2, 2, 103, '2025-03-01', 'synthetic', 4, 1500.0, 0.1),
                (3, 3, 101, '2025-01-01', 'synthetic', 4, 1300.0, 0.1)
            """
        )
    )
    session.execute(
        text(
            """
            INSERT INTO player_rating_history (
                id, player_id, rating_date, rating_type, rating_value,
                confidence_score, volatility_score, expected_performance,
                regional_adjustment_factor, global_percentile, match_count_used,
                calculation_version, batch_id
            )
            VALUES
                (1, 1, '2025-01-31', 'initial', 1400.0, 0.1, 0.2, 0.5,
                 1.0, 55.0, 0, 'internal', 101),
                (3, 1, '2025-02-28', 'match_update', 1412.0, 0.2, 0.3, 0.5,
                 1.0, 57.5, 3, 'internal', 102),
                (2, 2, '2025-03-31', 'initial', 1500.0, 0.1, 0.2, 0.5,
                 1.0, 60.0, 0, 'internal', 103)
            """
        )
    )
    session.execute(
        text(
            """
            INSERT INTO player_assessment_history (
                id, player_id, assessment_date, assessment_type, assessment_value,
                confidence_score, derived_from_matches, batch_id
            )
            VALUES
                (1, 1, '2025-02-15', 'consistency', 0.7, 0.8, 2, 102),
                (2, 2, '2025-03-15', 'consistency', 0.8, 0.8, 2, 103)
            """
        )
    )
    session.execute(
        text(
            """
            INSERT INTO matches (
                id, tournament_id, match_date, region_id, match_type, court_type,
                match_format, winning_team_id, predicted_winning_team_number,
                predicted_win_probability, total_points_played,
                expected_competitiveness, simulation_noise_factor, batch_id
            )
            VALUES
                (1, NULL, '2025-01-20', 3, 'recreational', 'indoor',
                 'best_of_3', 10, 1, 0.7, 33, 0.5, 0.1, 101),
                (2, NULL, '2025-03-20', 3, 'recreational', 'outdoor',
                 'best_of_3', 20, 1, 0.7, 35, 0.5, 0.1, 103)
            """
        )
    )
    session.execute(
        text(
            """
            INSERT INTO match_teams (
                id, match_id, team_number, team_score, expected_win_probability,
                average_team_rating, source_team_id
            )
            VALUES
                (10, 1, 1, 2, 0.7, 1400.0, 1),
                (11, 1, 2, 1, 0.3, 1350.0, NULL),
                (20, 2, 1, 2, 0.7, 1500.0, 3)
            """
        )
    )
    session.execute(
        text(
            """
            INSERT INTO match_team_players (
                id, match_team_id, player_id, player_position,
                player_rating_at_match
            )
            VALUES
                (100, 10, 1, 1, 1400.0),
                (101, 11, 1, 1, 1400.0),
                (200, 20, 2, 1, 1500.0)
            """
        )
    )
    session.execute(
        text(
            """
            INSERT INTO match_games (
                id, match_id, game_number, team_one_score, team_two_score,
                winning_team_number, target_score, win_by,
                expected_team_one_score_share, actual_team_one_score_share,
                expected_team_one_score, expected_team_two_score,
                score_noise_factor
            )
            VALUES
                (1, 1, 1, 11, 8, 1, 11, 2, 0.6, 0.579, 11.0, 8.0, 0.1),
                (2, 2, 1, 11, 7, 1, 11, 2, 0.6, 0.611, 11.0, 7.0, 0.1)
            """
        )
    )
    session.execute(
        text(
            """
            INSERT INTO teams (
                id, team_type, team_status, country_code, formation_date, dissolution_date,
                chemistry_score, persistence_probability, generation_run_id
            )
            VALUES
                (1, 'mixed_doubles', 'retired', 'US', '2025-01-01', '2025-04-15',
                 0.8, 0.9, 1),
                (2, 'mixed_doubles', 'dormant', 'CA', '2025-01-01', '2025-01-15',
                 0.7, 0.8, 1),
                (3, 'mixed_doubles', 'active', 'US', '2025-03-01', NULL,
                 0.6, 0.7, 1),
                (4, 'mixed_doubles', 'active', 'CA', '2025-01-01', NULL,
                 0.5, 0.6, 2)
            """
        )
    )
    session.execute(
        text(
            """
            INSERT INTO team_memberships (
                id, team_id, player_id, player_position, joined_date, left_date
            )
            VALUES
                (1, 1, 1, 1, '2025-01-01', '2025-04-15'),
                (2, 2, 1, 1, '2025-01-01', '2025-01-15'),
                (3, 3, 1, 1, '2025-03-01', NULL),
                (4, 1, 2, 2, '2025-01-01', NULL)
            """
        )
    )
    session.execute(
        text(
            """
            INSERT INTO clubs (
                id, club_name, region_id, club_type, competitiveness_level,
                member_capacity, founding_date, indoor_court_count,
                outdoor_court_count, generation_run_id
            )
            VALUES
                (1, 'Early Club', 2, 'private_club', 'competitive', 100,
                 '2025-01-01', 2, 4, 1),
                (2, 'Referenced Club', 2, 'private_club', 'competitive',
                 100, '2025-02-01', 2, 4, 1),
                (3, 'Future Club', 2, 'private_club', 'competitive', 100,
                 '2025-04-01', 2, 4, 1),
                (4, 'Other Run Club', 2, 'private_club', 'competitive', 100,
                 '2025-01-01', 2, 4, 2)
            """
        )
    )
    session.execute(
        text(
            """
            INSERT INTO club_memberships (
                id, player_id, club_id, membership_type, start_date, end_date,
                is_primary, generation_run_id
            )
            VALUES
                (1, 1, 1, 'member', '2025-01-01', '2025-04-01', 1, 1),
                (2, 1, 2, 'member', '2025-01-15', NULL, 0, 1),
                (3, 1, 3, 'member', '2025-03-01', NULL, 0, 1),
                (4, 2, 1, 'member', '2025-01-01', NULL, 0, 1),
                (5, 1, 4, 'member', '2025-01-01', NULL, 0, 2)
            """
        )
    )
    session.commit()


def rows(session, table_name, query_context):
    return (
        session.execute(build_student_dataset_query(table_name, query_context))
        .mappings()
        .all()
    )


def test_build_student_dataset_queries_covers_all_projection_tables(query_context):
    queries = build_student_dataset_queries(query_context)

    assert tuple(queries) == STUDENT_TABLE_ORDER
    for table_name, query in queries.items():
        assert len(query.selected_columns) == len(
            PROJECTION_BY_TABLE[table_name].included_columns
        )


def test_build_student_dataset_query_rejects_unknown_table(query_context):
    with pytest.raises(StudentDatasetQueryError, match="No student dataset query"):
        build_student_dataset_query("generation_runs", query_context)


def test_batch_tied_queries_use_included_batch_ids(session, query_context):
    seed_snapshot_query_data(session)

    assert [row["id"] for row in rows(session, "monthly_batches", query_context)] == [
        101,
        102,
    ]
    assert [row["id"] for row in rows(session, "matches", query_context)] == [1]
    match_team_rows = rows(session, "match_teams", query_context)
    assert [row["id"] for row in match_team_rows] == [10, 11]
    assert [row["team_id"] for row in match_team_rows] == [1, None]
    assert [row["id"] for row in rows(session, "match_games", query_context)] == [1]
    assert [
        row["id"] for row in rows(session, "player_assessment_history", query_context)
    ] == [1]
    assert [
        row["id"] for row in rows(session, "player_registrations", query_context)
    ] == [1]


def test_incremental_batch_tied_queries_use_fact_batch_ids(
    session,
    incremental_query_context,
):
    seed_snapshot_query_data(session)

    assert [
        row["id"] for row in rows(session, "monthly_batches", incremental_query_context)
    ] == [103]
    assert [row["id"] for row in rows(session, "matches", incremental_query_context)] == [2]
    match_team_rows = rows(session, "match_teams", incremental_query_context)
    assert [row["id"] for row in match_team_rows] == [20]
    assert [row["team_id"] for row in match_team_rows] == [3]
    assert [row["id"] for row in rows(session, "match_games", incremental_query_context)] == [2]
    assert [
        row["id"]
        for row in rows(session, "player_assessment_history", incremental_query_context)
    ] == [2]
    assert [
        row["id"]
        for row in rows(session, "player_registrations", incremental_query_context)
    ] == [2]


def test_incremental_fact_queries_do_not_hide_non_snapshot_player_references(
    session,
    incremental_query_context,
):
    seed_snapshot_query_data(session)
    session.execute(
        text(
            """
            INSERT INTO match_team_players (
                id, match_team_id, player_id, player_position,
                player_rating_at_match
            )
            VALUES (202, 20, 3, 2, 1300.0)
            """
        )
    )
    session.commit()

    assert [
        row["id"]
        for row in rows(session, "match_team_players", incremental_query_context)
    ] == [200, 202]


def test_incremental_dimension_queries_remain_snapshot_scoped(
    session,
    incremental_query_context,
):
    seed_snapshot_query_data(session)

    assert [row["player_id"] for row in rows(session, "player_master", incremental_query_context)] == [1, 2]
    assert [row["id"] for row in rows(session, "teams", incremental_query_context)] == [1, 3]
    assert [row["id"] for row in rows(session, "clubs", incremental_query_context)] == [1]
    assert [row["id"] for row in rows(session, "club_memberships", incremental_query_context)] == [4]
    assert [row["id"] for row in rows(session, "team_memberships", incremental_query_context)] == [3, 4]
    assert [row["id"] for row in rows(session, "regions", incremental_query_context)] == [1, 2, 3, 4]


def test_players_query_uses_latest_snapshot_scope_rating(session, query_context):
    seed_snapshot_query_data(session)

    row = rows(session, "player_master", query_context)[0]

    assert row["player_id"] == 1
    assert str(row["external_player_key"]) == "00000000-0000-0000-0000-000000000001"
    assert row["first_name"] == "Ada"
    assert row["last_name"] == "Ace"
    assert row["gender"] == "F"
    assert row["birth_date"] == date(1990, 1, 1)
    assert row["dominant_hand"] == "RIGHT"
    assert row["home_region_id"] == 1
    assert row["registration_date"] == date(2025, 1, 5)
    assert row["player_status"] == "ACTIVE"
    assert float(row["rating_value"]) == 1412.0
    assert float(row["confidence_score"]) == 0.2
    assert float(row["volatility_score"]) == 0.3
    assert float(row["global_percentile"]) == 57.5
    assert row["match_count_used"] == 3
    assert row["rating_date"] == date(2025, 2, 28)
    assert row["rating_batch_id"] == 102
    assert row["snapshot_month"] == date(2025, 2, 1)


def test_players_query_returns_only_incremental_player_deltas(
    session,
    incremental_query_context,
):
    seed_snapshot_query_data(session)

    rows_out = rows(session, "player_master", incremental_query_context)

    assert [row["player_id"] for row in rows_out] == [1, 2]
    assert float(rows_out[0]["rating_value"]) == 1412.0
    assert rows_out[0]["rating_batch_id"] == 102
    assert rows_out[0]["snapshot_month"] == date(2025, 3, 1)
    assert float(rows_out[1]["rating_value"]) == 1500.0
    assert rows_out[1]["rating_batch_id"] == 103
    assert rows_out[1]["rating_date"] == date(2025, 3, 31)


def test_player_and_match_participation_queries_do_not_export_future_players(
    session,
    query_context,
):
    seed_snapshot_query_data(session)

    assert [row["player_id"] for row in rows(session, "player_master", query_context)] == [1]
    assert [row["id"] for row in rows(session, "match_team_players", query_context)] == [
        100,
        101,
    ]


def test_team_queries_apply_as_of_lifecycle_transformations(session, query_context):
    seed_snapshot_query_data(session)

    team_rows = rows(session, "teams", query_context)
    assert [row["id"] for row in team_rows] == [1, 2]
    assert [row["country_code"] for row in team_rows] == ["US", "CA"]
    assert "chemistry_score" not in team_rows[0]
    assert "persistence_probability" not in team_rows[0]
    assert team_rows[0]["team_status"] == "active"
    assert team_rows[0]["dissolution_date"] is None
    assert team_rows[1]["team_status"] == "dormant"
    assert team_rows[1]["dissolution_date"] == date(2025, 1, 15)

    membership_rows = rows(session, "team_memberships", query_context)
    assert [row["id"] for row in membership_rows] == [1, 2]
    assert membership_rows[0]["left_date"] is None
    assert membership_rows[1]["left_date"] == date(2025, 1, 15)


def test_club_queries_apply_reachability_and_as_of_end_date(session, query_context):
    seed_snapshot_query_data(session)

    club_rows = rows(session, "clubs", query_context)
    assert [row["id"] for row in club_rows] == [1, 2]

    membership_rows = rows(session, "club_memberships", query_context)
    assert [row["id"] for row in membership_rows] == [1, 2]
    assert membership_rows[0]["end_date"] is None


def test_regions_query_uses_referenced_regions_only(session, query_context):
    seed_snapshot_query_data(session)

    region_rows = rows(session, "regions", query_context)
    assert [row["id"] for row in region_rows] == [1, 2, 3, 4]


STUDENT_SOURCE_TABLES_SQL = (
    """
    CREATE TABLE monthly_batches (
        id integer primary key,
        generation_run_id bigint not null,
        batch_month date not null,
        batch_sequence integer not null,
        batch_type varchar(30) not null,
        active_player_count_start integer,
        new_player_count integer,
        active_player_count_end integer,
        match_count_generated integer,
        rating_update_count integer,
        assessment_update_count integer,
        processing_status varchar(30) not null,
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
        competitiveness_multiplier numeric(8, 4),
        latitude numeric(10, 6),
        longitude numeric(10, 6),
        created_at datetime default current_timestamp not null,
        updated_at datetime default current_timestamp not null
    )
    """,
    """
    CREATE TABLE players (
        id integer primary key,
        external_player_key text not null,
        first_name varchar(100) not null,
        last_name varchar(100) not null,
        gender varchar(20),
        birth_date date not null,
        dominant_hand varchar(10),
        home_region_id bigint,
        registration_date date not null,
        initial_skill_seed numeric(8, 4),
        player_status varchar(30) not null,
        generation_run_id bigint,
        created_at datetime default current_timestamp not null,
        updated_at datetime default current_timestamp not null
    )
    """,
    """
    CREATE TABLE player_registrations (
        id integer primary key,
        player_id bigint not null,
        batch_id bigint not null,
        registration_month date not null,
        registration_source varchar(50) not null,
        assigned_region_id bigint,
        initial_rating_value numeric(8, 3),
        initial_confidence_score numeric(8, 3),
        created_at datetime default current_timestamp not null
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
    CREATE TABLE player_assessment_history (
        id integer primary key,
        player_id bigint not null,
        assessment_date date not null,
        assessment_type varchar(100) not null,
        assessment_value numeric(8, 3),
        confidence_score numeric(8, 3),
        derived_from_matches integer,
        batch_id bigint not null,
        created_at datetime default current_timestamp not null
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
        pairing_source varchar(30),
        source_team_id bigint,
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
    """
    CREATE TABLE teams (
        id integer primary key,
        team_type varchar(50) not null,
        team_status varchar(30),
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
    CREATE TABLE clubs (
        id integer primary key,
        club_name varchar(255) not null,
        region_id bigint not null,
        club_type varchar(50),
        competitiveness_level varchar(50),
        member_capacity integer,
        founding_date date,
        indoor_court_count integer,
        outdoor_court_count integer,
        generation_run_id bigint,
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
        is_primary boolean,
        generation_run_id bigint,
        created_at datetime default current_timestamp not null,
        updated_at datetime default current_timestamp not null
    )
    """,
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
        updated_at datetime default current_timestamp not null,
        completed_at datetime,
        error_message text
    )
    """,
    """
    CREATE TABLE student_dataset_release_files (
        id integer primary key,
        release_id bigint not null,
        table_name varchar(255) not null,
        file_path text not null,
        row_count bigint,
        schema_hash varchar(128),
        checksum varchar(128),
        created_at datetime default current_timestamp not null
    )
    """,
)
