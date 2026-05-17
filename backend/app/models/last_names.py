"""Last names reference data model."""
from sqlalchemy import (
    Column, BigInteger, String, Integer, Numeric, CheckConstraint, Index
)
from .base import Base, TimestampMixin


class LastName(Base, TimestampMixin):
    """Last names by country and state/province."""
    
    __tablename__ = 'last_names'
    
    id = Column(BigInteger, primary_key=True)
    country_code = Column(String(2), nullable=False)
    state_province_code = Column(String(2), nullable=False)
    last_name = Column(String(100), nullable=False)
    frequency_count = Column(Integer, nullable=False)
    bias_multiplier = Column(Numeric(10, 4))
    adjusted_frequency_count = Column(Numeric(18, 4))
    normalized_probability = Column(Numeric(12, 8))
    source_dataset = Column(String(255))
    
    __table_args__ = (
        Index('idx_last_names_lookup', 'country_code', 'state_province_code'),
        Index('idx_last_names_country', 'country_code'),
        CheckConstraint('frequency_count > 0', name='chk_last_names_freq'),
        CheckConstraint("country_code IN ('US', 'CA')", name='chk_last_names_country'),
    )
