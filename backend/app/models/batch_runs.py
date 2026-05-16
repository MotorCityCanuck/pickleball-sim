"""Batch runs model."""
from sqlalchemy import Column, BigInteger, String, DateTime, Text, ForeignKey, CheckConstraint
from sqlalchemy.orm import relationship
from .base import Base, TimestampMixin


class BatchRun(Base, TimestampMixin):
    """Execution tracking for batch processing."""
    
    __tablename__ = 'batch_runs'
    
    id = Column(BigInteger, primary_key=True)
    batch_id = Column(BigInteger, ForeignKey('monthly_batches.id'), nullable=False)
    run_status = Column(String(30), nullable=False, default='pending')
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    error_message = Column(Text)
    
    # Relationships
    batch = relationship("MonthlyBatch")
    
    __table_args__ = (
        CheckConstraint("run_status IN ('pending', 'running', 'completed', 'failed')", name='chk_run_status'),
    )