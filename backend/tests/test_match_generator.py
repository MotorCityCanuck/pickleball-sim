"""Tests for monthly match generation."""
from copy import deepcopy
from datetime import date
from decimal import Decimal
from pathlib import Path
import sys

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.default_configuration import DEFAULT_CONFIG_PAYLOAD  # noqa: E402
from app.generators import MatchGenerationConfig, MatchGenerator  # noqa: E402
from app.models import (  # noqa: E402
    GenerationRun,
    Match,
    MatchGame,
    MatchTeam,
    MatchTeamPlayer,
    MonthlyBatch,
    Player,
    PlayerRatingHistory,
    Team,
    TeamMembership,
)


def test_payload():
    payload = deepcopy(DEFAULT_CONFIG_PAYLOAD)
    payload["match_scheduling"]["matches_per_team_per_month"] = 1
    payload["match_scheduling"]["max_daily_matches_per_team"] = 1
    payload["match_types"]["weights"] = {
        "recreational": 1.0,
        "league": 0.0,
        "ladder": 0.0,
        "tournament": 0.0,
        "challenge": 0.0,
        "clinic": 0.0,
    }
    payload["games_and_scores"]["games_per_match"] = {
        "recreational": 1,
        "league": 2,
        "tournament": 3,
    }
    return payload


test_payload.__test__ = False


