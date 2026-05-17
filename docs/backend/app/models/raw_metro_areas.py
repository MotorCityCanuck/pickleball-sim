"""Raw metro area seed data staging."""
from sqlalchemy import BigInteger, CheckConstraint, Column, ForeignKey, Index, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import JSONB

from .base import Base, TimestampMixin


class RawMetroArea(Base, TimestampMixin):
    """Stages raw USA and Canada metro area source rows."""

    __tablename__ = "raw_metro_areas"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    load_run_id = Column(BigInteger, ForeignKey("raw_seed_load_runs.id"), nullable=False)
    source_file = Column(String(500), nullable=False)
    source_row_number = Column(Integer, nullable=False)
    raw_payload = Column(JSONB, nullable=False)
    country_code = Column(String(2), nullable=False)
    state_province_code = Column(String(10), nullable=False)
    metro_area_name = Column(String(255), nullable=False)
    population = Column(BigInteger, nullable=False)
    selection_probability = Column(Numeric(12, 8), nullable=False)
    source_dataset = Column(String(255))

    __table_args__ = (
        Index("idx_raw_metro_areas_load_run", "load_run_id"),
        Index("idx_raw_metro_areas_country_state", "country_code", "state_province_code"),
        Index("idx_raw_metro_areas_probability", "selection_probability"),
        CheckConstraint("country_code IN ('US', 'CA')", name="chk_raw_metro_country"),
        CheckConstraint("population > 0", name="chk_raw_metro_population"),
        CheckConstraint(
            "selection_probability >= 0",
            name="chk_raw_metro_probability",
        ),
    )
