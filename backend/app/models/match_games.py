"""Match games model."""
from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import relationship

from .base import Base, TimestampMixin


class MatchGame(Base, TimestampMixin):
    """Individual games within a match."""

    __tablename__ = 'match_games'

    id = Column(BigInteger, primary_key=True)
    match_id = Column(BigInteger, ForeignKey('matches.id'), nullable=False)
    game_number = Column(Integer, nullable=False)
    team_one_score = Column(Integer, nullable=False)
    team_two_score = Column(Integer, nullable=False)
    winning_team_number = Column(Integer, nullable=False)
    target_score = Column(
        Integer,
        nullable=False,
        default=11,
        server_default=text("11"),
    )
    win_by = Column(
        Integer,
        nullable=False,
        default=2,
        server_default=text("2"),
    )
    expected_team_one_score_share = Column(Numeric(8, 4))
    actual_team_one_score_share = Column(Numeric(8, 4))
    score_noise_factor = Column(Numeric(8, 3))

    # Relationships
    match = relationship("Match", back_populates="games")

    __table_args__ = (
        UniqueConstraint('match_id', 'game_number', name='uq_match_game_number'),
        Index('idx_match_games_match', 'match_id'),
        Index('idx_match_games_winner', 'winning_team_number'),
        CheckConstraint('game_number >= 1', name='chk_game_number'),
        CheckConstraint(
            'team_one_score >= 0 AND team_two_score >= 0',
            name='chk_game_scores_nonnegative',
        ),
        CheckConstraint(
            'winning_team_number IN (1, 2)',
            name='chk_game_winning_team',
        ),
        CheckConstraint(
            'target_score IN (11, 15, 21)',
            name='chk_game_target_score',
        ),
        CheckConstraint('win_by >= 1', name='chk_game_win_by'),
    )
