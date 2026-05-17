"""Raw pickleball club name seed data staging."""
from sqlalchemy import BigInteger, CheckConstraint, Column, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB

from .base import Base, TimestampMixin


class RawPickleballClubName(Base, TimestampMixin):
    """Stages candidate pickleball club names by country and state/province."""

    __tablename__ = "raw_pickleball_club_names"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    load_run_id = Column(BigInteger, ForeignKey("raw_seed_load_runs.id"), nullable=False)
    source_file = Column(String(500), nullable=False)
    source_row_number = Column(Integer, nullable=False)
    raw_payload = Column(JSONB, nullable=False)
    club_seed = Column(BigInteger, nullable=False)
    country_code = Column(String(2), nullable=False)
    state_province_code = Column(String(10), nullable=False)
    club_name = Column(String(255), nullable=False)
    club_type = Column(String(80))
    size_tier = Column(String(30))
    generation_method = Column(String(100))
    source_dataset = Column(String(255))

    __table_args__ = (
        UniqueConstraint("load_run_id", "club_seed", name="uq_raw_club_name_seed"),
        Index("idx_raw_club_names_load_run", "load_run_id"),
        Index("idx_raw_club_names_country_state", "country_code", "state_province_code"),
        Index("idx_raw_club_names_seed", "club_seed"),
        CheckConstraint("country_code IN ('US', 'CA')", name="chk_raw_club_names_country"),
    )
