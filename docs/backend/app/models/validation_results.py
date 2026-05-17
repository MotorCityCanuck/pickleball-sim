"""Validation results model."""
from sqlalchemy import (
    Column, BigInteger, String, Text, ForeignKey, CheckConstraint, Index
)
from sqlalchemy.orm import relationship
from .base import Base, TimestampMixin


class ValidationResult(Base, TimestampMixin):
    """Data validation tracking."""
    
    __tablename__ = 'validation_results'
    
    id = Column(BigInteger, primary_key=True)
    batch_id = Column(BigInteger, ForeignKey('monthly_batches.id'))
    validation_rule_id = Column(String(100), nullable=False)
    validation_rule_name = Column(String(255), nullable=False)
    severity = Column(String(30), nullable=False)
    entity_type = Column(String(100))
    entity_id = Column(BigInteger)
    field_name = Column(String(100))
    observed_value = Column(Text)
    expected_value = Column(Text)
    validation_message = Column(Text)
    
    # Relationships
    batch = relationship("MonthlyBatch")
    
    __table_args__ = (
        Index('idx_validation_results_batch', 'batch_id'),
        Index('idx_validation_results_severity', 'severity'),
        Index('idx_validation_results_rule', 'validation_rule_id'),
        CheckConstraint("severity IN ('info', 'warning', 'error', 'blocker')", name='chk_severity'),
    )
