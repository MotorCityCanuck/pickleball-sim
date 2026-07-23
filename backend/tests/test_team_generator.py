"""Tests for point-in-time team determination."""
from copy import deepcopy
from datetime import date
from decimal import Decimal
from pathlib import Path
import sys

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.default_configuration import DEFAULT_CONFIG_PAYLOAD  # noqa: E402
from app.generators import TeamFormationConfig, TeamGenerator  # noqa: E402
from app.models import (  # noqa: E402
    Club,
    ClubMembership,
    GenerationRun,
    MonthlyBatch,
    Player,
    PlayerRatingHistory,
    Region,
    Team,
    TeamLifecycleEvent,
    TeamMembership,
)


def test_payload(player_count=20):
    payload = deepcopy(DEFAULT_CONFIG_PAYLOAD)
    payload["player_generation"]["player_count"] = player_count
    payload["team_formation"]["player_team_participation_rate"] = 0.80
    payload["team_formation"]["team_type_weights"] = {
        "mens_doubles": 0.25,
        "womens_doubles": 0.25,
        "mixed_doubles": 0.25,
        "open_doubles": 0.25,
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
            CREATE TABLE regions (
                id integer primary key autoincrement,
                country_code varchar(10) not null,
                region_type varchar(20),
                region_name varchar(255) not null,
                state_province_code varchar(10),
                population bigint,
                selection_probability numeric(12, 8),
                competitiveness_multiplier numeric(8, 4) default 1.0,
                latitude numeric(10, 6),
                longitude numeric(10, 6),
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
            CREATE TABLE clubs (
                id integer primary key autoincrement,
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
                updated_at datetime default current_timestamp not null
            )
            """
        )
        conn.exec_driver_sql(
            """
            CREATE TABLE club_memberships (
                id integer primary key autoincrement,
                player_id bigint not null,
                club_id bigint not null,
                membership_type varchar(50),
                start_date date not null,
                end_date date,
                is_primary boolean default true,
                generation_run_id bigint,
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
            CREATE TABLE teams (
                id integer primary key autoincrement,
                team_type varchar(50) not null,
                team_identity_type varchar(30) not null default 'competitive',
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
            CREATE TABLE team_lifecycle_events (
                id integer primary key autoincrement,
                generation_run_id bigint not null,
                batch_id bigint not null,
                team_id bigint not null,
                event_date date not null,
                event_type varchar(30) not null,
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


def seed_team_data(
    session,
    *,
    payload=None,
    player_count=20,
    club_competitiveness_levels=("competitive", "recreational"),
):
    generation_run = GenerationRun(
        generation_name="team gen",
        seed_value=123,
        simulation_version="test",
        parameter_snapshot=payload or test_payload(player_count),
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
    if not session.get(Region, 1):
        session.add_all(
            [
                Region(
                    id=1,
                    country_code="US",
                    region_type="metro",
                    region_name="Test USA",
                    state_province_code="FL",
                ),
                Region(
                    id=2,
                    country_code="CA",
                    region_type="metro",
                    region_name="Test Canada",
                    state_province_code="ON",
                ),
            ]
        )
        session.flush()
    clubs = [
        Club(
            club_name=f"Club {region_id}",
            region_id=region_id,
            club_type="public_park",
            competitiveness_level=club_competitiveness_levels[index],
            member_capacity=100,
        )
        for index, region_id in enumerate([1, 2])
    ]
    session.add_all(clubs)
    session.flush()

    players = []
    for index in range(player_count):
        players.append(
            Player(
                first_name=f"Player{index}",
                last_name="Team",
                gender="M" if index % 2 == 0 else "F",
                birth_date=date(1980, 1, 1),
                home_region_id=1 if index < player_count // 2 else 2,
                registration_date=date(2024, 1, 1),
                player_status="ACTIVE",
                generation_run_id=generation_run.id,
            )
        )
    session.add_all(players)
    session.flush()
    for index, player in enumerate(players):
        club = clubs[0] if player.home_region_id == 1 else clubs[1]
        session.add(
            ClubMembership(
                player_id=player.id,
                club_id=club.id,
                membership_type="member",
                start_date=date(2024, 1, 1),
                is_primary=True,
                generation_run_id=generation_run.id,
            )
        )
        session.add(
            PlayerRatingHistory(
                player_id=player.id,
                rating_date=date(2024, 1, 1),
                rating_type="initial",
                rating_value=Decimal("1400") + Decimal(index * 10),
                confidence_score=Decimal("0.2"),
                batch_id=batch.id,
            )
        )
    session.commit()
    return generation_run, batch


def test_generate_for_batch_creates_teams_and_memberships(session):
    generation_run, batch = seed_team_data(session, player_count=20)

    result = TeamGenerator().generate_for_batch(
        generation_run_id=generation_run.id,
        batch_id=batch.id,
        session=session,
    )

    assert result.eligible_player_count == 20
    assert result.target_team_count == 8
    assert result.rows_loaded == session.query(Team).count()
    assert result.membership_rows_loaded == session.query(TeamMembership).count()
    assert result.membership_rows_loaded == result.rows_loaded * 2
    assert {team.team_status for team in session.query(Team)} == {"active"}
    assert {team.country_code for team in session.query(Team)} == {"US", "CA"}
    assert {team.formation_date for team in session.query(Team)} == {
        date(2024, 1, 1)
    }
    assert {
        event.event_type for event in session.query(TeamLifecycleEvent).all()
    } == {"formed"}
    assert _all_teams_have_two_players(session)
    assert _no_duplicate_players(session)
    assert _no_cross_country_teams(session)


def test_generate_for_batch_enforces_team_type_gender_constraints(session):
    payload = test_payload(20)
    payload["team_formation"]["team_type_weights"] = {
        "mens_doubles": 0.0,
        "womens_doubles": 0.0,
        "mixed_doubles": 1.0,
        "open_doubles": 0.0,
    }
    generation_run, batch = seed_team_data(session, payload=payload, player_count=20)

    TeamGenerator().generate_for_batch(
        generation_run_id=generation_run.id,
        batch_id=batch.id,
        session=session,
    )

    for team in session.query(Team):
        genders = {
            session.get(Player, membership.player_id).gender
            for membership in team.memberships
        }
        assert team.team_type == "mixed_doubles"
        assert genders == {"M", "F"}


def test_generate_for_batch_assigns_recreational_persistence_when_competitive_rate_zero(session):
    payload = test_payload(20)
    payload["team_formation"]["same_club_team_rate"] = 1.0
    payload["team_formation"]["same_region_team_rate"] = 1.0
    payload["team_formation"]["competitive_team_rate"] = 0.0
    payload["team_formation"]["team_persistence_probability_recreational"] = 0.61
    payload["team_formation"]["team_persistence_probability_competitive"] = 0.93
    generation_run, batch = seed_team_data(session, payload=payload, player_count=20)

    TeamGenerator().generate_for_batch(
        generation_run_id=generation_run.id,
        batch_id=batch.id,
        session=session,
    )

    for team in session.query(Team):
        assert Decimal(str(team.persistence_probability)) == Decimal("0.61")


def test_generate_for_batch_assigns_competitive_persistence_when_competitive_rate_one(session):
    payload = test_payload(20)
    payload["team_formation"]["competitive_team_rate"] = 1.0
    payload["team_formation"]["team_persistence_probability_recreational"] = 0.61
    payload["team_formation"]["team_persistence_probability_competitive"] = 0.93
    generation_run, batch = seed_team_data(session, payload=payload, player_count=20)

    TeamGenerator().generate_for_batch(
        generation_run_id=generation_run.id,
        batch_id=batch.id,
        session=session,
    )

    for team in session.query(Team):
        assert Decimal(str(team.persistence_probability)) == Decimal("0.93")


def test_generate_for_batch_is_deterministic(session_factory):
    first_session = session_factory()
    second_session = session_factory()
    try:
        first_run, first_batch = seed_team_data(first_session)
        second_run, second_batch = seed_team_data(second_session)

        TeamGenerator().generate_for_batch(
            generation_run_id=first_run.id,
            batch_id=first_batch.id,
            session=first_session,
        )
        TeamGenerator().generate_for_batch(
            generation_run_id=second_run.id,
            batch_id=second_batch.id,
            session=second_session,
        )

        assert _team_snapshot(first_session) == _team_snapshot(second_session)
    finally:
        first_session.close()
        second_session.close()


def test_generate_for_batch_rejects_existing_active_teams(session):
    generation_run, batch = seed_team_data(session)

    TeamGenerator().generate_for_batch(
        generation_run_id=generation_run.id,
        batch_id=batch.id,
        session=session,
    )

    with pytest.raises(ValueError, match="already has team updates for batch"):
        TeamGenerator().generate_for_batch(
            generation_run_id=generation_run.id,
            batch_id=batch.id,
            session=session,
        )


def test_generate_for_batch_requires_ratings(session):
    generation_run, batch = seed_team_data(session)
    session.query(PlayerRatingHistory).delete()
    session.commit()

    with pytest.raises(ValueError, match="No rating snapshots"):
        TeamGenerator().generate_for_batch(
            generation_run_id=generation_run.id,
            batch_id=batch.id,
            session=session,
        )


def test_generate_for_batch_validates_batch_ownership(session):
    generation_run, batch = seed_team_data(session)
    other_run = GenerationRun(
        generation_name="other",
        seed_value=999,
        parameter_snapshot=test_payload(2),
        status="pending",
    )
    session.add(other_run)
    session.commit()

    with pytest.raises(ValueError, match="Batch does not belong"):
        TeamGenerator().generate_for_batch(
            generation_run_id=other_run.id,
            batch_id=batch.id,
            session=session,
        )


def test_config_validates_team_type_weights():
    payload = test_payload(2)
    payload["team_formation"]["team_type_weights"] = {
        "mens_doubles": 0.9,
        "womens_doubles": 0.9,
    }

    with pytest.raises(ValueError, match="sum to 1.0"):
        TeamFormationConfig.from_payload(payload)


def test_config_validates_probability_fields():
    payload = test_payload(2)
    payload["team_formation"]["player_team_participation_rate"] = 2

    with pytest.raises(ValueError, match="player_team_participation_rate"):
        TeamFormationConfig.from_payload(payload)


def test_config_validates_competitive_team_rate():
    payload = test_payload(2)
    payload["team_formation"]["competitive_team_rate"] = 2

    with pytest.raises(ValueError, match="competitive_team_rate"):
        TeamFormationConfig.from_payload(payload)


def test_generate_for_later_batch_adds_teams_for_new_uncovered_players(session):
    payload = test_payload(20)
    payload["team_formation"]["player_team_participation_rate"] = 1.0
    payload["team_formation"]["dormant_team_reactivation_rate"] = 0.0
    payload["team_formation"]["team_persistence_probability_recreational"] = 1.0
    payload["team_formation"]["team_persistence_probability_competitive"] = 1.0
    payload["team_formation"]["same_club_team_rate"] = 0.0
    payload["team_formation"]["same_region_team_rate"] = 0.0
    payload["team_formation"]["rating_gap_max"] = 10_000
    payload["team_formation"]["team_type_weights"] = {
        "mens_doubles": 0.0,
        "womens_doubles": 0.0,
        "mixed_doubles": 0.0,
        "open_doubles": 1.0,
    }
    generation_run, batch = seed_team_data(session, payload=payload, player_count=20)

    TeamGenerator().generate_for_batch(
        generation_run_id=generation_run.id,
        batch_id=batch.id,
        session=session,
    )

    second_batch = MonthlyBatch(
        generation_run_id=generation_run.id,
        batch_month=date(2024, 2, 1),
        batch_sequence=2,
        batch_type="future_increment",
        processing_status="pending",
    )
    session.add(second_batch)
    session.flush()

    new_players = [
        Player(
            first_name="LateA",
            last_name="Team",
            gender="M",
            birth_date=date(1982, 1, 1),
            home_region_id=1,
            registration_date=date(2024, 2, 1),
            player_status="ACTIVE",
            generation_run_id=generation_run.id,
        ),
        Player(
            first_name="LateB",
            last_name="Team",
            gender="F",
            birth_date=date(1984, 1, 1),
            home_region_id=1,
            registration_date=date(2024, 2, 1),
            player_status="ACTIVE",
            generation_run_id=generation_run.id,
        ),
    ]
    session.add_all(new_players)
    session.flush()
    north_club = session.query(Club).filter_by(region_id=1).one()
    for player, rating in zip(new_players, [Decimal("1510"), Decimal("1520")]):
        session.add(
            ClubMembership(
                player_id=player.id,
                club_id=north_club.id,
                membership_type="member",
                start_date=date(2024, 2, 1),
                is_primary=True,
                generation_run_id=generation_run.id,
            )
        )
        session.add(
            PlayerRatingHistory(
                player_id=player.id,
                rating_date=date(2024, 2, 1),
                rating_type="initial",
                rating_value=rating,
                confidence_score=Decimal("0.2"),
                batch_id=second_batch.id,
            )
        )
    session.commit()

    result = TeamGenerator().generate_for_batch(
        generation_run_id=generation_run.id,
        batch_id=second_batch.id,
        session=session,
    )

    assert result.rows_loaded == 1
    assert result.membership_rows_loaded == 2
    assert result.target_team_count == 1
    assert session.query(Team).count() == 11
    new_team = session.query(Team).order_by(Team.id.desc()).first()
    assert new_team.formation_date == date(2024, 2, 1)
    assert new_team.country_code == "US"
    assert {membership.player_id for membership in new_team.memberships} == {
        new_players[0].id,
        new_players[1].id,
    }


def test_generate_for_later_batch_uses_stored_persistence_probability_for_lifecycle(session):
    payload = test_payload(4)
    payload["team_formation"]["player_team_participation_rate"] = 1.0
    payload["team_formation"]["competitive_team_rate"] = 0.0
    payload["team_formation"]["dormant_team_reactivation_rate"] = 0.0
    payload["team_formation"]["retired_team_rate_on_dissolution"] = 0.0
    payload["team_formation"]["team_type_weights"] = {
        "mens_doubles": 0.0,
        "womens_doubles": 0.0,
        "mixed_doubles": 0.0,
        "open_doubles": 1.0,
    }
    generation_run, batch = seed_team_data(session, payload=payload, player_count=4)

    TeamGenerator().generate_for_batch(
        generation_run_id=generation_run.id,
        batch_id=batch.id,
        session=session,
    )

    teams = session.query(Team).order_by(Team.id).all()
    teams[0].persistence_probability = Decimal("1.0")
    teams[1].persistence_probability = Decimal("0.0")
    session.commit()

    second_batch = MonthlyBatch(
        generation_run_id=generation_run.id,
        batch_month=date(2024, 2, 1),
        batch_sequence=2,
        batch_type="future_increment",
        processing_status="pending",
    )
    session.add(second_batch)
    session.commit()

    result = TeamGenerator().generate_for_batch(
        generation_run_id=generation_run.id,
        batch_id=second_batch.id,
        session=session,
    )

    session.refresh(teams[0])
    session.refresh(teams[1])
    assert result.rows_loaded == 1
    assert teams[0].team_status == "active"
    assert teams[0].dissolution_date is None
    assert teams[1].team_status == "dormant"
    assert teams[1].dissolution_date == date(2024, 2, 1)
    lifecycle_events = (
        session.query(TeamLifecycleEvent)
        .filter(TeamLifecycleEvent.batch_id == second_batch.id)
        .order_by(TeamLifecycleEvent.team_id, TeamLifecycleEvent.id)
        .all()
    )
    assert [(event.team_id, event.event_type) for event in lifecycle_events] == [
        (teams[1].id, "dormant"),
        (session.query(Team).order_by(Team.id.desc()).first().id, "formed"),
    ]


def test_generate_for_later_batch_records_reactivated_team_event(session):
    payload = test_payload(4)
    payload["team_formation"]["player_team_participation_rate"] = 1.0
    payload["team_formation"]["competitive_team_rate"] = 0.0
    payload["team_formation"]["dormant_team_reactivation_rate"] = 1.0
    payload["team_formation"]["retired_team_rate_on_dissolution"] = 0.0
    payload["team_formation"]["team_type_weights"] = {
        "mens_doubles": 0.0,
        "womens_doubles": 0.0,
        "mixed_doubles": 0.0,
        "open_doubles": 1.0,
    }
    generation_run, batch = seed_team_data(session, payload=payload, player_count=4)

    TeamGenerator().generate_for_batch(
        generation_run_id=generation_run.id,
        batch_id=batch.id,
        session=session,
    )

    team = session.query(Team).order_by(Team.id).first()
    team.team_status = "dormant"
    team.dissolution_date = date(2024, 2, 1)
    dormant_batch = MonthlyBatch(
        generation_run_id=generation_run.id,
        batch_month=date(2024, 2, 1),
        batch_sequence=2,
        batch_type="future_increment",
        processing_status="succeeded",
    )
    session.add(dormant_batch)
    session.flush()
    session.add(
        TeamLifecycleEvent(
            generation_run_id=generation_run.id,
            batch_id=dormant_batch.id,
            team_id=team.id,
            event_date=date(2024, 2, 1),
            event_type="dormant",
        )
    )
    session.commit()

    reactivation_batch = MonthlyBatch(
        generation_run_id=generation_run.id,
        batch_month=date(2024, 3, 1),
        batch_sequence=3,
        batch_type="future_increment",
        processing_status="pending",
    )
    session.add(reactivation_batch)
    session.commit()

    TeamGenerator().generate_for_batch(
        generation_run_id=generation_run.id,
        batch_id=reactivation_batch.id,
        session=session,
    )

    reactivation_event = (
        session.query(TeamLifecycleEvent)
        .filter(
            TeamLifecycleEvent.batch_id == reactivation_batch.id,
            TeamLifecycleEvent.team_id == team.id,
            TeamLifecycleEvent.event_type == "reactivated",
        )
        .one()
    )
    assert reactivation_event.event_date == date(2024, 3, 1)


def _all_teams_have_two_players(session):
    return all(len(team.memberships) == 2 for team in session.query(Team))


def _no_duplicate_players(session):
    player_ids = [
        membership.player_id for membership in session.query(TeamMembership).all()
    ]
    return len(player_ids) == len(set(player_ids))


def _no_cross_country_teams(session):
    country_by_region_id = {
        region.id: region.country_code for region in session.query(Region).all()
    }
    for team in session.query(Team):
        member_countries = {
            country_by_region_id[session.get(Player, membership.player_id).home_region_id]
            for membership in team.memberships
        }
        if member_countries != {team.country_code}:
            return False
    return True


def _team_snapshot(session):
    return [
        (
            team.team_type,
            team.team_status,
            team.country_code,
            team.formation_date,
            str(team.chemistry_score),
            str(team.persistence_probability),
            tuple(
                (membership.player_id, membership.player_position)
                for membership in sorted(
                    team.memberships,
                    key=lambda membership: membership.player_position,
                )
            ),
        )
        for team in session.query(Team).order_by(Team.id)
    ]
