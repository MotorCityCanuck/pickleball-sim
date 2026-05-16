"""
Region model - Stores MSA/CMA/CA regional definitions.

Supports:
- Regional player allocation
- Population-based distribution
- Competitiveness multipliers
- Geographic coordinates
"""
from sqlalchemy import (
    BigInteger, Column, String, Numeric, UniqueConstraint
)
from sqlalchemy.orm import relationship

from .base import Base, TimestampMixin


class Region(Base, TimestampMixin):
    """
    Regional definition for player allocation.
    
    Represents Metropolitan Statistical Areas (MSA) in USA,
    Census Metropolitan Areas (CMA) in Canada, or
    Census Agglomerations (CA) in Canada.
    """
    
    __tablename__ = 'regions'
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    country_code = Column(String(10), nullable=False)
    region_type = Column(String(20))  # MSA, CMA, CA
    region_name = Column(String(255), nullable=False)
    state_province_code = Column(String(10))
    population = Column(BigInteger)
    competitiveness_multiplier = Column(
        Numeric(8, 4),
        default=1.0,
        server_default='1.0'
    )
    latitude = Column(Numeric(10, 6))
    longitude = Column(Numeric(10, 6))
    
    # Relationships
    players = relationship(
        'Player',
        back_populates='home_region',
        foreign_keys='Player.home_region_id'
    )
    clubs = relationship(
        'Club',
        back_populates='region'
    )
    matches = relationship(
        'Match',
        back_populates='region'
    )
    tournaments = relationship(
        'Tournament',
        back_populates='region'
    )
    
    # Constraints
    __table_args__ = (
        UniqueConstraint(
            'country_code',
            'region_name',
            name='uq_region_country_name'
        ),
    )
    
    def __repr__(self) -> str:
        return f"<Region(id={self.id}, name='{self.region_name}', country='{self.country_code}')>"
