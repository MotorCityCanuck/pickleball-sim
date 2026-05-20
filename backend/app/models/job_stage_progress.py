"""Per-stage progress tracking for long-running jobs."""
from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from .base import Base, TimestampMixin


class JobStageProgress(Base, TimestampMixin):
    """Durable per-stage progress state for polling UIs."""

    __tablename__ = "job_stage_progress"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    job_status_id = Column(
        BigInteger,
        ForeignKey("job_status.id"),
        nullable=False,
    )
    generation_run_id = Column(BigInteger, ForeignKey("generation_runs.id"))
    batch_id = Column(BigInteger, ForeignKey("monthly_batches.id"))
    stage_name = Column(String(100), nullable=False)
    stage_sequence = Column(BigInteger)
    status = Column(
        String(30),
        nullable=False,
        default="pending",
        server_default=text("'pending'"),
    )
    progress_current = Column(BigInteger, nullable=False, default=0, server_default=text("0"))
    progress_total = Column(BigInteger)
    progress_unit = Column(String(100))
    progress_percent = Column(Numeric(5, 2))
    last_heartbeat_at = Column(DateTime)
    progress_message = Column(Text)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    error_message = Column(Text)
    metadata_json = Column(JSONB)

    job_status = relationship("JobStatus")
    generation_run = relationship("GenerationRun")
    batch = relationship("MonthlyBatch")

    __table_args__ = (
        UniqueConstraint(
            "job_status_id",
            "batch_id",
            "stage_name",
            name="uq_job_stage_progress_stage",
        ),
        Index("idx_job_stage_progress_job", "job_status_id"),
        Index("idx_job_stage_progress_generation_run", "generation_run_id"),
        Index("idx_job_stage_progress_batch", "batch_id"),
        Index("idx_job_stage_progress_status", "status"),
        Index("idx_job_stage_progress_heartbeat", "last_heartbeat_at"),
        CheckConstraint(
            "status IN ('pending', 'running', 'succeeded', 'failed')",
            name="chk_job_stage_progress_status",
        ),
        CheckConstraint(
            "progress_percent IS NULL OR (progress_percent >= 0 AND progress_percent <= 100)",
            name="chk_job_stage_progress_percent",
        ),
    )
