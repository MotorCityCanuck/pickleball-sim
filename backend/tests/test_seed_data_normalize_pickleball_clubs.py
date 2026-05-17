"""Tests for pickleball club seed normalization."""
from pathlib import Path
import sys

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.models import Club, Region  # noqa: E402
from app.seed_data_normalize import PickleballClubNormalizer  # noqa: E402
from app.seed_data_normalize.pickleball_clubs import (  # noqa: E402
    ClubGenerationConfig,
    capacity_for,
    court_counts_for,
    founding_date_for,
    map_club_type,
)


@pytest.fixture()
def session_factory():
    engine = create_engine("sqlite:///:memory:", future=True)
    with engine.begin() as conn:
        conn.exec_driver_sql(
            """
            CREATE TABLE raw_pickleball_club_distributions (
                id integer primary key autoincrement,
                load_run_id bigint not null,
                source_file varchar(500) not null,
                source_row_number integer not null,
                raw_payload text not null,
                country_code varchar(2) not null,
                state_province_code varchar(10) not null,
                state_province_name varchar(255) not null,
                target_club_count integer not null,
                source_dataset varchar(255),
                created_at datetime default current_timestamp not null,
                updated_at datetime default current_timestamp not null
            )
            """
        )
        conn.exec_driver_sql(
            """
            CREATE TABLE raw_pickleball_club_names (
                id integer primary key autoincrement,
                load_run_id bigint not null,
                source_file varchar(500) not null,
                source_row_number integer not null,
                raw_payload text not null,
                club_seed bigint not null,
                country_code varchar(2) not null,
                state_province_code varchar(10) not null,
                club_name varchar(255) not null,
                club_type varchar(80),
                size_tier varchar(30),
                generation_method varchar(100),
                source_dataset varchar(255),
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
                updated_at datetime default current_timestamp not null,
                unique (region_id, club_name)
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


def insert_distribution(
    session,
    *,
    country_code: str,
    state_province_code: str,
    target_club_count: int,
) -> None:
    session.execute(
        text(
            """
            INSERT INTO raw_pickleball_club_distributions (
                load_run_id,
                source_file,
                source_row_number,
                raw_payload,
                country_code,
                state_province_code,
                state_province_name,
                target_club_count,
                source_dataset
            )
            VALUES (
                1,
                'club_distribution.csv',
                2,
                '{}',
                :country_code,
                :state_province_code,
                :state_province_code,
                :target_club_count,
                'test'
            )
            """
        ),
        {
            "country_code": country_code,
            "state_province_code": state_province_code,
            "target_club_count": target_club_count,
        },
    )
    session.commit()


def insert_club_name(
    session,
    *,
    club_seed: int,
    country_code: str,
    state_province_code: str,
    club_name: str,
    club_type: str = "Public Park Club",
    size_tier: str = "Small",
) -> None:
    session.execute(
        text(
            """
            INSERT INTO raw_pickleball_club_names (
                load_run_id,
                source_file,
                source_row_number,
                raw_payload,
                club_seed,
                country_code,
                state_province_code,
                club_name,
                club_type,
                size_tier,
                generation_method,
                source_dataset
            )
            VALUES (
                1,
                'club_names.csv',
                2,
                '{}',
                :club_seed,
                :country_code,
                :state_province_code,
                :club_name,
                :club_type,
                :size_tier,
                'test',
                'test'
            )
            """
        ),
        {
            "club_seed": club_seed,
            "country_code": country_code,
            "state_province_code": state_province_code,
            "club_name": club_name,
            "club_type": club_type,
            "size_tier": size_tier,
        },
    )
    session.commit()


def insert_region(
    session,
    *,
    country_code: str,
    state_province_code: str,
    region_name: str,
    selection_probability: str,
) -> Region:
    region = Region(
        country_code=country_code,
        state_province_code=state_province_code,
        region_name=region_name,
        selection_probability=selection_probability,
    )
    session.add(region)
    session.commit()
    return region


def test_requires_replace_production_flag(session):
    insert_distribution(
        session,
        country_code="US",
        state_province_code="TX",
        target_club_count=1,
    )

    with pytest.raises(ValueError, match="replace-production"):
        PickleballClubNormalizer().normalize(session=session)

    assert session.query(Club).count() == 0


def test_normalizes_clubs_with_derived_fields(session):
    region = insert_region(
        session,
        country_code="US",
        state_province_code="TX",
        region_name="Austin",
        selection_probability="1.0",
    )
    insert_distribution(
        session,
        country_code="US",
        state_province_code="TX",
        target_club_count=2,
    )
    insert_club_name(
        session,
        club_seed=101,
        country_code="US",
        state_province_code="TX",
        club_name="Austin Public Pickleball",
        club_type="Public Park Club",
        size_tier="Small",
    )
    insert_club_name(
        session,
        club_seed=202,
        country_code="US",
        state_province_code="TX",
        club_name="Austin Tournament Center",
        club_type="Tournament Club",
        size_tier="Large",
    )

    result = PickleballClubNormalizer().normalize(
        replace_production=True,
        session=session,
    )

    assert result.status == "completed"
    assert result.rows_read == 1
    assert result.rows_deleted == 0
    assert result.rows_loaded == 2

    clubs = session.query(Club).order_by(Club.club_name).all()
    assert [club.region_id for club in clubs] == [region.id, region.id]
    assert [
        (
            club.club_name,
            club.club_type,
            club.competitiveness_level,
            club.member_capacity,
            club.founding_date,
            club.indoor_court_count,
            club.outdoor_court_count,
        )
        for club in clubs
    ] == [
        (
            "Austin Public Pickleball",
            "public_park",
            "recreational",
            capacity_for("Small", 101),
            founding_date_for("public_park", "Small", 101),
            *court_counts_for("public_park", "Small", 101),
        ),
        (
            "Austin Tournament Center",
            "dedicated_facility",
            "elite",
            capacity_for("Large", 202),
            founding_date_for("dedicated_facility", "Large", 202),
            *court_counts_for("dedicated_facility", "Large", 202),
        ),
    ]


def test_fills_name_shortages_with_visible_placeholder(session):
    insert_region(
        session,
        country_code="US",
        state_province_code="TX",
        region_name="Austin",
        selection_probability="1.0",
    )
    insert_distribution(
        session,
        country_code="US",
        state_province_code="TX",
        target_club_count=2,
    )
    insert_club_name(
        session,
        club_seed=101,
        country_code="US",
        state_province_code="TX",
        club_name="Austin Public Pickleball",
    )

    PickleballClubNormalizer().normalize(
        replace_production=True,
        session=session,
    )

    assert {
        club.club_name for club in session.query(Club).all()
    } == {
        "Austin Public Pickleball",
        "Not Enough Club Names TX-2",
    }


def test_rejects_distribution_without_eligible_region(session):
    insert_distribution(
        session,
        country_code="CA",
        state_province_code="NU",
        target_club_count=1,
    )
    insert_club_name(
        session,
        club_seed=1,
        country_code="CA",
        state_province_code="NU",
        club_name="Nunavut Pickleball",
    )

    with pytest.raises(ValueError, match="no eligible production regions"):
        PickleballClubNormalizer().normalize(
            replace_production=True,
            session=session,
        )

    assert session.query(Club).count() == 0


def test_replaces_existing_clubs(session):
    region = insert_region(
        session,
        country_code="US",
        state_province_code="TX",
        region_name="Austin",
        selection_probability="1.0",
    )
    session.add(
        Club(
            club_name="Old Club",
            region_id=region.id,
            club_type="public_park",
        )
    )
    session.commit()
    insert_distribution(
        session,
        country_code="US",
        state_province_code="TX",
        target_club_count=1,
    )
    insert_club_name(
        session,
        club_seed=101,
        country_code="US",
        state_province_code="TX",
        club_name="Austin Public Pickleball",
    )

    result = PickleballClubNormalizer().normalize(
        replace_production=True,
        session=session,
    )

    assert result.rows_deleted == 1
    assert [club.club_name for club in session.query(Club).all()] == [
        "Austin Public Pickleball"
    ]


def test_club_type_mapping_covers_staged_values():
    assert map_club_type("Community Recreation Club") == "community_center"
    assert map_club_type("Competitive Training Club") == "dedicated_facility"
    assert map_club_type("Indoor Facility Club") == "dedicated_facility"
    assert map_club_type("League Organization") == "municipal_recreation"
    assert map_club_type("Private Athletic Club") == "private_club"
    assert map_club_type("Public Park Club") == "public_park"
    assert map_club_type("Retirement Community Club") == "community_center"
    assert map_club_type("Social Club") == "community_center"
    assert map_club_type("Tournament Club") == "dedicated_facility"
    assert map_club_type("Unexpected") == "community_center"


def test_club_generation_config_reads_json_payload_values():
    config = ClubGenerationConfig.from_payload(
        {
            "club_generation": {
                "capacity_ranges": {"small": [100, 100]},
                "court_ranges": {"small": [10, 10]},
                "indoor_court_ratios": {"public_park": 0.5},
            }
        }
    )

    assert capacity_for("Small", 101, config) == 100
    assert court_counts_for("public_park", "Small", 101, config) == (5, 5)
