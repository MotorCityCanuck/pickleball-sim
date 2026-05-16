"""
PlayerAssessmentHistory model - historical player assessment metrics.
"""
from sqlalchemy import (
    BigInteger, Column, Date, Integer, String, Numeric, CheckConstraint, ForeignKey,
    DateTime
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import text

from .base import Base


class PlayerAssessmentHistory(Base):
    """
    Historical player assessment metrics.
    
    Examples:
    - Mental resilience
    - Fatigue resistance
    - Momentum sensitivity
    - Consistency
    - Aggression
    - Tournament pressure handling
    
    All assessments are time-series data with confidence scores.
    """
    __tablename__ = "player_assessment_history"
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    player_id = Column(
        BigInteger,
        ForeignKey("players.id"),
        nullable=False,
        index=True
    )
    assessment_date = Column(Date, nullable=False, index=True)
    assessment_type = Column(String(100), nullable=False)
    assessment_value = Column(Numeric(8, 3))
    confidence_score = Column(Numeric(8, 3))
    derived_from_matches = Column(Integer)
    batch_id = Column(
        BigInteger,
        ForeignKey("monthly_batches.id"),
        nullable=False,
        index=True
    )
    
    # Single timestamp column
    created_at = Column(
        DateTime,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP")
    )
    
    # Relationships
    player = relationship("Player", back_populates="assessment_history")
    batch = relationship("MonthlyBatch", back_populates="assessment_updates")
    
    # Constraints
    __table_args__ = (
        CheckConstraint(
            "confidence_score >= 0 AND confidence_score <= 1",
            name="chk_assessment_confidence"
        ),
    )
    
    def __repr__(self):
        return (
            f"<PlayerAssessmentHistory(player_id={self.player_id}, "
            f"type='{self.assessment_type}', date={self.assessment_date})>"
        )
