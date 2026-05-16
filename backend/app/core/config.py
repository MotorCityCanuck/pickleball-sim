"""Environment-backed application settings."""
from __future__ import annotations

from dataclasses import dataclass
from os import environ
from typing import Mapping


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
    )
