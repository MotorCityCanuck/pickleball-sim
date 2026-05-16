"""
PlayerRegistration model - tracks player intake by monthly batch.
"""
from sqlalchemy import (
    BigInteger, Column, Date, String, Numeric, ForeignKey, UniqueConstraint,
    DateTime
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import text

from .base import Base


class PlayerRegistration(Base):
    """
    Player registration records tracking when players were introduced.
    
    Links players to the monthly batch that added them to the system.
    Used for:
    - New player growth tracking
    - Batch-level player intake validation
    - Registration source tracking (synthetic vs uploaded)
    """
    __tablename__ = "player_registrations"
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    player_id = Column(
        BigInteger,
        ForeignKey("players.id"),
        nullable=False,
        index=True
    )
    batch_id = Column(
        BigInteger,
        ForeignKey("monthly_batches.id"),
        nullable=False,
        index=True
    )
    registration_month = Column(Date, nullable=False, index=True)
    registration_source = Column(
        String(50),
        nullable=False,
        server_default=text("'synthetic'")
    )
    assigned_region_id = Column(
        BigInteger,
        ForeignKey("regions.id")
    )
    initial_rating_value = Column(Numeric(8, 3))
    initial_confidence_score = Column(Numeric(8, 3))
    created_at = Column(
        DateTime,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP")
    )
    
    # Relationships
    player = relationship("Player", back_populates="registrations")
    batch = relationship("MonthlyBatch", back_populates="player_registrations")
    assigned_region = relationship("Region")
    
    # Constraints
    __table_args__ = (
        UniqueConstraint("player_id", "batch_id", name="uq_player_batch"),
    )
    
    def __repr__(self):
        return (
            f"<PlayerRegistration(player_id={self.player_id}, "
            f"batch_id={self.batch_id}, month={self.registration_month})>"
        )
