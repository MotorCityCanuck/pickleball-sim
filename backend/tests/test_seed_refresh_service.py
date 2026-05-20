"""Tests for operator-facing seed refresh orchestration."""
from pathlib import Path
import sys

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core import ConfigurationLifecycleService  # noqa: E402
from app.generation import SeedRefreshService  # noqa: E402
from app.models import JobStageProgress, JobStatus  # noqa: E402
from app.seed_data_ingest.base import RawSeedLoadResult  # noqa: E402
from app.seed_data_normalize.base import SeedNormalizeResult  # noqa: E402


@pytest.fixture()
def session():
    engine = create_engine("sqlite:///:memory:", future=True)
    with engine.begin() as conn:
        conn.exec_driver_sql(
            """
            CREATE TABLE configuration_profiles (
                id integer primary key autoincrement,
                profile_name varchar(255) not null unique,
                description text,
                is_active boolean not null default true,
                created_at datetime default current_timestamp not null,
                updated_at datetime default current_timestamp not null
            )
            """
        )
        conn.exec_driver_sql(
            """
            CREATE TABLE configuration_profile_versions (
                id integer primary key autoincrement,
                profile_id bigint not null,
                version_number integer not null,
                title varchar(255) not null,
                notes text,
                config_schema_version varchar(50) not null,
                config_hash varchar(128),
                config_payload json not null,
                created_by varchar(255),
                lifecycle_status varchar(30) not null default 'valid',
                last_used_at datetime,
                deprecated_at datetime,
                created_at datetime default current_timestamp not null,
                updated_at datetime default current_timestamp not null,
                unique (profile_id, version_number),
                foreign key(profile_id) references configuration_profiles(id)
            )
            """
        )
        conn.exec_driver_sql(
            """
            CREATE TABLE job_status (
                id integer primary key autoincrement,
                job_type varchar(50) not null,
                job_id varchar(100) not null unique,
                status varchar(30) not null default 'pending',
                current_phase varchar(100),
                percent_complete numeric(5,2),
                current_message text,
                started_at datetime,
                completed_at datetime,
                error_message text,
                created_at datetime default current_timestamp not null,
                updated_at datetime default current_timestamp not null
            )
            """
        )
        conn.exec_driver_sql(
            """
            CREATE TABLE job_stage_progress (
                id integer primary key autoincrement,
                job_status_id bigint not null,
                generation_run_id bigint,
                batch_id bigint,
                stage_name varchar(100) not null,
                stage_sequence integer,
                status varchar(30) not null default 'pending',
                progress_current bigint not null default 0,
                progress_total bigint,
                progress_unit varchar(100),
                progress_percent numeric(5,2),
                last_heartbeat_at datetime,
                progress_message text,
                started_at datetime,
                completed_at datetime,
                error_message text,
                metadata_json text,
                created_at datetime default current_timestamp not null,
                updated_at datetime default current_timestamp not null,
                unique(job_status_id, batch_id, stage_name),
                foreign key(job_status_id) references job_status(id)
            )
            """
        )
        conn.exec_driver_sql(
            """
            CREATE TABLE raw_seed_load_runs (
                id integer primary key autoincrement,
                dataset_type varchar(80) not null,
                source_path varchar(1000) not null,
                source_file_count integer not null default 0,
                source_checksum varchar(128),
                started_at datetime,
                completed_at datetime,
                status varchar(30) not null default 'pending',
                rows_read integer not null default 0,
                rows_loaded integer not null default 0,
                rows_rejected integer not null default 0,
                error_message text,
                created_at datetime default current_timestamp not null,
                updated_at datetime default current_timestamp not null
            )
            """
        )
    db_session = sessionmaker(bind=engine, autoflush=False, future=True)()
    try:
        yield db_session
    finally:
        db_session.close()


def _seed_valid_config(session):
    payload = {
        "runtime": {},
        "simulation": {
            "simulation_name": "Seed Refresh Test",
            "simulation_version": "v1",
            "master_seed": 42,
            "historical_batch_count": 2,
            "first_batch_month": "2026-01-01",
            "target_total_players": 100,
        },
        "raw_seed_data": {
            "supported_datasets": [
                "metro_areas_us",
                "first_names_us",
                "last_names_us",
                "state_prov_biases_us",
                "pickleball_club_names",
                "pickleball_club_distributions",
            ]
        },
    }
    version = ConfigurationLifecycleService().save_new_version(
        session,
        title="Seed orchestration config",
        notes=None,
        payload=payload,
    ).version
    session.commit()
    return version


def test_refresh_seed_data_tracks_stage_progress_and_marks_job_complete(session):
    _seed_valid_config(session)
    load_calls: list[str] = []
    normalize_calls: list[str] = []

    def fake_load(dataset, *, session=None):
        del session
        load_calls.append(dataset)
        return RawSeedLoadResult(
            load_run_id=len(load_calls),
            dataset_type=dataset,
            source_file_count=1,
            rows_read=10,
            rows_loaded=8,
            rows_rejected=2,
            status="completed",
        )

    def fake_normalize(dataset, *, replace_production=False, config_payload=None, session=None):
        del config_payload, session
        assert replace_production is True
        normalize_calls.append(dataset)
        return SeedNormalizeResult(
            dataset=dataset,
            status="completed",
            rows_read=10,
            rows_deleted=3,
            rows_loaded=7,
        )

    service = SeedRefreshService(
        load_dataset_fn=fake_load,
        normalize_dataset_fn=fake_normalize,
    )

    result = service.refresh_seed_data(session=session)
    session.commit()

    assert load_calls == [
        "metro_areas_us",
        "first_names_us",
        "last_names_us",
        "state_prov_biases_us",
        "pickleball_club_names",
        "pickleball_club_distributions",
    ]
    assert normalize_calls == [
        "metro_areas",
        "first_names",
        "last_names",
        "pickleball_clubs",
    ]
    assert result.job_status.job_type == "seed_refresh"
    assert result.job_status.status == "succeeded"
    assert result.configuration_version.last_used_at is not None

    job_rows = session.query(JobStatus).all()
    assert len(job_rows) == 1
    assert job_rows[0].percent_complete == 100

    stage_rows = (
        session.query(JobStageProgress)
        .order_by(JobStageProgress.stage_sequence.asc(), JobStageProgress.id.asc())
        .all()
    )
    assert len(stage_rows) == 2
    assert [row.stage_name for row in stage_rows] == [
        "raw_seed_ingest",
        "seed_normalization",
    ]
    assert {row.status for row in stage_rows} == {"succeeded"}
    assert stage_rows[0].progress_current == 6
    assert stage_rows[1].progress_current == 4


def test_refresh_seed_data_blocks_concurrent_seed_jobs(session):
    _seed_valid_config(session)
    session.execute(
        text(
            """
            INSERT INTO job_status (
                job_type, job_id, status, current_phase, created_at, updated_at
            ) VALUES (
                'seed_refresh', 'seed-refresh-active', 'running', 'raw_seed_ingest',
                CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
            """
        )
    )
    session.commit()

    service = SeedRefreshService(
        load_dataset_fn=lambda dataset, *, session=None: RawSeedLoadResult(1, dataset, 1, 1, 1, 0, "completed"),
        normalize_dataset_fn=lambda dataset, *, replace_production=False, config_payload=None, session=None: SeedNormalizeResult(dataset, "completed", 1, 0, 1),
    )

    with pytest.raises(ValueError, match="already running"):
        service.refresh_seed_data(session=session)
