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
)


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
