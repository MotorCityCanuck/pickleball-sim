"""Matches model."""
from sqlalchemy import Column, BigInteger, String, Date, Integer, Numeric, ForeignKey, CheckConstraint
from sqlalchemy.orm import relationship
from .base import Base, TimestampMixin


class Match(Base, TimestampMixin):
    """Individual matches."""
    
    __tablename__ = 'matches'
    
    id = Column(BigInteger, primary_key=True)
    tournament_id = Column(BigInteger, ForeignKey('tournaments.id'))
    match_date = Column(Date, nullable=False)
    region_id = Column(BigInteger, ForeignKey('regions.id'))
    match_type = Column(String(50), nullable=False)
    court_type = Column(String(50))
    match_format = Column(String(50))
    winning_team_id = Column(BigInteger)
    total_points_played = Column(Integer)
    expected_competitiveness = Column(Numeric(8, 3))
    simulation_noise_factor = Column(Numeric(8, 3))
    batch_id = Column(BigInteger, ForeignKey('monthly_batches.id'), nullable=False)
    
    # Relationships
    tournament = relationship("Tournament", back_populates="matches")
    region = relationship("Region")
    batch = relationship("MonthlyBatch")
    match_teams = relationship("MatchTeam", back_populates="match")
    
    __table_args__ = (
        CheckConstraint(
            "match_type IN ('recreational', 'league', 'ladder', 'tournament', 'challenge', 'clinic', 'open_play')",
            name='chk_match_type'
        ),
    )
