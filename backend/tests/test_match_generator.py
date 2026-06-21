"""Tests for monthly match generation."""
from copy import deepcopy
from datetime import date
from decimal import Decimal
import logging
from pathlib import Path
import random
import sys

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.default_configuration import DEFAULT_CONFIG_PAYLOAD  # noqa: E402
from app.generation.runtime_metrics import RuntimeMetricRecorder  # noqa: E402
from app.generators import MatchGenerationConfig, MatchGenerator  # noqa: E402
from app.generators.games import expected_scores, game_score  # noqa: E402
from app.generators import matches as match_generator_module  # noqa: E402
from app.generators.matches import (  # noqa: E402
    ActivePlayerCandidate,
    ActivePlayerPool,
    _active_player_pool,
    _active_teams,
    _ad_hoc_pair_weight,
    _expected_win_probability,
    _prior_player_pair_counts,
    _sample_ad_hoc_pair_candidates,
)
from app.models import (  # noqa: E402
    GenerationRuntimeMetric,
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
    payload["match_scheduling"]["monthly_matches_per_active_player_mean"] = 2
    payload["match_scheduling"]["monthly_matches_per_active_player_std_dev"] = 0
    payload["match_scheduling"]["match_volume_noise_factor"] = 0
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
                country_code varchar(2),
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
        conn.exec_driver_sql(
            """
            CREATE TABLE generation_runtime_metrics (
                id integer primary key autoincrement,
                generation_run_id bigint not null,
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


def add_historical_match(
    session,
    *,
    generation_run_id,
    batch_month,
    match_date,
    first_team_player_ids,
    second_team_player_ids,
    add_game=False,
):
    prior_batch = MonthlyBatch(
        generation_run_id=generation_run_id,
        batch_month=batch_month,
        batch_sequence=0,
        batch_type="historical_initial",
        processing_status="succeeded",
    )
    session.add(prior_batch)
    session.flush()

    match = Match(
        match_date=match_date,
        region_id=1,
        match_type="recreational",
        court_type="standard",
        match_format="single_game",
        predicted_winning_team_number=1,
        predicted_win_probability=Decimal("0.6000"),
        batch_id=prior_batch.id,
    )
    session.add(match)
    session.flush()

    team_one = MatchTeam(
        match_id=match.id,
        team_number=1,
        team_score=1,
        expected_win_probability=Decimal("0.6000"),
        average_team_rating=Decimal("1500"),
    )
    team_two = MatchTeam(
        match_id=match.id,
        team_number=2,
        team_score=0,
        expected_win_probability=Decimal("0.4000"),
        average_team_rating=Decimal("1500"),
    )
    session.add_all([team_one, team_two])
    session.flush()

    session.add_all(
        [
            MatchTeamPlayer(match_team_id=team_one.id, player_id=player_id)
            for player_id in first_team_player_ids
        ]
        + [
            MatchTeamPlayer(match_team_id=team_two.id, player_id=player_id)
            for player_id in second_team_player_ids
        ]
    )
    if add_game:
        session.add(
            MatchGame(
                match_id=match.id,
                game_number=1,
                team_one_score=11,
                team_two_score=8,
                winning_team_number=1,
                target_score=11,
                win_by=2,
            )
        )
    session.commit()


def active_player_candidate(
    player_id,
    *,
    rating,
    region_id=1,
    gender="M",
    recent_match_count=0,
    recent_game_count=0,
):
    return ActivePlayerCandidate(
        id=player_id,
        gender=gender,
        region_id=region_id,
        rating=Decimal(str(rating)),
        club_ids=frozenset({region_id}),
        primary_club_ids=frozenset({region_id}),
        active_team_ids=(),
        is_teamed=False,
        recent_match_count=recent_match_count,
        recent_game_count=recent_game_count,
    )


active_player_candidate.__test__ = False


def add_unteamed_players(session, *, generation_run_id, batch_id, count, rating_start=1800):
    players = []
    for index in range(count):
        players.append(
            Player(
                first_name=f"Unt{index}",
                last_name="Eamed",
                gender="M" if index % 2 == 0 else "F",
                birth_date=date(1985, 1, 1),
                home_region_id=1,
                registration_date=date(2024, 1, 1),
                player_status="ACTIVE",
                generation_run_id=generation_run_id,
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
                rating_value=Decimal(rating_start + index),
                confidence_score=Decimal("0.2"),
                batch_id=batch_id,
            )
        )
    session.commit()
    return players


add_unteamed_players.__test__ = False


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


def test_active_teams_include_hidden_bias_context_fields(session):
    payload = test_payload()
    generation_run, batch = seed_match_data(session, payload=payload, team_count=4)
    batch.batch_month = date(2024, 2, 1)
    session.commit()
    add_historical_match(
        session,
        generation_run_id=generation_run.id,
        batch_month=date(2024, 1, 1),
        match_date=date(2024, 1, 25),
        first_team_player_ids=(1, 2),
        second_team_player_ids=(3, 4),
        add_game=True,
    )
    config = MatchGenerationConfig.from_payload(payload)

    teams = _active_teams(
        session,
        generation_run.id,
        batch.batch_month,
        config=config,
    )
    first_team = next(team for team in teams if team.player_ids == (1, 2))
    second_team = next(team for team in teams if team.player_ids == (3, 4))

    assert first_team.avg_age == Decimal("44.00")
    assert first_team.pairing_source == "competitive_team"
    assert first_team.source_team_id == first_team.id
    assert first_team.formation_date == date(2024, 1, 1)
    assert first_team.club_ids == frozenset()
    assert first_team.primary_club_ids == frozenset()
    assert first_team.region_name is None
    assert first_team.team_total_prior_matches == 1
    assert first_team.recent_game_count == 1
    assert first_team.recent_pair_counts == {(1, 2): 1}
    assert second_team.team_total_prior_matches == 1
    assert second_team.recent_game_count == 1
    assert second_team.recent_pair_counts == {(3, 4): 1}


def test_active_player_pool_includes_unteamed_active_players(session):
    payload = test_payload()
    generation_run, batch = seed_match_data(session, payload=payload, team_count=2)
    batch.batch_month = date(2024, 2, 1)
    session.commit()
    add_historical_match(
        session,
        generation_run_id=generation_run.id,
        batch_month=date(2024, 1, 1),
        match_date=date(2024, 1, 25),
        first_team_player_ids=(1, 2),
        second_team_player_ids=(3, 4),
        add_game=True,
    )
    unteamed_player = Player(
        first_name="Unt",
        last_name="Eamed",
        gender="F",
        birth_date=date(1985, 1, 1),
        home_region_id=2,
        registration_date=date(2024, 1, 1),
        player_status="ACTIVE",
        generation_run_id=generation_run.id,
    )
    session.add(unteamed_player)
    session.flush()
    session.add(
        PlayerRatingHistory(
            player_id=unteamed_player.id,
            rating_date=date(2024, 1, 1),
            rating_type="initial",
            rating_value=Decimal("1550"),
            confidence_score=Decimal("0.2"),
            batch_id=batch.id,
        )
    )
    session.commit()

    pool = _active_player_pool(
        session,
        generation_run.id,
        batch.batch_month,
        config=MatchGenerationConfig.from_payload(payload),
    )

    assert unteamed_player.id in pool.by_id
    candidate = pool.by_id[unteamed_player.id]
    assert candidate.gender == "F"
    assert candidate.region_id == 2
    assert candidate.rating == Decimal("1550")
    assert candidate.active_team_ids == ()
    assert candidate.is_teamed is False
    assert candidate.recent_match_count == 0
    assert candidate.recent_game_count == 0
    assert unteamed_player.id in pool.ids_by_team_status["unteamed"]
    assert unteamed_player.id in pool.ids_by_region[2]
    assert unteamed_player.id in pool.ids_by_gender["F"]
    assert unteamed_player.id in pool.ids_by_rating_band["1500_1749"]

    teamed_candidate = pool.by_id[1]
    assert teamed_candidate.is_teamed is True
    assert teamed_candidate.active_team_ids
    assert teamed_candidate.recent_match_count == 1
    assert teamed_candidate.recent_game_count == 1
    assert 1 in pool.ids_by_team_status["teamed"]


def test_active_player_pool_excludes_players_without_current_rating(session):
    payload = test_payload()
    generation_run, batch = seed_match_data(session, payload=payload, team_count=2)
    unrated_player = Player(
        first_name="Un",
        last_name="Rated",
        gender="M",
        birth_date=date(1980, 1, 1),
        home_region_id=1,
        registration_date=date(2024, 1, 1),
        player_status="ACTIVE",
        generation_run_id=generation_run.id,
    )
    session.add(unrated_player)
    session.commit()

    pool = _active_player_pool(session, generation_run.id, batch.batch_month)

    assert unrated_player.id not in pool.by_id
    assert set(pool.all_ids) == {1, 2, 3, 4}


def test_ad_hoc_sampler_returns_two_unique_non_overlapping_sides():
    payload = test_payload()
    config = MatchGenerationConfig.from_payload(payload)
    pool = ActivePlayerPool(
        [
            active_player_candidate(1, rating=1500, gender="M"),
            active_player_candidate(2, rating=1520, gender="F"),
            active_player_candidate(3, rating=1510, gender="M"),
            active_player_candidate(4, rating=1530, gender="F"),
        ]
    )

    sampled = _sample_ad_hoc_pair_candidates(
        random.Random(7),
        player_pool=pool,
        match_date=date(2024, 2, 1),
        match_type="recreational",
        match_class="casual",
        player_day_counts={},
        prior_pair_counts={},
        config=config,
    )

    assert sampled is not None
    first_side, second_side = sampled
    assert first_side.pairing_source == "ad_hoc"
    assert second_side.pairing_source == "ad_hoc"
    assert first_side.source_team_id is None
    assert second_side.source_team_id is None
    assert len(set(first_side.player_ids)) == 2
    assert len(set(second_side.player_ids)) == 2
    assert set(first_side.player_ids).isdisjoint(second_side.player_ids)
    assert first_side.average_rating == (
        sum(rating for _, _, rating in first_side.players) / Decimal("2")
    ).quantize(Decimal("0.001"))


def test_ad_hoc_sampler_respects_player_daily_caps():
    payload = test_payload()
    payload["match_scheduling"]["max_daily_matches_per_team"] = 1
    config = MatchGenerationConfig.from_payload(payload)
    match_date = date(2024, 2, 1)
    pool = ActivePlayerPool(
        [
            active_player_candidate(1, rating=1500),
            active_player_candidate(2, rating=1510),
            active_player_candidate(3, rating=1520),
            active_player_candidate(4, rating=1530),
            active_player_candidate(5, rating=1540),
            active_player_candidate(6, rating=1550),
        ]
    )

    sampled = _sample_ad_hoc_pair_candidates(
        random.Random(3),
        player_pool=pool,
        match_date=match_date,
        match_type="recreational",
        match_class="casual",
        player_day_counts={
            (1, match_date): 1,
            (2, match_date): 1,
        },
        prior_pair_counts={},
        config=config,
    )

    assert sampled is not None
    selected_player_ids = set(sampled[0].player_ids) | set(sampled[1].player_ids)
    assert 1 not in selected_player_ids
    assert 2 not in selected_player_ids


def test_ad_hoc_sampler_uses_rating_band_when_possible():
    payload = test_payload()
    payload["matchmaking"]["rating_band_width"]["recreational"] = 60
    config = MatchGenerationConfig.from_payload(payload)
    pool = ActivePlayerPool(
        [
            active_player_candidate(1, rating=1500),
            active_player_candidate(2, rating=1540),
            active_player_candidate(3, rating=1700),
            active_player_candidate(4, rating=1740),
        ]
    )

    sampled = _sample_ad_hoc_pair_candidates(
        random.Random(4),
        player_pool=pool,
        match_date=date(2024, 2, 1),
        match_type="recreational",
        match_class="casual",
        player_day_counts={},
        prior_pair_counts={},
        config=config,
    )

    assert sampled is not None
    for side in sampled:
        ratings = [rating for _, _, rating in side.players]
        assert abs(ratings[0] - ratings[1]) <= Decimal("60")


def test_ad_hoc_sampler_uses_bounded_sampling_for_large_pool(monkeypatch):
    payload = test_payload()
    payload["matchmaking"]["rating_band_width"]["recreational"] = 80
    config = MatchGenerationConfig.from_payload(payload)
    pool = ActivePlayerPool(
        [
            active_player_candidate(
                index,
                rating=1500 + (index % 60),
                region_id=1 + (index % 3),
            )
            for index in range(1, 301)
        ]
    )

    def fail_exhaustive_pairing(*_args, **_kwargs):
        raise AssertionError("large ad hoc pools must not enumerate every player pair")

    monkeypatch.setattr(
        match_generator_module,
        "_ad_hoc_player_pairs",
        fail_exhaustive_pairing,
    )

    sampled = _sample_ad_hoc_pair_candidates(
        random.Random(11),
        player_pool=pool,
        match_date=date(2024, 2, 1),
        match_type="recreational",
        match_class="casual",
        player_day_counts={},
        prior_pair_counts={},
        config=config,
    )

    assert sampled is not None
    selected_player_ids = set(sampled[0].player_ids) | set(sampled[1].player_ids)
    assert len(selected_player_ids) == 4


def test_ad_hoc_pair_weight_prefers_local_pairs():
    same_region_pair = (
        active_player_candidate(1, rating=1500, region_id=1),
        active_player_candidate(2, rating=1510, region_id=1),
    )
    cross_region_pair = (
        active_player_candidate(3, rating=1500, region_id=1),
        active_player_candidate(4, rating=1510, region_id=2),
    )

    assert _ad_hoc_pair_weight(
        same_region_pair,
        target_rating=None,
        target_region_id=None,
        prior_pair_counts={},
        match_class="casual",
        band=Decimal("400"),
    ) > _ad_hoc_pair_weight(
        cross_region_pair,
        target_rating=None,
        target_region_id=None,
        prior_pair_counts={},
        match_class="casual",
        band=Decimal("400"),
    )


def test_prior_player_pair_counts_derive_from_match_history(session):
    payload = test_payload()
    generation_run, batch = seed_match_data(session, payload=payload, team_count=2)
    batch.batch_month = date(2024, 2, 1)
    session.commit()
    add_historical_match(
        session,
        generation_run_id=generation_run.id,
        batch_month=date(2024, 1, 1),
        match_date=date(2024, 1, 15),
        first_team_player_ids=(1, 2),
        second_team_player_ids=(3, 4),
    )

    pair_counts = _prior_player_pair_counts(
        session,
        generation_run_id=generation_run.id,
        batch_month=batch.batch_month,
        player_ids={1, 2, 3, 4},
    )

    assert pair_counts[(1, 2)] == 1
    assert pair_counts[(3, 4)] == 1

    pool = _active_player_pool(session, generation_run.id, batch.batch_month)
    sampled = _sample_ad_hoc_pair_candidates(
        random.Random(1),
        player_pool=pool,
        match_date=batch.batch_month,
        match_type="recreational",
        match_class="casual",
        player_day_counts={},
        prior_pair_counts=pair_counts,
        config=MatchGenerationConfig.from_payload(payload),
    )

    assert sampled is not None
    assert all(
        side.recent_pair_counts[side.player_ids] == side.team_total_prior_matches
        for side in sampled
    )


def test_generate_for_batch_uses_visible_probability_when_hidden_bias_disabled(session):
    payload = test_payload()
    _, batch = seed_match_data(session, payload=payload, team_count=2)

    MatchGenerator().generate_for_batch(batch_id=batch.id, session=session)

    match_teams = session.query(MatchTeam).order_by(MatchTeam.team_number).all()
    team_one, team_two = match_teams
    expected_probability = _expected_win_probability(
        team_one.average_team_rating,
        team_two.average_team_rating,
    )
    assert team_one.expected_win_probability == expected_probability
    assert team_two.expected_win_probability == Decimal("1") - expected_probability
    match = session.query(Match).one()
    expected_winner = 1 if expected_probability >= Decimal("0.5") else 2
    assert match.predicted_winning_team_number == expected_winner


def test_generate_for_batch_persists_competitive_team_source_metadata(session):
    payload = test_payload()
    _, batch = seed_match_data(session, payload=payload, team_count=4)

    MatchGenerator().generate_for_batch(batch_id=batch.id, session=session)

    source_rosters = {
        team_id: tuple(sorted(player_id for player_id, in rows))
        for team_id, rows in (
            (
                team.id,
                session.query(TeamMembership.player_id)
                .where(TeamMembership.team_id == team.id)
                .all(),
            )
            for team in session.query(Team)
        )
    }
    match_teams = session.query(MatchTeam).all()

    assert match_teams
    assert {match_team.pairing_source for match_team in match_teams} == {
        "competitive_team"
    }
    assert all(match_team.source_team_id is not None for match_team in match_teams)
    for match_team in match_teams:
        assert tuple(sorted(player.player_id for player in match_team.players)) == (
            source_rosters[match_team.source_team_id]
        )


def test_generate_for_batch_assigns_unteamed_players_to_ad_hoc_matches_when_enabled(
    session,
):
    payload = test_payload()
    payload["match_scheduling"]["matches_per_team_per_month"] = 2
    payload["match_scheduling"]["max_daily_matches_per_team"] = 4
    payload["matchmaking"]["pairing_source_overrides_by_type"] = {
        "recreational": {
            "competitive_team": 0.0,
            "ad_hoc": 1.0,
        },
    }
    generation_run, batch = seed_match_data(session, payload=payload, team_count=8)
    unteamed_players = add_unteamed_players(
        session,
        generation_run_id=generation_run.id,
        batch_id=batch.id,
        count=20,
    )
    unteamed_player_ids = {player.id for player in unteamed_players}

    result = MatchGenerator().generate_for_batch(batch_id=batch.id, session=session)

    assert result.match_count > 0
    ad_hoc_match_teams = (
        session.query(MatchTeam)
        .where(MatchTeam.pairing_source == "ad_hoc")
        .all()
    )
    assert ad_hoc_match_teams
    assert all(match_team.source_team_id is None for match_team in ad_hoc_match_teams)
    ad_hoc_player_ids = {
        player.player_id
        for match_team in ad_hoc_match_teams
        for player in match_team.players
    }
    assert ad_hoc_player_ids & unteamed_player_ids
    assert all(
        len({match_team.pairing_source for match_team in match.match_teams}) == 1
        for match in session.query(Match).where(Match.batch_id == batch.id)
    )


def test_generate_for_batch_applies_hidden_bias_to_prediction_only(session):
    payload = test_payload()
    payload["hidden_performance_bias"] = {
        **DEFAULT_CONFIG_PAYLOAD["hidden_performance_bias"],
        "enabled": True,
        "total_max_rating_points": 250,
        "age_advantage": {
            **DEFAULT_CONFIG_PAYLOAD["hidden_performance_bias"]["age_advantage"],
            "max_rating_points": 250,
            "points_per_year_gap": 5,
            "close_match_multiplier": 1,
        },
    }
    _, batch = seed_match_data(session, payload=payload, team_count=2)
    players = {player.id: player for player in session.query(Player)}
    players[1].birth_date = date(1990, 1, 1)
    players[2].birth_date = date(1990, 1, 1)
    players[3].birth_date = date(1950, 1, 1)
    players[4].birth_date = date(1950, 1, 1)
    session.commit()

    MatchGenerator().generate_for_batch(batch_id=batch.id, session=session)

    match = session.query(Match).one()
    match_teams = session.query(MatchTeam).order_by(MatchTeam.team_number).all()
    team_numbers_by_players = {
        frozenset(
            player.player_id for player in match_team.players
        ): match_team.team_number
        for match_team in match_teams
    }
    younger_team_number = team_numbers_by_players[frozenset((1, 2))]
    older_team_number = team_numbers_by_players[frozenset((3, 4))]
    team_one, team_two = match_teams
    visible_probability = _expected_win_probability(
        team_one.average_team_rating,
        team_two.average_team_rating,
    )

    assert match.predicted_winning_team_number == younger_team_number
    winning_team = next(
        match_team
        for match_team in match_teams
        if match_team.team_number == younger_team_number
    )
    assert match.predicted_win_probability == winning_team.expected_win_probability
    assert winning_team.expected_win_probability > Decimal("0.5")
    assert team_one.expected_win_probability != visible_probability

    visible_ratings = {
        frozenset(
            player.player_id for player in match_team.players
        ): match_team.average_team_rating
        for match_team in match_teams
    }
    assert visible_ratings == {
        frozenset((1, 2)): Decimal("1410.000"),
        frozenset((3, 4)): Decimal("1450.000"),
    }
    assert {younger_team_number, older_team_number} == {1, 2}


def test_generate_for_batch_does_not_log_hidden_bias_when_debug_disabled(
    session,
    caplog,
):
    payload = test_payload()
    payload["hidden_performance_bias"] = {
        **DEFAULT_CONFIG_PAYLOAD["hidden_performance_bias"],
        "enabled": True,
        "debug_enabled": False,
    }
    _, batch = seed_match_data(session, payload=payload, team_count=2)

    with caplog.at_level(logging.INFO, logger="uvicorn.error"):
        MatchGenerator().generate_for_batch(batch_id=batch.id, session=session)

    assert not [
        record
        for record in caplog.records
        if hasattr(record, "hidden_performance_bias_debug")
    ]


def test_generate_for_batch_logs_hidden_bias_debug_payload(session, caplog):
    payload = test_payload()
    payload["hidden_performance_bias"] = {
        **DEFAULT_CONFIG_PAYLOAD["hidden_performance_bias"],
        "enabled": True,
        "debug_enabled": True,
        "age_advantage": {
            **DEFAULT_CONFIG_PAYLOAD["hidden_performance_bias"]["age_advantage"],
            "points_per_year_gap": 5,
        },
    }
    _, batch = seed_match_data(session, payload=payload, team_count=2)

    with caplog.at_level(logging.INFO, logger="uvicorn.error"):
        MatchGenerator().generate_for_batch(batch_id=batch.id, session=session)

    debug_records = [
        record
        for record in caplog.records
        if hasattr(record, "hidden_performance_bias_debug")
    ]
    assert len(debug_records) == 1
    payload = debug_records[0].hidden_performance_bias_debug
    assert payload["visible_team_ratings"].keys() == {"team_one", "team_two"}
    assert payload["factor_adjustments"].keys() == {"team_one", "team_two"}
    assert payload["total_adjustments"].keys() == {
        "team_one_before_cap",
        "team_two_before_cap",
        "team_one",
        "team_two",
    }
    assert payload["effective_team_ratings"].keys() == {"team_one", "team_two"}
    assert "visible_probability" in payload
    assert "final_probability" in payload


def test_generate_for_batch_records_runtime_metrics(session, caplog):
    generation_run, batch = seed_match_data(session, team_count=8)
    recorder = RuntimeMetricRecorder(
        session=session,
        generation_run_id=generation_run.id,
        batch_id=batch.id,
        stage_name="matches",
    )

    caplog.set_level(logging.INFO, logger="uvicorn.error")
    result = MatchGenerator().generate_for_batch(
        batch_id=batch.id,
        session=session,
        runtime_recorder=recorder,
    )

    metrics = session.scalars(
        select(GenerationRuntimeMetric).order_by(GenerationRuntimeMetric.id)
    ).all()
    assert [metric.subphase_name for metric in metrics] == [
        "load_active_team_rosters",
        "load_latest_team_player_ratings",
        "load_active_team_club_memberships",
        "load_active_team_regions",
        "load_historical_team_activity_maps",
        "load_active_team_history",
        "build_active_team_candidates",
        "load_active_teams",
        "calculate_team_targets",
        "load_recent_pair_dates",
        "load_active_player_pool",
        "load_prior_player_pair_counts",
        "baseline_guardrails",
        "planning",
        "planning_under_target_maintenance",
        "planning_first_team_selection",
        "planning_opponent_selection",
        "planning_match_object_construction",
        "persist_matches",
        "scoring",
        "scoring_generate_games",
        "scoring_build_match_teams",
        "scoring_build_game_rows",
        "persist_match_teams",
        "build_match_team_players",
        "persist_match_related_rows",
        "persist_match_team_players",
        "persist_match_games",
        "finalize_batch",
    ]
    assert {metric.event_type for metric in metrics} == {"completed"}
    assert all(metric.generation_run_id == generation_run.id for metric in metrics)
    assert all(metric.batch_id == batch.id for metric in metrics)
    assert all(metric.stage_name == "matches" for metric in metrics)
    assert all(metric.elapsed_ms >= 0 for metric in metrics)
    load_active_team_detail_metrics = [
        metric
        for metric in metrics
        if metric.subphase_name in {
            "load_active_team_rosters",
            "load_latest_team_player_ratings",
            "load_active_team_club_memberships",
            "load_active_team_regions",
            "load_historical_team_activity_maps",
            "load_active_team_history",
            "build_active_team_candidates",
        }
    ]
    assert len(load_active_team_detail_metrics) == 7
    assert all(
        metric.metadata_json["parent_subphase"] == "load_active_teams"
        for metric in load_active_team_detail_metrics
        if metric.subphase_name != "load_historical_team_activity_maps"
    )
    historical_team_activity_metric = next(
        metric
        for metric in metrics
        if metric.subphase_name == "load_historical_team_activity_maps"
    )
    assert (
        historical_team_activity_metric.metadata_json["parent_subphase"]
        == "load_active_team_history"
    )

    active_player_pool_metric = next(
        metric for metric in metrics if metric.subphase_name == "load_active_player_pool"
    )
    assert active_player_pool_metric.output_count == 0
    assert active_player_pool_metric.metadata_json["skipped"] is True
    assert active_player_pool_metric.metadata_json["ad_hoc_enabled"] is False

    prior_pair_counts_metric = next(
        metric
        for metric in metrics
        if metric.subphase_name == "load_prior_player_pair_counts"
    )
    assert prior_pair_counts_metric.input_count == 0
    assert prior_pair_counts_metric.output_count == 0
    assert prior_pair_counts_metric.metadata_json["skipped"] is True

    baseline_metric = next(
        metric for metric in metrics if metric.subphase_name == "baseline_guardrails"
    )
    assert baseline_metric.metadata_json["candidate_team_count"] == 8
    assert baseline_metric.metadata_json["under_target_team_count"] == 8
    assert baseline_metric.metadata_json["candidate_player_count"] == 0
    assert baseline_metric.metadata_json["active_player_pool_loaded"] is False
    assert baseline_metric.metadata_json["planned_match_count"] == result.match_count
    assert baseline_metric.metadata_json["pairing_source_weights_by_class"] == {
        "casual": {
            "competitive_team": "1.0",
            "ad_hoc": "0.0",
        },
        "semi_competitive": {
            "competitive_team": "1.0",
            "ad_hoc": "0.0",
        },
        "competitive": {
            "competitive_team": "1.0",
            "ad_hoc": "0.0",
        },
    }
    assert baseline_metric.metadata_json["ad_hoc_enabled_by_match_class"] == {
        "casual": False,
        "semi_competitive": False,
        "competitive": False,
    }

    planning_metric = next(
        metric for metric in metrics if metric.subphase_name == "planning"
    )
    assert planning_metric.input_count == result.match_count
    assert planning_metric.output_count == result.match_count
    assert planning_metric.attempt_count >= result.match_count
    assert planning_metric.metadata_json["target_match_count"] == result.match_count
    planning_detail_metrics = [
        metric
        for metric in metrics
        if metric.subphase_name.startswith("planning_")
    ]
    assert len(planning_detail_metrics) == 4
    assert all(
        metric.metadata_json["parent_subphase"] == "planning"
        for metric in planning_detail_metrics
    )
    assert all(metric.output_count == result.match_count for metric in planning_detail_metrics)
    assert all(
        metric.attempt_count == planning_metric.attempt_count
        for metric in planning_detail_metrics
    )
    assert all(metric.input_count >= result.match_count for metric in planning_detail_metrics)
    assert any(
        "Generation runtime phase completed" in record.message
        and "stage=matches" in record.message
        and "subphase=planning" in record.message
        for record in caplog.records
    )
    scoring_detail_metrics = [
        metric
        for metric in metrics
        if metric.subphase_name.startswith("scoring_")
    ]
    assert len(scoring_detail_metrics) == 3
    assert all(
        metric.metadata_json["parent_subphase"] == "scoring"
        for metric in scoring_detail_metrics
    )
    persistence_detail_metrics = [
        metric
        for metric in metrics
        if metric.subphase_name in {"persist_match_team_players", "persist_match_games"}
    ]
    assert len(persistence_detail_metrics) == 2
    assert all(
        metric.metadata_json["parent_subphase"] == "persist_match_related_rows"
        for metric in persistence_detail_metrics
    )


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


def test_generate_for_batch_varies_monthly_match_count_with_player_std_dev(session):
    payload = test_payload()
    payload["match_scheduling"]["matches_per_team_per_month"] = 4
    payload["match_scheduling"]["monthly_matches_per_active_player_mean"] = 8
    payload["match_scheduling"]["monthly_matches_per_active_player_std_dev"] = 4
    generation_run, first_batch = seed_match_data(session, payload=payload, team_count=8)
    second_batch = MonthlyBatch(
        generation_run_id=generation_run.id,
        batch_month=date(2024, 2, 1),
        batch_sequence=2,
        batch_type="historical_initial",
        processing_status="pending",
    )
    session.add(second_batch)
    session.commit()

    first_result = MatchGenerator().generate_for_batch(
        batch_id=first_batch.id,
        session=session,
    )
    second_result = MatchGenerator().generate_for_batch(
        batch_id=second_batch.id,
        session=session,
    )

    assert first_result.match_count != second_result.match_count


def test_generate_for_batch_varies_monthly_match_count_with_noise_factor(session):
    payload = test_payload()
    payload["match_scheduling"]["matches_per_team_per_month"] = 4
    payload["match_scheduling"]["monthly_matches_per_active_player_mean"] = 8
    payload["match_scheduling"]["monthly_matches_per_active_player_std_dev"] = 0
    payload["match_scheduling"]["match_volume_noise_factor"] = 0.25
    generation_run, first_batch = seed_match_data(session, payload=payload, team_count=8)
    second_batch = MonthlyBatch(
        generation_run_id=generation_run.id,
        batch_month=date(2024, 2, 1),
        batch_sequence=2,
        batch_type="historical_initial",
        processing_status="pending",
    )
    session.add(second_batch)
    session.commit()

    first_result = MatchGenerator().generate_for_batch(
        batch_id=first_batch.id,
        session=session,
    )
    second_result = MatchGenerator().generate_for_batch(
        batch_id=second_batch.id,
        session=session,
    )

    assert first_result.match_count != second_result.match_count


def test_generate_for_batch_avoids_recent_rematches_when_alternatives_exist(session):
    payload = test_payload()
    payload["match_scheduling"]["matches_per_team_per_month"] = 2
    payload["matchmaking"]["rematch_penalty_window_days"] = 30
    generation_run, batch = seed_match_data(session, payload=payload, team_count=4)
    batch.batch_month = date(2024, 2, 1)
    session.commit()

    add_historical_match(
        session,
        generation_run_id=generation_run.id,
        batch_month=date(2024, 1, 1),
        match_date=date(2024, 1, 31),
        first_team_player_ids=(1, 2),
        second_team_player_ids=(3, 4),
    )

    MatchGenerator().generate_for_batch(batch_id=batch.id, session=session)

    current_batch_pairs = {
        frozenset(
            frozenset(player.player_id for player in match_team.players)
            for match_team in match.match_teams
        )
        for match in session.query(Match).where(Match.batch_id == batch.id)
    }

    assert frozenset((frozenset((1, 2)), frozenset((3, 4)))) not in current_batch_pairs


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


def test_config_validates_monthly_matches_per_active_player_std_dev():
    payload = test_payload()
    payload["match_scheduling"]["monthly_matches_per_active_player_std_dev"] = -1

    with pytest.raises(ValueError, match="monthly_matches_per_active_player_std_dev"):
        MatchGenerationConfig.from_payload(payload)


def test_config_validates_match_volume_noise_factor():
    payload = test_payload()
    payload["match_scheduling"]["match_volume_noise_factor"] = 1.1

    with pytest.raises(ValueError, match="match_volume_noise_factor"):
        MatchGenerationConfig.from_payload(payload)


def test_config_validates_rematch_penalty_window_days():
    payload = test_payload()
    payload["matchmaking"]["rematch_penalty_window_days"] = -1

    with pytest.raises(ValueError, match="rematch_penalty_window_days"):
        MatchGenerationConfig.from_payload(payload)


def test_config_parses_match_class_and_pairing_source_defaults():
    config = MatchGenerationConfig.from_payload(test_payload())

    assert config.match_class_by_type == {
        "recreational": "casual",
        "clinic": "casual",
        "challenge": "semi_competitive",
        "ladder": "semi_competitive",
        "league": "competitive",
        "tournament": "competitive",
    }
    assert config.pairing_source_weights_by_class["casual"] == (
        ("competitive_team", Decimal("1.0")),
        ("ad_hoc", Decimal("0.0")),
    )
    assert config.pairing_source_weights_by_class["semi_competitive"] == (
        ("competitive_team", Decimal("1.0")),
        ("ad_hoc", Decimal("0.0")),
    )
    assert config.pairing_source_weights_by_class["competitive"] == (
        ("competitive_team", Decimal("1.0")),
        ("ad_hoc", Decimal("0.0")),
    )
    assert config.pairing_source_overrides_by_type["clinic"] == (
        ("competitive_team", Decimal("1.0")),
        ("ad_hoc", Decimal("0.0")),
    )
    assert config.pairing_source_overrides_by_type["tournament"] == (
        ("competitive_team", Decimal("1.0")),
        ("ad_hoc", Decimal("0.0")),
    )


def test_config_parses_match_class_and_pairing_source_overrides():
    payload = test_payload()
    payload["match_types"]["class_by_type"]["challenge"] = "competitive"
    payload["matchmaking"]["pairing_source_weights_by_class"]["casual"] = {
        "competitive_team": 0.25,
        "ad_hoc": 0.75,
    }
    payload["matchmaking"]["pairing_source_overrides_by_type"] = {
        "recreational": {
            "competitive_team": 0.05,
            "ad_hoc": 0.95,
        },
    }

    config = MatchGenerationConfig.from_payload(payload)

    assert config.match_class_by_type["challenge"] == "competitive"
    assert config.pairing_source_weights_by_class["casual"] == (
        ("competitive_team", Decimal("0.25")),
        ("ad_hoc", Decimal("0.75")),
    )
    assert config.pairing_source_overrides_by_type == {
        "recreational": (
            ("competitive_team", Decimal("0.05")),
            ("ad_hoc", Decimal("0.95")),
        ),
    }


def test_config_validates_match_class_values():
    payload = test_payload()
    payload["match_types"]["class_by_type"]["recreational"] = "social"

    with pytest.raises(ValueError, match="match_types.class_by_type.recreational"):
        MatchGenerationConfig.from_payload(payload)


def test_config_validates_pairing_source_names():
    payload = test_payload()
    payload["matchmaking"]["pairing_source_weights_by_class"]["casual"] = {
        "competitive_team": 0.5,
        "walkup": 0.5,
    }

    with pytest.raises(ValueError, match="unsupported pairing sources: walkup"):
        MatchGenerationConfig.from_payload(payload)


def test_config_validates_pairing_source_weight_sums():
    payload = test_payload()
    payload["matchmaking"]["pairing_source_overrides_by_type"]["clinic"] = {
        "competitive_team": 0.6,
        "ad_hoc": 0.6,
    }

    with pytest.raises(ValueError, match="pairing_source_overrides_by_type.clinic"):
        MatchGenerationConfig.from_payload(payload)


def test_config_derives_team_match_mean_from_player_mean():
    payload = test_payload()
    del payload["match_scheduling"]["matches_per_team_per_month"]
    payload["match_scheduling"]["monthly_matches_per_active_player_mean"] = 7

    config = MatchGenerationConfig.from_payload(payload)

    assert config.monthly_matches_per_active_player_mean == Decimal("7")
    assert config.matches_per_team_per_month == Decimal("3.5")
    assert config.match_volume_noise_factor == Decimal("0")


def test_config_parses_hidden_performance_bias_defaults():
    config = MatchGenerationConfig.from_payload(test_payload())
    hidden_bias = config.hidden_performance_bias

    assert hidden_bias.enabled is False
    assert hidden_bias.debug_enabled is False
    assert hidden_bias.total_max_rating_points == Decimal("50")
    assert hidden_bias.age_advantage.enabled is True
    assert hidden_bias.age_advantage.max_rating_points == Decimal("35")
    assert hidden_bias.fatigue.window_days == 14
    assert hidden_bias.regional_strength.max_rating_points == Decimal("20")
    assert hidden_bias.regional_strength.strength_map["Florida"] == Decimal("15")
    assert hidden_bias.partnership_affinity.new_team_penalty == Decimal("-10")
    assert hidden_bias.experience.log_multiplier == Decimal("2")


def test_config_parses_hidden_performance_bias_overrides():
    payload = test_payload()
    payload["hidden_performance_bias"] = {
        "enabled": True,
        "debug_enabled": True,
        "total_max_rating_points": 40,
        "age_advantage": {
            "enabled": False,
            "max_rating_points": 22,
        },
        "fatigue": {
            "enabled": False,
            "window_days": 7,
        },
        "regional_strength": {
            "enabled": True,
            "map": {
                "Napa, CA": 11.5,
                "Rural": -4,
            },
        },
        "partnership_affinity": {
            "enabled": False,
            "matches_together_threshold_1": 5,
            "matches_together_threshold_2": 12,
            "new_team_penalty": -6,
        },
        "experience": {
            "enabled": False,
            "close_match_multiplier": 1.75,
        },
    }

    hidden_bias = MatchGenerationConfig.from_payload(payload).hidden_performance_bias

    assert hidden_bias.enabled is True
    assert hidden_bias.debug_enabled is True
    assert hidden_bias.total_max_rating_points == Decimal("40")
    assert hidden_bias.age_advantage.enabled is False
    assert hidden_bias.age_advantage.max_rating_points == Decimal("22")
    assert hidden_bias.age_advantage.points_per_year_gap == Decimal("1.25")
    assert hidden_bias.fatigue.enabled is False
    assert hidden_bias.fatigue.window_days == 7
    assert hidden_bias.regional_strength.strength_map == {
        "Napa, CA": Decimal("11.5"),
        "Rural": Decimal("-4"),
    }
    assert hidden_bias.partnership_affinity.enabled is False
    assert hidden_bias.partnership_affinity.matches_together_threshold_1 == 5
    assert hidden_bias.partnership_affinity.matches_together_threshold_2 == 12
    assert hidden_bias.partnership_affinity.new_team_penalty == Decimal("-6")
    assert hidden_bias.experience.enabled is False
    assert hidden_bias.experience.close_match_multiplier == Decimal("1.75")


def test_config_validates_hidden_performance_bias_boolean_flags():
    payload = test_payload()
    payload["hidden_performance_bias"]["enabled"] = "yes"

    with pytest.raises(ValueError, match="hidden_performance_bias.enabled"):
        MatchGenerationConfig.from_payload(payload)


def test_config_validates_hidden_performance_bias_caps():
    payload = test_payload()
    payload["hidden_performance_bias"]["fatigue"]["max_rating_penalty"] = -1

    with pytest.raises(
        ValueError,
        match="hidden_performance_bias.fatigue.max_rating_penalty",
    ):
        MatchGenerationConfig.from_payload(payload)


def test_config_validates_hidden_performance_bias_regional_map():
    payload = test_payload()
    payload["hidden_performance_bias"]["regional_strength"]["map"] = {
        "Florida": True,
    }

    with pytest.raises(
        ValueError,
        match="hidden_performance_bias.regional_strength.map",
    ):
        MatchGenerationConfig.from_payload(payload)


def test_config_validates_hidden_performance_bias_partnership_threshold_order():
    payload = test_payload()
    payload["hidden_performance_bias"]["partnership_affinity"][
        "matches_together_threshold_1"
    ] = 25
    payload["hidden_performance_bias"]["partnership_affinity"][
        "matches_together_threshold_2"
    ] = 10

    with pytest.raises(
        ValueError,
        match="matches_together_threshold_2",
    ):
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


def test_config_validates_games_per_match_values():
    payload = test_payload()
    payload["games_and_scores"]["games_per_match"]["league"] = 0

    with pytest.raises(ValueError, match="games_per_match.league"):
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


class StubRandom:
    def __init__(self, random_values, randint_value):
        self._random_values = iter(random_values)
        self._randint_value = randint_value

    def random(self):
        return next(self._random_values)

    def randint(self, low, high):
        assert low <= self._randint_value <= high
        return self._randint_value


def test_game_score_allows_dominant_non_extended_results():
    payload = test_payload()
    payload["games_and_scores"]["win_by_two_extension_rate"] = 0.0
    config = MatchGenerationConfig.from_payload(payload)

    team_one_score, team_two_score = game_score(
        StubRandom([0.99], -2),
        team_one_wins=True,
        adjusted_probability=Decimal("0.95"),
        config=config,
    )

    assert (team_one_score, team_two_score) == (11, 0)


def test_expected_scores_widen_for_mismatched_games():
    config = MatchGenerationConfig.from_payload(test_payload())

    close_team_one_score, close_team_two_score = expected_scores(
        Decimal("0.55"),
        config,
    )
    lopsided_team_one_score, lopsided_team_two_score = expected_scores(
        Decimal("0.85"),
        config,
    )

    assert close_team_one_score == Decimal("11.000")
    assert lopsided_team_one_score == Decimal("11.000")
    assert close_team_two_score > Decimal("7.000")
    assert lopsided_team_two_score < Decimal("4.000")


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
