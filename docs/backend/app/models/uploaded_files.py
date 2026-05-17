"""Uploaded files model."""
from sqlalchemy import Column, BigInteger, String, DateTime, CheckConstraint, Index, text
from .base import Base, TimestampMixin


class UploadedFile(Base, TimestampMixin):
    """Tracking for uploaded files."""
    
    __tablename__ = 'uploaded_files'
    
    id = Column(BigInteger, primary_key=True)
    original_filename = Column(String(255), nullable=False)
    stored_filename = Column(String(255), nullable=False)
    file_type = Column(String(50))
    file_size_bytes = Column(BigInteger)
    upload_timestamp = Column(DateTime, nullable=False, server_default=text('CURRENT_TIMESTAMP'))
    validation_status = Column(String(30))
    
    __table_args__ = (
        Index('idx_uploaded_files_timestamp', 'upload_timestamp'),
        Index('idx_uploaded_files_status', 'validation_status'),
        CheckConstraint('file_size_bytes >= 0', name='chk_file_size'),
    )
