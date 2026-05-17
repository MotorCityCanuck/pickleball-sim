"""First names reference data model."""
from sqlalchemy import (
    Column, BigInteger, String, Integer, Numeric, CheckConstraint, Index
)
from .base import Base, TimestampMixin


class FirstName(Base, TimestampMixin):
    """First names by country, state/province, year, and gender."""
    
    __tablename__ = 'first_names'
    
    id = Column(BigInteger, primary_key=True)
    country_code = Column(String(2), nullable=False)
    state_province_code = Column(String(2), nullable=False)
    birth_year = Column(Integer, nullable=False)
    gender = Column(String(1), nullable=False)
    first_name = Column(String(100), nullable=False)
    frequency_count = Column(Integer, nullable=False)
    normalized_probability = Column(Numeric(12, 8))
    source_dataset = Column(String(255))
    
    __table_args__ = (
        Index(
            'idx_first_names_lookup',
            'country_code',
            'state_province_code',
            'birth_year',
            'gender'
        ),
        Index('idx_first_names_probability', 'normalized_probability'),
        Index('idx_first_names_country', 'country_code'),
        CheckConstraint("gender IN ('M', 'F')", name='chk_first_names_gender'),
        CheckConstraint('frequency_count > 0', name='chk_first_names_freq'),
        CheckConstraint("country_code IN ('US', 'CA')", name='chk_first_names_country'),
    )
