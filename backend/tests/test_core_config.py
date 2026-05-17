"""Tests for application settings."""
from pathlib import Path
import sys


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.config import (  # noqa: E402
    DEFAULT_DATABASE_URL,
    DEFAULT_INITIAL_HISTORICAL_MONTHS,
    DEFAULT_SEED_VALUE,
    DEFAULT_SIMULATION_VERSION,
    get_database_url,
    load_settings,
    settings_from_payload,
)
from app.core.default_configuration import DEFAULT_CONFIG_PROFILE_NAME  # noqa: E402


def test_get_database_url_uses_default_when_env_missing():
    assert get_database_url({}) == DEFAULT_DATABASE_URL


def test_load_settings_uses_defaults():
    settings = load_settings({})

    assert settings.database_url == DEFAULT_DATABASE_URL
    assert settings.database_echo is False
    assert settings.simulation_version == DEFAULT_SIMULATION_VERSION
    assert settings.default_seed_value == DEFAULT_SEED_VALUE
    assert settings.initial_historical_months == DEFAULT_INITIAL_HISTORICAL_MONTHS


def test_load_settings_uses_environment_overrides():
    settings = load_settings(
        {
            "DATABASE_URL": "postgresql://example:example@localhost/example",
            "DATABASE_ECHO": "true",
            "SIMULATION_VERSION": "2026.05",
            "SIMULATION_DEFAULT_SEED": "987",
            "SIMULATION_INITIAL_HISTORICAL_MONTHS": "24",
        }
    )

    assert settings.database_url == "postgresql://example:example@localhost/example"
    assert settings.database_echo is True
    assert settings.simulation_version == "2026.05"
    assert settings.default_seed_value == 987
    assert settings.initial_historical_months == 24


def test_settings_from_payload_uses_json_values():
    settings = settings_from_payload(
        {
            "runtime": {
                "database_url": "postgresql://payload:payload@localhost/payload",
                "database_echo": True,
            },
            "simulation": {
                "simulation_version": "payload-version",
                "master_seed": 42,
                "historical_batch_count": 18,
            },
        }
    )

    assert settings.database_url == "postgresql://payload:payload@localhost/payload"
    assert settings.database_echo is True
    assert settings.simulation_version == "payload-version"
    assert settings.default_seed_value == 42
    assert settings.initial_historical_months == 18
    assert settings.configuration_profile_name == DEFAULT_CONFIG_PROFILE_NAME
    assert settings.config_payload["simulation"]["master_seed"] == 42


def test_settings_from_payload_allows_environment_overrides():
    settings = settings_from_payload(
        {
            "simulation": {
                "simulation_version": "payload-version",
                "master_seed": 42,
                "historical_batch_count": 18,
            },
        },
        {
            "SIMULATION_VERSION": "env-version",
            "SIMULATION_DEFAULT_SEED": "77",
            "SIMULATION_INITIAL_HISTORICAL_MONTHS": "6",
            "SIMULATION_CONFIG_PROFILE": "env-profile",
            "SIMULATION_CONFIG_VERSION": "3",
        },
    )

    assert settings.simulation_version == "env-version"
    assert settings.default_seed_value == 77
    assert settings.initial_historical_months == 6
    assert settings.configuration_profile_name == "env-profile"
    assert settings.configuration_profile_version == 3
