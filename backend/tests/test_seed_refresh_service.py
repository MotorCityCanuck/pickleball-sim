"""Tests for operator-facing seed refresh orchestration."""
from pathlib import Path
import re
import sys

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core import ConfigurationLifecycleService  # noqa: E402
from app.generation import seed_refresh_service as seed_refresh_module  # noqa: E402
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
                job_status_id bigint,
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
    events: list[str] = []
    load_calls: list[str] = []
    normalize_calls: list[str] = []

    def fake_load(dataset, *, session=None, job_status_id=None):
        del session, job_status_id
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
        events.append(f"normalize:{dataset}")
        normalize_calls.append(dataset)
        return SeedNormalizeResult(
            dataset=dataset,
            status="completed",
            rows_read=10,
            rows_deleted=3,
            rows_loaded=7,
        )

    def fake_reset(*, session=None, preserve_job_status_id=None, progress_listener=None):
        del session
        events.append(f"reset:{preserve_job_status_id}")
        if progress_listener is not None:
            progress_listener(
                seed_refresh_module.ResetProgressEvent(
                    model_name="matches",
                    model_label="Match",
                    step_index=1,
                    total_steps=2,
                    status="running",
                )
            )
            progress_listener(
                seed_refresh_module.ResetProgressEvent(
                    model_name="matches",
                    model_label="Match",
                    step_index=1,
                    total_steps=2,
                    status="succeeded",
                    rows_affected=10,
                )
            )
            progress_listener(
                seed_refresh_module.ResetProgressEvent(
                    model_name="players",
                    model_label="Player",
                    step_index=2,
                    total_steps=2,
                    status="running",
                )
            )
            progress_listener(
                seed_refresh_module.ResetProgressEvent(
                    model_name="players",
                    model_label="Player",
                    step_index=2,
                    total_steps=2,
                    status="succeeded",
                    rows_affected=5,
                )
            )

    service = SeedRefreshService(
        load_dataset_fn=fake_load,
        normalize_dataset_fn=fake_normalize,
        reset_generated_data_fn=fake_reset,
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
    assert events[0].startswith("reset:")
    assert events[1:] == [
        "normalize:metro_areas",
        "normalize:first_names",
        "normalize:last_names",
        "normalize:pickleball_clubs",
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
    assert len(stage_rows) == 3
    assert [row.stage_name for row in stage_rows] == [
        "raw_seed_ingest",
        "generated_data_reset",
        "seed_normalization",
    ]
    assert {row.status for row in stage_rows} == {"succeeded"}
    assert stage_rows[0].progress_current == 6
    assert stage_rows[1].progress_current == len(seed_refresh_module.DELETE_MODELS_IN_ORDER)
    assert stage_rows[2].progress_current == 4


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


def test_refresh_seed_data_ignores_stale_running_seed_job(session):
    _seed_valid_config(session)
    session.execute(
        text(
            """
            INSERT INTO job_status (
                id, job_type, job_id, status, current_phase, percent_complete,
                current_message, started_at, created_at, updated_at
            ) VALUES (
                10, 'seed_refresh', 'seed-refresh-stale', 'running',
                'seed_normalization', 50.00, 'Stale normalization.',
                '2026-05-20 09:00:00', '2026-05-20 09:00:00',
                '2026-05-20 09:00:00'
            )
            """
        )
    )
    session.execute(
        text(
            """
            INSERT INTO job_stage_progress (
                id, job_status_id, generation_run_id, batch_id, stage_name,
                stage_sequence, status, progress_current, progress_total,
                progress_unit, progress_percent, last_heartbeat_at,
                progress_message, started_at, created_at, updated_at
            ) VALUES (
                20, 10, NULL, NULL, 'seed_normalization', 2, 'running',
                2, 4, 'dataset', 50.00, '2026-05-20 09:01:00',
                'Stale normalization.', '2026-05-20 09:00:00',
                '2026-05-20 09:00:00', '2026-05-20 09:00:00'
            )
            """
        )
    )
    session.commit()

    service = SeedRefreshService(
        load_dataset_fn=lambda dataset, *, session=None: RawSeedLoadResult(1, dataset, 1, 1, 1, 0, "completed"),
        normalize_dataset_fn=lambda dataset, *, replace_production=False, config_payload=None, session=None: SeedNormalizeResult(dataset, "completed", 1, 0, 1),
    )

    registration = service.register_raw_seed_ingest(session=session)

    assert registration.job_status.id != 10
    assert registration.job_status.status == "pending"


def test_background_seed_job_persists_failed_status(session, monkeypatch):
    _seed_valid_config(session)

    local_session_factory = sessionmaker(
        bind=session.bind,
        autoflush=False,
        expire_on_commit=False,
        future=True,
    )
    monkeypatch.setattr(seed_refresh_module, "SessionLocal", local_session_factory)

    def failing_load(dataset, *, session=None, job_status_id=None):
        del dataset, session, job_status_id
        raise RuntimeError("planned raw load failure")

    service = SeedRefreshService(
        load_dataset_fn=failing_load,
        normalize_dataset_fn=lambda dataset, **kwargs: SeedNormalizeResult(dataset, "completed", 1, 0, 1),
    )
    registration = service.register_raw_seed_ingest(session=session)
    session.commit()

    service.execute_registered_seed_job_in_background(
        config_version_id=registration.configuration_version.id,
        job_status_id=registration.job_status.id,
        mode=registration.mode,
    )

    session.expire_all()
    job = session.get(JobStatus, registration.job_status.id)
    assert job is not None
    assert job.status == "failed"
    assert job.current_phase == "failed"
    assert "planned raw load failure" in job.current_message

    stage_rows = session.query(JobStageProgress).filter_by(job_status_id=job.id).all()
    assert len(stage_rows) == 1
    assert stage_rows[0].status == "failed"


def test_normalize_seed_data_resets_generated_data_before_normalization(session):
    _seed_valid_config(session)
    events: list[str] = []

    def fake_reset(*, session=None, preserve_job_status_id=None, progress_listener=None):
        del session, progress_listener
        events.append(f"reset:{preserve_job_status_id}")

    def fake_normalize(dataset, *, replace_production=False, config_payload=None, session=None):
        del config_payload, session
        assert replace_production is True
        events.append(f"normalize:{dataset}")
        return SeedNormalizeResult(
            dataset=dataset,
            status="completed",
            rows_read=1,
            rows_deleted=0,
            rows_loaded=1,
        )

    service = SeedRefreshService(
        normalize_dataset_fn=fake_normalize,
        reset_generated_data_fn=fake_reset,
    )

    result = service.normalize_seed_data(session=session)
    session.commit()

    assert result.job_status.job_type == "seed_normalization"
    assert events[0].startswith("reset:")
    assert events[1:] == [
        "normalize:metro_areas",
        "normalize:first_names",
        "normalize:last_names",
        "normalize:pickleball_clubs",
    ]


def test_refresh_seed_data_logs_job_and_stage_lifecycle(session, caplog):
    _seed_valid_config(session)

    def fake_load(dataset, *, session=None, job_status_id=None):
        del session, job_status_id
        return RawSeedLoadResult(
            load_run_id=1,
            dataset_type=dataset,
            source_file_count=1,
            rows_read=10,
            rows_loaded=8,
            rows_rejected=2,
            status="completed",
        )

    def fake_normalize(dataset, *, replace_production=False, config_payload=None, session=None):
        del dataset, replace_production, config_payload, session
        return SeedNormalizeResult(
            dataset="normalized",
            status="completed",
            rows_read=10,
            rows_deleted=3,
            rows_loaded=7,
        )

    service = SeedRefreshService(
        load_dataset_fn=fake_load,
        normalize_dataset_fn=fake_normalize,
        reset_generated_data_fn=lambda **kwargs: None,
    )

    with caplog.at_level("INFO", logger="uvicorn.error"):
        service.refresh_seed_data(session=session)

    messages = [record.getMessage() for record in caplog.records]
    assert any("Seed job started" in message and "mode=refresh" in message for message in messages)
    assert any(
        "Seed stage completed" in message and "stage_name=raw_seed_ingest" in message
        for message in messages
    )
    assert any(
        "Seed stage completed" in message and "stage_name=generated_data_reset" in message
        for message in messages
    )
    assert any(
        "Seed stage completed" in message and "stage_name=seed_normalization" in message
        for message in messages
    )
    assert any("Seed job completed" in message and "phase=completed" in message for message in messages)
    assert all(
        re.search(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} UTC", message)
        for message in messages
        if "Seed job" in message or "Seed stage completed" in message
    )
