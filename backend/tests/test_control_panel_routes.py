"""Route tests for the read-only control panel shell."""
from pathlib import Path
import sys

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.requests import Request


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core import ConfigurationLifecycleService  # noqa: E402
from app.main import create_app  # noqa: E402
from app.web.routes import get_configuration_lifecycle  # noqa: E402
from app.web.control_panel_queries import ControlPanelQueries  # noqa: E402


@pytest.fixture()
def session_factory():
    engine = create_engine(
        "sqlite://",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.begin() as conn:
        conn.exec_driver_sql("PRAGMA foreign_keys = ON")
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
        conn.exec_driver_sql(
            """
            CREATE TABLE generation_runs (
                id integer primary key autoincrement,
                generation_name varchar(255) not null,
                seed_value bigint not null,
                simulation_version varchar(100),
                parameter_snapshot text,
                started_at datetime,
                completed_at datetime,
                status varchar(30) not null default 'not_started',
                created_at datetime default current_timestamp not null,
                updated_at datetime default current_timestamp not null
            )
            """
        )
        conn.exec_driver_sql(
            """
            CREATE TABLE monthly_batches (
                id integer primary key autoincrement,
                generation_run_id bigint not null,
                batch_month date not null,
                batch_sequence integer not null,
                batch_type varchar(30) not null default 'future_increment',
                active_player_count_start integer,
                new_player_count integer,
                active_player_count_end integer,
                match_count_generated integer,
                rating_update_count integer,
                assessment_update_count integer,
                processing_status varchar(30) not null default 'pending',
                started_at datetime,
                completed_at datetime,
                error_message text,
                created_at datetime default current_timestamp not null,
                updated_at datetime default current_timestamp not null,
                unique (generation_run_id, batch_month),
                foreign key(generation_run_id) references generation_runs(id)
            )
            """
        )
        conn.exec_driver_sql(
            """
            CREATE TABLE job_status (
                id integer primary key autoincrement,
                job_type varchar(50) not null,
                job_id varchar(100) not null unique,
                status varchar(30) not null default 'pending',
                current_phase varchar(100),
                percent_complete numeric(5,2),
                current_message text,
                started_at datetime,
                completed_at datetime,
                error_message text,
                created_at datetime default current_timestamp not null,
                updated_at datetime default current_timestamp not null
            )
            """
        )
        conn.exec_driver_sql(
            """
            CREATE TABLE job_stage_progress (
                id integer primary key autoincrement,
                job_status_id bigint not null,
                generation_run_id bigint,
                batch_id bigint,
                stage_name varchar(100) not null,
                stage_sequence integer,
                status varchar(30) not null default 'pending',
                progress_current bigint not null default 0,
                progress_total bigint,
                progress_unit varchar(100),
                progress_percent numeric(5,2),
                last_heartbeat_at datetime,
                progress_message text,
                started_at datetime,
                completed_at datetime,
                error_message text,
                metadata_json text,
                created_at datetime default current_timestamp not null,
                updated_at datetime default current_timestamp not null,
                unique(job_status_id, batch_id, stage_name),
                foreign key(job_status_id) references job_status(id),
                foreign key(generation_run_id) references generation_runs(id),
                foreign key(batch_id) references monthly_batches(id)
            )
            """
        )
    yield sessionmaker(bind=engine, autoflush=False, future=True)


def _seed_snapshot_state(session_factory):
    session = session_factory()
    try:
        lifecycle = ConfigurationLifecycleService()
        lifecycle.save_new_version(
            session,
            title="Read only config",
            notes=None,
            payload={
                "runtime": {},
                "simulation": {
                    "simulation_name": "Route Test",
                    "simulation_version": "v1",
                    "master_seed": 11,
                    "historical_batch_count": 2,
                    "first_batch_month": "2026-01-01",
                    "target_total_players": 1000,
                },
            },
        )
        session.execute(
            text(
                """
                INSERT INTO generation_runs (
                    id, generation_name, seed_value, simulation_version, status, started_at, created_at, updated_at
                ) VALUES (
                    1, 'UI run', 11, 'v1', 'running', '2026-05-20 09:00:00', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                )
                """
            )
        )
        session.execute(
            text(
                """
                INSERT INTO monthly_batches (
                    id, generation_run_id, batch_month, batch_sequence, batch_type, processing_status, created_at, updated_at
                ) VALUES
                    (1, 1, '2026-01-01', 1, 'historical_initial', 'succeeded', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
                    (2, 1, '2026-02-01', 2, 'historical_initial', 'running', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """
            )
        )
        session.execute(
            text(
                """
                INSERT INTO job_status (
                    id, job_type, job_id, status, current_phase, percent_complete, current_message, created_at, updated_at
                ) VALUES (
                    1, 'generation_run', 'generation-run-1-test', 'running', 'matches', 40.00, 'matches running',
                    CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                )
                """
            )
        )
        session.execute(
            text(
                """
                INSERT INTO job_stage_progress (
                    id, job_status_id, generation_run_id, batch_id, stage_name, stage_sequence, status,
                    progress_current, progress_total, progress_unit, progress_percent, progress_message,
                    created_at, updated_at
                ) VALUES
                    (1, 1, 1, 1, 'players', 1, 'succeeded', 1, 1, 'stage', 100.00, 'players succeeded', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
                    (2, 1, 1, 2, 'matches', 4, 'running', 0, 1, 'stage', 0.00, 'matches running', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """
            )
        )
        session.commit()
    finally:
        session.close()


def _seed_idle_config_state(session_factory):
    session = session_factory()
    try:
        lifecycle = ConfigurationLifecycleService()
        lifecycle.save_new_version(
            session,
            title="Editable config",
            notes="base",
            payload={
                "runtime": {},
                "simulation": {
                    "simulation_name": "Editable Route Test",
                    "simulation_version": "v1",
                    "master_seed": 21,
                    "historical_batch_count": 2,
                    "first_batch_month": "2026-03-01",
                    "target_total_players": 1000,
                },
            },
        )
        session.commit()
    finally:
        session.close()


def _request(path: str, *, method: str = "GET") -> Request:
    return Request({"type": "http", "method": method, "path": path, "headers": []})


def _route_map(app):
    return {route.path: route.endpoint for route in app.router.routes if hasattr(route, "path")}


def test_control_panel_shell_renders_tabs_and_initial_content(session_factory):
    _seed_snapshot_state(session_factory)
    app = create_app()
    routes = _route_map(app)
    session = session_factory()
    try:
        response = routes["/control"](
            request=_request("/control"),
            session=session,
            queries=ControlPanelQueries(),
        )
    finally:
        session.close()

    body = response.body.decode()
    assert response.status_code == 200
    assert "/control" in routes
    assert "/control/partials/config" in routes
    assert "Simulation Control Panel" in body
    assert "Configuration" in body
    assert "Orchestration" in body
    assert 'hx-get="/control/partials/config"' in body
    assert "Read only config" in body


def test_control_panel_partials_render_run_status_batch_table_and_progress(session_factory):
    _seed_snapshot_state(session_factory)
    app = create_app()
    routes = _route_map(app)
    session = session_factory()
    try:
        run_status = routes["/control/partials/run-status"](
            request=_request("/control/partials/run-status"),
            session=session,
            queries=ControlPanelQueries(),
        )
        batch_table = routes["/control/partials/batch-table"](
            request=_request("/control/partials/batch-table"),
            session=session,
            queries=ControlPanelQueries(),
        )
        progress = routes["/control/partials/progress-bars"](
            request=_request("/control/partials/progress-bars"),
            session=session,
            queries=ControlPanelQueries(),
        )
        orchestration = routes["/control/partials/orchestration"](
            request=_request("/control/partials/orchestration"),
            session=session,
            queries=ControlPanelQueries(),
        )
    finally:
        session.close()

    assert run_status.status_code == 200
    assert "UI run" in run_status.body.decode()
    assert "running" in run_status.body.decode()

    assert batch_table.status_code == 200
    assert "Monthly Batches" in batch_table.body.decode()
    assert "2026-02-01" in batch_table.body.decode()

    assert progress.status_code == 200
    assert "Stage Progress" in progress.body.decode()
    assert "matches" in progress.body.decode()

    assert orchestration.status_code == 200
    assert 'hx-get="/control/partials/run-status"' in orchestration.body.decode()
    assert 'hx-get="/control/partials/batch-table"' in orchestration.body.decode()


def test_control_panel_config_validate_renders_validation_success(session_factory):
    _seed_idle_config_state(session_factory)
    app = create_app()
    routes = _route_map(app)
    session = session_factory()
    lifecycle = get_configuration_lifecycle()
    try:
        response = routes["/control/config/validate"](
            request=_request("/control/config/validate", method="POST"),
            config_title="March tuning",
            config_notes="adjusted player count",
            config_payload_json='{"runtime": {}, "simulation": {"simulation_name": "Editable Route Test", "simulation_version": "v2", "master_seed": 21, "historical_batch_count": 3, "first_batch_month": "2026-03-01", "target_total_players": 1200}}',
            session=session,
            queries=ControlPanelQueries(),
            lifecycle=lifecycle,
        )
    finally:
        session.close()

    body = response.body.decode()
    assert response.status_code == 200
    assert "Configuration validated successfully." in body
    assert "Save New Version" in body
    assert "March tuning" in body


def test_control_panel_config_save_persists_new_version_when_idle(session_factory):
    _seed_idle_config_state(session_factory)
    app = create_app()
    routes = _route_map(app)
    session = session_factory()
    lifecycle = get_configuration_lifecycle()
    try:
        response = routes["/control/config/save"](
            request=_request("/control/config/save", method="POST"),
            config_title="April tuning",
            config_notes="saved",
            config_payload_json='{"runtime": {}, "simulation": {"simulation_name": "Editable Route Test", "simulation_version": "v3", "master_seed": 21, "historical_batch_count": 4, "first_batch_month": "2026-03-01", "target_total_players": 1400}}',
            session=session,
            queries=ControlPanelQueries(),
            lifecycle=lifecycle,
        )
        current_version = lifecycle.load_current_valid_version(session)
    finally:
        session.close()

    body = response.body.decode()
    assert response.status_code == 200
    assert "Configuration saved as the current valid version." in body
    assert "April tuning" in body
    assert current_version.title == "April tuning"
    assert current_version.version_number == 2
    assert current_version.config_payload["simulation"]["simulation_version"] == "v3"


def test_control_panel_config_save_is_blocked_while_run_active(session_factory):
    _seed_snapshot_state(session_factory)
    app = create_app()
    routes = _route_map(app)
    session = session_factory()
    lifecycle = get_configuration_lifecycle()
    try:
        response = routes["/control/config/save"](
            request=_request("/control/config/save", method="POST"),
            config_title="Blocked save",
            config_notes="should not persist",
            config_payload_json='{"runtime": {}, "simulation": {"simulation_name": "Route Test", "simulation_version": "v2", "master_seed": 11, "historical_batch_count": 2, "first_batch_month": "2026-01-01", "target_total_players": 1000}}',
            session=session,
            queries=ControlPanelQueries(),
            lifecycle=lifecycle,
        )
        current_version = lifecycle.load_current_valid_version(session)
    finally:
        session.close()

    body = response.body.decode()
    assert response.status_code == 200
    assert "Configuration editing is blocked while a generation run is active." in body
    assert current_version.title == "Read only config"
