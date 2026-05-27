"""Configuration lifecycle service for validated immutable config versions."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
import json
from typing import Any, Mapping

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import ConfigurationProfile, ConfigurationProfileVersion

from .config import SimulationSettings, settings_from_payload
from .default_configuration import DEFAULT_CONFIG_PROFILE_NAME, DEFAULT_CONFIG_SCHEMA_VERSION
from .live_config_validation import ConfigValidationIssue, validate_live_config_payload


def compute_config_hash(payload: Mapping[str, Any]) -> str:
    """Return a stable hash for a configuration payload."""
    encoded = json.dumps(
        dict(payload),
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


@dataclass(frozen=True)
class ConfigurationFieldChange:
    """One payload-level difference between two configuration versions."""

    path: str
    change_type: str
    old_value: Any
    new_value: Any


@dataclass(frozen=True)
class ConfigurationValidationResult:
    """Validation outcome for a working configuration payload."""

    is_valid: bool
    normalized_payload: dict[str, Any]
    config_hash: str | None
    settings: SimulationSettings | None
    issues: tuple[ConfigValidationIssue, ...]
    errors: tuple[str, ...]


@dataclass(frozen=True)
class ConfigurationSaveResult:
    """Result of saving a new immutable configuration version."""

    version: ConfigurationProfileVersion
    previous_version: ConfigurationProfileVersion | None
    diff: tuple[ConfigurationFieldChange, ...]
    validation: ConfigurationValidationResult


def diff_config_payloads(
    previous_payload: Mapping[str, Any] | None,
    next_payload: Mapping[str, Any] | None,
) -> tuple[ConfigurationFieldChange, ...]:
    """Return a flat, path-oriented diff between two payloads."""
    changes: list[ConfigurationFieldChange] = []
    _append_diff(changes, "", previous_payload, next_payload)
    return tuple(changes)


class ConfigurationLifecycleService:
    """Application service for validating and versioning configuration payloads."""

    def load_current_valid_version(
        self,
        session: Session,
        *,
        profile_name: str = DEFAULT_CONFIG_PROFILE_NAME,
        version_number: int | None = None,
    ) -> ConfigurationProfileVersion:
        """Return the current valid version for a profile or a selected version."""
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
        return profile_version

    def validate_working_copy(
        self,
        payload: Mapping[str, Any] | None,
        *,
        profile_name: str = DEFAULT_CONFIG_PROFILE_NAME,
        profile_version: int | None = None,
        env: Mapping[str, str] | None = None,
    ) -> ConfigurationValidationResult:
        """Validate a working configuration payload against the typed settings model."""
        errors: list[str] = []
        issues: list[ConfigValidationIssue] = []
        normalized_payload: dict[str, Any]
        if not isinstance(payload, Mapping):
            issue = ConfigValidationIssue(
                path=None,
                message="Configuration payload must be a mapping object.",
            )
            issues.append(issue)
            errors.append(issue.error_text)
            normalized_payload = {}
            return ConfigurationValidationResult(
                is_valid=False,
                normalized_payload=normalized_payload,
                config_hash=None,
                settings=None,
                issues=tuple(issues),
                errors=tuple(errors),
            )

        normalized_payload = deepcopy(dict(payload))
        simulation = normalized_payload.get("simulation")
        if not isinstance(simulation, Mapping):
            issue = ConfigValidationIssue(
                path=None,
                message="Configuration payload must include a simulation section.",
            )
            issues.append(issue)
            errors.append(issue.error_text)
        else:
            if not simulation.get("simulation_name"):
                issue = ConfigValidationIssue(
                    path="simulation.simulation_name",
                    message="is required.",
                )
                issues.append(issue)
                errors.append(issue.error_text)
            if not simulation.get("first_batch_month"):
                issue = ConfigValidationIssue(
                    path="simulation.first_batch_month",
                    message="is required.",
                )
                issues.append(issue)
                errors.append(issue.error_text)
            for issue in _validate_int_field(
                simulation,
                "master_seed",
                minimum=0,
            ):
                issues.append(issue)
                errors.append(issue.error_text)
            for issue in _validate_int_field(
                simulation,
                "historical_batch_count",
                minimum=1,
            ):
                issues.append(issue)
                errors.append(issue.error_text)
        for issue in validate_live_config_payload(normalized_payload):
            issues.append(issue)
            errors.append(issue.error_text)

        try:
            settings = settings_from_payload(
                normalized_payload,
                env,
                profile_name=profile_name,
                profile_version=profile_version,
            )
        except (TypeError, ValueError) as exc:
            issue = ConfigValidationIssue(path=None, message=str(exc))
            issues.append(issue)
            errors.append(issue.error_text)
            settings = None

        try:
            config_hash = compute_config_hash(normalized_payload)
        except (TypeError, ValueError) as exc:
            issue = ConfigValidationIssue(
                path=None,
                message=f"Configuration payload is not JSON serializable: {exc}",
            )
            issues.append(issue)
            errors.append(issue.error_text)
            config_hash = None

        return ConfigurationValidationResult(
            is_valid=not errors,
            normalized_payload=normalized_payload,
            config_hash=config_hash,
            settings=settings if not errors else None,
            issues=tuple(issues),
            errors=tuple(errors),
        )

    def save_new_version(
        self,
        session: Session,
        *,
        title: str,
        notes: str | None,
        payload: Mapping[str, Any],
        created_by: str | None = None,
        profile_name: str = DEFAULT_CONFIG_PROFILE_NAME,
        config_schema_version: str = DEFAULT_CONFIG_SCHEMA_VERSION,
    ) -> ConfigurationSaveResult:
        """Validate and save a new immutable configuration version."""
        normalized_title = title.strip()
        if not normalized_title:
            raise ValueError("Configuration version title is required.")

        validation = self.validate_working_copy(
            payload,
            profile_name=profile_name,
        )
        if not validation.is_valid:
            raise ValueError("; ".join(validation.errors))

        profile = session.scalar(
            select(ConfigurationProfile).where(
                ConfigurationProfile.profile_name == profile_name
            )
        )
        if profile is None:
            profile = ConfigurationProfile(
                profile_name=profile_name,
                description=f"Configuration profile for {profile_name}.",
                is_active=True,
            )
            session.add(profile)
            session.flush()

        previous_version = session.scalar(
            select(ConfigurationProfileVersion)
            .where(ConfigurationProfileVersion.lifecycle_status == "valid")
            .order_by(ConfigurationProfileVersion.version_number.desc())
        )
        next_version_number = (
            session.scalar(
                select(func.coalesce(func.max(ConfigurationProfileVersion.version_number), 0))
                .where(ConfigurationProfileVersion.profile_id == profile.id)
            )
            or 0
        ) + 1

        if previous_version is not None:
            previous_version.lifecycle_status = "deprecated"
            previous_version.deprecated_at = _utc_now()

        version = ConfigurationProfileVersion(
            profile_id=profile.id,
            version_number=next_version_number,
            title=normalized_title,
            notes=notes,
            config_schema_version=config_schema_version,
            config_hash=validation.config_hash,
            config_payload=deepcopy(validation.normalized_payload),
            created_by=created_by,
            lifecycle_status="valid",
        )
        session.add(version)
        session.flush()

        return ConfigurationSaveResult(
            version=version,
            previous_version=previous_version,
            diff=diff_config_payloads(
                previous_version.config_payload if previous_version is not None else None,
                validation.normalized_payload,
            ),
            validation=validation,
        )

    def mark_version_used(
        self,
        session: Session,
        *,
        profile_name: str = DEFAULT_CONFIG_PROFILE_NAME,
        version_id: int | None = None,
        version_number: int | None = None,
    ) -> ConfigurationProfileVersion:
        """Update last_used_at for the active or specified valid configuration version."""
        if version_id is not None:
            version = session.get(ConfigurationProfileVersion, version_id)
            if version is None:
                raise ValueError(f"Configuration profile version {version_id} does not exist.")
        else:
            version = self.load_current_valid_version(
                session,
                profile_name=profile_name,
                version_number=version_number,
            )

        if version.lifecycle_status != "valid":
            raise ValueError(
                f"Configuration profile version {version.id} is not valid and cannot be marked used."
            )

        version.last_used_at = _utc_now()
        session.flush()
        return version


def _append_diff(
    changes: list[ConfigurationFieldChange],
    prefix: str,
    previous_value: Any,
    next_value: Any,
) -> None:
    if isinstance(previous_value, Mapping) and isinstance(next_value, Mapping):
        keys = sorted(set(previous_value) | set(next_value))
        for key in keys:
            path = f"{prefix}.{key}" if prefix else str(key)
            previous_child = previous_value.get(key)
            next_child = next_value.get(key)
            if key not in previous_value:
                changes.append(
                    ConfigurationFieldChange(
                        path=path,
                        change_type="added",
                        old_value=None,
                        new_value=next_child,
                    )
                )
                continue
            if key not in next_value:
                changes.append(
                    ConfigurationFieldChange(
                        path=path,
                        change_type="removed",
                        old_value=previous_child,
                        new_value=None,
                    )
                )
                continue
            _append_diff(changes, path, previous_child, next_child)
        return

    if previous_value != next_value:
        changes.append(
            ConfigurationFieldChange(
                path=prefix or "$",
                change_type="changed",
                old_value=previous_value,
                new_value=next_value,
            )
        )


def _validate_int_field(
    container: Mapping[str, Any],
    key: str,
    *,
    minimum: int | None = None,
) -> list[ConfigValidationIssue]:
    value = container.get(key)
    if value is None:
        return [
            ConfigValidationIssue(
                path=f"simulation.{key}",
                message="is required.",
            )
        ]
    if isinstance(value, bool) or not isinstance(value, int):
        return [
            ConfigValidationIssue(
                path=f"simulation.{key}",
                message="must be an integer.",
            )
        ]
    if minimum is not None and value < minimum:
        return [
            ConfigValidationIssue(
                path=f"simulation.{key}",
                message=f"must be >= {minimum}.",
            )
        ]
    return []


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)
