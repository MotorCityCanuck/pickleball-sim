"""Tests for raw pickleball club name ingestion."""
from pathlib import Path
import sys

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.models import RawPickleballClubName, RawSeedLoadError, RawSeedLoadRun  # noqa: E402
from app.seed_data_ingest import PickleballClubNameIngestor  # noqa: E402


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
            CREATE TABLE clubs (
                id integer primary key autoincrement,
                club_name varchar(255) not null
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


def test_loads_valid_club_name_rows(tmp_path, session):
    source = tmp_path / "pickleball_club_names_by_state_province.csv"
    source.write_text(
        "club_seed_id,country,state_province_code,state_province_name,"
        "club_name,club_type,size_tier,generation_method\n"
        "1,US,AL,Alabama,Heart of Dixie Pickleball Community,"
        "Private Athletic Club,Small,ai_seed_template_v1\n"
        "2,CA,ON,Ontario,Toronto Paddle Club,"
        "Community Recreation Club,Medium,ai_seed_template_v1\n",
        encoding="utf-8",
    )

    result = PickleballClubNameIngestor().load_dataset(
        "pickleball_club_names",
        input_path=tmp_path,
        session=session,
    )

    assert result.status == "completed"
    assert result.rows_read == 2
    assert result.rows_loaded == 2
    assert result.rows_rejected == 0

    rows = session.query(RawPickleballClubName).order_by(RawPickleballClubName.id).all()
    assert [(row.club_seed, row.country_code, row.state_province_code) for row in rows] == [
        (1, "US", "AL"),
        (2, "CA", "ON"),
    ]
    assert rows[0].club_name == "Heart of Dixie Pickleball Community"
    assert rows[0].club_type == "Private Athletic Club"
    assert rows[0].size_tier == "Small"
    assert rows[0].generation_method == "ai_seed_template_v1"
    assert rows[0].source_dataset == "pickleball_club_names_by_state_province"
    assert session.query(RawSeedLoadRun).count() == 1
    assert session.query(RawSeedLoadError).count() == 0


def test_invalid_club_name_rows_are_recorded_as_errors(tmp_path, session):
    source = tmp_path / "pickleball_club_names_by_state_province.csv"
    source.write_text(
        "club_seed_id,country,state_province_code,state_province_name,"
        "club_name,club_type,size_tier,generation_method\n"
        "0,XX,,,,Small,ai_seed_template_v1\n",
        encoding="utf-8",
    )

    result = PickleballClubNameIngestor().load_dataset(
        "pickleball_club_names",
        input_path=tmp_path,
        session=session,
    )

    assert result.rows_read == 1
    assert result.rows_loaded == 0
    assert result.rows_rejected == 1
    assert session.query(RawPickleballClubName).count() == 0

    error = session.query(RawSeedLoadError).one()
    assert error.error_code == "INVALID_CLUB_NAME_ROW"
    assert "club seed id must be a positive integer" in error.error_message
    assert "country must map to US or CA" in error.error_message
    assert "state/province code is required" in error.error_message
    assert "club name is required" in error.error_message


def test_reload_replaces_existing_club_name_rows(tmp_path, session):
    session.add(
        RawPickleballClubName(
            load_run_id=999,
            source_file="old",
            source_row_number=1,
            raw_payload={"old": "row"},
            club_seed=999,
            country_code="US",
            state_province_code="TX",
            club_name="Old Club",
            source_dataset="pickleball_club_names_by_state_province",
        )
    )
    session.flush()

    source = tmp_path / "pickleball_club_names_by_state_province.csv"
    source.write_text(
        "club_seed_id,country,state_province_code,state_province_name,"
        "club_name,club_type,size_tier,generation_method\n"
        "1,US,AL,Alabama,Heart of Dixie Pickleball Community,"
        "Private Athletic Club,Small,ai_seed_template_v1\n",
        encoding="utf-8",
    )

    PickleballClubNameIngestor().load_dataset(
        "pickleball_club_names",
        input_path=tmp_path,
        session=session,
    )

    rows = session.query(RawPickleballClubName).all()
    assert len(rows) == 1
    assert rows[0].club_name == "Heart of Dixie Pickleball Community"


def test_failed_club_name_load_rolls_back_replacement(tmp_path, session, monkeypatch):
    session.add(
        RawPickleballClubName(
            load_run_id=999,
            source_file="old",
            source_row_number=1,
            raw_payload={"old": "row"},
            club_seed=999,
            country_code="US",
            state_province_code="TX",
            club_name="Old Club",
            source_dataset="pickleball_club_names_by_state_province",
        )
    )
    session.flush()

    source = tmp_path / "pickleball_club_names_by_state_province.csv"
    source.write_text(
        "club_seed_id,country,state_province_code,state_province_name,"
        "club_name,club_type,size_tier,generation_method\n"
        "1,US,AL,Alabama,Heart of Dixie Pickleball Community,"
        "Private Athletic Club,Small,ai_seed_template_v1\n",
        encoding="utf-8",
    )

    def fail_parse(source_file, source_row_number, raw_row, load_run_id):
        raise RuntimeError("forced club-name failure")

    ingestor = PickleballClubNameIngestor()
    monkeypatch.setattr(ingestor, "_parse_club_name_row", fail_parse)

    with pytest.raises(RuntimeError, match="forced club-name failure"):
        ingestor.load_dataset("pickleball_club_names", input_path=tmp_path, session=session)

    rows = session.query(RawPickleballClubName).all()
    assert len(rows) == 1
    assert rows[0].club_name == "Old Club"
    assert session.query(RawSeedLoadRun).count() == 0


def test_club_name_ingestion_does_not_write_production_clubs(tmp_path, session):
    source = tmp_path / "pickleball_club_names_by_state_province.csv"
    source.write_text(
        "club_seed_id,country,state_province_code,state_province_name,"
        "club_name,club_type,size_tier,generation_method\n"
        "1,US,AL,Alabama,Heart of Dixie Pickleball Community,"
        "Private Athletic Club,Small,ai_seed_template_v1\n",
        encoding="utf-8",
    )

    PickleballClubNameIngestor().load_dataset(
        "pickleball_club_names",
        input_path=tmp_path,
        session=session,
    )

    assert session.execute(text("SELECT COUNT(*) FROM clubs")).scalar_one() == 0


def test_unsupported_club_name_dataset_is_rejected(session):
    with pytest.raises(ValueError, match="Unsupported dataset"):
        PickleballClubNameIngestor().load_dataset(
            "pickleball_club_distributions",
            session=session,
        )
