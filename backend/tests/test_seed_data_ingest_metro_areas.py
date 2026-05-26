"""Tests for raw metro-area seed ingestion."""
from pathlib import Path
import sys

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.models import RawMetroArea, RawSeedLoadError, RawSeedLoadRun  # noqa: E402
from app.seed_data_ingest import RawSeedIngestor  # noqa: E402


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
                region_name varchar(255) not null
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


def test_loads_valid_us_metro_rows(tmp_path, session):
    source = tmp_path / "USA Regional MSA Data.csv"
    source.write_text(
        "Country,GEO,state,value,probability\n"
        'USA,Abilene,TX,"185,429",0.00061524\n'
        'USA,"New York-Newark-Jersey City",NY,"19,498,249",0.06472311\n',
        encoding="utf-8",
    )

    result = RawSeedIngestor().load_dataset(
        "metro_areas_us",
        input_path=tmp_path,
        session=session,
    )

    assert result.status == "completed"
    assert result.source_file_count == 1
    assert result.rows_read == 2
    assert result.rows_loaded == 2
    assert result.rows_rejected == 0

    staged_rows = session.query(RawMetroArea).order_by(RawMetroArea.id).all()
    assert [row.metro_area_name for row in staged_rows] == [
        "Abilene",
        "New York-Newark-Jersey City",
    ]
    assert staged_rows[0].country_code == "US"
    assert staged_rows[0].state_province_code == "TX"
    assert staged_rows[0].population == 185429
    assert staged_rows[0].source_dataset == "usa_regional_msa_data"
    assert session.query(RawSeedLoadRun).count() == 1
    assert session.query(RawSeedLoadError).count() == 0


def test_loads_valid_canadian_metro_rows(tmp_path, session):
    source = tmp_path / "CAN Regional MSA Data.csv"
    source.write_text(
        "COUNTRY,Metro Area Name,State/Prov,Population,Probability\n"
        'CAN,"Toronto (CMA), Ontario",ON,"7,108,874.00",0.191921586\n',
        encoding="utf-8",
    )

    result = RawSeedIngestor().load_dataset(
        "metro_areas_ca",
        input_path=source,
        session=session,
    )

    assert result.rows_read == 1
    assert result.rows_loaded == 1
    assert result.rows_rejected == 0

    row = session.query(RawMetroArea).one()
    assert row.country_code == "CA"
    assert row.state_province_code == "ON"
    assert row.metro_area_name == "Toronto (CMA), Ontario"
    assert row.population == 7108874
    assert row.source_dataset == "can_regional_msa_data"


def test_loads_cp1252_encoded_metro_rows(tmp_path, session):
    source = tmp_path / "CAN Regional MSA Data.csv"
    source.write_bytes(
        (
            "COUNTRY,Metro Area Name,State/Prov,Population,Probability\n"
            'CAN,"Montréal (CMA), Québec",QC,"4,291,732.00",0.115882\n'
        ).encode("cp1252")
    )

    result = RawSeedIngestor().load_dataset(
        "metro_areas_ca",
        input_path=source,
        session=session,
    )

    assert result.rows_loaded == 1
    row = session.query(RawMetroArea).one()
    assert row.metro_area_name == "Montréal (CMA), Québec"
    assert row.state_province_code == "QC"


def test_invalid_rows_are_recorded_as_errors(tmp_path, session):
    source = tmp_path / "USA Regional MSA Data.csv"
    source.write_text(
        "Country,GEO,state,value,probability\n"
        "USA,,TX,-1,not-a-number\n",
        encoding="utf-8",
    )

    result = RawSeedIngestor().load_dataset(
        "metro_areas_us",
        input_path=tmp_path,
        session=session,
    )

    assert result.rows_read == 1
    assert result.rows_loaded == 0
    assert result.rows_rejected == 1
    assert session.query(RawMetroArea).count() == 0

    error = session.query(RawSeedLoadError).one()
    assert error.error_code == "INVALID_METRO_AREA_ROW"
    assert "metro area name is required" in error.error_message
    assert "population must be a positive integer" in error.error_message
    assert "selection probability" in error.error_message


def test_reload_replaces_only_same_dataset_rows(tmp_path, session):
    session.add(
        RawMetroArea(
            load_run_id=999,
            source_file="old",
            source_row_number=1,
            raw_payload={"old": "us"},
            country_code="US",
            state_province_code="TX",
            metro_area_name="Old US",
            population=100,
            selection_probability=0,
            source_dataset="usa_regional_msa_data",
        )
    )
    session.add(
        RawMetroArea(
            load_run_id=998,
            source_file="old",
            source_row_number=1,
            raw_payload={"old": "ca"},
            country_code="CA",
            state_province_code="ON",
            metro_area_name="Old CA",
            population=100,
            selection_probability=0,
            source_dataset="can_regional_msa_data",
        )
    )
    session.flush()

    source = tmp_path / "USA Regional MSA Data.csv"
    source.write_text(
        "Country,GEO,state,value,probability\n"
        'USA,Abilene,TX,"185,429",0.00061524\n',
        encoding="utf-8",
    )

    RawSeedIngestor().load_dataset("metro_areas_us", input_path=tmp_path, session=session)

    names = {
        row.metro_area_name
        for row in session.query(RawMetroArea).order_by(RawMetroArea.id)
    }
    assert names == {"Abilene", "Old CA"}


def test_ingestion_does_not_write_production_regions(tmp_path, session):
    source = tmp_path / "USA Regional MSA Data.csv"
    source.write_text(
        "Country,GEO,state,value,probability\n"
        'USA,Abilene,TX,"185,429",0.00061524\n',
        encoding="utf-8",
    )

    RawSeedIngestor().load_dataset("metro_areas_us", input_path=tmp_path, session=session)

    assert session.execute(text("SELECT COUNT(*) FROM regions")).scalar_one() == 0


def test_failed_load_rolls_back_staging_replacement(tmp_path, session, monkeypatch):
    session.add(
        RawMetroArea(
            load_run_id=999,
            source_file="old",
            source_row_number=1,
            raw_payload={"old": "us"},
            country_code="US",
            state_province_code="TX",
            metro_area_name="Old US",
            population=100,
            selection_probability=0,
            source_dataset="usa_regional_msa_data",
        )
    )
    session.flush()

    source = tmp_path / "USA Regional MSA Data.csv"
    source.write_text(
        "Country,GEO,state,value,probability\n"
        'USA,Abilene,TX,"185,429",0.00061524\n',
        encoding="utf-8",
    )

    def fail_iter_csv_rows(source_file):
        raise RuntimeError("forced load failure")
        yield  # pragma: no cover

    ingestor = RawSeedIngestor()
    monkeypatch.setattr(ingestor, "_iter_csv_rows", fail_iter_csv_rows)

    with pytest.raises(RuntimeError, match="forced load failure"):
        ingestor.load_dataset("metro_areas_us", input_path=tmp_path, session=session)

    rows = session.query(RawMetroArea).all()
    assert len(rows) == 1
    assert rows[0].metro_area_name == "Old US"
    assert session.query(RawSeedLoadRun).count() == 0


def test_unsupported_dataset_is_rejected(session):
    with pytest.raises(ValueError, match="Unsupported dataset"):
        RawSeedIngestor().load_dataset("first_names_us", session=session)
