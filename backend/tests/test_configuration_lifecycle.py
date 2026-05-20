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
