"""Raw first-name seed data staging."""
from sqlalchemy import BigInteger, CheckConstraint, Column, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB

from .base import Base, TimestampMixin


class RawFirstName(Base, TimestampMixin):
    """Stages first-name frequency rows by country, state/province, year, and gender."""

    __tablename__ = "raw_first_names"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    load_run_id = Column(BigInteger, ForeignKey("raw_seed_load_runs.id"), nullable=False)
    source_file = Column(String(500), nullable=False)
    source_row_number = Column(Integer, nullable=False)
    raw_payload = Column(JSONB, nullable=False)
    country_code = Column(String(2), nullable=False)
    state_province_code = Column(String(10), nullable=False)
    gender = Column(String(1), nullable=False)
    birth_year = Column(Integer, nullable=False)
    first_name = Column(String(100), nullable=False)
    frequency_count = Column(Integer, nullable=False)
    source_dataset = Column(String(255))

    __table_args__ = (
        Index("idx_raw_first_names_load_run", "load_run_id"),
        Index(
            "idx_raw_first_names_lookup",
            "country_code",
            "state_province_code",
            "birth_year",
            "gender",
        ),
        CheckConstraint("country_code IN ('US', 'CA')", name="chk_raw_first_names_country"),
        CheckConstraint("gender IN ('M', 'F')", name="chk_raw_first_names_gender"),
        CheckConstraint("frequency_count > 0", name="chk_raw_first_names_freq"),
    )
