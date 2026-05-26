"""Tests for raw first-name ingestion."""
from pathlib import Path
import sys

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.models import RawFirstName, RawSeedLoadError, RawSeedLoadRun  # noqa: E402
from app.seed_data_ingest import FirstNameIngestor  # noqa: E402


@pytest.fixture()
def session_factory():
    engine = create_engine("sqlite:///:memory:", future=True)
    with engine.begin() as conn:
        conn.exec_driver_sql(
            """
            CREATE TABLE raw_seed_load_runs (
                id integer primary key autoincrement,
                job_status_id bigint,
                dataset_type varchar(80) not null,
                source_path varchar(1000) not null,
                source_file_count integer not null,
                source_checksum varchar(128),
                started_at datetime,
                completed_at datetime,
                status varchar(30) not null default 'pending',
                rows_read integer not null,
                rows_loaded integer not null,
                rows_rejected integer not null,
                error_message text,
                created_at datetime default current_timestamp not null,
                updated_at datetime default current_timestamp not null
            )
            """
        )
        conn.exec_driver_sql(
            """
            CREATE TABLE raw_seed_load_errors (
                id integer primary key autoincrement,
                load_run_id bigint not null,
                source_file varchar(500) not null,
                source_row_number integer,
                error_code varchar(80) not null,
                error_message text not null,
                raw_payload text,
                created_at datetime default current_timestamp not null,
                updated_at datetime default current_timestamp not null
            )
            """
        )
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
                frequency_count integer not null
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


def test_loads_headerless_us_first_name_rows(tmp_path, session):
    source = tmp_path / "AL.TXT"
    source.write_text(
        "AL,F,1910,Mary,875\n"
        "AL,M,1910,James,422\n",
        encoding="utf-8",
    )

    result = FirstNameIngestor().load_dataset(
        "first_names_us",
        input_path=tmp_path,
        session=session,
    )

    assert result.status == "completed"
    assert result.rows_read == 2
    assert result.rows_loaded == 2
    assert result.rows_rejected == 0

    rows = session.query(RawFirstName).order_by(RawFirstName.id).all()
    assert [
        (
            row.country_code,
            row.state_province_code,
            row.gender,
            row.birth_year,
            row.first_name,
            row.frequency_count,
        )
        for row in rows
    ] == [
        ("US", "AL", "F", 1910, "Mary", 875),
        ("US", "AL", "M", 1910, "James", 422),
    ]
    assert rows[0].source_dataset == "usa_first_names"
    assert session.query(RawSeedLoadRun).count() == 1
    assert session.query(RawSeedLoadError).count() == 0


def test_loads_pipe_delimited_canadian_first_name_rows(tmp_path, session):
    source = tmp_path / "canada_first_names_AB.txt"
    source.write_text(
        "province|sex|birth_year|name|number_of_occurrences\n"
        "AB|F|1940|Amelia|7\n",
        encoding="utf-8",
    )

    result = FirstNameIngestor().load_dataset(
        "first_names_ca",
        input_path=source,
        session=session,
    )

    assert result.rows_loaded == 1
    row = session.query(RawFirstName).one()
    assert row.country_code == "CA"
    assert row.state_province_code == "AB"
    assert row.gender == "F"
    assert row.birth_year == 1940
    assert row.first_name == "Amelia"
    assert row.frequency_count == 7
    assert row.source_dataset == "canada_first_names"


def test_invalid_first_name_rows_are_recorded_as_errors(tmp_path, session):
    source = tmp_path / "AL.TXT"
    source.write_text("AL,X,not-year,,0\n", encoding="utf-8")

    result = FirstNameIngestor().load_dataset(
        "first_names_us",
        input_path=tmp_path,
        session=session,
    )

    assert result.rows_read == 1
    assert result.rows_loaded == 0
    assert result.rows_rejected == 1
    assert session.query(RawFirstName).count() == 0

    error = session.query(RawSeedLoadError).one()
    assert error.error_code == "INVALID_FIRST_NAME_ROW"
    assert "gender must be M or F" in error.error_message
    assert "birth year must be an integer" in error.error_message
    assert "first name is required" in error.error_message
    assert "frequency count must be a positive integer" in error.error_message


def test_reload_replaces_only_same_first_name_dataset(tmp_path, session):
    session.add(
        RawFirstName(
            load_run_id=999,
            source_file="old",
            source_row_number=1,
            raw_payload={"old": "us"},
            country_code="US",
            state_province_code="AL",
            gender="F",
            birth_year=1910,
            first_name="Oldus",
            frequency_count=1,
            source_dataset="usa_first_names",
        )
    )
    session.add(
        RawFirstName(
            load_run_id=998,
            source_file="old",
            source_row_number=1,
            raw_payload={"old": "ca"},
            country_code="CA",
            state_province_code="AB",
            gender="F",
            birth_year=1940,
            first_name="Oldca",
            frequency_count=1,
            source_dataset="canada_first_names",
        )
    )
    session.flush()

    source = tmp_path / "AL.TXT"
    source.write_text("AL,F,1910,Mary,875\n", encoding="utf-8")

    FirstNameIngestor().load_dataset("first_names_us", input_path=tmp_path, session=session)

    names = {row.first_name for row in session.query(RawFirstName).all()}
    assert names == {"Mary", "Oldca"}


def test_failed_first_name_load_rolls_back_replacement(tmp_path, session, monkeypatch):
    session.add(
        RawFirstName(
            load_run_id=999,
            source_file="old",
            source_row_number=1,
            raw_payload={"old": "us"},
            country_code="US",
            state_province_code="AL",
            gender="F",
            birth_year=1910,
            first_name="Oldus",
            frequency_count=1,
            source_dataset="usa_first_names",
        )
    )
    session.flush()

    source = tmp_path / "AL.TXT"
    source.write_text("AL,F,1910,Mary,875\n", encoding="utf-8")

    def fail_parse(config, source_file, source_row_number, raw_row, load_run_id):
        raise RuntimeError("forced first-name failure")

    ingestor = FirstNameIngestor()
    monkeypatch.setattr(ingestor, "_parse_first_name_row", fail_parse)

    with pytest.raises(RuntimeError, match="forced first-name failure"):
        ingestor.load_dataset("first_names_us", input_path=tmp_path, session=session)

    rows = session.query(RawFirstName).all()
    assert len(rows) == 1
    assert rows[0].first_name == "Oldus"
    assert session.query(RawSeedLoadRun).count() == 0


def test_first_name_ingestion_does_not_write_production_first_names(tmp_path, session):
    source = tmp_path / "AL.TXT"
    source.write_text("AL,F,1910,Mary,875\n", encoding="utf-8")

    FirstNameIngestor().load_dataset("first_names_us", input_path=tmp_path, session=session)

    assert session.execute(text("SELECT COUNT(*) FROM first_names")).scalar_one() == 0


def test_unsupported_first_name_dataset_is_rejected(session):
    with pytest.raises(ValueError, match="Unsupported dataset"):
        FirstNameIngestor().load_dataset("last_names_us", session=session)
