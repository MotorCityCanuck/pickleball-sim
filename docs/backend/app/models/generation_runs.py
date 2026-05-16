"""
GenerationRun model - Represents a complete simulation scenario.

A generation run creates the initial controlled environment and
serves as the parent for all monthly batches.
"""
from datetime import datetime
from sqlalchemy import (
    BigInteger, Column, String, DateTime, CheckConstraint, Text
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from .base import Base, TimestampMixin


class GenerationRun(Base, TimestampMixin):
    """
    Represents a complete simulation scenario.
    
    A generation run defines:
    - Master seed for reproducibility
    - Parameter snapshot (configuration)
    - Overall execution status
    - Parent container for monthly batches
    """
    
    __tablename__ = 'generation_runs'
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    generation_name = Column(String(255), nullable=False)
    seed_value = Column(BigInteger, nullable=False)
    simulation_version = Column(String(100))
    parameter_snapshot = Column(JSONB)  # Full configuration as JSON
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    status = Column(
        String(30),
        nullable=False,
        default='pending',
        server_default='pending'
    )
    
    # Relationships
    monthly_batches = relationship(
        'MonthlyBatch',
        back_populates='generation_run',
        cascade='all, delete-orphan'
    )
    players = relationship(
        'Player',
        back_populates='generation_run'
    )
    clubs = relationship(
        'Club',
        back_populates='generation_run'
    )
    
    # Constraints
    __table_args__ = (
        CheckConstraint(
            status.in_(['pending', 'running', 'completed', 'failed', 'cancelled']),
            name='chk_generation_status'
        ),
    )
    
    def __repr__(self) -> str:
        return f"<GenerationRun(id={self.id}, name='{self.generation_name}', status='{self.status}')>"
