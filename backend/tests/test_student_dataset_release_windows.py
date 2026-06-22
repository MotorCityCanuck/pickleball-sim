"""Tests for student dataset release-window planning."""

from datetime import date
from pathlib import Path
import sys

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.exports.student_dataset import (  # noqa: E402
    HISTORICAL_BASELINE_RELEASE_TYPE,
    MONTHLY_INCREMENTAL_RELEASE_TYPE,
    ReleaseBatch,
    ReleaseWindowValidationError,
    StudentDatasetReleaseRequest,
    build_release_windows,
    first_day_of_next_month,
    plan_release_windows,
    resolve_release_request,
)
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
                updated_at datetime default current_timestamp not null
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


def seed_generation_run(session, *, status="succeeded") -> GenerationRun:
    generation_run = GenerationRun(
        generation_name="student export test",
        seed_value=123,
        status=status,
    )
    session.add(generation_run)
    session.commit()
    return generation_run


def seed_monthly_batches(
    session,
    generation_run_id: int,
    *,
    count: int,
    status: str = "succeeded",
) -> tuple[MonthlyBatch, ...]:
    batches: list[MonthlyBatch] = []
    for sequence in range(1, count + 1):
        batch = MonthlyBatch(
            generation_run_id=generation_run_id,
            batch_month=date(2025, sequence, 1),
            batch_sequence=sequence,
            batch_type=(
                "historical_initial" if sequence <= 12 else "future_increment"
            ),
            processing_status=status,
        )
        session.add(batch)
        batches.append(batch)
    session.commit()
    return tuple(batches)


def test_resolve_release_request_validates_counts():
    request = resolve_release_request(
        generation_run_id="7",
        initial_history_month_count="12",
        subsequent_month_count="6",
    )

    assert request.generation_run_id == 7
    assert request.initial_history_month_count == 12
    assert request.subsequent_month_count == 6
    assert request.maximum_batch_sequence == 18


@pytest.mark.parametrize(
    ("kwargs", "message"),
    (
        (
            {
                "generation_run_id": 0,
                "initial_history_month_count": 12,
                "subsequent_month_count": 6,
            },
            "generation_run_id",
        ),
        (
            {
                "generation_run_id": 1,
                "initial_history_month_count": 0,
                "subsequent_month_count": 6,
            },
            "initial_history_month_count",
        ),
        (
            {
                "generation_run_id": 1,
                "initial_history_month_count": 12,
                "subsequent_month_count": -1,
            },
            "subsequent_month_count",
        ),
        (
            {
                "generation_run_id": 1.2,
                "initial_history_month_count": 12,
                "subsequent_month_count": 6,
            },
            "generation_run_id",
        ),
        (
            {
                "generation_run_id": True,
                "initial_history_month_count": 12,
                "subsequent_month_count": 6,
            },
            "generation_run_id",
        ),
    ),
)
def test_resolve_release_request_rejects_invalid_counts(kwargs, message):
    with pytest.raises(ReleaseWindowValidationError, match=message):
        resolve_release_request(**kwargs)


def test_plan_release_windows_builds_baseline_and_incremental_windows(session):
    generation_run = seed_generation_run(session)
    seed_monthly_batches(session, generation_run.id, count=5)

    windows = plan_release_windows(
        session=session,
        generation_run_id=generation_run.id,
        initial_history_month_count=3,
        subsequent_month_count=2,
    )

    assert len(windows) == 3
    assert windows[0].release_type == HISTORICAL_BASELINE_RELEASE_TYPE
    assert windows[0].release_sequence_number == 1
    assert windows[0].folder_suffix == "_initial_history"
    assert windows[0].batch_sequences == (1, 2, 3)
    assert windows[0].snapshot_batch_sequences == (1, 2, 3)
    assert windows[0].fact_batch_sequences == (1, 2, 3)
    assert windows[0].prior_snapshot_batch_sequences == ()
    assert windows[0].release_month is None
    assert windows[0].snapshot_month == date(2025, 3, 1)
    assert windows[0].prior_snapshot_month is None
    assert windows[0].snapshot_end_exclusive == date(2025, 4, 1)
    assert windows[0].prior_snapshot_end_exclusive is None

    assert windows[1].release_type == MONTHLY_INCREMENTAL_RELEASE_TYPE
    assert windows[1].release_sequence_number == 2
    assert windows[1].folder_suffix == "_snapshot_2025_04"
    assert windows[1].batch_sequences == (1, 2, 3, 4)
    assert windows[1].snapshot_batch_sequences == (1, 2, 3, 4)
    assert windows[1].fact_batch_sequences == (4,)
    assert windows[1].fact_batch_ids == (4,)
    assert windows[1].prior_snapshot_batch_sequences == (1, 2, 3)
    assert windows[1].release_month == date(2025, 4, 1)
    assert windows[1].prior_snapshot_month == date(2025, 3, 1)
    assert windows[1].prior_snapshot_end_exclusive == date(2025, 4, 1)

    assert windows[2].release_type == MONTHLY_INCREMENTAL_RELEASE_TYPE
    assert windows[2].release_sequence_number == 3
    assert windows[2].folder_suffix == "_snapshot_2025_05"
    assert windows[2].batch_sequences == (1, 2, 3, 4, 5)
    assert windows[2].snapshot_batch_sequences == (1, 2, 3, 4, 5)
    assert windows[2].fact_batch_sequences == (5,)
    assert windows[2].batch_ids == (1, 2, 3, 4, 5)
    assert windows[2].batch_months == (
        date(2025, 1, 1),
        date(2025, 2, 1),
        date(2025, 3, 1),
        date(2025, 4, 1),
        date(2025, 5, 1),
    )
    assert windows[2].fact_batch_months == (date(2025, 5, 1),)
    assert windows[2].prior_snapshot_batch_sequences == (1, 2, 3, 4)
    assert windows[2].release_month == date(2025, 5, 1)
    assert windows[2].prior_snapshot_month == date(2025, 4, 1)
    assert windows[2].prior_snapshot_end_exclusive == date(2025, 5, 1)


