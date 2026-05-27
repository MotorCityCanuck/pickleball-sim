"""Offline tests for high-level generation orchestration."""
from datetime import date
from pathlib import Path
import sys

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core import SimulationSettings  # noqa: E402
from app.core.configuration_lifecycle import ConfigurationLifecycleService  # noqa: E402
from app.generation import GenerationOrchestrator  # noqa: E402
from app.models import ConfigurationProfileVersion, GenerationRun, MonthlyBatch  # noqa: E402


@pytest.fixture()
def session_factory():
    engine = create_engine("sqlite:///:memory:", future=True)
    with engine.begin() as conn:
        conn.exec_driver_sql(
            """
            CREATE TABLE generation_runs (
                id integer primary key autoincrement,
                generation_name varchar(255) not null,
                seed_value bigint not null,
                simulation_version varchar(100),
                parameter_snapshot text,
                started_at datetime,
                completed_at datetime,
                status varchar(30) not null default 'not_started',
                created_at datetime default current_timestamp not null,
                updated_at datetime default current_timestamp not null
            )
            """
        )
        conn.exec_driver_sql(
            """
            CREATE TABLE monthly_batches (
                id integer primary key autoincrement,
                generation_run_id bigint not null,
                batch_month date not null,
                batch_sequence integer not null,
                batch_type varchar(30) not null default 'future_increment',
                active_player_count_start integer,
                new_player_count integer,
                active_player_count_end integer,
                match_count_generated integer,
                rating_update_count integer,
                assessment_update_count integer,
                processing_status varchar(30) not null default 'pending',
                started_at datetime,
                completed_at datetime,
                error_message text,
                created_at datetime default current_timestamp not null,
                updated_at datetime default current_timestamp not null,
                unique (generation_run_id, batch_month)
            )
            """
        )
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
    return sessionmaker(bind=engine, autoflush=False, future=True)


@pytest.fixture()
def session(session_factory):
    db_session = session_factory()
    try:
        yield db_session
    finally:
        db_session.close()


@pytest.fixture()
def orchestrator():
    return GenerationOrchestrator(
        SimulationSettings(
            simulation_version="orchestrator-test",
            default_seed_value=2468,
            initial_historical_months=3,
            config_payload={
                "simulation": {
                    "simulation_version": "orchestrator-test",
                    "master_seed": 2468,
                    "historical_batch_count": 3,
                }
            },
        )
    )


def test_create_initial_generation_plan_creates_run_and_batches(
    orchestrator,
    session,
):
    plan = orchestrator.create_initial_generation_plan(
        "initial setup",
        date(2026, 1, 17),
        session=session,
    )

    assert plan.generation_run.id is not None
    assert plan.generation_run.generation_name == "initial setup"
    assert plan.generation_run.seed_value == 2468
    assert plan.generation_run.simulation_version == "orchestrator-test"
    assert plan.generation_run.parameter_snapshot == {
        "simulation": {
            "simulation_version": "orchestrator-test",
            "master_seed": 2468,
            "historical_batch_count": 3,
        }
    }
    assert plan.generation_run.status == "not_started"
    assert [batch.batch_month for batch in plan.monthly_batches] == [
        date(2026, 1, 1),
        date(2026, 2, 1),
        date(2026, 3, 1),
    ]
    assert [batch.batch_sequence for batch in plan.monthly_batches] == [1, 2, 3]
    assert {batch.batch_type for batch in plan.monthly_batches} == {
        "historical_initial"
    }
    assert {batch.processing_status for batch in plan.monthly_batches} == {"pending"}


def test_create_initial_generation_plan_can_override_seed_and_month_count(
    orchestrator,
    session,
):
    plan = orchestrator.create_initial_generation_plan(
        "custom setup",
        date(2026, 11, 1),
        seed_value=99,
        historical_months=4,
        session=session,
    )

    assert plan.generation_run.seed_value == 99
    assert [batch.batch_month for batch in plan.monthly_batches] == [
        date(2026, 11, 1),
        date(2026, 12, 1),
        date(2027, 1, 1),
        date(2027, 2, 1),
    ]


def test_create_initial_generation_plan_rejects_empty_month_count(
    orchestrator,
    session,
):
    with pytest.raises(ValueError, match="historical_months"):
        orchestrator.create_initial_generation_plan(
            "invalid setup",
            date(2026, 1, 1),
            historical_months=0,
            session=session,
        )


def test_create_initial_generation_plan_rolls_back_as_single_unit(
    orchestrator,
    session_factory,
):
    session = session_factory()
    try:
        with pytest.raises(RuntimeError):
            with session.begin():
                orchestrator.create_initial_generation_plan(
                    "rollback setup",
                    date(2026, 1, 1),
                    session=session,
                )
                raise RuntimeError("force rollback")

        assert session.query(GenerationRun).count() == 0
        assert session.query(MonthlyBatch).count() == 0
    finally:
        session.close()


def test_create_initial_generation_plan_marks_loaded_config_version_used(session):
    lifecycle = ConfigurationLifecycleService()
    payload = {
        "runtime": {},
        "simulation": {
            "simulation_name": "db-backed",
            "simulation_version": "db-backed",
            "master_seed": 123,
            "historical_batch_count": 2,
            "first_batch_month": "2026-01-01",
        },
        "player_generation": {
            "player_count": 1000,
        },
    }
    saved = lifecycle.save_new_version(
        session,
        title="Database config",
        notes=None,
        payload=payload,
    )
    session.commit()

    orchestrator = GenerationOrchestrator(
        SimulationSettings(
            simulation_version="ignored",
            default_seed_value=999,
            initial_historical_months=1,
            config_payload=None,
        )
    )
    plan = orchestrator.create_initial_generation_plan(
        "db config run",
        date(2026, 1, 1),
        session=session,
    )
    session.commit()

    reloaded = session.get(ConfigurationProfileVersion, saved.version.id)
    assert plan.generation_run.seed_value == 123
    assert reloaded is not None
    assert reloaded.last_used_at is not None
