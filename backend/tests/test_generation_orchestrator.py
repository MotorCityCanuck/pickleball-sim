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
from app.generation import GenerationOrchestrator  # noqa: E402
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
                status varchar(30) not null default 'pending',
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
    assert plan.generation_run.status == "pending"
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
