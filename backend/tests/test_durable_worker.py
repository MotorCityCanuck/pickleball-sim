"""Tests for durable background worker primitives."""
from datetime import datetime, timedelta
from pathlib import Path
import sys

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.generation.durable_worker import (  # noqa: E402
    WorkerIdentity,
    claim_next_realism_audit_job,
    generate_worker_identity,
    heartbeat_worker,
    register_worker,
    release_job_lease,
    renew_job_lease,
    write_job_event,
)
from app.models import BackgroundJobEvent, BackgroundJobLease, BackgroundWorker, JobStatus  # noqa: E402


@pytest.fixture()
def session():
    engine = create_engine("sqlite:///:memory:", future=True)
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
    Session = sessionmaker(bind=engine, future=True)
    with Session() as active_session:
        yield active_session


def test_generate_worker_identity_includes_process_details():
    identity = generate_worker_identity(
        "realism_audit",
        hostname="audit-host",
        process_id=1234,
    )

    assert identity.worker_type == "realism_audit"
    assert identity.hostname == "audit-host"
    assert identity.process_id == 1234
    assert identity.worker_id.startswith("realism-audit-1234-")
    assert len(identity.worker_id) <= 64


def test_register_and_heartbeat_worker(session):
    now = datetime(2026, 1, 1, 12, 0, 0)
    identity = _worker("worker-one")

    worker = register_worker(session, identity, now=now, metadata={"slot": 1})
    session.commit()

    assert worker.worker_id == "worker-one"
    assert worker.host_name == "host-one"
    assert worker.process_id == 1001
    assert worker.metadata_json == {"slot": 1}

    heartbeat_at = now + timedelta(minutes=2)
    heartbeat_worker(session, identity.worker_id, now=heartbeat_at)
    session.commit()

    refreshed = session.get(BackgroundWorker, identity.worker_id)
    assert refreshed.last_heartbeat_at == heartbeat_at
    assert refreshed.status == "running"


def test_one_worker_claims_pending_realism_audit_job(session):
    now = datetime(2026, 1, 1, 12, 0, 0)
    worker = _registered_worker(session, "worker-one", now=now)
    job = _job(1, status="pending", created_at=now)
    session.add(job)
    session.commit()

    lease = claim_next_realism_audit_job(session, worker.worker_id, now=now)
    session.commit()

    assert lease is not None
    assert lease.job_status_id == job.id
    assert lease.worker_id == worker.worker_id
    assert lease.attempt_count == 1
    assert lease.lease_expires_at == now + timedelta(minutes=15)

    claimed_job = session.get(JobStatus, job.id)
    assert claimed_job.status == "running"
    assert claimed_job.started_at == now

    event = session.execute(select(BackgroundJobEvent)).scalar_one()
    assert event.job_status_id == job.id
    assert event.worker_id == worker.worker_id
    assert event.event_type == "job_claimed"


def test_second_worker_cannot_claim_fresh_lease(session):
    now = datetime(2026, 1, 1, 12, 0, 0)
    first_worker = _registered_worker(session, "worker-one", now=now)
    second_worker = _registered_worker(session, "worker-two", now=now)
    session.add(_job(1, status="pending", created_at=now))
    session.commit()

    first_lease = claim_next_realism_audit_job(
        session,
        first_worker.worker_id,
        now=now,
    )
    session.commit()
    second_lease = claim_next_realism_audit_job(
        session,
        second_worker.worker_id,
        now=now + timedelta(minutes=1),
    )
    session.commit()

    assert first_lease is not None
    assert second_lease is None
    persisted_lease = session.get(BackgroundJobLease, 1)
    assert persisted_lease.worker_id == first_worker.worker_id


