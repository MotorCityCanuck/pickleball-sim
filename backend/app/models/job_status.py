"""Job status model."""
from sqlalchemy import (
    Column, BigInteger, String, Numeric, Text, DateTime, CheckConstraint, Index
)
from .base import Base, TimestampMixin


class JobStatus(Base, TimestampMixin):
    """Asynchronous job tracking."""
    
    __tablename__ = 'job_status'
    
    id = Column(BigInteger, primary_key=True)
    job_type = Column(String(50), nullable=False)
    job_id = Column(String(100), nullable=False, unique=True)
    status = Column(String(30), nullable=False, default='pending')
    current_phase = Column(String(100))
    percent_complete = Column(Numeric(5, 2))
    current_message = Column(Text)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    error_message = Column(Text)
    
    __table_args__ = (
        Index('idx_job_status_type', 'job_type'),
        Index('idx_job_status_status', 'status'),
        Index('idx_job_status_started', 'started_at'),
        CheckConstraint("status IN ('pending', 'running', 'completed', 'failed', 'cancelled')", name='chk_job_status'),
        CheckConstraint('percent_complete >= 0 AND percent_complete <= 100', name='chk_percent_complete'),
    )
