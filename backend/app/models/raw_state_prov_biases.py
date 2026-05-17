"""Raw state/province last-name bias seed data staging."""
from sqlalchemy import BigInteger, CheckConstraint, Column, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB

from .base import Base, TimestampMixin


class RawStateProvBias(Base, TimestampMixin):
    """Stages state/province surname bias rules."""

    __tablename__ = "raw_state_prov_biases"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    load_run_id = Column(BigInteger, ForeignKey("raw_seed_load_runs.id"), nullable=False)
    source_file = Column(String(500), nullable=False)
    source_row_number = Column(Integer, nullable=False)
    raw_payload = Column(JSONB, nullable=False)
    country_code = Column(String(2), nullable=False)
    state_province_code = Column(String(10), nullable=False)
    last_name = Column(String(100), nullable=False)
    bias_multiplier = Column(Numeric(10, 4), nullable=False)
    bias_reason = Column(Text)
    source_dataset = Column(String(255))

    __table_args__ = (
        Index("idx_raw_state_prov_biases_load_run", "load_run_id"),
        Index(
            "idx_raw_state_prov_biases_lookup",
            "country_code",
            "state_province_code",
            "last_name",
        ),
        Index("idx_raw_state_prov_biases_country_state", "country_code", "state_province_code"),
        CheckConstraint("country_code IN ('US', 'CA')", name="chk_raw_state_bias_country"),
        CheckConstraint("bias_multiplier > 0", name="chk_raw_state_bias_multiplier"),
    )
