"""Player rating history model."""
from sqlalchemy import Column, BigInteger, Date, String, Numeric, Integer, ForeignKey, CheckConstraint
from sqlalchemy.orm import relationship
from .base import Base, TimestampMixin


class PlayerRatingHistory(Base, TimestampMixin):
    """Player rating history over time."""
    
    __tablename__ = 'player_rating_history'
    
    id = Column(BigInteger, primary_key=True)
    player_id = Column(BigInteger, ForeignKey('players.id'), nullable=False)
    rating_date = Column(Date, nullable=False)
    rating_type = Column(String(50), nullable=False)
    rating_value = Column(Numeric(8, 3), nullable=False)
    confidence_score = Column(Numeric(8, 3))
    volatility_score = Column(Numeric(8, 3))
    expected_performance = Column(Numeric(8, 3))
    regional_adjustment_factor = Column(Numeric(8, 4))
    global_percentile = Column(Numeric(5, 2))
    match_count_used = Column(Integer)
    calculation_version = Column(String(50))
    batch_id = Column(BigInteger, ForeignKey('monthly_batches.id'), nullable=False)
    
    # Relationships
    player = relationship("Player", back_populates="rating_history")
    batch = relationship("MonthlyBatch")
    
    __table_args__ = (
        CheckConstraint('rating_value >= 0 AND rating_value <= 5000', name='chk_rating_value'),
        CheckConstraint('confidence_score >= 0 AND confidence_score <= 1', name='chk_confidence_score'),
    )