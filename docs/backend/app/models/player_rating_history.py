"""
PlayerRatingHistory model - time-series player rating data.
"""
from sqlalchemy import (
    BigInteger, Column, Date, Integer, String, Numeric, CheckConstraint, ForeignKey
)
from sqlalchemy.orm import relationship

from .base import Base


class PlayerRatingHistory(Base):
    """
    Historical rating records with effective dates.
    
    Supports:
    - Time-series analytics
    - Rating evolution tracking
    - Confidence modeling
    - Point-in-time rating queries
    
    Critical: Never update historical records in place.
    All corrections must append new records.
    """
    __tablename__ = "player_rating_history"
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    player_id = Column(
        BigInteger,
        ForeignKey("players.id"),
        nullable=False,
        index=True
    )
    rating_date = Column(Date, nullable=False, index=True)
    rating_type = Column(String(50), nullable=False)
    rating_value = Column(Numeric(8, 3), nullable=False)
    confidence_score = Column(Numeric(8, 3))
    volatility_score = Column(Numeric(8, 3))
    expected_performance = Column(Numeric(8, 3))
    regional_adjustment_factor = Column(Numeric(8, 4))
    global_percentile = Column(Numeric(5, 2))
    match_count_used = Column(Integer)
    calculation_version = Column(String(50))
    batch_id = Column(
        BigInteger,
        ForeignKey("monthly_batches.id"),
        nullable=False,
        index=True
    )
    
    # No created_at/updated_at from TimestampMixin - using custom created_at only
    from sqlalchemy import DateTime
    from sqlalchemy.sql import text
    created_at = Column(
        DateTime,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP")
    )
    
    # Relationships
    player = relationship("Player", back_populates="rating_history")
    batch = relationship("MonthlyBatch", back_populates="rating_updates")
    
    # Constraints
    __table_args__ = (
        CheckConstraint(
            "rating_value >= 0 AND rating_value <= 5000",
            name="chk_rating_value"
        ),
        CheckConstraint(
            "confidence_score >= 0 AND confidence_score <= 1",
            name="chk_confidence_score"
        ),
    )
    
    def __repr__(self):
        return (
            f"<PlayerRatingHistory(player_id={self.player_id}, "
            f"date={self.rating_date}, rating={self.rating_value})>"
        )
