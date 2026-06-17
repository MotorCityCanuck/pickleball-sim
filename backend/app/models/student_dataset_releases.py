"""Student dataset release tracking models."""
from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
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


class StudentDatasetComparison(Base, TimestampMixin):
    """Operator-facing history of clean-vs-tainted export comparisons."""

    __tablename__ = "student_dataset_comparisons"

    id = Column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    clean_export_path = Column(Text, nullable=False)
    tainted_export_path = Column(Text, nullable=False)
    clean_generation_run_id = Column(
        BigInteger,
        ForeignKey("generation_runs.id"),
    )
    tainted_generation_run_id = Column(
        BigInteger,
        ForeignKey("generation_runs.id"),
    )
    compared_release_count = Column(
        BigInteger,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    total_issue_count = Column(
        BigInteger,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    missing_clean_release_count = Column(
        BigInteger,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    missing_tainted_release_count = Column(
        BigInteger,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    status = Column(
        String(30),
        nullable=False,
        default="succeeded",
        server_default=text("'succeeded'"),
    )
    summary_payload = Column(Text, nullable=False)
    error_message = Column(Text)

    clean_generation_run = relationship(
        "GenerationRun",
        foreign_keys=[clean_generation_run_id],
    )
    tainted_generation_run = relationship(
        "GenerationRun",
        foreign_keys=[tainted_generation_run_id],
    )

    __table_args__ = (
        Index("idx_student_dataset_comparisons_clean_run", "clean_generation_run_id"),
        Index("idx_student_dataset_comparisons_created", "created_at"),
        Index("idx_student_dataset_comparisons_status", "status"),
        Index("idx_student_dataset_comparisons_tainted_run", "tainted_generation_run_id"),
        CheckConstraint(
            "compared_release_count >= 0 "
            "AND total_issue_count >= 0 "
            "AND missing_clean_release_count >= 0 "
            "AND missing_tainted_release_count >= 0",
            name="chk_student_dataset_comparison_counts",
        ),
        CheckConstraint(
            "status IN ('succeeded', 'failed')",
            name="chk_student_dataset_comparison_status",
        ),
    )
