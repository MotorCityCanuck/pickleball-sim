"""Tests for durable realism-audit job execution."""
from datetime import datetime
import json
from pathlib import Path
import sys

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.generation.realism_audit import RealismAuditQuery, RealismAuditResult  # noqa: E402
from app.generation.realism_audit_checkpoints import (  # noqa: E402
    initialize_realism_audit_query_checkpoints,
    mark_realism_audit_query_succeeded,
)
from app.generation.realism_audit_job_handler import RealismAuditJobHandler  # noqa: E402
from app.models import BackgroundJobEvent, JobStageProgress, JobStatus, RealismAuditQueryRun  # noqa: E402


@pytest.fixture()
def session():
    engine = create_engine("sqlite:///:memory:", future=True)
    with engine.begin() as conn:
        conn.exec_driver_sql("ATTACH DATABASE ':memory:' AS ops")
        conn.exec_driver_sql(
            """
            CREATE TABLE generation_runs (
                id integer primary key,
                generation_name varchar(255) not null,
                seed_value bigint not null,
                parameter_snapshot json,
                status varchar(30) not null default 'succeeded',
                created_at datetime default current_timestamp not null,
                updated_at datetime default current_timestamp not null
            )
            """
        )
        conn.exec_driver_sql(
            """
            CREATE TABLE monthly_batches (
                id integer primary key,
                generation_run_id bigint not null,
                batch_month date not null,
                batch_sequence integer not null,
                processing_status varchar(30) not null default 'succeeded',
                created_at datetime default current_timestamp not null,
                updated_at datetime default current_timestamp not null
            )
            """
        )
        conn.exec_driver_sql(
            """
            CREATE TABLE job_status (
                id integer primary key,
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
                id integer primary key,
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
                metadata_json json,
                created_at datetime default current_timestamp not null,
                updated_at datetime default current_timestamp not null
            )
            """
        )
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
        conn.exec_driver_sql(
            """
            CREATE TABLE ops.background_job_events (
                id integer primary key autoincrement,
                job_status_id bigint not null,
                worker_id varchar(64),
                event_type varchar(50) not null,
                event_message text,
                event_metadata_json json,
                created_at datetime default current_timestamp not null
            )
            """
        )
    Session = sessionmaker(bind=engine, future=True)
    with Session() as active_session:
        _seed_job(active_session)
        yield active_session


def test_durable_handler_produces_current_snapshot_shape(session, tmp_path):
    queries = (_query("alpha"), _query("bravo"))
    initialize_realism_audit_query_checkpoints(
        session,
        job_status_id=10,
        generation_run_id=2,
        batch_id=22,
        queries=queries,
    )
    session.commit()
    runner = FakeRunner(
        queries,
        results={
            "alpha": [{"query_name": "alpha", "value": 1}],
            "bravo": [{"query_name": "bravo", "value": 2}],
        },
    )

    result = RealismAuditJobHandler(
        session,
        snapshot_dir=tmp_path,
        runner_factory=lambda active_session: runner,
        now_factory=lambda: datetime(2026, 1, 1, 12, 0, 0),
    ).run_claimed_job(job_status_id=10, worker_id="worker-one")
    session.commit()

    assert result.executed_query_count == 2
    assert result.reused_query_count == 0
    assert result.snapshot_path is not None
    payload = json.loads(result.snapshot_path.read_text(encoding="utf-8"))
    assert set(payload) >= {
        "executed_at",
        "generation_run_id",
        "batch_id",
        "batch_month",
        "results",
        "assessment",
        "snapshot_path",
        "snapshot_version",
        "query_count",
    }
    assert payload["generation_run_id"] == 2
    assert payload["batch_id"] == 22
    assert payload["batch_month"] == "2026-02-01"
    assert payload["query_count"] == 2
    assert [row["query"] for row in payload["results"]] == ["alpha", "bravo"]

    job = session.get(JobStatus, 10)
    stage = session.get(JobStageProgress, 100)
    assert job.status == "succeeded"
    assert job.current_phase == "completed"
    assert stage.status == "succeeded"
    assert stage.progress_current == 2
    assert session.query(RealismAuditQueryRun).filter_by(status="succeeded").count() == 2


def test_durable_handler_restart_resumes_after_succeeded_query(session, tmp_path):
    queries = (_query("alpha"), _query("bravo"), _query("charlie"))
    checkpoints = initialize_realism_audit_query_checkpoints(
        session,
        job_status_id=10,
        generation_run_id=2,
        batch_id=22,
        queries=queries,
    )
    mark_realism_audit_query_succeeded(
        session,
        checkpoints[0],
        result={
            "query": "alpha",
            "scope": "generation_run",
            "category": "test",
            "description": "alpha query",
            "tags": [],
            "related_config_keys": [],
            "rows": [{"query_name": "alpha", "value": 1}],
        },
        elapsed_ms=10,
        now=datetime(2026, 1, 1, 12, 0, 0),
    )
    session.commit()
    runner = FakeRunner(
        queries,
        results={
            "alpha": [{"query_name": "alpha", "value": 999}],
            "bravo": [{"query_name": "bravo", "value": 2}],
            "charlie": [{"query_name": "charlie", "value": 3}],
        },
    )

    result = RealismAuditJobHandler(
        session,
        snapshot_dir=tmp_path,
        runner_factory=lambda active_session: runner,
        now_factory=lambda: datetime(2026, 1, 1, 12, 0, 0),
    ).run_claimed_job(job_status_id=10, worker_id="worker-one")
    session.commit()

    assert result.executed_query_count == 2
    assert result.reused_query_count == 1
    assert runner.executed_query_names == ["bravo", "charlie"]
    payload = json.loads(result.snapshot_path.read_text(encoding="utf-8"))
    assert [row["query"] for row in payload["results"]] == ["alpha", "bravo", "charlie"]
    assert payload["results"][0]["rows"] == [{"query_name": "alpha", "value": 1}]


