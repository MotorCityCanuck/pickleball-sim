"""Durable background worker state in the ops schema."""
from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from .base import Base, TimestampMixin

SqliteAutoincrementBigInteger = BigInteger().with_variant(Integer, "sqlite")


class BackgroundWorker(Base, TimestampMixin):
    """Registered durable worker process."""

    __tablename__ = "background_workers"
    __table_args__ = (
        Index("idx_background_workers_status", "status"),
        Index("idx_background_workers_heartbeat", "last_heartbeat_at"),
        CheckConstraint(
            "status IN ('running', 'stopped', 'failed')",
            name="chk_background_workers_status",
        ),
        {"schema": "ops"},
    )

    worker_id = Column(String(64), primary_key=True)
    worker_type = Column(String(50), nullable=False)
    host_name = Column(String(255))
    process_id = Column(Integer)
    started_at = Column(
        DateTime,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    last_heartbeat_at = Column(
        DateTime,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    status = Column(
        String(30),
        nullable=False,
        default="running",
        server_default=text("'running'"),
    )
    metadata_json = Column(JSONB().with_variant(JSON(), "sqlite"))


class BackgroundJobLease(Base, TimestampMixin):
    """Current worker lease for a pending or running job."""

    __tablename__ = "background_job_leases"
    __table_args__ = (
        Index("idx_background_job_leases_token", "lease_token", unique=True),
        Index("idx_background_job_leases_worker", "worker_id"),
        Index("idx_background_job_leases_expiry", "lease_expires_at"),
        {"schema": "ops"},
    )

    job_status_id = Column(
        BigInteger,
        ForeignKey("job_status.id", ondelete="CASCADE"),
        primary_key=True,
    )
    worker_id = Column(
        String(64),
        ForeignKey("ops.background_workers.worker_id"),
        nullable=False,
    )
    lease_token = Column(String(64), nullable=False)
    claimed_at = Column(
        DateTime,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    lease_expires_at = Column(DateTime, nullable=False)
    last_heartbeat_at = Column(
        DateTime,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    attempt_count = Column(
        Integer,
        nullable=False,
        default=1,
        server_default=text("1"),
    )
    metadata_json = Column(JSONB().with_variant(JSON(), "sqlite"))

    job_status = relationship("JobStatus")
    worker = relationship("BackgroundWorker")


class BackgroundJobEvent(Base):
    """Append-only durable job lifecycle event."""

    __tablename__ = "background_job_events"
    __table_args__ = (
        Index("idx_background_job_events_job", "job_status_id", "id"),
        Index("idx_background_job_events_type", "event_type"),
        {"schema": "ops"},
    )

    id = Column(SqliteAutoincrementBigInteger, primary_key=True, autoincrement=True)
    job_status_id = Column(
        BigInteger,
        ForeignKey("job_status.id", ondelete="CASCADE"),
        nullable=False,
    )
    worker_id = Column(String(64))
    event_type = Column(String(50), nullable=False)
    event_message = Column(Text)
    event_metadata_json = Column(JSONB().with_variant(JSON(), "sqlite"))
    created_at = Column(
        DateTime,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )

    job_status = relationship("JobStatus")


class RealismAuditQueryRun(Base, TimestampMixin):
    """Per-query checkpoint row for durable realism audit execution."""

    __tablename__ = "realism_audit_query_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'running', 'succeeded', 'failed', 'skipped')",
            name="chk_realism_audit_query_runs_status",
        ),
        Index(
            "uq_realism_audit_query_runs_job_query",
            "job_status_id",
            "query_name",
            unique=True,
        ),
        Index("idx_realism_audit_query_runs_job_index", "job_status_id", "query_index"),
        Index("idx_realism_audit_query_runs_status", "status"),
        Index("idx_realism_audit_query_runs_generation_run", "generation_run_id"),
        {"schema": "ops"},
    )

    id = Column(SqliteAutoincrementBigInteger, primary_key=True, autoincrement=True)
    job_status_id = Column(
        BigInteger,
        ForeignKey("job_status.id", ondelete="CASCADE"),
        nullable=False,
    )
    generation_run_id = Column(BigInteger, ForeignKey("generation_runs.id"))
    batch_id = Column(BigInteger, ForeignKey("monthly_batches.id"))
    query_index = Column(Integer, nullable=False)
    query_name = Column(String(255), nullable=False)
    status = Column(
        String(30),
        nullable=False,
        default="pending",
        server_default=text("'pending'"),
    )
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    elapsed_ms = Column(BigInteger)
    row_count = Column(BigInteger)
    result_json = Column(JSONB().with_variant(JSON(), "sqlite"))
    error_message = Column(Text)

    job_status = relationship("JobStatus")
    generation_run = relationship("GenerationRun")
    batch = relationship("MonthlyBatch")