def test_expired_lease_can_be_reclaimed(session):
    now = datetime(2026, 1, 1, 12, 0, 0)
    first_worker = _registered_worker(session, "worker-one", now=now)
    second_worker = _registered_worker(session, "worker-two", now=now)
    session.add(_job(1, status="pending", created_at=now))
    session.commit()

    first_lease = claim_next_realism_audit_job(
        session,
        first_worker.worker_id,
        now=now,
        lease_duration=timedelta(minutes=5),
    )
    first_token = first_lease.lease_token
    session.commit()

    reclaimed = claim_next_realism_audit_job(
        session,
        second_worker.worker_id,
        now=now + timedelta(minutes=6),
        lease_duration=timedelta(minutes=10),
    )
    session.commit()

    assert reclaimed is not None
    assert reclaimed.worker_id == second_worker.worker_id
    assert reclaimed.lease_token != first_token
    assert reclaimed.attempt_count == 2
    assert reclaimed.lease_expires_at == now + timedelta(minutes=16)

    event_types = [
        row.event_type
        for row in session.scalars(
            select(BackgroundJobEvent).order_by(BackgroundJobEvent.id)
        )
    ]
    assert event_types == ["job_claimed", "job_reclaimed"]


def test_running_job_with_missing_lease_can_be_reclaimed(session):
    now = datetime(2026, 1, 1, 12, 0, 0)
    worker = _registered_worker(session, "worker-one", now=now)
    session.add(_job(1, status="running", created_at=now - timedelta(hours=1)))
    session.commit()

    lease = claim_next_realism_audit_job(session, worker.worker_id, now=now)
    session.commit()

    assert lease is not None
    assert lease.job_status_id == 1
    assert lease.worker_id == worker.worker_id


def test_renew_and_release_lease(session):
    now = datetime(2026, 1, 1, 12, 0, 0)
    worker = _registered_worker(session, "worker-one", now=now)
    session.add(_job(1, status="pending", created_at=now))
    session.commit()
    lease = claim_next_realism_audit_job(session, worker.worker_id, now=now)
    token = lease.lease_token
    session.commit()

    renewed = renew_job_lease(
        session,
        job_status_id=1,
        worker_id=worker.worker_id,
        lease_token=token,
        now=now + timedelta(minutes=5),
        lease_duration=timedelta(minutes=20),
    )
    session.commit()

    assert renewed is not None
    assert renewed.lease_expires_at == now + timedelta(minutes=25)

    released = release_job_lease(
        session,
        job_status_id=1,
        worker_id=worker.worker_id,
        lease_token=token,
        final_status="succeeded",
        now=now + timedelta(minutes=6),
    )
    session.commit()

    assert released is True
    assert session.get(BackgroundJobLease, 1) is None
    assert session.get(JobStatus, 1).status == "succeeded"
    event_types = [
        row.event_type
        for row in session.scalars(
            select(BackgroundJobEvent).order_by(BackgroundJobEvent.id)
        )
    ]
    assert event_types == ["job_claimed", "lease_renewed", "lease_released"]


def test_event_writer_records_event(session):
    now = datetime(2026, 1, 1, 12, 0, 0)
    session.add(_job(1, status="pending", created_at=now))
    session.commit()

    event = write_job_event(
        session,
        job_status_id=1,
        event_type="probe",
        worker_id="worker-one",
        message="Probe event.",
        metadata={"query": "one"},
        now=now,
    )
    session.commit()

    assert event.id == 1
    assert event.job_status_id == 1
    assert event.worker_id == "worker-one"
    assert event.event_type == "probe"
    assert event.event_message == "Probe event."
    assert event.event_metadata_json == {"query": "one"}
    assert event.created_at == now


def _worker(worker_id: str) -> WorkerIdentity:
    suffix = worker_id.rsplit("-", maxsplit=1)[-1]
    process_id = 1001 if suffix == "one" else 1002
    return WorkerIdentity(
        worker_id=worker_id,
        worker_type="realism_audit",
        hostname=f"host-{suffix}",
        process_id=process_id,
    )


def _registered_worker(
    session,
    worker_id: str,
    *,
    now: datetime,
) -> BackgroundWorker:
    return register_worker(session, _worker(worker_id), now=now)


def _job(
    job_id: int,
    *,
    status: str,
    created_at: datetime,
) -> JobStatus:
    return JobStatus(
        id=job_id,
        job_type="realism_audit",
        job_id=f"realism-audit-{job_id}",
        status=status,
        created_at=created_at,
        updated_at=created_at,
    )
