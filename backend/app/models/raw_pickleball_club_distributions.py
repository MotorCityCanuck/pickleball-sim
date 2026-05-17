"""Raw pickleball club distribution seed data staging."""
from sqlalchemy import BigInteger, CheckConstraint, Column, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB

from .base import Base, TimestampMixin


class RawPickleballClubDistribution(Base, TimestampMixin):
    """Stages target pickleball club counts by state/province."""

    __tablename__ = "raw_pickleball_club_distributions"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    load_run_id = Column(BigInteger, ForeignKey("raw_seed_load_runs.id"), nullable=False)
    source_file = Column(String(500), nullable=False)
    source_row_number = Column(Integer, nullable=False)
    raw_payload = Column(JSONB, nullable=False)
    country_code = Column(String(2), nullable=False)
    state_province_code = Column(String(10), nullable=False)
    state_province_name = Column(String(255), nullable=False)
    target_club_count = Column(Integer, nullable=False)
    source_dataset = Column(String(255))

    __table_args__ = (
        UniqueConstraint(
            "load_run_id",
            "country_code",
            "state_province_code",
            name="uq_raw_club_distribution_state",
        ),
        Index("idx_raw_club_distributions_load_run", "load_run_id"),
        Index("idx_raw_club_distributions_country_state", "country_code", "state_province_code"),
        CheckConstraint("country_code IN ('US', 'CA')", name="chk_raw_club_dist_country"),
        CheckConstraint("target_club_count >= 0", name="chk_raw_club_dist_count"),
    )
