"""
MonthlyBatch model - Central control table for monthly simulation progression.

Each batch represents one month of simulation activity:
- Initial 12 historical months
- Future monthly increments

All generated data (matches, ratings, assessments) must link to a batch.
"""
from datetime import datetime
from sqlalchemy import (
    BigInteger, Column, String, Date, Integer, DateTime,
    ForeignKey, CheckConstraint, UniqueConstraint, Text
)
from sqlalchemy.orm import relationship

from sqlalchemy import text
from .base import Base, TimestampMixin


class MonthlyBatch(Base, TimestampMixin):
    """
    Monthly batch processing control record.
    
    Represents one month of simulation activity.
    Tracks player intake, match generation, and processing status.
    """
    
    __tablename__ = 'monthly_batches'
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    generation_run_id = Column(
        BigInteger,
        ForeignKey('generation_runs.id'),
        nullable=False
    )
    batch_month = Column(Date, nullable=False)
    batch_sequence = Column(Integer, nullable=False)
    batch_type = Column(
        String(30),
        nullable=False,
        default='future_increment',
        server_default=text('future_increment')
    )
    active_player_count_start = Column(Integer)
    new_player_count = Column(Integer)
    active_player_count_end = Column(Integer)
    match_count_generated = Column(Integer)
    rating_update_count = Column(Integer)
    assessment_update_count = Column(Integer)
    processing_status = Column(
        String(30),
        nullable=False,
        default='pending',
        server_default=text('pending')
    )
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    error_message = Column(Text)
    
    # Constraints
    __table_args__ = (
        UniqueConstraint(
            'generation_run_id',
            'batch_month',
            name='uq_batch_generation_month'
        ),
        CheckConstraint(
            batch_type.in_(['historical_initial', 'future_increment']),
            name='chk_batch_type'
        ),
        CheckConstraint(
            processing_status.in_([
                'pending', 'running', 'validating', 'exporting',
                'completed', 'failed', 'superseded'
            ]),
            name='chk_processing_status'
        ),
    )
    
    def __repr__(self) -> str:
        return (
            f"<MonthlyBatch(id={self.id}, month='{self.batch_month}', "
            f"sequence={self.batch_sequence}, status='{self.processing_status}')>"
        )
