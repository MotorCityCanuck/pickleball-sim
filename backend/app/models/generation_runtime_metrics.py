"""Operational runtime metrics for generation stages."""
from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    JSON,
    String,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from .base import Base, TimestampMixin


class GenerationRuntimeMetric(Base, TimestampMixin):
    """Subphase timing and count metrics for long-running generation work."""

    __tablename__ = "generation_runtime_metrics"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    generation_run_id = Column(
        BigInteger,
        ForeignKey("generation_runs.id"),
        nullable=False,
    )
    job_status_id = Column(BigInteger, ForeignKey("job_status.id"))
    batch_id = Column(BigInteger, ForeignKey("monthly_batches.id"))
    stage_name = Column(String(100), nullable=False)
    subphase_name = Column(String(100), nullable=False)
    event_type = Column(String(30), nullable=False)
    started_at = Column(DateTime, nullable=False)
    completed_at = Column(DateTime, nullable=False)
    elapsed_ms = Column(BigInteger, nullable=False)
    input_count = Column(BigInteger)
    output_count = Column(BigInteger)
    attempt_count = Column(BigInteger)
    metadata_json = Column(JSONB().with_variant(JSON(), "sqlite"))

    generation_run = relationship("GenerationRun")
    job_status = relationship("JobStatus")
    batch = relationship("MonthlyBatch")

    __table_args__ = (
        Index("idx_generation_runtime_metrics_run", "generation_run_id"),
        Index("idx_generation_runtime_metrics_job", "job_status_id"),
        Index("idx_generation_runtime_metrics_batch", "batch_id"),
        Index("idx_generation_runtime_metrics_stage", "stage_name"),
        Index("idx_generation_runtime_metrics_subphase", "subphase_name"),
        Index("idx_generation_runtime_metrics_event", "event_type"),
        CheckConstraint(
            "event_type IN ('completed', 'failed')",
            name="chk_generation_runtime_metric_event_type",
        ),
        CheckConstraint(
            "elapsed_ms >= 0",
            name="chk_generation_runtime_metric_elapsed",
        ),
    )
