"""
SQLAlchemy base model and common mixins.

Provides:
- Declarative base for all models
- Timestamp mixin for created_at/updated_at
- Common utilities
"""
from datetime import datetime
from sqlalchemy import Column, DateTime
from sqlalchemy.orm import DeclarativeBase, declared_attr


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""
    
    @declared_attr.directive
    def __tablename__(cls) -> str:
        """Generate table name from class name (snake_case)."""
        import re
        name = re.sub(r'(?<!^)(?=[A-Z])', '_', cls.__name__).lower()
        return name


class TimestampMixin:
    """Mixin to add created_at and updated_at timestamps."""
    
    created_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        server_default='CURRENT_TIMESTAMP'
    )
    
    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        server_default='CURRENT_TIMESTAMP'
    )
