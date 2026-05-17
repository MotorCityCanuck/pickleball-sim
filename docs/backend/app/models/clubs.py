"""Clubs model."""
from sqlalchemy import (
    Column, BigInteger, String, Integer, Date, ForeignKey, CheckConstraint,
    Index, UniqueConstraint
)
from sqlalchemy.orm import relationship
from .base import Base, TimestampMixin


class Club(Base, TimestampMixin):
    """Pickleball clubs and facilities."""
    
    __tablename__ = 'clubs'
    
    id = Column(BigInteger, primary_key=True)
    club_name = Column(String(255), nullable=False)
    region_id = Column(BigInteger, ForeignKey('regions.id'), nullable=False)
    club_type = Column(String(50))
    competitiveness_level = Column(String(50))
    member_capacity = Column(Integer)
    founding_date = Column(Date)
    indoor_court_count = Column(Integer, default=0)
    outdoor_court_count = Column(Integer, default=0)
    generation_run_id = Column(BigInteger, ForeignKey('generation_runs.id'))
    
    # Relationships
    region = relationship("Region")
    generation_run = relationship("GenerationRun")
    memberships = relationship("ClubMembership", back_populates="club")
    
    __table_args__ = (
        UniqueConstraint('region_id', 'club_name', name='uq_club_region_name'),
        Index('idx_clubs_region', 'region_id'),
        Index('idx_clubs_type', 'club_type'),
        Index('idx_clubs_generation_run', 'generation_run_id'),
        CheckConstraint(
            "club_type IN ('public_park', 'private_club', 'community_center', 'resort', 'university', 'municipal_recreation', 'dedicated_facility')",
            name='chk_club_type'
        ),
        CheckConstraint('indoor_court_count >= 0 AND outdoor_court_count >= 0', name='chk_court_counts'),
    )
