"""Environment-backed application settings."""
from __future__ import annotations

from dataclasses import dataclass
from copy import deepcopy
from os import environ
from typing import Any, Mapping

from .default_configuration import (
    DEFAULT_CONFIG_PAYLOAD,
    DEFAULT_CONFIG_PROFILE_NAME,
    default_config_payload,
)


DEFAULT_DATABASE_URL = "postgresql://postgres:postgres@localhost:5432/pickleball"
DEFAULT_SIMULATION_VERSION = "0.1.0"
DEFAULT_INITIAL_HISTORICAL_MONTHS = 12
DEFAULT_SEED_VALUE = 1


def _get_bool(value: str | None, *, default: bool = False) -> bool:
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


def _get_int(value: str | None, *, default: int) -> int:
    if value is None or value == "":
        return default
    return int(value)


@dataclass(frozen=True)
class SimulationSettings:
    """Configuration values needed to coordinate simulation runs."""

    database_url: str = DEFAULT_DATABASE_URL
    database_echo: bool = False
    simulation_version: str = DEFAULT_SIMULATION_VERSION
    default_seed_value: int = DEFAULT_SEED_VALUE
    initial_historical_months: int = DEFAULT_INITIAL_HISTORICAL_MONTHS
    configuration_profile_name: str = DEFAULT_CONFIG_PROFILE_NAME
    configuration_profile_version: int | None = None
    config_payload: dict[str, Any] | None = None


def get_database_url(env: Mapping[str, str] | None = None) -> str:
    """Return the configured database URL."""
    source = env if env is not None else environ
    return source.get("DATABASE_URL") or DEFAULT_DATABASE_URL


def load_settings(env: Mapping[str, str] | None = None) -> SimulationSettings:
    """Load simulation settings from environment variables."""
    source = env if env is not None else environ
    return SimulationSettings(
        database_url=get_database_url(source),
        database_echo=_get_bool(source.get("DATABASE_ECHO")),
        simulation_version=(
            source.get("SIMULATION_VERSION") or DEFAULT_SIMULATION_VERSION
        ),
        default_seed_value=_get_int(
            source.get("SIMULATION_DEFAULT_SEED"),
            default=DEFAULT_SEED_VALUE,
        ),
        initial_historical_months=_get_int(
            source.get("SIMULATION_INITIAL_HISTORICAL_MONTHS"),
            default=DEFAULT_INITIAL_HISTORICAL_MONTHS,
        ),
        configuration_profile_name=(
            source.get("SIMULATION_CONFIG_PROFILE") or DEFAULT_CONFIG_PROFILE_NAME
        ),
        configuration_profile_version=(
            _get_int(source.get("SIMULATION_CONFIG_VERSION"), default=0) or None
        ),
    )


def settings_from_payload(
    payload: Mapping[str, Any] | None,
    env: Mapping[str, str] | None = None,
    *,
    profile_name: str = DEFAULT_CONFIG_PROFILE_NAME,
    profile_version: int | None = None,
) -> SimulationSettings:
    """Build settings from a configuration payload with environment overrides."""
    source = env if env is not None else environ
    config_payload = deepcopy(dict(payload or DEFAULT_CONFIG_PAYLOAD))
    runtime = config_payload.get("runtime", {})
    simulation = config_payload.get("simulation", {})

    return SimulationSettings(
        database_url=source.get("DATABASE_URL")
        or runtime.get("database_url")
        or DEFAULT_DATABASE_URL,
        database_echo=_get_bool(
            source.get("DATABASE_ECHO"),
            default=bool(runtime.get("database_echo", False)),
        ),
        simulation_version=(
            source.get("SIMULATION_VERSION")
            or simulation.get("simulation_version")
            or DEFAULT_SIMULATION_VERSION
        ),
        default_seed_value=_get_int(
            source.get("SIMULATION_DEFAULT_SEED"),
            default=int(simulation.get("master_seed", DEFAULT_SEED_VALUE)),
        ),
        initial_historical_months=_get_int(
            source.get("SIMULATION_INITIAL_HISTORICAL_MONTHS"),
            default=int(
                simulation.get(
                    "historical_batch_count",
                    DEFAULT_INITIAL_HISTORICAL_MONTHS,
                )
            ),
        ),
        configuration_profile_name=(
            source.get("SIMULATION_CONFIG_PROFILE") or profile_name
        ),
        configuration_profile_version=(
            _get_int(source.get("SIMULATION_CONFIG_VERSION"), default=0)
            or profile_version
        ),
        config_payload=config_payload,
    )


def load_default_payload_settings(env: Mapping[str, str] | None = None) -> SimulationSettings:
    """Build settings from the built-in default configuration payload."""
    return settings_from_payload(default_config_payload(), env)
