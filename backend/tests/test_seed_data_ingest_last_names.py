"""Tests for raw last-name ingestion."""
from pathlib import Path
import sys

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.models import RawLastName, RawSeedLoadError, RawSeedLoadRun  # noqa: E402
from app.seed_data_ingest import LastNameIngestor  # noqa: E402


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
            CREATE TABLE last_names (
                id integer primary key autoincrement,
                country_code varchar(2) not null,
                state_province_code varchar(2) not null,
                last_name varchar(100) not null,
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


def test_loads_valid_us_last_name_rows(tmp_path, session):
    source = tmp_path / "USA_last_names.csv"
    source.write_text(
        "name,count\n"
        "SMITH,2442977\n"
        "JOHNSON,1932812\n",
        encoding="utf-8",
    )

    result = LastNameIngestor().load_dataset(
        "last_names_us",
        input_path=tmp_path,
        session=session,
    )

    assert result.status == "completed"
    assert result.rows_read == 2
    assert result.rows_loaded == 2
    assert result.rows_rejected == 0

    rows = session.query(RawLastName).order_by(RawLastName.id).all()
    assert [(row.country_code, row.last_name, row.frequency_count) for row in rows] == [
        ("US", "SMITH", 2442977),
        ("US", "JOHNSON", 1932812),
    ]
    assert rows[0].source_dataset == "usa_last_names"
    assert session.query(RawSeedLoadRun).count() == 1
    assert session.query(RawSeedLoadError).count() == 0


def test_loads_valid_canadian_last_name_rows_from_occurrence_header(tmp_path, session):
    source = tmp_path / "CAN_last_names.csv"
    source.write_text(
        "name,num_of_occurrences\n"
        "Smith,100\n",
        encoding="utf-8",
    )

    result = LastNameIngestor().load_dataset(
        "last_names_ca",
        input_path=source,
        session=session,
    )

    assert result.rows_loaded == 1
    row = session.query(RawLastName).one()
    assert row.country_code == "CA"
    assert row.last_name == "SMITH"
    assert row.frequency_count == 100
    assert row.source_dataset == "can_last_names"


def test_invalid_last_name_rows_are_recorded_as_errors(tmp_path, session):
    source = tmp_path / "USA_last_names.csv"
    source.write_text(
        "name,count\n"
        ",0\n",
        encoding="utf-8",
    )

    result = LastNameIngestor().load_dataset(
        "last_names_us",
        input_path=tmp_path,
        session=session,
    )

    assert result.rows_read == 1
    assert result.rows_loaded == 0
    assert result.rows_rejected == 1
    assert session.query(RawLastName).count() == 0

    error = session.query(RawSeedLoadError).one()
    assert error.error_code == "INVALID_LAST_NAME_ROW"
    assert "last name is required" in error.error_message
    assert "frequency count must be a positive integer" in error.error_message


def test_reload_replaces_only_same_last_name_dataset(tmp_path, session):
    session.add(
        RawLastName(
            load_run_id=999,
            source_file="old",
            source_row_number=1,
            raw_payload={"old": "us"},
            country_code="US",
            last_name="OLDUS",
            frequency_count=1,
            source_dataset="usa_last_names",
        )
    )
    session.add(
        RawLastName(
            load_run_id=998,
            source_file="old",
            source_row_number=1,
            raw_payload={"old": "ca"},
            country_code="CA",
            last_name="OLDCA",
            frequency_count=1,
            source_dataset="can_last_names",
        )
    )
    session.flush()

    source = tmp_path / "USA_last_names.csv"
    source.write_text("name,count\nSMITH,2442977\n", encoding="utf-8")

    LastNameIngestor().load_dataset("last_names_us", input_path=tmp_path, session=session)

    names = {row.last_name for row in session.query(RawLastName).all()}
    assert names == {"SMITH", "OLDCA"}


def test_failed_last_name_load_rolls_back_replacement(tmp_path, session, monkeypatch):
    session.add(
        RawLastName(
            load_run_id=999,
            source_file="old",
            source_row_number=1,
            raw_payload={"old": "us"},
            country_code="US",
            last_name="OLDUS",
            frequency_count=1,
            source_dataset="usa_last_names",
        )
    )
    session.flush()

    source = tmp_path / "USA_last_names.csv"
    source.write_text("name,count\nSMITH,2442977\n", encoding="utf-8")

    def fail_parse(config, source_file, source_row_number, raw_row, load_run_id):
        raise RuntimeError("forced last-name failure")

    ingestor = LastNameIngestor()
    monkeypatch.setattr(ingestor, "_parse_last_name_row", fail_parse)

    with pytest.raises(RuntimeError, match="forced last-name failure"):
        ingestor.load_dataset("last_names_us", input_path=tmp_path, session=session)

    rows = session.query(RawLastName).all()
    assert len(rows) == 1
    assert rows[0].last_name == "OLDUS"
    assert session.query(RawSeedLoadRun).count() == 0


def test_last_name_ingestion_does_not_write_production_last_names(tmp_path, session):
    source = tmp_path / "USA_last_names.csv"
    source.write_text("name,count\nSMITH,2442977\n", encoding="utf-8")

    LastNameIngestor().load_dataset("last_names_us", input_path=tmp_path, session=session)

    assert session.execute(text("SELECT COUNT(*) FROM last_names")).scalar_one() == 0


def test_unsupported_last_name_dataset_is_rejected(session):
    with pytest.raises(ValueError, match="Unsupported dataset"):
        LastNameIngestor().load_dataset("first_names_us", session=session)
