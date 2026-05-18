"""Tests for generated player-to-club assignments."""
from copy import deepcopy
from datetime import date
from pathlib import Path
import sys

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.default_configuration import DEFAULT_CONFIG_PAYLOAD  # noqa: E402
from app.generators import (  # noqa: E402
    ClubMembershipGenerationConfig,
    ClubMembershipGenerator,
)
from app.models import Club, ClubMembership, GenerationRun, Player  # noqa: E402


def test_payload(player_count=100):
    payload = deepcopy(DEFAULT_CONFIG_PAYLOAD)
    payload["player_generation"]["player_count"] = player_count
    payload["simulation"]["target_total_players"] = player_count
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
    return sessionmaker(bind=engine, autoflush=False, future=True)


@pytest.fixture()
def session(session_factory):
    db_session = session_factory()
    try:
        yield db_session
    finally:
        db_session.close()


def seed_players_and_clubs(session, *, payload=None, player_count=100):
    generation_run = GenerationRun(
        generation_name="club membership gen",
        seed_value=123,
        simulation_version="test",
        parameter_snapshot=payload or test_payload(player_count),
        status="pending",
    )
    session.add(generation_run)
    session.flush()

    clubs = []
    for region_id in [1, 2]:
        for index in range(5):
            clubs.append(
                Club(
                    club_name=f"Region {region_id} Club {index}",
                    region_id=region_id,
                    club_type="public_park",
                    competitiveness_level="recreational",
                    member_capacity=25 + index * 25,
                    founding_date=date(2010, 1, 1),
                )
            )
    session.add_all(clubs)
    session.flush()

    players = [
        Player(
            first_name=f"Player{index}",
            last_name="Test",
            birth_date=date(1980, 1, 1),
            home_region_id=1 if index % 2 == 0 else 2,
            registration_date=date(2024, 1, 1),
            player_status="ACTIVE",
            generation_run_id=generation_run.id,
        )
        for index in range(player_count)
    ]
    session.add_all(players)
    session.commit()
    return generation_run


def test_generate_for_run_creates_primary_and_secondary_memberships(session):
    payload = test_payload(100)
    payload["club_generation"]["unaffiliated_player_rate"] = 0.12
    payload["club_generation"]["multi_club_membership_rate"] = 0.10
    payload["club_generation"]["max_club_memberships_per_player"] = 3
    generation_run = seed_players_and_clubs(
        session,
        payload=payload,
        player_count=100,
    )

    result = ClubMembershipGenerator().generate_for_run(
        generation_run_id=generation_run.id,
        session=session,
    )

    assert result.players_evaluated == 100
    assert result.affiliated_player_count + result.unaffiliated_player_count == 100
    assert result.rows_loaded == session.query(ClubMembership).count()
    assert result.affiliated_player_count == _primary_membership_count(session)
    assert result.multi_club_player_count == _secondary_player_count(session)
    assert result.unaffiliated_player_count > 0
    assert result.multi_club_player_count > 0

    primary_memberships = (
        session.query(ClubMembership).filter(ClubMembership.is_primary.is_(True)).all()
    )
    assert all(row.membership_type == "member" for row in primary_memberships)
    secondary_memberships = (
        session.query(ClubMembership).filter(ClubMembership.is_primary.is_(False)).all()
    )
    assert all(row.membership_type == "secondary" for row in secondary_memberships)


def test_generate_for_run_is_deterministic(session_factory):
    first_session = session_factory()
    second_session = session_factory()
    try:
        first_run = seed_players_and_clubs(first_session)
        second_run = seed_players_and_clubs(second_session)

        ClubMembershipGenerator().generate_for_run(
            generation_run_id=first_run.id,
            session=first_session,
        )
        ClubMembershipGenerator().generate_for_run(
            generation_run_id=second_run.id,
            session=second_session,
        )

        first_memberships = _membership_snapshot(first_session)
        second_memberships = _membership_snapshot(second_session)

        assert first_memberships == second_memberships
    finally:
        first_session.close()
        second_session.close()


def test_generate_for_run_rejects_existing_memberships(session):
    generation_run = seed_players_and_clubs(session, player_count=5)

    ClubMembershipGenerator().generate_for_run(
        generation_run_id=generation_run.id,
        session=session,
    )

    with pytest.raises(ValueError, match="already has club memberships"):
        ClubMembershipGenerator().generate_for_run(
            generation_run_id=generation_run.id,
            session=session,
        )


def test_generate_for_run_requires_players(session):
    generation_run = GenerationRun(
        generation_name="empty",
        seed_value=123,
        parameter_snapshot=test_payload(1),
        status="pending",
    )
    session.add(generation_run)
    session.commit()

    with pytest.raises(ValueError, match="has no players"):
        ClubMembershipGenerator().generate_for_run(
            generation_run_id=generation_run.id,
            session=session,
        )


def test_generate_for_run_requires_clubs(session):
    generation_run = seed_players_and_clubs(session, player_count=1)
    session.query(Club).delete()
    session.commit()

    with pytest.raises(ValueError, match="No clubs"):
        ClubMembershipGenerator().generate_for_run(
            generation_run_id=generation_run.id,
            session=session,
        )


def test_config_validates_membership_probabilities():
    payload = test_payload(1)
    payload["club_generation"]["multi_club_membership_rate"] = 2

    with pytest.raises(ValueError, match="multi_club_membership_rate"):
        ClubMembershipGenerationConfig.from_payload(payload)


def test_config_validates_membership_bounds():
    payload = test_payload(1)
    payload["club_generation"]["min_club_memberships_per_affiliated_player"] = 4
    payload["club_generation"]["max_club_memberships_per_player"] = 3

    with pytest.raises(ValueError, match="max_club_memberships_per_player"):
        ClubMembershipGenerationConfig.from_payload(payload)


def _membership_snapshot(session):
    return [
        (
            membership.player_id,
            membership.club_id,
            membership.membership_type,
            membership.start_date,
            membership.is_primary,
            membership.generation_run_id,
        )
        for membership in session.query(ClubMembership).order_by(ClubMembership.id)
    ]


def _primary_membership_count(session):
    return (
        session.query(ClubMembership.player_id)
        .filter(ClubMembership.is_primary.is_(True))
        .distinct()
        .count()
    )


def _secondary_player_count(session):
    return (
        session.query(ClubMembership.player_id)
        .filter(ClubMembership.is_primary.is_(False))
        .distinct()
        .count()
    )
