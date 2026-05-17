"""Raw last-name seed data staging."""
from sqlalchemy import BigInteger, CheckConstraint, Column, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB

from .base import Base, TimestampMixin


class RawLastName(Base, TimestampMixin):
    """Stages country-level last-name frequency rows."""

    __tablename__ = "raw_last_names"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    load_run_id = Column(BigInteger, ForeignKey("raw_seed_load_runs.id"), nullable=False)
    source_file = Column(String(500), nullable=False)
    source_row_number = Column(Integer, nullable=False)
    raw_payload = Column(JSONB, nullable=False)
    country_code = Column(String(2), nullable=False)
    last_name = Column(String(100), nullable=False)
    frequency_count = Column(Integer, nullable=False)
    source_dataset = Column(String(255))

    __table_args__ = (
        Index("idx_raw_last_names_load_run", "load_run_id"),
        Index("idx_raw_last_names_country", "country_code"),
        Index("idx_raw_last_names_name", "last_name"),
        CheckConstraint("country_code IN ('US', 'CA')", name="chk_raw_last_names_country"),
        CheckConstraint("frequency_count > 0", name="chk_raw_last_names_freq"),
    )
