"""Raw seed data load run tracking."""
from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.orm import relationship

from .base import Base, TimestampMixin


class RawSeedLoadRun(Base, TimestampMixin):
    """Tracks one raw seed data ingestion attempt."""

    __tablename__ = "raw_seed_load_runs"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    dataset_type = Column(String(80), nullable=False)
    source_path = Column(String(1000), nullable=False)
    source_file_count = Column(Integer, nullable=False, default=0)
    source_checksum = Column(String(128))
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    status = Column(
        String(30),
        nullable=False,
        default="pending",
        server_default=text("'pending'"),
    )
    rows_read = Column(Integer, nullable=False, default=0)
    rows_loaded = Column(Integer, nullable=False, default=0)
    rows_rejected = Column(Integer, nullable=False, default=0)
    error_message = Column(Text)

    errors = relationship("RawSeedLoadError", back_populates="load_run")

    __table_args__ = (
        Index("idx_raw_seed_load_runs_dataset", "dataset_type"),
        Index("idx_raw_seed_load_runs_status", "status"),
        Index("idx_raw_seed_load_runs_started", "started_at"),
        CheckConstraint(
            "status IN ('pending', 'running', 'completed', 'failed')",
            name="chk_raw_seed_load_status",
        ),
        CheckConstraint(
            "source_file_count >= 0 AND rows_read >= 0 AND rows_loaded >= 0 AND rows_rejected >= 0",
            name="chk_raw_seed_load_counts",
        ),
    )
