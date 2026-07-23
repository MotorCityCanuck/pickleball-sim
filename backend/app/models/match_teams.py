"""Match teams model."""
from sqlalchemy import (
    Column, BigInteger, Integer, Numeric, String, ForeignKey, CheckConstraint, Index,
    UniqueConstraint
)
from sqlalchemy.orm import relationship
from .base import Base, TimestampMixin


class MatchTeam(Base, TimestampMixin):
    """Teams participating in a match."""
    
    __tablename__ = 'match_teams'
    
    id = Column(BigInteger, primary_key=True)
    match_id = Column(BigInteger, ForeignKey('matches.id'), nullable=False)
    team_number = Column(Integer, nullable=False)
    team_score = Column(Integer, nullable=False)
    expected_win_probability = Column(Numeric(8, 4))
    average_team_rating = Column(Numeric(8, 3))
    pairing_source = Column(String(30))
    source_team_id = Column(BigInteger, ForeignKey('teams.id'), nullable=False)
    
    # Relationships
    match = relationship("Match", back_populates="match_teams")
    players = relationship("MatchTeamPlayer", back_populates="match_team")
    source_team = relationship("Team")
    
    __table_args__ = (
        Index('idx_match_teams_match', 'match_id'),
        CheckConstraint('team_number IN (1, 2)', name='chk_team_number'),
        CheckConstraint(
            "pairing_source IS NULL OR pairing_source IN ('competitive_team', 'ad_hoc')",
            name='chk_match_team_pairing_source',
        ),
        UniqueConstraint('match_id', 'team_number', name='uq_match_team_number'),
    )