def test_plan_release_windows_requires_succeeded_generation_run(session):
    generation_run = seed_generation_run(session, status="running")
    seed_monthly_batches(session, generation_run.id, count=3)

    with pytest.raises(ReleaseWindowValidationError, match="status 'succeeded'"):
        plan_release_windows(
            session=session,
            generation_run_id=generation_run.id,
            initial_history_month_count=3,
            subsequent_month_count=0,
        )


def test_plan_release_windows_rejects_unknown_generation_run(session):
    with pytest.raises(ReleaseWindowValidationError, match="does not exist"):
        plan_release_windows(
            session=session,
            generation_run_id=999,
            initial_history_month_count=3,
            subsequent_month_count=0,
        )


def test_plan_release_windows_rejects_missing_requested_batches(session):
    generation_run = seed_generation_run(session)
    seed_monthly_batches(session, generation_run.id, count=2)

    with pytest.raises(ReleaseWindowValidationError, match="Missing"):
        plan_release_windows(
            session=session,
            generation_run_id=generation_run.id,
            initial_history_month_count=3,
            subsequent_month_count=0,
        )


def test_plan_release_windows_rejects_incomplete_requested_batches(session):
    generation_run = seed_generation_run(session)
    seed_monthly_batches(session, generation_run.id, count=3)
    batch = session.get(MonthlyBatch, 2)
    batch.processing_status = "failed"
    session.commit()

    with pytest.raises(ReleaseWindowValidationError, match="incomplete sequences"):
        plan_release_windows(
            session=session,
            generation_run_id=generation_run.id,
            initial_history_month_count=3,
            subsequent_month_count=0,
        )


def test_plan_release_windows_rejects_duplicate_batch_sequences(session):
    generation_run = seed_generation_run(session)
    seed_monthly_batches(session, generation_run.id, count=3)
    session.execute(
        text(
            """
            INSERT INTO monthly_batches (
                generation_run_id,
                batch_month,
                batch_sequence,
                processing_status
            )
            VALUES (:generation_run_id, '2025-04-01', 2, 'succeeded')
            """
        ),
        {"generation_run_id": generation_run.id},
    )
    session.commit()

    with pytest.raises(ReleaseWindowValidationError, match="Duplicate"):
        plan_release_windows(
            session=session,
            generation_run_id=generation_run.id,
            initial_history_month_count=3,
            subsequent_month_count=0,
        )


def test_build_release_windows_accepts_release_batch_values_without_database():
    request = StudentDatasetReleaseRequest(
        generation_run_id=1,
        initial_history_month_count=2,
        subsequent_month_count=1,
    )
    batches = (
        ReleaseBatch(id=10, batch_sequence=1, batch_month=date(2025, 1, 1)),
        ReleaseBatch(id=20, batch_sequence=2, batch_month=date(2025, 2, 1)),
        ReleaseBatch(id=30, batch_sequence=3, batch_month=date(2025, 3, 1)),
    )

    windows = build_release_windows(request, batches)

    assert tuple(window.batch_sequences for window in windows) == (
        (1, 2),
        (1, 2, 3),
    )
    assert tuple(window.fact_batch_sequences for window in windows) == (
        (1, 2),
        (3,),
    )


def test_first_day_of_next_month_handles_december():
    assert first_day_of_next_month(date(2025, 12, 1)) == date(2026, 1, 1)
