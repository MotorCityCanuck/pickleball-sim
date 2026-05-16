"""Match team players model."""
from sqlalchemy import Column, BigInteger, Integer, Numeric, ForeignKey, CheckConstraint, UniqueConstraint
from sqlalchemy.orm import relationship
from .base import Base, TimestampMixin


class MatchTeamPlayer(Base, TimestampMixin):
    """Players on match teams."""
    
    __tablename__ = 'match_team_players'
    
    id = Column(BigInteger, primary_key=True)
    match_team_id = Column(BigInteger, ForeignKey('match_teams.id'), nullable=False)
    player_id = Column(BigInteger, ForeignKey('players.id'), nullable=False)
    player_position = Column(Integer)
    player_rating_at_match = Column(Numeric(8, 3))
    
    # Relationships
    match_team = relationship("MatchTeam", back_populates="players")
    player = relationship("Player")
    
    __table_args__ = (
        CheckConstraint('player_position IN (1, 2)', name='chk_player_position'),
        UniqueConstraint('match_team_id', 'player_id', name='uq_match_team_player'),
    )