"""Export runs model."""
from sqlalchemy import Column, BigInteger, String, Text, ForeignKey, CheckConstraint
from sqlalchemy.orm import relationship
from .base import Base, TimestampMixin


class ExportRun(Base, TimestampMixin):
    """Tracking for data exports."""
    
    __tablename__ = 'export_runs'
    
    id = Column(BigInteger, primary_key=True)
    batch_id = Column(BigInteger, ForeignKey('monthly_batches.id'))
    export_type = Column(String(50), nullable=False)
    export_format = Column(String(50), nullable=False)
    export_path = Column(Text, nullable=False)
    partition_strategy = Column(String(100))
    row_count = Column(BigInteger)
    schema_hash = Column(String(64))
    checksum = Column(String(64))
    
    # Relationships
    batch = relationship("MonthlyBatch")
    
    __table_args__ = (
        CheckConstraint("export_format IN ('parquet', 'csv', 'json', 'sql')", name='chk_export_format'),
    )