"""
Player model - core player identity and static attributes.
"""
from sqlalchemy import (
    BigInteger, Column, Date, String, Numeric, CheckConstraint, ForeignKey
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import text

from .base import Base, TimestampMixin


class Player(Base, TimestampMixin):
    """
    Core player identity table.
    
    Stores static player attributes only - no mutable ratings.
    Ratings are stored in player_rating_history.
    Age is calculated from birth_date at query time.
    """
    __tablename__ = "players"
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    external_player_key = Column(
        UUID(as_uuid=True),
        nullable=False,
        unique=True,
        server_default=text("gen_random_uuid()")
    )
    first_name = Column(String(100), nullable=False)
    last_name = Column(String(100), nullable=False)
    gender = Column(String(20))
    birth_date = Column(Date, nullable=False)
    dominant_hand = Column(String(10))
    home_region_id = Column(
        BigInteger,
        ForeignKey("regions.id"),
        index=True
    )
    registration_date = Column(Date, nullable=False)
    initial_skill_seed = Column(Numeric(8, 4))
    player_status = Column(
        String(30),
        nullable=False,
        server_default=text("'ACTIVE'")
    )
    generation_run_id = Column(
        BigInteger,
        ForeignKey("generation_runs.id"),
        index=True
    )
    
    # Relationships
    home_region = relationship("Region")
    generation_run = relationship("GenerationRun")
    rating_history = relationship(
        "PlayerRatingHistory",
        back_populates="player",
        order_by="PlayerRatingHistory.rating_date.desc()"
    )
    assessment_history = relationship(
        "PlayerAssessmentHistory",
        back_populates="player",
        order_by="PlayerAssessmentHistory.assessment_date.desc()"
    )
    registrations = relationship("PlayerRegistration")
    
    # Constraints
    __table_args__ = (
        CheckConstraint(
            "birth_date < CURRENT_DATE",
            name="chk_player_birth_date"
        ),
        CheckConstraint(
            "player_status IN ('ACTIVE', 'INACTIVE', 'RETIRED')",
            name="chk_player_status"
        ),
    )
    
    def __repr__(self):
        return (
            f"<Player(id={self.id}, name='{self.first_name} {self.last_name}', "
            f"status='{self.player_status}')>"
        )
