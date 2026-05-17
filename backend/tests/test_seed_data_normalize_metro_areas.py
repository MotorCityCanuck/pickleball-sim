"""Tests for metro-area seed normalization."""
from decimal import Decimal
from pathlib import Path
import sys

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.models import Region  # noqa: E402
from app.seed_data_normalize import MetroAreaNormalizer  # noqa: E402


@pytest.fixture()
def session_factory():
    engine = create_engine("sqlite:///:memory:", future=True)
    with engine.begin() as conn:
        conn.exec_driver_sql(
            """
            CREATE TABLE raw_metro_areas (
                id integer primary key autoincrement,
                load_run_id bigint not null,
                source_file varchar(500) not null,
                source_row_number integer not null,
                raw_payload text not null,
                country_code varchar(2) not null,
                state_province_code varchar(10) not null,
                metro_area_name varchar(255) not null,
                population bigint not null,
                selection_probability numeric(12, 8) not null,
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
                updated_at datetime default current_timestamp not null,
                unique (country_code, state_province_code, region_name)
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


def insert_raw_metro(
    session,
    *,
    country_code: str,
    state_province_code: str,
    metro_area_name: str,
    population: int = 1000,
    selection_probability: str = "0.50000000",
) -> None:
    session.execute(
        text(
            """
            INSERT INTO raw_metro_areas (
                load_run_id,
                source_file,
                source_row_number,
                raw_payload,
                country_code,
                state_province_code,
                metro_area_name,
                population,
                selection_probability,
                source_dataset
            )
            VALUES (
                1,
                'metro.csv',
                2,
                '{}',
                :country_code,
                :state_province_code,
                :metro_area_name,
                :population,
                :selection_probability,
                'test'
            )
            """
        ),
        {
            "country_code": country_code,
            "state_province_code": state_province_code,
            "metro_area_name": metro_area_name,
            "population": population,
            "selection_probability": selection_probability,
        },
    )
    session.commit()


def test_requires_replace_production_flag(session):
    insert_raw_metro(
        session,
        country_code="US",
        state_province_code="TX",
        metro_area_name="Austin",
    )

    with pytest.raises(ValueError, match="replace-production"):
        MetroAreaNormalizer().normalize(session=session)

    assert session.query(Region).count() == 0


def test_normalizes_raw_metro_areas_to_regions(session):
    insert_raw_metro(
        session,
        country_code="US",
        state_province_code="TX",
        metro_area_name="Austin",
        population=2283371,
        selection_probability="0.12000000",
    )
    insert_raw_metro(
        session,
        country_code="CA",
        state_province_code="ON",
        metro_area_name="Ottawa-Gatineau (CMA), Ontario",
        population=1488307,
        selection_probability="0.08000000",
    )

    result = MetroAreaNormalizer().normalize(
        replace_production=True,
        session=session,
    )

    assert result.status == "completed"
    assert result.rows_read == 2
    assert result.rows_deleted == 0
    assert result.rows_loaded == 2

    regions = session.query(Region).order_by(Region.country_code.desc()).all()
    assert [(row.country_code, row.state_province_code, row.region_name) for row in regions] == [
        ("US", "TX", "Austin"),
        ("CA", "ON", "Ottawa-Gatineau (CMA), Ontario"),
    ]
    assert regions[0].region_type == "MSA"
    assert regions[0].population == 2283371
    assert regions[0].selection_probability == Decimal("0.12000000")
    assert regions[1].region_type == "CMA"
    assert regions[1].selection_probability == Decimal("0.08000000")


def test_replace_deletes_existing_regions_for_raw_countries_only(session):
    session.add(
        Region(
            country_code="US",
            state_province_code="TX",
            region_name="Old Austin",
        )
    )
    session.add(
        Region(
            country_code="MX",
            state_province_code="CMX",
            region_name="Mexico City",
        )
    )
    session.commit()
    insert_raw_metro(
        session,
        country_code="US",
        state_province_code="TX",
        metro_area_name="Austin",
    )

    result = MetroAreaNormalizer().normalize(
        replace_production=True,
        session=session,
    )

    assert result.rows_deleted == 1
    assert {
        (row.country_code, row.state_province_code, row.region_name)
        for row in session.query(Region).all()
    } == {
        ("US", "TX", "Austin"),
        ("MX", "CMX", "Mexico City"),
    }


def test_aggregates_duplicate_raw_region_natural_keys(session):
    for _ in range(2):
        insert_raw_metro(
            session,
            country_code="US",
            state_province_code="MO",
            metro_area_name="Springfield",
            population=1000,
            selection_probability="0.10000000",
        )

    result = MetroAreaNormalizer().normalize(
        replace_production=True,
        session=session,
    )

    assert result.rows_read == 2
    assert result.rows_loaded == 1

    region = session.query(Region).one()
    assert region.country_code == "US"
    assert region.state_province_code == "MO"
    assert region.region_name == "Springfield"
    assert region.population == 2000
    assert region.selection_probability == Decimal("0.20000000")
