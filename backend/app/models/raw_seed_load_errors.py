"""Raw seed data load error tracking."""
from sqlalchemy import BigInteger, Column, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from .base import Base, TimestampMixin


class RawSeedLoadError(Base, TimestampMixin):
    """Stores row-level and file-level raw seed ingestion errors."""

    __tablename__ = "raw_seed_load_errors"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    load_run_id = Column(
        BigInteger,
        ForeignKey("raw_seed_load_runs.id"),
        nullable=False,
    )
    source_file = Column(String(500), nullable=False)
    source_row_number = Column(Integer)
    error_code = Column(String(80), nullable=False)
    error_message = Column(Text, nullable=False)
    raw_payload = Column(JSONB)

    load_run = relationship("RawSeedLoadRun", back_populates="errors")

    __table_args__ = (
        Index("idx_raw_seed_load_errors_load_run", "load_run_id"),
        Index("idx_raw_seed_load_errors_code", "error_code"),
    )
