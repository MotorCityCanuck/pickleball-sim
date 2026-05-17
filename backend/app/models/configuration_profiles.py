"""Configuration profile models for UI-managed generation settings."""
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from .base import Base, TimestampMixin


class ConfigurationProfile(Base, TimestampMixin):
    """Named editable configuration profile."""

    __tablename__ = "configuration_profiles"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    profile_name = Column(String(255), nullable=False)
    description = Column(Text)
    is_active = Column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("true"),
    )

    versions = relationship(
        "ConfigurationProfileVersion",
        back_populates="profile",
    )

    __table_args__ = (
        UniqueConstraint("profile_name", name="uq_configuration_profile_name"),
        Index("idx_configuration_profiles_active", "is_active"),
    )


class ConfigurationProfileVersion(Base, TimestampMixin):
    """Immutable versioned configuration payload for a profile."""

    __tablename__ = "configuration_profile_versions"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    profile_id = Column(
        BigInteger,
        ForeignKey("configuration_profiles.id"),
        nullable=False,
    )
    version_number = Column(Integer, nullable=False)
    config_schema_version = Column(String(50), nullable=False)
    config_payload = Column(JSONB, nullable=False)
    created_by = Column(String(255))
    validation_status = Column(
        String(30),
        nullable=False,
        default="pending",
        server_default=text("'pending'"),
    )

    profile = relationship(
        "ConfigurationProfile",
        back_populates="versions",
    )

    __table_args__ = (
        UniqueConstraint(
            "profile_id",
            "version_number",
            name="uq_configuration_profile_version",
        ),
        CheckConstraint(
            "version_number > 0",
            name="chk_configuration_version_number",
        ),
        CheckConstraint(
            "validation_status IN ('pending', 'valid', 'invalid')",
            name="chk_configuration_validation_status",
        ),
        Index("idx_configuration_versions_profile", "profile_id"),
        Index("idx_configuration_versions_schema", "config_schema_version"),
        Index("idx_configuration_versions_status", "validation_status"),
    )
