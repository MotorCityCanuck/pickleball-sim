"""Tests for last-name seed normalization."""
from decimal import Decimal
from pathlib import Path
import sys

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.models import LastName, Region  # noqa: E402
from app.seed_data_normalize import LastNameNormalizer  # noqa: E402


@pytest.fixture()
def session_factory():
    engine = create_engine("sqlite:///:memory:", future=True)
    with engine.begin() as conn:
        conn.exec_driver_sql(
            """
            CREATE TABLE raw_last_names (
                id integer primary key autoincrement,
                load_run_id bigint not null,
                source_file varchar(500) not null,
                source_row_number integer not null,
                raw_payload text not null,
                country_code varchar(2) not null,
                last_name varchar(100) not null,
                frequency_count integer not null,
                source_dataset varchar(255),
                created_at datetime default current_timestamp not null,
                updated_at datetime default current_timestamp not null
            )
            """
        )
        conn.exec_driver_sql(
            """
            CREATE TABLE raw_state_prov_biases (
                id integer primary key autoincrement,
                load_run_id bigint not null,
                source_file varchar(500) not null,
                source_row_number integer not null,
                raw_payload text not null,
                country_code varchar(2) not null,
                state_province_code varchar(10) not null,
                last_name varchar(100) not null,
                bias_multiplier numeric(10, 4) not null,
                bias_reason text,
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
            CREATE TABLE last_names (
                id integer primary key autoincrement,
                country_code varchar(2) not null,
                state_province_code varchar(2) not null,
                last_name varchar(100) not null,
                frequency_count integer not null,
                bias_multiplier numeric(10, 4),
                adjusted_frequency_count numeric(18, 4),
                normalized_probability numeric(12, 8),
                source_dataset varchar(255),
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


def insert_region(session, country_code: str, state_province_code: str) -> None:
    session.add(
        Region(
            country_code=country_code,
            state_province_code=state_province_code,
            region_name=f"{state_province_code} Metro",
        )
    )
    session.commit()


def insert_raw_last_name(
    session,
    *,
    country_code: str,
    last_name: str,
    frequency_count: int,
    source_dataset: str = "test",
) -> None:
    session.execute(
        text(
            """
            INSERT INTO raw_last_names (
                load_run_id,
                source_file,
                source_row_number,
                raw_payload,
                country_code,
                last_name,
                frequency_count,
                source_dataset
            )
            VALUES (
                1,
                'last_names.csv',
                2,
                '{}',
                :country_code,
                :last_name,
                :frequency_count,
                :source_dataset
            )
            """
        ),
        {
            "country_code": country_code,
            "last_name": last_name,
            "frequency_count": frequency_count,
            "source_dataset": source_dataset,
        },
    )
    session.commit()


def insert_bias(
    session,
    *,
    country_code: str,
    state_province_code: str,
    last_name: str,
    bias_multiplier: str,
) -> None:
    session.execute(
        text(
            """
            INSERT INTO raw_state_prov_biases (
                load_run_id,
                source_file,
                source_row_number,
                raw_payload,
                country_code,
                state_province_code,
                last_name,
                bias_multiplier,
                source_dataset
            )
            VALUES (
                1,
                'biases.csv',
                2,
                '{}',
                :country_code,
                :state_province_code,
                :last_name,
                :bias_multiplier,
                'test'
            )
            """
        ),
        {
            "country_code": country_code,
            "state_province_code": state_province_code,
            "last_name": last_name,
            "bias_multiplier": bias_multiplier,
        },
    )
    session.commit()


def test_requires_replace_production_flag(session):
    insert_region(session, "US", "TX")
    insert_raw_last_name(
        session,
        country_code="US",
        last_name="Smith",
        frequency_count=10,
    )

    with pytest.raises(ValueError, match="replace-production"):
        LastNameNormalizer().normalize(session=session)

    assert session.query(LastName).count() == 0


def test_applies_bias_and_normalizes_by_country_state_cohort(session):
    insert_region(session, "US", "TX")
    insert_region(session, "US", "CA")
    insert_raw_last_name(
        session,
        country_code="US",
        last_name="Smith",
        frequency_count=30,
    )
    insert_raw_last_name(
        session,
        country_code="US",
        last_name="Jones",
        frequency_count=10,
    )
    insert_bias(
        session,
        country_code="US",
        state_province_code="TX",
        last_name="Smith",
        bias_multiplier="2.0000",
    )

    result = LastNameNormalizer().normalize(
        replace_production=True,
        session=session,
    )

    assert result.status == "completed"
    assert result.rows_read == 2
    assert result.rows_deleted == 0
    assert result.rows_loaded == 4

    rows = session.query(LastName).order_by(
        LastName.state_province_code,
        LastName.last_name,
    ).all()
    assert [
        (
            row.state_province_code,
            row.last_name,
            row.frequency_count,
            row.bias_multiplier,
            row.adjusted_frequency_count,
            row.normalized_probability,
        )
        for row in rows
    ] == [
        ("CA", "Jones", 10, Decimal("1.0000"), Decimal("10.0000"), Decimal("0.25000000")),
        ("CA", "Smith", 30, Decimal("1.0000"), Decimal("30.0000"), Decimal("0.75000000")),
        ("TX", "Jones", 10, Decimal("1.0000"), Decimal("10.0000"), Decimal("0.14285714")),
        ("TX", "Smith", 30, Decimal("2.0000"), Decimal("60.0000"), Decimal("0.85714286")),
    ]


def test_aggregates_duplicate_raw_last_names_before_bias(session):
    insert_region(session, "CA", "ON")
    insert_raw_last_name(
        session,
        country_code="CA",
        last_name="Smith",
        frequency_count=6,
    )
    insert_raw_last_name(
        session,
        country_code="CA",
        last_name="Smith",
        frequency_count=4,
    )
    insert_raw_last_name(
        session,
        country_code="CA",
        last_name="Tremblay",
        frequency_count=10,
    )

    result = LastNameNormalizer().normalize(
        replace_production=True,
        session=session,
    )

    assert result.rows_read == 3
    assert result.rows_loaded == 2
    rows = session.query(LastName).order_by(LastName.last_name).all()
    assert [
        (row.last_name, row.frequency_count, row.normalized_probability)
        for row in rows
    ] == [
        ("Smith", 10, Decimal("0.50000000")),
        ("Tremblay", 10, Decimal("0.50000000")),
    ]


def test_rejects_duplicate_bias_rules(session):
    insert_region(session, "US", "TX")
    insert_raw_last_name(
        session,
        country_code="US",
        last_name="Smith",
        frequency_count=10,
    )
    for _ in range(2):
        insert_bias(
            session,
            country_code="US",
            state_province_code="TX",
            last_name="Smith",
            bias_multiplier="2.0000",
        )

    with pytest.raises(ValueError, match="Duplicate state/province last-name bias rules"):
        LastNameNormalizer().normalize(
            replace_production=True,
            session=session,
        )


def test_rejects_bias_rules_for_missing_raw_last_names(session):
    insert_region(session, "US", "TX")
    insert_raw_last_name(
        session,
        country_code="US",
        last_name="Smith",
        frequency_count=10,
    )
    insert_bias(
        session,
        country_code="US",
        state_province_code="TX",
        last_name="Missing",
        bias_multiplier="2.0000",
    )

    with pytest.raises(ValueError, match="missing raw last names"):
        LastNameNormalizer().normalize(
            replace_production=True,
            session=session,
        )


def test_replace_deletes_existing_last_names_for_region_countries_only(session):
    insert_region(session, "US", "TX")
    session.add(
        LastName(
            country_code="US",
            state_province_code="TX",
            last_name="Old",
            frequency_count=1,
        )
    )
    session.add(
        LastName(
            country_code="MX",
            state_province_code="CM",
            last_name="Garcia",
            frequency_count=1,
        )
    )
    session.commit()
    insert_raw_last_name(
        session,
        country_code="US",
        last_name="Smith",
        frequency_count=10,
    )

    result = LastNameNormalizer().normalize(
        replace_production=True,
        session=session,
    )

    assert result.rows_deleted == 1
    assert {
        (row.country_code, row.state_province_code, row.last_name)
        for row in session.query(LastName).all()
    } == {
        ("US", "TX", "Smith"),
        ("MX", "CM", "Garcia"),
    }
