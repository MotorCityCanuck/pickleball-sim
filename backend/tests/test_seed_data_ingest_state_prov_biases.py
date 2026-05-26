"""Tests for raw state/province surname-bias ingestion."""
from pathlib import Path
from decimal import Decimal
import sys

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.models import RawSeedLoadError, RawSeedLoadRun, RawStateProvBias  # noqa: E402
from app.seed_data_ingest import StateProvBiasIngestor  # noqa: E402


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


def test_loads_valid_us_bias_rows(tmp_path, session):
    source = tmp_path / "usa_state_surname_bias.csv"
    source.write_text(
        "state_code,last_name,bias_multiplier,bias_reason\n"
        "AK,JOHNSON,10.83,synthetic_demographic_regional_bias\n"
        "AK,SMITH,9.62,synthetic_demographic_regional_bias\n",
        encoding="utf-8",
    )

    result = StateProvBiasIngestor().load_dataset(
        "state_prov_biases_us",
        input_path=tmp_path,
        session=session,
    )

    assert result.status == "completed"
    assert result.rows_read == 2
    assert result.rows_loaded == 2
    assert result.rows_rejected == 0

    rows = session.query(RawStateProvBias).order_by(RawStateProvBias.id).all()
    assert [(row.country_code, row.state_province_code, row.last_name) for row in rows] == [
        ("US", "AK", "JOHNSON"),
        ("US", "AK", "SMITH"),
    ]
    assert rows[0].bias_multiplier == Decimal("10.8300")
    assert rows[0].bias_reason == "synthetic_demographic_regional_bias"
    assert rows[0].source_dataset == "usa_state_surname_bias"
    assert session.query(RawSeedLoadRun).count() == 1
    assert session.query(RawSeedLoadError).count() == 0


def test_loads_valid_canadian_bias_rows(tmp_path, session):
    source = tmp_path / "canada_province_surname_bias.csv"
    source.write_text(
        "province_code,last_name,bias_multiplier,bias_reason\n"
        "AB,SMITH,13.04,primary_province_demographic_bias\n",
        encoding="utf-8",
    )

    result = StateProvBiasIngestor().load_dataset(
        "state_prov_biases_ca",
        input_path=source,
        session=session,
    )

    assert result.rows_loaded == 1
    row = session.query(RawStateProvBias).one()
    assert row.country_code == "CA"
    assert row.state_province_code == "AB"
    assert row.last_name == "SMITH"
    assert row.source_dataset == "canada_province_surname_bias"


def test_invalid_bias_rows_are_recorded_as_errors(tmp_path, session):
    source = tmp_path / "usa_state_surname_bias.csv"
    source.write_text(
        "state_code,last_name,bias_multiplier,bias_reason\n"
        ",,0,\n",
        encoding="utf-8",
    )

    result = StateProvBiasIngestor().load_dataset(
        "state_prov_biases_us",
        input_path=tmp_path,
        session=session,
    )

    assert result.rows_read == 1
    assert result.rows_loaded == 0
    assert result.rows_rejected == 1
    assert session.query(RawStateProvBias).count() == 0

    error = session.query(RawSeedLoadError).one()
    assert error.error_code == "INVALID_STATE_PROV_BIAS_ROW"
    assert "state/province code is required" in error.error_message
    assert "last name is required" in error.error_message
    assert "bias multiplier must be a positive decimal" in error.error_message


def test_reload_replaces_only_same_bias_dataset(tmp_path, session):
    session.add(
        RawStateProvBias(
            load_run_id=999,
            source_file="old",
            source_row_number=1,
            raw_payload={"old": "us"},
            country_code="US",
            state_province_code="TX",
            last_name="OLDUS",
            bias_multiplier=1,
            source_dataset="usa_state_surname_bias",
        )
    )
    session.add(
        RawStateProvBias(
            load_run_id=998,
            source_file="old",
            source_row_number=1,
            raw_payload={"old": "ca"},
            country_code="CA",
            state_province_code="ON",
            last_name="OLDCA",
            bias_multiplier=1,
            source_dataset="canada_province_surname_bias",
        )
    )
    session.flush()

    source = tmp_path / "usa_state_surname_bias.csv"
    source.write_text(
        "state_code,last_name,bias_multiplier,bias_reason\n"
        "AK,JOHNSON,10.83,synthetic_demographic_regional_bias\n",
        encoding="utf-8",
    )

    StateProvBiasIngestor().load_dataset(
        "state_prov_biases_us",
        input_path=tmp_path,
        session=session,
    )

    names = {row.last_name for row in session.query(RawStateProvBias).all()}
    assert names == {"JOHNSON", "OLDCA"}


def test_failed_bias_load_rolls_back_replacement(tmp_path, session, monkeypatch):
    session.add(
        RawStateProvBias(
            load_run_id=999,
            source_file="old",
            source_row_number=1,
            raw_payload={"old": "us"},
            country_code="US",
            state_province_code="TX",
            last_name="OLDUS",
            bias_multiplier=1,
            source_dataset="usa_state_surname_bias",
        )
    )
    session.flush()

    source = tmp_path / "usa_state_surname_bias.csv"
    source.write_text(
        "state_code,last_name,bias_multiplier,bias_reason\n"
        "AK,JOHNSON,10.83,synthetic_demographic_regional_bias\n",
        encoding="utf-8",
    )

    def fail_parse(config, source_file, source_row_number, raw_row, load_run_id):
        raise RuntimeError("forced bias failure")

    ingestor = StateProvBiasIngestor()
    monkeypatch.setattr(ingestor, "_parse_bias_row", fail_parse)

    with pytest.raises(RuntimeError, match="forced bias failure"):
        ingestor.load_dataset("state_prov_biases_us", input_path=tmp_path, session=session)

    rows = session.query(RawStateProvBias).all()
    assert len(rows) == 1
    assert rows[0].last_name == "OLDUS"
    assert session.query(RawSeedLoadRun).count() == 0


def test_bias_ingestion_does_not_write_production_last_names(tmp_path, session):
    source = tmp_path / "usa_state_surname_bias.csv"
    source.write_text(
        "state_code,last_name,bias_multiplier,bias_reason\n"
        "AK,JOHNSON,10.83,synthetic_demographic_regional_bias\n",
        encoding="utf-8",
    )

    StateProvBiasIngestor().load_dataset(
        "state_prov_biases_us",
        input_path=tmp_path,
        session=session,
    )

    assert session.execute(text("SELECT COUNT(*) FROM last_names")).scalar_one() == 0


def test_unsupported_bias_dataset_is_rejected(session):
    with pytest.raises(ValueError, match="Unsupported dataset"):
        StateProvBiasIngestor().load_dataset("last_names_us", session=session)
