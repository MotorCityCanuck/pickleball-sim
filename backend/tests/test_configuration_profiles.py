"""Tests for configuration profile repository helpers."""
from pathlib import Path
import sys

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core import (  # noqa: E402
    DEFAULT_CONFIG_PROFILE_NAME,
    DEFAULT_CONFIG_VERSION_NUMBER,
    get_configuration_payload,
    upsert_default_configuration_profile,
)
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


def test_upsert_default_configuration_profile_creates_valid_version(session):
    profile_version = upsert_default_configuration_profile(session)

    assert profile_version.version_number == DEFAULT_CONFIG_VERSION_NUMBER
    assert profile_version.lifecycle_status == "valid"
    assert profile_version.title == "Default configuration"
    assert profile_version.config_hash is not None
    assert profile_version.config_payload["simulation"]["master_seed"] == 42
    assert profile_version.config_payload["simulation"]["target_total_players"] == 50000


def test_get_configuration_payload_returns_latest_valid_version(session):
    upsert_default_configuration_profile(session)

    payload = get_configuration_payload(
        session,
        profile_name=DEFAULT_CONFIG_PROFILE_NAME,
    )

    assert payload["simulation"]["simulation_name"] == "NAPA_Olympic_Analytics_v1"
    assert payload["export"]["export_included_table_groups"] == [
        "student_core",
        "reference",
    ]


def test_get_configuration_payload_rejects_missing_profile(session):
    with pytest.raises(ValueError, match="No valid configuration profile version"):
        get_configuration_payload(session, profile_name="missing")
