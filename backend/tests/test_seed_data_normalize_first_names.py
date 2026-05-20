"""Tests for first-name seed normalization."""
from decimal import Decimal
from pathlib import Path
import sys

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.models import FirstName  # noqa: E402
from app.seed_data_normalize import FirstNameNormalizer  # noqa: E402


@pytest.fixture()
def session_factory():
    engine = create_engine("sqlite:///:memory:", future=True)
    with engine.begin() as conn:
        conn.exec_driver_sql(
            """
            CREATE TABLE raw_first_names (
                id integer primary key autoincrement,
                load_run_id bigint not null,
                source_file varchar(500) not null,
                source_row_number integer not null,
                raw_payload text not null,
                country_code varchar(2) not null,
                state_province_code varchar(10) not null,
                gender varchar(1) not null,
                birth_year integer not null,
                first_name varchar(100) not null,
                frequency_count integer not null,
                source_dataset varchar(255),
                created_at datetime default current_timestamp not null,
                updated_at datetime default current_timestamp not null
            )
            """
        )
        conn.exec_driver_sql(
            """
            CREATE TABLE first_names (
                id integer primary key autoincrement,
                country_code varchar(2) not null,
                state_province_code varchar(2) not null,
                birth_year integer not null,
                gender varchar(1) not null,
                first_name varchar(100) not null,
                frequency_count integer not null,
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


def insert_raw_first_name(
    session,
    *,
    country_code: str,
    state_province_code: str,
    birth_year: int,
    gender: str,
    first_name: str,
    frequency_count: int,
    source_dataset: str = "test",
) -> None:
    session.execute(
        text(
            """
            INSERT INTO raw_first_names (
                load_run_id,
                source_file,
                source_row_number,
                raw_payload,
                country_code,
                state_province_code,
                gender,
                birth_year,
                first_name,
                frequency_count,
                source_dataset
            )
            VALUES (
                1,
                'first_names.csv',
                2,
                '{}',
                :country_code,
                :state_province_code,
                :gender,
                :birth_year,
                :first_name,
                :frequency_count,
                :source_dataset
            )
            """
        ),
        {
            "country_code": country_code,
            "state_province_code": state_province_code,
            "birth_year": birth_year,
            "gender": gender,
            "first_name": first_name,
            "frequency_count": frequency_count,
            "source_dataset": source_dataset,
        },
    )
    session.commit()


def test_requires_replace_production_flag(session):
    insert_raw_first_name(
        session,
        country_code="US",
        state_province_code="TX",
        birth_year=2000,
        gender="F",
        first_name="Emma",
        frequency_count=10,
    )

    with pytest.raises(ValueError, match="replace-production"):
        FirstNameNormalizer().normalize(session=session)

    assert session.query(FirstName).count() == 0


def test_normalizes_probabilities_by_country_state_year_gender_cohort(session):
    insert_raw_first_name(
        session,
        country_code="US",
        state_province_code="TX",
        birth_year=2000,
        gender="F",
        first_name="Emma",
        frequency_count=30,
    )
    insert_raw_first_name(
        session,
        country_code="US",
        state_province_code="TX",
        birth_year=2000,
        gender="F",
        first_name="Olivia",
        frequency_count=10,
    )
    insert_raw_first_name(
        session,
        country_code="US",
        state_province_code="TX",
        birth_year=2000,
        gender="M",
        first_name="Noah",
        frequency_count=7,
    )

    result = FirstNameNormalizer().normalize(
        replace_production=True,
        session=session,
    )

    assert result.status == "completed"
    assert result.rows_read == 3
    assert result.rows_deleted == 0
    assert result.rows_loaded == 3

    rows = session.query(FirstName).order_by(FirstName.gender, FirstName.first_name).all()
    assert [
        (row.gender, row.first_name, row.frequency_count, row.normalized_probability)
        for row in rows
    ] == [
        ("F", "Emma", 30, Decimal("0.75000000")),
        ("F", "Olivia", 10, Decimal("0.25000000")),
        ("M", "Noah", 7, Decimal("1.00000000")),
    ]


def test_aggregates_duplicate_first_name_rows_before_probability(session):
    insert_raw_first_name(
        session,
        country_code="CA",
        state_province_code="ON",
        birth_year=1999,
        gender="M",
        first_name="Liam",
        frequency_count=6,
    )
    insert_raw_first_name(
        session,
        country_code="CA",
        state_province_code="ON",
        birth_year=1999,
        gender="M",
        first_name="Liam",
        frequency_count=4,
    )
    insert_raw_first_name(
        session,
        country_code="CA",
        state_province_code="ON",
        birth_year=1999,
        gender="M",
        first_name="Noah",
        frequency_count=10,
    )

    result = FirstNameNormalizer().normalize(
        replace_production=True,
        session=session,
    )

    assert result.rows_read == 3
    assert result.rows_loaded == 2

    rows = session.query(FirstName).order_by(FirstName.first_name).all()
    assert [
        (row.first_name, row.frequency_count, row.normalized_probability)
        for row in rows
    ] == [
        ("Liam", 10, Decimal("0.50000000")),
        ("Noah", 10, Decimal("0.50000000")),
    ]


def test_replace_deletes_existing_first_names_for_raw_countries_only(session):
    session.add(
        FirstName(
            country_code="US",
            state_province_code="TX",
            birth_year=2000,
            gender="F",
            first_name="Old",
            frequency_count=1,
        )
    )
    session.add(
        FirstName(
            country_code="MX",
            state_province_code="CM",
            birth_year=2000,
            gender="F",
            first_name="Maria",
            frequency_count=1,
        )
    )
    session.commit()
    insert_raw_first_name(
        session,
        country_code="US",
        state_province_code="TX",
        birth_year=2000,
        gender="F",
        first_name="Emma",
        frequency_count=10,
    )

    result = FirstNameNormalizer().normalize(
        replace_production=True,
        session=session,
    )

    assert result.rows_deleted == 1
    assert {
        (row.country_code, row.state_province_code, row.first_name)
        for row in session.query(FirstName).all()
    } == {
        ("US", "TX", "Emma"),
        ("MX", "CM", "Maria"),
    }


def test_normalizes_multiple_state_chunks(session):
    insert_raw_first_name(
        session,
        country_code="US",
        state_province_code="TX",
        birth_year=2000,
        gender="F",
        first_name="Emma",
        frequency_count=30,
    )
    insert_raw_first_name(
        session,
        country_code="US",
        state_province_code="CA",
        birth_year=2000,
        gender="F",
        first_name="Ava",
        frequency_count=20,
    )
    insert_raw_first_name(
        session,
        country_code="US",
        state_province_code="CA",
        birth_year=2000,
        gender="F",
        first_name="Mia",
        frequency_count=20,
    )

    result = FirstNameNormalizer().normalize(
        replace_production=True,
        session=session,
    )

    assert result.rows_read == 3
    assert result.rows_loaded == 3
    rows = (
        session.query(FirstName)
        .order_by(
            FirstName.state_province_code.asc(),
            FirstName.first_name.asc(),
        )
        .all()
    )
    assert [
        (
            row.state_province_code,
            row.first_name,
            row.normalized_probability,
        )
        for row in rows
    ] == [
        ("CA", "Ava", Decimal("0.50000000")),
        ("CA", "Mia", Decimal("0.50000000")),
        ("TX", "Emma", Decimal("1.00000000")),
    ]
