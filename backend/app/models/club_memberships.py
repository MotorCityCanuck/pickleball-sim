"""Club memberships model."""
from sqlalchemy import Column, BigInteger, String, Date, Boolean, ForeignKey, CheckConstraint
from sqlalchemy.orm import relationship
from .base import Base, TimestampMixin


class ClubMembership(Base, TimestampMixin):
    """Player memberships at clubs."""
    
    __tablename__ = 'club_memberships'
    
    id = Column(BigInteger, primary_key=True)
    player_id = Column(BigInteger, ForeignKey('players.id'), nullable=False)
    club_id = Column(BigInteger, ForeignKey('clubs.id'), nullable=False)
    membership_type = Column(String(50), default='member')
    start_date = Column(Date, nullable=False)
    end_date = Column(Date)
    is_primary = Column(Boolean, default=True)
    generation_run_id = Column(BigInteger, ForeignKey('generation_runs.id'))
    
    # Relationships
    player = relationship("Player", back_populates="club_memberships")
    club = relationship("Club", back_populates="memberships")
    generation_run = relationship("GenerationRun")
    
    __table_args__ = (
        CheckConstraint('end_date IS NULL OR end_date >= start_date', name='chk_membership_dates'),
    )