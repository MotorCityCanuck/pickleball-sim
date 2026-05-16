"""Team memberships model."""
from sqlalchemy import Column, BigInteger, Integer, Date, ForeignKey, CheckConstraint, UniqueConstraint
from sqlalchemy.orm import relationship
from .base import Base, TimestampMixin


class TeamMembership(Base, TimestampMixin):
    """Player memberships on teams."""
    
    __tablename__ = 'team_memberships'
    
    id = Column(BigInteger, primary_key=True)
    team_id = Column(BigInteger, ForeignKey('teams.id'), nullable=False)
    player_id = Column(BigInteger, ForeignKey('players.id'), nullable=False)
    player_position = Column(Integer, nullable=False)
    joined_date = Column(Date, nullable=False)
    left_date = Column(Date)
    
    # Relationships
    team = relationship("Team", back_populates="memberships")
    player = relationship("Player", back_populates="team_memberships")
    
    __table_args__ = (
        CheckConstraint('player_position IN (1, 2)', name='chk_position'),
        CheckConstraint('left_date IS NULL OR left_date >= joined_date', name='chk_membership_dates'),
        UniqueConstraint('team_id', 'player_id', 'joined_date', name='uq_team_player_joined'),
    )