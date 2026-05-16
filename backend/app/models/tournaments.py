"""Tournaments model."""
from sqlalchemy import Column, BigInteger, String, Date, Integer, ForeignKey, CheckConstraint
from sqlalchemy.orm import relationship
from .base import Base, TimestampMixin


class Tournament(Base, TimestampMixin):
    """Tournament events."""
    
    __tablename__ = 'tournaments'
    
    id = Column(BigInteger, primary_key=True)
    tournament_name = Column(String(255), nullable=False)
    region_id = Column(BigInteger, ForeignKey('regions.id'))
    tournament_start_date = Column(Date, nullable=False)
    tournament_end_date = Column(Date, nullable=False)
    tournament_type = Column(String(50))
    skill_division = Column(String(50))
    participant_count = Column(Integer)
    generation_run_id = Column(BigInteger, ForeignKey('generation_runs.id'))
    
    # Relationships
    region = relationship("Region")
    generation_run = relationship("GenerationRun")
    matches = relationship("Match", back_populates="tournament")
    
    __table_args__ = (
        CheckConstraint('tournament_end_date >= tournament_start_date', name='chk_tournament_dates'),
    )
