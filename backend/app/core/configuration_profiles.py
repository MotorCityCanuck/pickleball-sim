"""Configuration profile loading and seeding helpers."""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ConfigurationProfile, ConfigurationProfileVersion

from .default_configuration import (
    DEFAULT_CONFIG_CREATED_BY,
    DEFAULT_CONFIG_PAYLOAD,
    DEFAULT_CONFIG_PROFILE_NAME,
    DEFAULT_CONFIG_SCHEMA_VERSION,
    DEFAULT_CONFIG_VERSION_NUMBER,
)


def get_configuration_payload(
    session: Session,
    *,
    profile_name: str = DEFAULT_CONFIG_PROFILE_NAME,
    version_number: int | None = None,
) -> dict[str, Any]:
    """Load a configuration payload by profile and optional version."""
    statement = (
        select(ConfigurationProfileVersion)
        .join(ConfigurationProfile)
        .where(
            ConfigurationProfile.profile_name == profile_name,
            ConfigurationProfile.is_active.is_(True),
            ConfigurationProfileVersion.lifecycle_status == "valid",
        )
        .order_by(ConfigurationProfileVersion.version_number.desc())
    )
    if version_number is not None:
        statement = statement.where(
            ConfigurationProfileVersion.version_number == version_number
        )

    profile_version = session.scalars(statement).first()
    if profile_version is None:
        version_label = "latest" if version_number is None else str(version_number)
        raise ValueError(
            "No valid configuration profile version found for "
            f"profile={profile_name!r}, version={version_label}."
        )

    return deepcopy(profile_version.config_payload)


def upsert_default_configuration_profile(session: Session) -> ConfigurationProfileVersion:
    """Create the current default configuration profile version if absent."""
    profile = session.scalar(
        select(ConfigurationProfile).where(
            ConfigurationProfile.profile_name == DEFAULT_CONFIG_PROFILE_NAME
        )
    )
    if profile is None:
        profile = ConfigurationProfile(
            profile_name=DEFAULT_CONFIG_PROFILE_NAME,
            description="Default generation configuration profile.",
            is_active=True,
        )
        session.add(profile)
        session.flush()

    profile_version = session.scalar(
        select(ConfigurationProfileVersion).where(
            ConfigurationProfileVersion.profile_id == profile.id,
            ConfigurationProfileVersion.version_number == DEFAULT_CONFIG_VERSION_NUMBER,
        )
    )
    if profile_version is None:
        profile_version = ConfigurationProfileVersion(
            profile_id=profile.id,
            version_number=DEFAULT_CONFIG_VERSION_NUMBER,
            title="Default configuration",
            notes="Seeded default generation configuration.",
            config_schema_version=DEFAULT_CONFIG_SCHEMA_VERSION,
            config_hash=_config_hash(DEFAULT_CONFIG_PAYLOAD),
            config_payload=deepcopy(DEFAULT_CONFIG_PAYLOAD),
            created_by=DEFAULT_CONFIG_CREATED_BY,
            lifecycle_status="valid",
        )
        session.add(profile_version)
        session.flush()
    else:
        profile_version.title = profile_version.title or "Default configuration"
        profile_version.notes = profile_version.notes or "Seeded default generation configuration."
        profile_version.config_hash = profile_version.config_hash or _config_hash(
            profile_version.config_payload
        )
    if profile_version.lifecycle_status != "valid":
        profile_version.lifecycle_status = "valid"
    session.flush()

    return profile_version


def _config_hash(payload: dict[str, Any]) -> str:
    """Return a stable hash for a configuration payload."""
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return sha256(encoded).hexdigest()