def test_durable_handler_retries_interrupted_running_checkpoint(session, tmp_path):
    queries = (_query("alpha"), _query("bravo"))
    checkpoints = initialize_realism_audit_query_checkpoints(
        session,
        job_status_id=10,
        generation_run_id=2,
        batch_id=22,
        queries=queries,
    )
    checkpoints[0].status = "running"
    checkpoints[0].started_at = datetime(2026, 1, 1, 11, 0, 0)
    session.commit()
    runner = FakeRunner(
        queries,
        results={
            "alpha": [{"query_name": "alpha", "value": 1}],
            "bravo": [{"query_name": "bravo", "value": 2}],
        },
    )

    RealismAuditJobHandler(
        session,
        snapshot_dir=tmp_path,
        runner_factory=lambda active_session: runner,
        now_factory=lambda: datetime(2026, 1, 1, 12, 0, 0),
    ).run_claimed_job(job_status_id=10, worker_id="worker-one")
    session.commit()

    assert runner.executed_query_names == ["alpha", "bravo"]
    assert session.get(RealismAuditQueryRun, checkpoints[0].id).status == "succeeded"


def test_durable_handler_failed_query_leaves_exact_query_name(session, tmp_path):
    queries = (_query("alpha"), _query("bravo"))
    initialize_realism_audit_query_checkpoints(
        session,
        job_status_id=10,
        generation_run_id=2,
        batch_id=22,
        queries=queries,
    )
    session.commit()
    runner = FakeRunner(
        queries,
        results={"alpha": [{"query_name": "alpha", "value": 1}]},
        failure_by_query={"bravo": RuntimeError("boom")},
    )

    with pytest.raises(RuntimeError, match="boom"):
        RealismAuditJobHandler(
            session,
            snapshot_dir=tmp_path,
            runner_factory=lambda active_session: runner,
            now_factory=lambda: datetime(2026, 1, 1, 12, 0, 0),
        ).run_claimed_job(job_status_id=10, worker_id="worker-one")
    session.commit()

    failed_checkpoint = session.scalar(
        select(RealismAuditQueryRun).where(RealismAuditQueryRun.status == "failed")
    )
    job = session.get(JobStatus, 10)
    stage = session.get(JobStageProgress, 100)
    event = session.scalar(select(BackgroundJobEvent).where(BackgroundJobEvent.event_type == "query_failed"))
    assert failed_checkpoint.query_name == "bravo"
    assert failed_checkpoint.error_message == "boom"
    assert job.status == "failed"
    assert job.current_phase == "bravo"
    assert "bravo" in job.error_message
    assert stage.status == "failed"
    assert "bravo" in stage.error_message
    assert event.event_metadata_json == {"query_name": "bravo"}


class FakeRunner:
    def __init__(
        self,
        queries,
        *,
        results,
        failure_by_query=None,
    ):
        self.queries = tuple(queries)
        self.query_lookup = {query.name: query for query in self.queries}
        self.results = results
        self.failure_by_query = failure_by_query or {}
        self.executed_query_names = []

    def available_queries(self):
        return self.queries

    def run(self, *, query_names=None, params=None):
        query_name = query_names[0]
        self.executed_query_names.append(query_name)
        failure = self.failure_by_query.get(query_name)
        if failure is not None:
            raise failure
        return (
            RealismAuditResult(
                query=self.query_lookup[query_name],
                rows=tuple(self.results[query_name]),
            ),
        )


def _seed_job(session):
    session.execute(
        select(RealismAuditQueryRun)
    )
    session.execute(
        text_sql(
            """
            INSERT INTO generation_runs (id, generation_name, seed_value, status)
            VALUES (2, 'run', 123, 'succeeded')
            """
        )
    )
    session.execute(
        text_sql(
            """
            INSERT INTO monthly_batches (
                id, generation_run_id, batch_month, batch_sequence, processing_status
            )
            VALUES (22, 2, '2026-02-01', 1, 'succeeded')
            """
        )
    )
    session.add(
        JobStatus(
            id=10,
            job_type="realism_audit",
            job_id="realism-audit-10",
            status="running",
            current_phase="queued",
            created_at=datetime(2026, 1, 1, 11, 59, 0),
            updated_at=datetime(2026, 1, 1, 11, 59, 0),
        )
    )
    session.add(
        JobStageProgress(
            id=100,
            job_status_id=10,
            generation_run_id=2,
            batch_id=22,
            stage_name="run_realism_audit",
            stage_sequence=1,
            status="pending",
            progress_current=0,
            progress_total=0,
            progress_unit="query",
            created_at=datetime(2026, 1, 1, 11, 59, 0),
            updated_at=datetime(2026, 1, 1, 11, 59, 0),
        )
    )
    session.commit()


def _query(name: str) -> RealismAuditQuery:
    return RealismAuditQuery(
        name=name,
        description=f"{name} query",
        sql="SELECT 1 AS value",
        scope="generation_run",
        category="test",
        required_params=("generation_run_id",),
    )


def text_sql(sql: str):
    from sqlalchemy import text

    return text(sql)
