"""Tests for the durable background worker CLI."""
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
import sys

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker


BACKEND_DIR = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = BACKEND_DIR / "scripts"
for path in (BACKEND_DIR, SCRIPTS_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from app.models import BackgroundJobEvent, BackgroundJobLease, BackgroundWorker, JobStatus  # noqa: E402
from run_background_worker import (  # noqa: E402
    WorkerConfig,
    config_from_args,
    parse_args,
    run_worker,
)


@pytest.fixture()
def worker_session_factory():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    with engine.begin() as conn:
        conn.exec_driver_sql("ATTACH DATABASE ':memory:' AS ops")
        conn.exec_driver_sql(
            """
            CREATE TABLE job_status (
                id integer primary key,
                job_type varchar(50) not null,
                job_id varchar(100) not null unique,
                status varchar(30) not null default 'pending',
                current_phase varchar(100),
                percent_complete numeric(5, 2),
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
            CREATE TABLE ops.background_workers (
                worker_id varchar(64) primary key,
                worker_type varchar(50) not null,
                host_name varchar(255),
                process_id integer,
                started_at datetime default current_timestamp not null,
                last_heartbeat_at datetime default current_timestamp not null,
                status varchar(30) default 'running' not null,
                metadata_json json,
                created_at datetime default current_timestamp not null,
                updated_at datetime default current_timestamp not null
            )
            """
        )
        conn.exec_driver_sql(
            """
            CREATE TABLE ops.background_job_leases (
                job_status_id bigint primary key,
                worker_id varchar(64) not null,
                lease_token varchar(64) not null unique,
                claimed_at datetime default current_timestamp not null,
                lease_expires_at datetime not null,
                last_heartbeat_at datetime default current_timestamp not null,
                attempt_count integer default 1 not null,
                metadata_json json,
                created_at datetime default current_timestamp not null,
                updated_at datetime default current_timestamp not null
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
    Session = sessionmaker(bind=engine, future=True, expire_on_commit=False)

    @contextmanager
    def factory():
        session = Session()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    return factory


def test_parse_config_accepts_realism_audit_queue():
    config = config_from_args(
        parse_args(
            [
                "--queues",
                "realism_audit",
                "--once",
                "--poll-interval-seconds",
                "1",
                "--lease-seconds",
                "30",
                "--heartbeat-seconds",
                "5",
            ]
        )
    )

    assert config.queues == ("realism_audit",)
    assert config.once is True
    assert config.poll_interval_seconds == 1
    assert config.lease_seconds == 30
    assert config.heartbeat_seconds == 5


def test_parse_config_rejects_unsupported_queue():
    with pytest.raises(ValueError, match="Unsupported queue"):
        config_from_args(parse_args(["--queues", "generation_run"]))


def test_once_exits_cleanly_with_no_job_and_registers_worker(worker_session_factory):
    config = WorkerConfig(
        queues=("realism_audit",),
        once=True,
        poll_interval_seconds=0.01,
        lease_seconds=60,
        heartbeat_seconds=5,
    )

    exit_code = run_worker(
        config,
        session_factory=worker_session_factory,
        realism_audit_handler=lambda job_status_id: None,
    )

    assert exit_code == 0
    with worker_session_factory() as session:
        workers = list(session.scalars(select(BackgroundWorker)))
        assert len(workers) == 1
        assert workers[0].status == "running"
        assert workers[0].last_heartbeat_at is not None


def test_once_claims_job_runs_handler_and_releases_lease(worker_session_factory):
    created_at = datetime(2026, 1, 1, 12, 0, 0)
    with worker_session_factory() as session:
        session.add(
            JobStatus(
                id=1,
                job_type="realism_audit",
                job_id="realism-audit-1",
                status="pending",
                created_at=created_at,
                updated_at=created_at,
            )
        )

    handled_jobs = []

    def handler(job_status_id: int) -> None:
        handled_jobs.append(job_status_id)

    config = WorkerConfig(
        queues=("realism_audit",),
        once=True,
        poll_interval_seconds=0.01,
        lease_seconds=60,
        heartbeat_seconds=5,
    )

    exit_code = run_worker(
        config,
        session_factory=worker_session_factory,
        realism_audit_handler=handler,
    )

    assert exit_code == 0
    assert handled_jobs == [1]
    with worker_session_factory() as session:
        job = session.get(JobStatus, 1)
        assert job.status == "succeeded"
        assert session.get(BackgroundJobLease, 1) is None
        event_types = [
            event.event_type
            for event in session.scalars(
                select(BackgroundJobEvent).order_by(BackgroundJobEvent.id)
            )
        ]
        assert event_types == [
            "job_claimed",
            "job_started",
            "job_succeeded",
            "lease_released",
        ]
