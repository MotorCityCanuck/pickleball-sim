"""Tests for match-driven rating updates."""
from copy import deepcopy
from datetime import date
from decimal import Decimal
from pathlib import Path
import sys
from uuid import UUID

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.default_configuration import DEFAULT_CONFIG_PAYLOAD  # noqa: E402
from app.generation.runtime_metrics import RuntimeMetricRecorder  # noqa: E402
from app.generators import RatingUpdateGenerator  # noqa: E402
from app.generators.ratings import _initial_rating_states  # noqa: E402
from app.models import (  # noqa: E402
    GenerationRuntimeMetric,
    GenerationRun,
    Match,
    MatchGame,
    MatchTeam,
    MatchTeamPlayer,
    MonthlyBatch,
    Player,
    PlayerAssessmentHistory,
    PlayerRatingHistory,
    RatingsUpdateLog,
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
                parameter_snapshot json,
                started_at datetime,
                completed_at datetime,
                status varchar(30) not null default 'pending',
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
                updated_at datetime default current_timestamp not null
            )
            """
        )
        conn.exec_driver_sql(
            """
            CREATE TABLE players (
                id integer primary key,
                external_player_key blob not null unique,
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
            """
        )
        conn.exec_driver_sql(
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
            """
        )
        conn.exec_driver_sql(
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
                target_score integer not null default 11,
                win_by integer not null default 2,
                expected_team_one_score_share numeric(8, 4),
                actual_team_one_score_share numeric(8, 4),
                expected_team_one_score numeric(8, 3),
                expected_team_two_score numeric(8, 3),
                score_noise_factor numeric(8, 3),
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
        conn.exec_driver_sql(
            """
            CREATE TABLE generation_runtime_metrics (
                id integer primary key autoincrement,
                generation_run_id bigint not null,
                job_status_id bigint,
                batch_id bigint,
                stage_name varchar(100) not null,
                subphase_name varchar(100) not null,
                event_type varchar(30) not null,
                started_at datetime not null,
                completed_at datetime not null,
                elapsed_ms bigint not null,
                input_count bigint,
                output_count bigint,
                attempt_count bigint,
                metadata_json json,
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


def test_payload():
    payload = deepcopy(DEFAULT_CONFIG_PAYLOAD)
    payload["ratings"]["k_factor_new_player"] = 48
    payload["confidence"]["confidence_increment_per_match"] = 0.02
    return payload


test_payload.__test__ = False


def seed_rating_match(session, *, payload=None):
    generation_run = GenerationRun(
        id=1,
        generation_name="ratings",
        seed_value=42,
        simulation_version="test",
        parameter_snapshot=payload or test_payload(),
        status="pending",
    )
    batch = MonthlyBatch(
        id=1,
        generation_run_id=1,
        batch_month=date(2024, 1, 1),
        batch_sequence=1,
        batch_type="historical_initial",
        processing_status="pending",
    )
    players = [
        Player(
            id=player_id,
            external_player_key=UUID(int=player_id),
            first_name=f"Player{player_id}",
            last_name="Rating",
            gender="M",
            birth_date=date(1980, 1, 1),
            registration_date=date(2024, 1, 1),
            player_status="ACTIVE",
            generation_run_id=1,
        )
        for player_id in range(1, 5)
    ]
    ratings = [
        PlayerRatingHistory(
            id=index,
            player_id=index,
            rating_date=date(2024, 1, 1),
            rating_type="initial",
            rating_value=Decimal("1500.000"),
            confidence_score=Decimal("0.200"),
            batch_id=1,
        )
        for index in range(1, 5)
    ]
    match = Match(
        id=1,
        match_date=date(2024, 1, 15),
        match_type="recreational",
        match_format="single_game",
        winning_team_id=1,
        predicted_winning_team_number=1,
        predicted_win_probability=Decimal("0.5000"),
        total_points_played=16,
        batch_id=1,
    )
    team_one = MatchTeam(
        id=1,
        match_id=1,
        team_number=1,
        team_score=1,
        expected_win_probability=Decimal("0.5000"),
        average_team_rating=Decimal("1500.000"),
    )
    team_two = MatchTeam(
        id=2,
        match_id=1,
        team_number=2,
        team_score=0,
        expected_win_probability=Decimal("0.5000"),
        average_team_rating=Decimal("1500.000"),
    )
    match_players = [
        MatchTeamPlayer(
            id=1,
            match_team_id=1,
            player_id=1,
            player_position=1,
            player_rating_at_match=Decimal("1500.000"),
        ),
        MatchTeamPlayer(
            id=2,
            match_team_id=1,
            player_id=2,
            player_position=2,
            player_rating_at_match=Decimal("1500.000"),
        ),
        MatchTeamPlayer(
            id=3,
            match_team_id=2,
            player_id=3,
            player_position=1,
            player_rating_at_match=Decimal("1500.000"),
        ),
        MatchTeamPlayer(
            id=4,
            match_team_id=2,
            player_id=4,
            player_position=2,
            player_rating_at_match=Decimal("1500.000"),
        ),
    ]
    game = MatchGame(
        id=1,
        match_id=1,
        game_number=1,
        team_one_score=11,
        team_two_score=5,
        winning_team_number=1,
        target_score=11,
        win_by=2,
        expected_team_one_score_share=Decimal("0.5000"),
        actual_team_one_score_share=Decimal("0.6875"),
        expected_team_one_score=Decimal("11.000"),
        expected_team_two_score=Decimal("9.000"),
        score_noise_factor=Decimal("0.000"),
    )
    session.add(generation_run)
    session.add(batch)
    session.add_all(players)
    session.add_all(ratings)
    session.add(match)
    session.add_all([team_one, team_two])
    session.add_all(match_players)
    session.add(game)
    session.commit()
    return batch


def test_rating_updates_write_history_and_match_logs(session):
    batch = seed_rating_match(session)

    result = RatingUpdateGenerator().generate_for_batch(
        batch_id=batch.id,
        session=session,
    )

    assert result.match_count == 1
    assert result.player_update_count == 4
    assert result.rating_history_count == 4
    assert result.log_count == 4
    assert session.query(RatingsUpdateLog).count() == 4
    assert session.query(PlayerRatingHistory).count() == 8
    assert session.query(PlayerAssessmentHistory).count() == 4
    team_one_log = (
        session.query(RatingsUpdateLog)
        .filter(RatingsUpdateLog.player_id == 1)
        .one()
    )
    team_two_log = (
        session.query(RatingsUpdateLog)
        .filter(RatingsUpdateLog.player_id == 3)
        .one()
    )
    assert team_one_log.rating_before == Decimal("1500.000")
    assert team_one_log.rating_after == Decimal("1509.000")
    assert team_one_log.rating_delta == Decimal("9.000")
    assert team_one_log.expected_score_share == Decimal("0.5000")
    assert team_one_log.actual_score_share == Decimal("0.6875")
    assert team_one_log.expected_raw_points == Decimal("11.000")
    assert team_one_log.actual_raw_points == Decimal("11.000")
    assert team_one_log.match_won == 1
    assert team_two_log.rating_after == Decimal("1491.000")
    assert team_two_log.rating_delta == Decimal("-9.000")
    confidence_assessment = (
        session.query(PlayerAssessmentHistory)
        .filter(PlayerAssessmentHistory.player_id == 1)
        .one()
    )
    assert confidence_assessment.assessment_type == "confidence"
    assert confidence_assessment.assessment_value == Decimal("0.220")
    assert confidence_assessment.confidence_score == Decimal("0.220")
    assert confidence_assessment.derived_from_matches == 1
    session.refresh(batch)
    assert batch.rating_update_count == 4
    assert batch.assessment_update_count == 4


def test_rating_updates_record_runtime_metrics(session):
    batch = seed_rating_match(session)
    recorder = RuntimeMetricRecorder(
        session=session,
        generation_run_id=batch.generation_run_id,
        batch_id=batch.id,
        stage_name="ratings",
    )

    result = RatingUpdateGenerator().generate_for_batch(
        batch_id=batch.id,
        session=session,
        runtime_recorder=recorder,
    )

    metrics = session.scalars(
        select(GenerationRuntimeMetric).order_by(GenerationRuntimeMetric.id)
    ).all()
    assert [metric.subphase_name for metric in metrics] == [
        "load_matches",
        "collect_player_ids",
        "load_initial_states",
        "compute_rating_updates",
        "stage_rating_history_rows",
        "stage_assessment_history_rows",
        "stage_rating_log_rows",
        "flush_rating_rows",
    ]
    assert {metric.event_type for metric in metrics} == {"completed"}
    assert all(metric.generation_run_id == batch.generation_run_id for metric in metrics)
    assert all(metric.batch_id == batch.id for metric in metrics)
    assert all(metric.stage_name == "ratings" for metric in metrics)
    assert all(metric.elapsed_ms >= 0 for metric in metrics)
    compute_metric = next(
        metric for metric in metrics if metric.subphase_name == "compute_rating_updates"
    )
    assert compute_metric.input_count == result.match_count
    assert compute_metric.output_count == result.log_count
    flush_metric = next(
        metric for metric in metrics if metric.subphase_name == "flush_rating_rows"
    )
    assert flush_metric.input_count == (
        result.rating_history_count
        + session.query(PlayerAssessmentHistory).count()
        + result.log_count
    )
    assert flush_metric.metadata_json["rating_history_count"] == result.rating_history_count
    assert flush_metric.metadata_json["assessment_history_count"] == 4
    assert flush_metric.metadata_json["log_count"] == result.log_count


def test_initial_rating_states_use_latest_rating_and_prior_match_count(session):
    batch = seed_rating_match(session)
    session.add_all(
        [
            PlayerRatingHistory(
                id=10,
                player_id=1,
                rating_date=date(2024, 1, 5),
                rating_type="match_update",
                rating_value=Decimal("1510.000"),
                confidence_score=Decimal("0.220"),
                match_count_used=1,
                batch_id=batch.id,
            ),
            PlayerRatingHistory(
                id=11,
                player_id=1,
                rating_date=date(2024, 1, 10),
                rating_type="match_update",
                rating_value=Decimal("1520.000"),
                confidence_score=Decimal("0.240"),
                match_count_used=2,
                batch_id=batch.id,
            ),
            PlayerRatingHistory(
                id=12,
                player_id=2,
                rating_date=date(2024, 1, 10),
                rating_type="manual_adjustment",
                rating_value=Decimal("1490.000"),
                confidence_score=Decimal("0.300"),
                batch_id=batch.id,
            ),
        ]
    )
    session.commit()

    states = _initial_rating_states(session, [1, 2, 999], batch.id)

    assert states[1].rating == Decimal("1520.000")
    assert states[1].confidence == Decimal("0.240")
    assert states[1].match_count == 2
    assert states[2].rating == Decimal("1490.000")
    assert states[2].confidence == Decimal("0.300")
    assert states[2].match_count == 0
    assert 999 not in states


def test_rating_updates_aggregate_multiple_games(session):
    batch = seed_rating_match(session)
    session.add(
        MatchGame(
            id=2,
            match_id=1,
            game_number=2,
            team_one_score=11,
            team_two_score=9,
            winning_team_number=1,
            target_score=11,
            win_by=2,
            expected_team_one_score_share=Decimal("0.5000"),
            actual_team_one_score_share=Decimal("0.5500"),
            expected_team_one_score=Decimal("11.000"),
            expected_team_two_score=Decimal("9.000"),
            score_noise_factor=Decimal("0.000"),
        )
    )
    session.commit()

    result = RatingUpdateGenerator().generate_for_batch(
        batch_id=batch.id,
        session=session,
    )

    team_one_log = (
        session.query(RatingsUpdateLog)
        .filter(RatingsUpdateLog.player_id == 1)
        .one()
    )
    assert result.match_count == 1
    assert team_one_log.games_played == 2
    assert team_one_log.games_won == 2
    assert team_one_log.expected_score_share == Decimal("0.5000")
    assert team_one_log.actual_score_share == Decimal("0.6188")
    assert team_one_log.expected_raw_points == Decimal("22.000")
    assert team_one_log.actual_raw_points == Decimal("22.000")
    assert team_one_log.rating_delta == Decimal("5.702")
    assert team_one_log.rating_after == Decimal("1505.702")


def test_rating_updates_reject_rerun_for_same_batch(session):
    batch = seed_rating_match(session)
    generator = RatingUpdateGenerator()

    generator.generate_for_batch(batch_id=batch.id, session=session)

    with pytest.raises(ValueError, match="already has rating updates"):
        generator.generate_for_batch(batch_id=batch.id, session=session)


def test_rating_updates_require_prior_rating(session):
    batch = seed_rating_match(session)
    session.query(PlayerRatingHistory).filter(PlayerRatingHistory.player_id == 4).delete()
    session.commit()

    with pytest.raises(ValueError, match="Missing prior rating history"):
        RatingUpdateGenerator().generate_for_batch(batch_id=batch.id, session=session)


def test_rating_updates_require_game_expectations(session):
    batch = seed_rating_match(session)
    game = session.query(MatchGame).one()
    game.expected_team_one_score_share = None
    session.commit()

    with pytest.raises(ValueError, match="expected_team_one_score_share"):
        RatingUpdateGenerator().generate_for_batch(batch_id=batch.id, session=session)


def test_rating_updates_reject_invalid_rating_bounds(session):
    payload = test_payload()
    payload["ratings"]["rating_min"] = 5000
    payload["ratings"]["rating_max"] = 1000
    batch = seed_rating_match(session, payload=payload)

    with pytest.raises(ValueError, match="rating bounds"):
        RatingUpdateGenerator().generate_for_batch(batch_id=batch.id, session=session)
