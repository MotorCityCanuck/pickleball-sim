"""Tests for durable realism-audit checkpoint helpers."""
from datetime import datetime
from pathlib import Path
import sys

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.generation.realism_audit import RealismAuditQuery  # noqa: E402
from app.generation.realism_audit_checkpoints import (  # noqa: E402
    initialize_realism_audit_query_checkpoints,
    load_realism_audit_query_checkpoints,
    mark_realism_audit_query_failed,
    mark_realism_audit_query_running,
    mark_realism_audit_query_succeeded,
)
from app.models import RealismAuditQueryRun  # noqa: E402


@pytest.fixture()
def session():
    engine = create_engine("sqlite:///:memory:", future=True)
    with engine.begin() as conn:
        conn.exec_driver_sql("ATTACH DATABASE ':memory:' AS ops")
        conn.exec_driver_sql(
            """
            CREATE TABLE ops.realism_audit_query_runs (
                id integer primary key autoincrement,
                job_status_id bigint not null,
                generation_run_id bigint,
                batch_id bigint,
                query_index integer not null,
                query_name varchar(255) not null,
                status varchar(30) default 'pending' not null,
                started_at datetime,
                completed_at datetime,
                elapsed_ms bigint,
                row_count bigint,
                result_json json,
                error_message text,
                created_at datetime default current_timestamp not null,
                updated_at datetime default current_timestamp not null,
                unique (job_status_id, query_name)
            )
            """
        )
    Session = sessionmaker(bind=engine, future=True)
    with Session() as active_session:
        yield active_session


def test_initialize_realism_audit_query_checkpoints_creates_pending_rows(session):
    queries = (_query("alpha"), _query("bravo"), _query("charlie"))

    checkpoints = initialize_realism_audit_query_checkpoints(
        session,
        job_status_id=10,
        generation_run_id=2,
        batch_id=22,
        queries=queries,
    )
    session.commit()

    assert [checkpoint.query_name for checkpoint in checkpoints] == [
        "alpha",
        "bravo",
        "charlie",
    ]
    rows = list(
        session.scalars(
            select(RealismAuditQueryRun).order_by(RealismAuditQueryRun.query_index)
        )
    )
    assert [row.query_index for row in rows] == [1, 2, 3]
    assert {row.status for row in rows} == {"pending"}
    assert {row.job_status_id for row in rows} == {10}
    assert {row.generation_run_id for row in rows} == {2}
    assert {row.batch_id for row in rows} == {22}


def test_initialize_realism_audit_query_checkpoints_is_idempotent(session):
    queries = (_query("alpha"), _query("bravo"))

    initialize_realism_audit_query_checkpoints(
        session,
        job_status_id=10,
        generation_run_id=2,
        batch_id=22,
        queries=queries,
    )
    initialize_realism_audit_query_checkpoints(
        session,
        job_status_id=10,
        generation_run_id=2,
        batch_id=22,
        queries=queries,
    )
    session.commit()

    assert session.query(RealismAuditQueryRun).count() == 2


def test_load_realism_audit_query_checkpoints_uses_resume_order(session):
    session.add_all(
        [
            _checkpoint(job_status_id=10, query_index=3, query_name="charlie"),
            _checkpoint(job_status_id=10, query_index=1, query_name="alpha"),
            _checkpoint(job_status_id=10, query_index=2, query_name="bravo", status="succeeded"),
            _checkpoint(job_status_id=11, query_index=1, query_name="other"),
        ]
    )
    session.commit()

    all_rows = load_realism_audit_query_checkpoints(session, job_status_id=10)
    resumable_rows = load_realism_audit_query_checkpoints(
        session,
        job_status_id=10,
        include_completed=False,
    )

    assert [row.query_name for row in all_rows] == ["alpha", "bravo", "charlie"]
    assert [row.query_name for row in resumable_rows] == ["alpha", "charlie"]


def test_mark_query_running_succeeded_and_failed(session):
    started_at = datetime(2026, 1, 1, 12, 0, 0)
    completed_at = datetime(2026, 1, 1, 12, 0, 2)
    checkpoint = _checkpoint(job_status_id=10, query_index=1, query_name="alpha")
    session.add(checkpoint)
    session.commit()

    mark_realism_audit_query_running(session, checkpoint, now=started_at)
    mark_realism_audit_query_succeeded(
        session,
        checkpoint,
        result={
            "query": "alpha",
            "rows": [{"value": 1}, {"value": 2}],
        },
        elapsed_ms=2000,
        now=completed_at,
    )
    session.commit()

    refreshed = session.get(RealismAuditQueryRun, checkpoint.id)
    assert refreshed.status == "succeeded"
    assert refreshed.started_at == started_at
    assert refreshed.completed_at == completed_at
    assert refreshed.elapsed_ms == 2000
    assert refreshed.row_count == 2
    assert refreshed.result_json == {
        "query": "alpha",
        "rows": [{"value": 1}, {"value": 2}],
    }

    mark_realism_audit_query_failed(
        session,
        refreshed,
        error_message="boom",
        elapsed_ms=2500,
        now=completed_at,
    )
    session.commit()

    failed = session.get(RealismAuditQueryRun, checkpoint.id)
    assert failed.status == "failed"
    assert failed.error_message == "boom"
    assert failed.elapsed_ms == 2500


def _query(name: str) -> RealismAuditQuery:
    return RealismAuditQuery(
        name=name,
        description=f"{name} query",
        sql="SELECT 1 AS value",
        scope="generation_run",
        category="test",
        required_params=("generation_run_id",),
    )


def _checkpoint(
    *,
    job_status_id: int,
    query_index: int,
    query_name: str,
    status: str = "pending",
) -> RealismAuditQueryRun:
    return RealismAuditQueryRun(
        job_status_id=job_status_id,
        query_index=query_index,
        query_name=query_name,
        status=status,
    )
