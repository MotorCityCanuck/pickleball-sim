"""Student dataset release tracking models."""
from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    text,
)
from sqlalchemy.orm import relationship

from .base import Base, TimestampMixin


class StudentDatasetRelease(Base, TimestampMixin):
    """Operator-facing release package record for student datasets."""

    __tablename__ = "student_dataset_releases"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    release_name = Column(String(255), nullable=False)
    release_type = Column(String(50), nullable=False)
    release_month = Column(Date)
    generation_run_id = Column(
        BigInteger,
        ForeignKey("generation_runs.id"),
        nullable=False,
    )
    data_quality_level = Column(String(50))
    output_path = Column(Text, nullable=False)
    status = Column(
        String(30),
        nullable=False,
        default="pending",
        server_default=text("'pending'"),
    )
    completed_at = Column(DateTime)
    error_message = Column(Text)

    generation_run = relationship("GenerationRun")
    files = relationship(
        "StudentDatasetReleaseFile",
        back_populates="release",
    )

    __table_args__ = (
        Index("idx_student_dataset_releases_generation_run", "generation_run_id"),
        Index("idx_student_dataset_releases_status", "status"),
        CheckConstraint(
            "release_type IN ('historical_baseline', 'monthly_incremental')",
            name="chk_student_release_type",
        ),
        CheckConstraint(
            "status IN ('pending', 'running', 'succeeded', 'failed')",
            name="chk_student_release_status",
        ),
    )


class StudentDatasetReleaseFile(Base):
    """File-level output metadata for a student dataset release."""

    __tablename__ = "student_dataset_release_files"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    release_id = Column(
        BigInteger,
        ForeignKey("student_dataset_releases.id"),
        nullable=False,
    )
    table_name = Column(String(255), nullable=False)
    file_path = Column(Text, nullable=False)
    row_count = Column(BigInteger)
    schema_hash = Column(String(128))
    checksum = Column(String(128))
    created_at = Column(
        DateTime,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )

    release = relationship(
        "StudentDatasetRelease",
        back_populates="files",
    )

    __table_args__ = (
        Index("idx_student_dataset_release_files_release", "release_id"),
        Index("idx_student_dataset_release_files_table", "table_name"),
    )
