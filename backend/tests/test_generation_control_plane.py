"""Offline tests for generation run and monthly batch orchestration."""
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
from app.generation import GenerationControlPlane  # noqa: E402
from app.models import GenerationRun, MonthlyBatch  # noqa: E402


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
    return sessionmaker(bind=engine, autoflush=False, future=True)


@pytest.fixture()
def session(session_factory):
    db_session = session_factory()
    try:
        yield db_session
    finally:
        db_session.close()


@pytest.fixture()
def control_plane():
    return GenerationControlPlane(
        SimulationSettings(
            simulation_version="test-version",
            default_seed_value=12345,
        )
    )


def test_create_generation_run_uses_settings_defaults(control_plane, session):
    generation_run = control_plane.create_generation_run(
        "baseline",
        session=session,
    )

    assert generation_run.id is not None
    assert generation_run.generation_name == "baseline"
    assert generation_run.seed_value == 12345
    assert generation_run.simulation_version == "test-version"
    assert generation_run.status == "not_started"


def test_generation_run_status_transitions(control_plane, session):
    generation_run = control_plane.create_generation_run(
        "status probe",
        session=session,
    )

    running = control_plane.start_generation_run(generation_run.id, session=session)
    assert running.status == "running"
    assert generation_run.started_at is not None

    completed = control_plane.complete_generation_run(
        generation_run.id,
        session=session,
    )

    assert completed.status == "succeeded"
    assert generation_run.completed_at is not None


def test_create_monthly_batch_is_idempotent_for_run_and_month(
    control_plane,
    session,
):
    generation_run = control_plane.create_generation_run(
        "batch probe",
        session=session,
    )

    first_batch = control_plane.get_or_create_monthly_batch(
        generation_run.id,
        date(2026, 1, 1),
        batch_sequence=1,
        batch_type="historical_initial",
        session=session,
    )
    second_batch = control_plane.get_or_create_monthly_batch(
        generation_run.id,
        date(2026, 1, 1),
        batch_sequence=2,
        session=session,
    )

    assert first_batch.id == second_batch.id
    assert first_batch.batch_sequence == 1
    assert first_batch.batch_type == "historical_initial"
    assert first_batch.processing_status == "pending"


def test_monthly_batch_status_transitions_and_failure_recording(
    control_plane,
    session,
):
    generation_run = control_plane.create_generation_run(
        "failure probe",
        session=session,
    )
    monthly_batch = control_plane.get_or_create_monthly_batch(
        generation_run.id,
        date(2026, 2, 1),
        batch_sequence=2,
        session=session,
    )

    control_plane.start_monthly_batch(monthly_batch.id, session=session)
    failed_batch = control_plane.fail_monthly_batch(
        monthly_batch.id,
        "planned failure",
        session=session,
    )

    assert failed_batch.processing_status == "failed"
    assert failed_batch.completed_at is not None
    assert failed_batch.error_message == "planned failure"


def test_terminal_status_cannot_transition_again(control_plane, session):
    generation_run = control_plane.create_generation_run(
        "terminal probe",
        session=session,
    )
    control_plane.fail_generation_run(generation_run.id, session=session)

    with pytest.raises(ValueError, match="already failed"):
        control_plane.start_generation_run(generation_run.id, session=session)


def test_transaction_rolls_back_control_plane_changes_on_failure(
    control_plane,
    session_factory,
):
    with pytest.raises(RuntimeError):
        session = session_factory()
        try:
            with session.begin():
                control_plane.create_generation_run("rollback probe", session=session)
                raise RuntimeError("force rollback")
        finally:
            session.close()

    session = session_factory()
    try:
        assert session.query(GenerationRun).count() == 0
        assert session.query(MonthlyBatch).count() == 0
    finally:
        session.close()
