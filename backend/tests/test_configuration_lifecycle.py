"""Tests for configuration lifecycle validation and version management."""
from datetime import datetime
from pathlib import Path
import sys

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core import ConfigurationLifecycleService, default_config_payload  # noqa: E402


@pytest.fixture()
def session():
    engine = create_engine("sqlite:///:memory:", future=True)
    with engine.begin() as conn:
        conn.exec_driver_sql(
            """
            CREATE TABLE configuration_profiles (
                id integer primary key autoincrement,
                profile_name varchar(255) not null unique,
                description text,
                is_active boolean not null default true,
                created_at datetime default current_timestamp not null,
                updated_at datetime default current_timestamp not null
            )
            """
        )
        conn.exec_driver_sql(
            """
            CREATE TABLE configuration_profile_versions (
                id integer primary key autoincrement,
                profile_id bigint not null,
                version_number integer not null,
                title varchar(255) not null,
                notes text,
                config_schema_version varchar(50) not null,
                config_hash varchar(128),
                config_payload json not null,
                created_by varchar(255),
                lifecycle_status varchar(30) not null default 'valid',
                last_used_at datetime,
                deprecated_at datetime,
                created_at datetime default current_timestamp not null,
                updated_at datetime default current_timestamp not null,
                unique (profile_id, version_number),
                foreign key(profile_id) references configuration_profiles(id)
            )
            """
        )
    session_factory = sessionmaker(bind=engine, autoflush=False, future=True)
    db_session = session_factory()
    try:
        yield db_session
    finally:
        db_session.close()


def test_validate_working_copy_accepts_default_payload():
    service = ConfigurationLifecycleService()

    result = service.validate_working_copy(default_config_payload())

    assert result.is_valid is True
    assert result.settings is not None
    assert result.config_hash is not None
    assert result.errors == ()


def test_validate_working_copy_reports_required_field_errors():
    service = ConfigurationLifecycleService()
    payload = default_config_payload()
    del payload["simulation"]["simulation_name"]
    payload["simulation"]["master_seed"] = "not-an-int"

    result = service.validate_working_copy(payload)

    assert result.is_valid is False
    assert "simulation.simulation_name is required." in result.errors
    assert "simulation.master_seed must be an integer." in result.errors


def test_validate_working_copy_reports_live_seed_dataset_errors():
    service = ConfigurationLifecycleService()
    payload = default_config_payload()
    payload["raw_seed_data"]["supported_datasets"] = [
        "metro_areas_us",
        "metro_areas_us",
        "future_dataset",
    ]

    result = service.validate_working_copy(payload)

    assert result.is_valid is False
    assert (
        "raw_seed_data.supported_datasets contains duplicates: metro_areas_us."
        in result.errors
    )
    assert (
        "raw_seed_data.supported_datasets contains unsupported datasets: future_dataset."
        in result.errors
    )


def test_validate_working_copy_reports_live_pipeline_bound_errors():
    service = ConfigurationLifecycleService()
    payload = default_config_payload()
    payload["simulation"]["historical_batch_count"] = 13
    payload["simulation"]["first_batch_month"] = "2026-99-01"
    payload["confidence"]["initial_confidence_score"] = 1.5
    payload["games_and_scores"]["games_per_match"]["league"] = 0

    result = service.validate_working_copy(payload)

    assert result.is_valid is False
    assert (
        "simulation.historical_batch_count must be <= 12 for the live monthly pipeline."
        in result.errors
    )
    assert (
        "simulation.first_batch_month must be a valid ISO date string."
        in result.errors
    )
    assert "confidence.initial_confidence_score must be between 0 and 1" in result.errors
    assert (
        "games_and_scores.games_per_match.league must be a positive integer"
        in result.errors
    )


def test_validate_working_copy_reports_monthly_player_inactivation_rate_errors():
    service = ConfigurationLifecycleService()
    payload = default_config_payload()
    payload["player_generation"]["monthly_player_inactivation_rate"] = 1.5

    result = service.validate_working_copy(payload)

    assert result.is_valid is False
    assert (
        "player_generation.monthly_player_inactivation_rate must be between 0 and 1"
        in result.errors
    )


def test_save_new_version_creates_profile_and_deprecates_prior_valid(session):
    service = ConfigurationLifecycleService()
    initial_payload = default_config_payload()
    first = service.save_new_version(
        session,
        title="Initial config",
        notes="base version",
        payload=initial_payload,
        created_by="tester",
    )
    session.commit()

    next_payload = default_config_payload()
    next_payload["simulation"]["master_seed"] = 99
    second = service.save_new_version(
        session,
        title="Seed update",
        notes="change seed",
        payload=next_payload,
        created_by="tester",
    )
    session.commit()

    assert first.version.version_number == 1
    assert second.version.version_number == 2
    assert second.previous_version is not None
    assert second.previous_version.lifecycle_status == "deprecated"
    assert second.previous_version.deprecated_at is not None
    assert second.version.lifecycle_status == "valid"
    assert any(change.path == "simulation.master_seed" for change in second.diff)


def test_load_current_valid_version_returns_latest_valid(session):
    service = ConfigurationLifecycleService()
    payload = default_config_payload()
    service.save_new_version(
        session,
        title="Initial config",
        notes=None,
        payload=payload,
    )
    session.commit()

    version = service.load_current_valid_version(session)

    assert version.title == "Initial config"
    assert version.lifecycle_status == "valid"


def test_mark_version_used_updates_last_used_at(session):
    service = ConfigurationLifecycleService()
    payload = default_config_payload()
    saved = service.save_new_version(
        session,
        title="Initial config",
        notes=None,
        payload=payload,
    )
    session.commit()

    marked = service.mark_version_used(session, version_id=saved.version.id)
    session.commit()

    assert isinstance(marked.last_used_at, datetime)