@pytest.fixture()
def session_factory():
    engine = create_engine("sqlite:///:memory:", future=True)
    with engine.begin() as conn:
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
                status varchar(30) not null default 'pending',
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
                id integer primary key autoincrement,
                external_player_key varchar(32) not null default (lower(hex(randomblob(16)))) unique,
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
            CREATE TABLE teams (
                id integer primary key autoincrement,
                team_type varchar(50) not null,
                team_status varchar(30) default 'active',
                formation_date date not null,
                dissolution_date date,
                chemistry_score numeric(8, 4),
                persistence_probability numeric(5, 4),
                generation_run_id bigint,
                created_at datetime default current_timestamp not null,
                updated_at datetime default current_timestamp not null
            )
            """
        )
        conn.exec_driver_sql(
            """
            CREATE TABLE team_memberships (
                id integer primary key autoincrement,
                team_id bigint not null,
                player_id bigint not null,
                player_position integer not null,
                joined_date date not null,
                left_date date,
                created_at datetime default current_timestamp not null,
                updated_at datetime default current_timestamp not null
            )
            """
        )
        conn.exec_driver_sql(
            """
            CREATE TABLE player_rating_history (
                id integer primary key autoincrement,
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
            CREATE TABLE matches (
                id integer primary key autoincrement,
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
                id integer primary key autoincrement,
                match_id bigint not null,
                team_number integer not null,
                team_score integer not null,
                expected_win_probability numeric(8, 4),
                average_team_rating numeric(8, 3),
                created_at datetime default current_timestamp not null,
                updated_at datetime default current_timestamp not null
            )
            """
        )
        conn.exec_driver_sql(
            """
            CREATE TABLE match_team_players (
                id integer primary key autoincrement,
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
                id integer primary key autoincrement,
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
    return sessionmaker(bind=engine, autoflush=False, future=True)


@pytest.fixture()
def session(session_factory):
    db_session = session_factory()
    try:
        yield db_session
    finally:
        db_session.close()


def seed_match_data(session, *, payload=None, team_count=8):
    generation_run = GenerationRun(
        generation_name="match gen",
        seed_value=123,
        simulation_version="test",
        parameter_snapshot=payload or test_payload(),
        status="pending",
    )
    session.add(generation_run)
    session.flush()
    batch = MonthlyBatch(
        generation_run_id=generation_run.id,
        batch_month=date(2024, 1, 1),
        batch_sequence=1,
        batch_type="historical_initial",
        processing_status="pending",
    )
    session.add(batch)
    session.flush()

    players = []
    for index in range(team_count * 2):
        players.append(
            Player(
                first_name=f"Player{index}",
                last_name="Match",
                gender="M" if index % 2 == 0 else "F",
                birth_date=date(1980, 1, 1),
                home_region_id=1 if index < team_count else 2,
                registration_date=date(2024, 1, 1),
                player_status="ACTIVE",
                generation_run_id=generation_run.id,
            )
        )
    session.add_all(players)
    session.flush()
    for index, player in enumerate(players):
        session.add(
            PlayerRatingHistory(
                player_id=player.id,
                rating_date=date(2024, 1, 1),
                rating_type="initial",
                rating_value=Decimal("1400") + Decimal(index * 20),
                confidence_score=Decimal("0.2"),
                batch_id=batch.id,
            )
        )

    for index in range(team_count):
        team = Team(
            team_type="mixed_doubles",
            team_status="active",
            formation_date=date(2024, 1, 1),
            generation_run_id=generation_run.id,
        )
        session.add(team)
        session.flush()
        first_player = players[index * 2]
        second_player = players[index * 2 + 1]
        session.add_all(
            [
                TeamMembership(
                    team_id=team.id,
                    player_id=first_player.id,
                    player_position=1,
                    joined_date=date(2024, 1, 1),
                ),
                TeamMembership(
                    team_id=team.id,
                    player_id=second_player.id,
                    player_position=2,
                    joined_date=date(2024, 1, 1),
                ),
            ]
        )
    session.commit()
    return generation_run, batch


def test_generate_for_batch_creates_matches_teams_players_and_games(session):
    _, batch = seed_match_data(session, team_count=8)

    result = MatchGenerator().generate_for_batch(batch_id=batch.id, session=session)

    assert result.match_count == 4
    assert result.match_team_count == 8
    assert result.match_team_player_count == 16
    assert result.game_count == 4
    assert session.query(Match).count() == 4
    assert session.query(MatchTeam).count() == 8
    assert session.query(MatchTeamPlayer).count() == 16
    assert session.query(MatchGame).count() == 4
    assert all(match.batch_id == batch.id for match in session.query(Match))
    assert all(match.match_date.month == 1 for match in session.query(Match))
    assert all(len(match.match_teams) == 2 for match in session.query(Match))
    assert all(len(match.games) == 1 for match in session.query(Match))
    assert all(
        match.predicted_winning_team_number in {1, 2}
        for match in session.query(Match)
    )
    assert all(match.predicted_win_probability is not None for match in session.query(Match))
    assert all(
        game.expected_team_one_score is not None
        and game.expected_team_two_score is not None
        for game in session.query(MatchGame)
    )
    assert {team.team_number for team in session.query(MatchTeam)} == {1, 2}
    session.refresh(batch)
    assert batch.match_count_generated == 4


def test_generate_for_batch_respects_daily_team_limit(session):
    payload = test_payload()
    payload["match_scheduling"]["matches_per_team_per_month"] = 2
    payload["match_scheduling"]["max_daily_matches_per_team"] = 1
    _, batch = seed_match_data(session, payload=payload, team_count=10)

    MatchGenerator().generate_for_batch(batch_id=batch.id, session=session)

    team_day_counts = {}
    for match in session.query(Match):
        for match_team in match.match_teams:
            player_ids = tuple(player.player_id for player in match_team.players)
            team_day_counts[(player_ids, match.match_date)] = (
                team_day_counts.get((player_ids, match.match_date), 0) + 1
            )
    assert max(team_day_counts.values()) == 1


def test_generate_for_batch_is_deterministic(session_factory):
    first_session = session_factory()
    second_session = session_factory()
    try:
        _, first_batch = seed_match_data(first_session, team_count=8)
        _, second_batch = seed_match_data(second_session, team_count=8)

        MatchGenerator().generate_for_batch(
            batch_id=first_batch.id,
            session=first_session,
        )
        MatchGenerator().generate_for_batch(
            batch_id=second_batch.id,
            session=second_session,
        )

        assert _match_snapshot(first_session) == _match_snapshot(second_session)
    finally:
        first_session.close()
        second_session.close()


def test_generate_for_batch_rejects_existing_matches(session):
    _, batch = seed_match_data(session, team_count=8)

    MatchGenerator().generate_for_batch(batch_id=batch.id, session=session)

    with pytest.raises(ValueError, match="already has matches"):
        MatchGenerator().generate_for_batch(batch_id=batch.id, session=session)


def test_generate_for_batch_requires_active_teams(session):
    _, batch = seed_match_data(session, team_count=1)
    session.query(TeamMembership).delete()
    session.query(Team).delete()
    session.commit()

    with pytest.raises(ValueError, match="At least two active teams"):
        MatchGenerator().generate_for_batch(batch_id=batch.id, session=session)


def test_config_validates_match_type_weights():
    payload = test_payload()
    payload["match_types"]["weights"] = {"recreational": 0.9, "league": 0.9}

    with pytest.raises(ValueError, match="sum to 1.0"):
        MatchGenerationConfig.from_payload(payload)


def test_config_validates_game_target_score():
    payload = test_payload()
    payload["games_and_scores"]["game_target_score"] = 13

    with pytest.raises(ValueError, match="game_target_score"):
        MatchGenerationConfig.from_payload(payload)


def test_config_validates_win_by_two_extension_rate():
    payload = test_payload()
    payload["games_and_scores"]["win_by_two_extension_rate"] = 1.2

    with pytest.raises(ValueError, match="win_by_two_extension_rate"):
        MatchGenerationConfig.from_payload(payload)


def test_generate_for_batch_uses_win_by_two_extension_rate(session):
    payload = test_payload()
    payload["games_and_scores"]["win_by_two_extension_rate"] = 1.0
    _, batch = seed_match_data(session, payload=payload, team_count=8)

    MatchGenerator().generate_for_batch(batch_id=batch.id, session=session)

    assert all(
        max(game.team_one_score, game.team_two_score) > game.target_score
        for game in session.query(MatchGame)
    )


def _match_snapshot(session):
    return [
        (
            match.match_date,
            match.match_type,
            match.match_format,
            match.region_id,
            str(match.expected_competitiveness),
            tuple(
                (
                    match_team.team_number,
                    match_team.team_score,
                    str(match_team.expected_win_probability),
                    tuple(
                        (
                            player.player_id,
                            player.player_position,
                            str(player.player_rating_at_match),
                        )
                        for player in sorted(
                            match_team.players,
                            key=lambda player: player.player_position,
                        )
                    ),
                )
                for match_team in sorted(
                    match.match_teams,
                    key=lambda match_team: match_team.team_number,
                )
            ),
            tuple(
                (
                    game.game_number,
                    game.team_one_score,
                    game.team_two_score,
                    game.winning_team_number,
                )
                for game in sorted(match.games, key=lambda game: game.game_number)
            ),
        )
        for match in session.query(Match).order_by(Match.id)
    ]
