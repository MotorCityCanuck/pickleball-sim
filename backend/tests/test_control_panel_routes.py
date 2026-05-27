"""Route tests for the read-only control panel shell."""
from pathlib import Path
import re
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
            CREATE TABLE raw_seed_load_runs (
                id integer primary key autoincrement,
                job_status_id bigint,
                dataset_type varchar(80) not null,
                source_path varchar(1000) not null,
                source_file_count integer not null default 0,
                source_checksum varchar(128),
                started_at datetime,
                completed_at datetime,
                status varchar(30) not null default 'pending',
                rows_read integer not null default 0,
                rows_loaded integer not null default 0,
                rows_rejected integer not null default 0,
                error_message text,
                created_at datetime default current_timestamp not null,
                updated_at datetime default current_timestamp not null
            )
            """
        )
        conn.exec_driver_sql(
            """
            CREATE TABLE regions (
                id integer primary key autoincrement,
                country_code varchar(10) not null,
                region_type varchar(20),
                region_name varchar(255) not null,
                state_province_code varchar(10),
                population bigint,
                selection_probability numeric(12,8),
                competitiveness_multiplier numeric(8,4) default 1.0,
                latitude numeric(10,6),
                longitude numeric(10,6),
                created_at datetime default current_timestamp not null,
                updated_at datetime default current_timestamp not null
            )
            """
        )
        conn.exec_driver_sql(
            """
            CREATE TABLE clubs (
                id integer primary key,
                club_name varchar(255) not null,
                region_id bigint not null,
                club_type varchar(50),
                competitiveness_level varchar(50),
                member_capacity integer,
                founding_date date,
                indoor_court_count integer default 0,
                outdoor_court_count integer default 0,
                generation_run_id bigint,
                created_at datetime default current_timestamp not null,
                updated_at datetime default current_timestamp not null,
                foreign key(region_id) references regions(id),
                foreign key(generation_run_id) references generation_runs(id)
            )
            """
        )
        conn.exec_driver_sql(
            """
            CREATE TABLE first_names (
                id integer primary key,
                country_code varchar(2) not null,
                state_province_code varchar(2) not null,
                birth_year integer not null,
                gender varchar(1) not null,
                first_name varchar(100) not null,
                frequency_count integer not null,
                normalized_probability numeric(12,8),
                source_dataset varchar(255),
                created_at datetime default current_timestamp not null,
                updated_at datetime default current_timestamp not null
            )
            """
        )
        conn.exec_driver_sql(
            """
            CREATE TABLE last_names (
                id integer primary key,
                country_code varchar(2) not null,
                state_province_code varchar(2) not null,
                last_name varchar(100) not null,
                frequency_count integer not null,
                bias_multiplier numeric(10,4),
                adjusted_frequency_count numeric(18,4),
                normalized_probability numeric(12,8),
                source_dataset varchar(255),
                created_at datetime default current_timestamp not null,
                updated_at datetime default current_timestamp not null
            )
            """
        )
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
        _seed_ready_reference_data(session)
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


def _seed_completed_generation_state(session_factory):
    session = session_factory()
    try:
        lifecycle = ConfigurationLifecycleService()
        lifecycle.save_new_version(
            session,
            title="Completed config",
            notes=None,
            payload={
                "runtime": {},
                "simulation": {
                    "simulation_name": "Completed Route Test",
                    "simulation_version": "v1",
                    "master_seed": 11,
                    "historical_batch_count": 2,
                    "first_batch_month": "2026-01-01",
                    "target_total_players": 1000,
                },
            },
        )
        _seed_ready_reference_data(session)
        session.execute(
            text(
                """
                INSERT INTO generation_runs (
                    id, generation_name, seed_value, simulation_version, status, started_at, completed_at, created_at, updated_at
                ) VALUES (
                    2, 'Completed UI run', 11, 'v1', 'succeeded', '2026-05-20 09:00:00', '2026-05-20 10:00:00', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                )
                """
            )
        )
        session.execute(
            text(
                """
                INSERT INTO monthly_batches (
                    id, generation_run_id, batch_month, batch_sequence, batch_type, processing_status, completed_at, created_at, updated_at
                ) VALUES
                    (21, 2, '2026-01-01', 1, 'historical_initial', 'succeeded', '2026-05-20 09:30:00', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
                    (22, 2, '2026-02-01', 2, 'historical_initial', 'succeeded', '2026-05-20 10:00:00', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """
            )
        )
        session.execute(
            text(
                """
                INSERT INTO job_status (
                    id, job_type, job_id, status, current_phase, percent_complete, current_message, started_at, completed_at, created_at, updated_at
                ) VALUES (
                    2, 'generation_run', 'generation-run-2-test', 'succeeded', 'completed', 100.00, 'Generation run completed successfully.',
                    '2026-05-20 09:00:00', '2026-05-20 10:00:00', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
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
                    (201, 2, 2, 21, 'players', 1, 'succeeded', 1, 1, 'stage', 100.00, 'players succeeded', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
                    (202, 2, 2, 22, 'matches', 4, 'succeeded', 1, 1, 'stage', 100.00, 'matches succeeded', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
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
        _seed_ready_reference_data(session)
        session.commit()
    finally:
        session.close()


def _seed_stale_seed_job_state(session_factory):
    _seed_idle_config_state(session_factory)
    session = session_factory()
    try:
        session.execute(
            text(
                """
                INSERT INTO job_status (
                    id, job_type, job_id, status, current_phase, percent_complete,
                    current_message, started_at, created_at, updated_at
                ) VALUES (
                    31, 'seed_refresh', 'seed-refresh-stale', 'running',
                    'seed_normalization', 50.00, 'Stale seed job.',
                    '2026-05-20 09:00:00', '2026-05-20 09:00:00',
                    '2026-05-20 09:00:00'
                )
                """
            )
        )
        session.execute(
            text(
                """
                INSERT INTO job_stage_progress (
                    id, job_status_id, generation_run_id, batch_id, stage_name,
                    stage_sequence, status, progress_current, progress_total,
                    progress_unit, progress_percent, last_heartbeat_at,
                    progress_message, started_at, created_at, updated_at
                ) VALUES (
                    31, 31, NULL, NULL, 'seed_normalization', 2, 'pending',
                    0, 4, 'dataset', 0.00, NULL,
                    'Pending execution.', NULL,
                    '2026-05-20 09:00:00', '2026-05-20 09:00:00'
                )
                """
            )
        )
        session.commit()
    finally:
        session.close()


def _seed_stale_generation_job_state(session_factory):
    _seed_idle_config_state(session_factory)
    session = session_factory()
    try:
        session.execute(
            text(
                """
                INSERT INTO generation_runs (
                    id, generation_name, seed_value, simulation_version, status,
                    started_at, created_at, updated_at
                ) VALUES (
                    41, 'Stale generation run', 11, 'v1', 'running',
                    '2026-05-20 09:00:00', '2026-05-20 09:00:00',
                    '2026-05-20 09:00:00'
                )
                """
            )
        )
        session.execute(
            text(
                """
                INSERT INTO monthly_batches (
                    id, generation_run_id, batch_month, batch_sequence,
                    batch_type, processing_status, created_at, updated_at
                ) VALUES (
                    41, 41, '2026-01-01', 1, 'historical_initial',
                    'running', '2026-05-20 09:00:00', '2026-05-20 09:00:00'
                )
                """
            )
        )
        session.execute(
            text(
                """
                INSERT INTO job_status (
                    id, job_type, job_id, status, current_phase, percent_complete,
                    current_message, started_at, created_at, updated_at
                ) VALUES (
                    41, 'generation_run', 'generation-run-stale', 'running',
                    'matches', 20.00, 'Stale generation job.',
                    '2026-05-20 09:00:00', '2026-05-20 09:00:00',
                    '2026-05-20 09:00:00'
                )
                """
            )
        )
        session.execute(
            text(
                """
                INSERT INTO job_stage_progress (
                    id, job_status_id, generation_run_id, batch_id, stage_name,
                    stage_sequence, status, progress_current, progress_total,
                    progress_unit, progress_percent, last_heartbeat_at,
                    progress_message, started_at, created_at, updated_at
                ) VALUES (
                    41, 41, 41, 41, 'matches', 4, 'running',
                    0, 1, 'stage', 0.00, '2026-05-20 09:01:00',
                    'Stale generation job.', '2026-05-20 09:00:00',
                    '2026-05-20 09:00:00', '2026-05-20 09:00:00'
                )
                """
            )
        )
        session.commit()
    finally:
        session.close()


def _seed_ready_reference_data(session):
    session.execute(
        text(
            """
            INSERT INTO regions (
                id, country_code, region_type, region_name, state_province_code, created_at, updated_at
            ) VALUES (1, 'US', 'MSA', 'Phoenix, AZ', 'AZ', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """
        )
    )
    session.execute(
        text(
            """
            INSERT INTO clubs (
                id, club_name, region_id, club_type, created_at, updated_at
            ) VALUES (1, 'Phoenix Pickleball Club', 1, 'public_park', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """
        )
    )
    session.execute(
        text(
            """
            INSERT INTO first_names (
                id, country_code, state_province_code, birth_year, gender, first_name, frequency_count, created_at, updated_at
            ) VALUES (1, 'US', 'AZ', 1990, 'M', 'Alex', 10, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """
        )
    )
    session.execute(
        text(
            """
            INSERT INTO last_names (
                id, country_code, state_province_code, last_name, frequency_count, created_at, updated_at
            ) VALUES (1, 'US', 'AZ', 'Smith', 10, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """
        )
    )
    session.execute(
        text(
            """
            INSERT INTO raw_seed_load_runs (
                id, dataset_type, source_path, source_file_count, status, rows_read, rows_loaded, rows_rejected, created_at, updated_at
            ) VALUES (
                1, 'metro_areas_us', 'data/raw/metro_areas/us.csv', 1, 'completed', 100, 100, 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
            """
        )
    )


def _request(path: str, *, method: str = "GET") -> Request:
    return Request({"type": "http", "method": method, "path": path, "headers": []})


def _route_map(app):
    return {route.path: route.endpoint for route in app.router.routes if hasattr(route, "path")}


class FakeGenerationRunService:
    def __init__(self, *, error: str | None = None) -> None:
        self.error = error
        self.calls: list[str] = []

    def register_generation_run(self, generation_name: str, *, session=None):
        del session
        self.calls.append(generation_name)
        if self.error is not None:
            raise ValueError(self.error)
        return type(
            "Registration",
            (),
            {
                "configuration_version": type("ConfigVersion", (), {"id": 1})(),
                "generation_run": type("GenerationRun", (), {"id": 2})(),
                "job_status": type("JobStatus", (), {"id": 3})(),
            },
        )()

    def execute_registered_generation_run_in_background(self, **kwargs):
        return kwargs


class FakeSeedRefreshService:
    def __init__(self, *, error: str | None = None) -> None:
        self.error = error
        self.calls: list[str] = []

    def register_raw_seed_ingest(self, *, session=None):
        del session
        self.calls.append("load")
        if self.error is not None:
            raise ValueError(self.error)
        return type(
            "Registration",
            (),
            {
                "configuration_version": type("ConfigVersion", (), {"id": 10})(),
                "job_status": type("JobStatus", (), {"id": 11})(),
                "mode": "load",
            },
        )()

    def register_seed_normalization(self, *, session=None):
        del session
        self.calls.append("normalize")
        if self.error is not None:
            raise ValueError(self.error)
        return type(
            "Registration",
            (),
            {
                "configuration_version": type("ConfigVersion", (), {"id": 10})(),
                "job_status": type("JobStatus", (), {"id": 11})(),
                "mode": "normalize",
            },
        )()

    def register_seed_refresh(self, *, session=None):
        del session
        self.calls.append("refresh")
        if self.error is not None:
            raise ValueError(self.error)
        return type(
            "Registration",
            (),
            {
                "configuration_version": type("ConfigVersion", (), {"id": 10})(),
                "job_status": type("JobStatus", (), {"id": 11})(),
                "mode": "refresh",
            },
        )()

    def execute_registered_seed_job_in_background(self, **kwargs):
        return kwargs


class FakeBackgroundRunner:
    def __init__(self) -> None:
        self.submissions: list[tuple[object, tuple[object, ...], dict[str, object]]] = []

    def submit(self, fn, /, *args, **kwargs):
        self.submissions.append((fn, args, kwargs))
        return object()


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
    assert "/control/partials/config/seed" in routes
    assert "/control/partials/config/player-match" in routes
    assert "Simulation Control Panel" in body
    assert "Seed Data Config" in body
    assert "Player and Match Config" in body
    assert "Orchestration" in body
    assert 'hx-get="/control/partials/config/seed"' in body
    assert 'hx-get="/control/partials/config/player-match"' in body
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
    assert "Generate seed data" in orchestration.body.decode()
    assert "Generate player and match data" in orchestration.body.decode()
    assert "Start Generation Run" in orchestration.body.decode()
    assert 'hx-post="/control/seed/load"' in orchestration.body.decode()
    assert 'hx-post="/control/seed/normalize"' in orchestration.body.decode()
    assert 'hx-post="/control/seed/refresh"' in orchestration.body.decode()
    assert 'hx-get="/control/partials/orchestration"' in orchestration.body.decode()
    assert 'hx-trigger="every 10s"' in orchestration.body.decode()


def test_completed_generation_run_renders_completion_popup_script(session_factory):
    _seed_completed_generation_state(session_factory)
    app = create_app()
    routes = _route_map(app)
    session = session_factory()
    try:
        orchestration = routes["/control/partials/orchestration"](
            request=_request("/control/partials/orchestration"),
            session=session,
            queries=ControlPanelQueries(),
        )
    finally:
        session.close()

    body = orchestration.body.decode()
    assert orchestration.status_code == 200
    assert "All monthly batches are complete." in body
    assert 'const runId = "2"' in body
    assert "generation-complete-notified:${runId}" in body


def test_completed_generation_run_marks_student_dataset_as_coming_soon(session_factory):
    _seed_completed_generation_state(session_factory)
    app = create_app()
    routes = _route_map(app)
    session = session_factory()
    try:
        orchestration = routes["/control/partials/orchestration"](
            request=_request("/control/partials/orchestration"),
            session=session,
            queries=ControlPanelQueries(),
        )
    finally:
        session.close()

    body = orchestration.body.decode()
    assert orchestration.status_code == 200
    assert "Student Dataset Release" in body
    assert "Prereqs met" in body
    assert "Generation export is not wired into the control panel yet." in body
    assert "Generate Student Dataset (coming soon)" in body


def test_clear_stalled_seed_job_route_marks_job_failed(session_factory):
    _seed_stale_seed_job_state(session_factory)
    app = create_app()
    routes = _route_map(app)
    session = session_factory()
    try:
        before = routes["/control/partials/orchestration"](
            request=_request("/control/partials/orchestration"),
            session=session,
            queries=ControlPanelQueries(),
        )
        response = routes["/control/jobs/clear-stalled"](
            request=_request("/control/jobs/clear-stalled", method="POST"),
            job_status_id=31,
            session=session,
            queries=ControlPanelQueries(),
        )
        job_status = session.execute(
            text("SELECT status, current_phase FROM job_status WHERE id = 31")
        ).one()
        stage_status = session.execute(
            text("SELECT status FROM job_stage_progress WHERE id = 31")
        ).scalar_one()
    finally:
        session.close()

    assert before.status_code == 200
    assert "Clear stalled job" in before.body.decode()
    assert response.status_code == 200
    assert "Cleared stalled seed_refresh job seed-refresh-stale." in response.body.decode()
    assert job_status == ("failed", "failed")
    assert stage_status == "failed"


def test_clear_stalled_generation_job_route_marks_run_and_batch_failed(session_factory):
    _seed_stale_generation_job_state(session_factory)
    app = create_app()
    routes = _route_map(app)
    session = session_factory()
    try:
        before = routes["/control/partials/orchestration"](
            request=_request("/control/partials/orchestration"),
            session=session,
            queries=ControlPanelQueries(),
        )
        response = routes["/control/jobs/clear-stalled"](
            request=_request("/control/jobs/clear-stalled", method="POST"),
            job_status_id=41,
            session=session,
            queries=ControlPanelQueries(),
        )
        run_status = session.execute(
            text("SELECT status FROM generation_runs WHERE id = 41")
        ).scalar_one()
        batch_status = session.execute(
            text("SELECT processing_status FROM monthly_batches WHERE id = 41")
        ).scalar_one()
        job_status = session.execute(
            text("SELECT status FROM job_status WHERE id = 41")
        ).scalar_one()
    finally:
        session.close()

    assert before.status_code == 200
    assert "Clear stalled job" in before.body.decode()
    assert response.status_code == 200
    assert "Cleared stalled generation_run job generation-run-stale." in response.body.decode()
    assert run_status == "failed"
    assert batch_status == "failed"
    assert job_status == "failed"


def test_clear_stalled_job_route_refuses_active_job(session_factory):
    _seed_idle_config_state(session_factory)
    app = create_app()
    routes = _route_map(app)
    session = session_factory()
    try:
        session.execute(
            text(
                """
                INSERT INTO job_status (
                    id, job_type, job_id, status, current_phase, percent_complete,
                    current_message, started_at, created_at, updated_at
                ) VALUES (
                    51, 'seed_refresh', 'seed-refresh-active', 'running',
                    'raw_seed_ingest', 0.00, 'Fresh seed job.',
                    CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                )
                """
            )
        )
        session.execute(
            text(
                """
                INSERT INTO job_stage_progress (
                    id, job_status_id, generation_run_id, batch_id, stage_name,
                    stage_sequence, status, progress_current, progress_total,
                    progress_unit, progress_percent, last_heartbeat_at,
                    progress_message, started_at, created_at, updated_at
                ) VALUES (
                    51, 51, NULL, NULL, 'raw_seed_ingest', 1, 'running',
                    0, 4, 'dataset', 0.00, CURRENT_TIMESTAMP,
                    'Fresh seed job.', CURRENT_TIMESTAMP,
                    CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                )
                """
            )
        )
        session.commit()
        response = routes["/control/jobs/clear-stalled"](
            request=_request("/control/jobs/clear-stalled", method="POST"),
            job_status_id=51,
            session=session,
            queries=ControlPanelQueries(),
        )
        job_status = session.execute(
            text("SELECT status FROM job_status WHERE id = 51")
        ).scalar_one()
    finally:
        session.close()

    assert response.status_code == 200
    assert "still has a fresh activity signal" in response.body.decode()
    assert job_status == "running"


def test_dismiss_failed_job_route_removes_failed_seed_job_from_snapshot(session_factory):
    _seed_idle_config_state(session_factory)
    app = create_app()
    routes = _route_map(app)
    session = session_factory()
    try:
        session.execute(
            text(
                """
                INSERT INTO job_status (
                    id, job_type, job_id, status, current_phase, percent_complete,
                    current_message, started_at, completed_at, error_message, created_at, updated_at
                ) VALUES (
                    61, 'seed_refresh', 'seed-refresh-failed', 'failed',
                    'failed', 0.00, 'Seed refresh failed.',
                    '2026-05-20 09:00:00', '2026-05-20 09:05:00', 'Seed refresh failed.',
                    CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                )
                """
            )
        )
        session.execute(
            text(
                """
                INSERT INTO job_stage_progress (
                    id, job_status_id, generation_run_id, batch_id, stage_name,
                    stage_sequence, status, progress_current, progress_total,
                    progress_unit, progress_percent, last_heartbeat_at,
                    progress_message, error_message, started_at, completed_at, created_at, updated_at
                ) VALUES (
                    61, 61, NULL, NULL, 'seed_normalization', 2, 'failed',
                    0, 4, 'dataset', 0.00, CURRENT_TIMESTAMP,
                    'Seed refresh failed.', 'Seed refresh failed.',
                    '2026-05-20 09:00:00', '2026-05-20 09:05:00', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                )
                """
            )
        )
        session.execute(
            text(
                """
                INSERT INTO raw_seed_load_runs (
                    id, job_status_id, dataset_type, source_path, source_file_count, status,
                    rows_read, rows_loaded, rows_rejected, error_message,
                    started_at, completed_at, created_at, updated_at
                ) VALUES (
                    61, 61, 'first_names_us', 'data/raw/first_names/us.txt', 1, 'failed',
                    100, 0, 100, 'parse failed',
                    '2026-05-20 09:00:00', '2026-05-20 09:01:00', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                )
                """
            )
        )
        session.commit()

        before = routes["/control/partials/orchestration"](
            request=_request("/control/partials/orchestration"),
            session=session,
            queries=ControlPanelQueries(),
        )
        response = routes["/control/jobs/dismiss-failed"](
            request=_request("/control/jobs/dismiss-failed", method="POST"),
            job_status_id=61,
            session=session,
            queries=ControlPanelQueries(),
        )
        remaining_job_count = session.execute(
            text("SELECT COUNT(*) FROM job_status WHERE id = 61")
        ).scalar_one()
        orphaned_load_job_id = session.execute(
            text("SELECT job_status_id FROM raw_seed_load_runs WHERE id = 61")
        ).scalar_one()
    finally:
        session.close()

    assert before.status_code == 200
    assert "Dismiss failed job" in before.body.decode()
    assert response.status_code == 200
    assert "Dismissed failed seed_refresh job seed-refresh-failed." in response.body.decode()
    assert remaining_job_count == 0
    assert orphaned_load_job_id is None


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
            active_config_scope="synthetic",
            seed_config_json='{"raw_seed_data": {"raw_data_root": "data/raw", "supported_datasets": ["metro_areas_us"]}}',
            synthetic_config_json='{"runtime": {}, "simulation": {"simulation_name": "Editable Route Test", "simulation_version": "v2", "master_seed": 21, "historical_batch_count": 3, "first_batch_month": "2026-03-01", "target_total_players": 1200}}',
            session=session,
            queries=ControlPanelQueries(),
            lifecycle=lifecycle,
        )
    finally:
        session.close()

    body = response.body.decode()
    assert response.status_code == 200
    assert "Validation passed." in body
    assert "Draft validated successfully and is ready to save." in body
    assert "Validate and Save" in body
    assert "March tuning" in body
    assert "Synthetic Workload Configuration" in body
    assert "Player and Match Generation" in body
    assert 'type="date"' in body
    assert 'value="v2"' in body
    assert "Valid input: whole number." in body
    assert "Monthly player growth rate" in body
    assert "Monthly player inactivation rate" in body
    assert 'data-config-section="synthetic:synthetic_simulation_identity"' in body


def test_control_panel_config_save_highlights_invalid_fields_without_persisting(session_factory):
    _seed_idle_config_state(session_factory)
    app = create_app()
    routes = _route_map(app)
    session = session_factory()
    lifecycle = get_configuration_lifecycle()
    try:
        response = routes["/control/config/save"](
            request=_request("/control/config/save", method="POST"),
            config_title="Broken tuning",
            config_notes="invalid month count",
            active_config_scope="synthetic",
            seed_config_json='{"raw_seed_data": {"raw_data_root": "data/raw", "supported_datasets": ["metro_areas_us"]}}',
            synthetic_config_json='{"runtime": {}, "simulation": {"simulation_name": "Editable Route Test", "simulation_version": "v2", "master_seed": 21, "historical_batch_count": 13, "first_batch_month": "2026-03-01", "target_total_players": 1200}}',
            session=session,
            queries=ControlPanelQueries(),
            lifecycle=lifecycle,
        )
        current_version = lifecycle.load_current_valid_version(session)
    finally:
        session.close()

    body = response.body.decode()
    assert response.status_code == 200
    assert "Validation failed" in body
    assert "Validate and Save again" in body
    assert re.search(
        r'data-config-control[^>]*data-config-path="simulation.historical_batch_count"[^>]*data-config-invalid="true"',
        body,
    )
    assert re.search(
        r'data-config-section="synthetic:synthetic_simulation_identity"[^>]*data-config-section-invalid="true"',
        body,
    )
    assert "live monthly pipeline" in body
    assert current_version.title == "Editable config"
    assert current_version.version_number == 1


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
            active_config_scope="synthetic",
            seed_config_json='{"raw_seed_data": {"raw_data_root": "data/raw", "supported_datasets": ["metro_areas_us", "first_names_us"]}}',
            synthetic_config_json='{"runtime": {}, "simulation": {"simulation_name": "Editable Route Test", "simulation_version": "v3", "master_seed": 21, "historical_batch_count": 4, "first_batch_month": "2026-03-01", "target_total_players": 1400}}',
            session=session,
            queries=ControlPanelQueries(),
            lifecycle=lifecycle,
        )
        current_version = lifecycle.load_current_valid_version(session)
    finally:
        session.close()

    body = response.body.decode()
    assert response.status_code == 200
    assert "Configuration validated and saved as the current valid version." in body
    assert "April tuning" in body
    assert "Simulation Scale and Determinism" in body
    assert current_version.title == "April tuning"
    assert current_version.version_number == 2
    assert current_version.config_payload["simulation"]["simulation_version"] == "v3"


def test_control_panel_config_save_requires_title_and_marks_title_field(session_factory):
    _seed_idle_config_state(session_factory)
    app = create_app()
    routes = _route_map(app)
    session = session_factory()
    lifecycle = get_configuration_lifecycle()
    try:
        response = routes["/control/config/save"](
            request=_request("/control/config/save", method="POST"),
            config_title="",
            config_notes="missing title",
            active_config_scope="synthetic",
            seed_config_json='{"raw_seed_data": {"raw_data_root": "data/raw", "supported_datasets": ["metro_areas_us"]}}',
            synthetic_config_json='{"runtime": {}, "simulation": {"simulation_name": "Editable Route Test", "simulation_version": "v3", "master_seed": 21, "historical_batch_count": 4, "first_batch_month": "2026-03-01", "target_total_players": 1400}}',
            session=session,
            queries=ControlPanelQueries(),
            lifecycle=lifecycle,
        )
        current_version = lifecycle.load_current_valid_version(session)
    finally:
        session.close()

    body = response.body.decode()
    assert response.status_code == 200
    assert "Configuration version title is required." in body
    assert re.search(
        r'<input[^>]*name="config_title"[^>]*border:1px solid #e07a75',
        body,
    )
    assert current_version.title == "Editable config"
    assert current_version.version_number == 1


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
            active_config_scope="seed",
            seed_config_json='{"raw_seed_data": {"raw_data_root": "data/raw"}}',
            synthetic_config_json='{"runtime": {}, "simulation": {"simulation_name": "Route Test", "simulation_version": "v2", "master_seed": 11, "historical_batch_count": 2, "first_batch_month": "2026-01-01", "target_total_players": 1000}}',
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
    assert "Seed Data Ingest and Preparation" in body
    assert current_version.title == "Read only config"


def test_control_panel_seed_config_partial_renders_current_values_in_controls(session_factory):
    _seed_idle_config_state(session_factory)
    app = create_app()
    routes = _route_map(app)
    session = session_factory()
    try:
        response = routes["/control/partials/config/seed"](
            request=_request("/control/partials/config/seed"),
            session=session,
            queries=ControlPanelQueries(),
        )
    finally:
        session.close()

    body = response.body.decode()
    assert response.status_code == 200
    assert "Seed Data Configuration" in body
    assert "Current draft matches the saved configuration." in body
    assert 'name="config_title"' in body
    assert 'value="Editable config"' in body
    assert "Supported raw seed datasets" in body
    assert "Club Facilities and Membership Policy" in body
    assert "Club size distribution and capacity ranges" in body
    assert "Distribution" in body
    assert "Club court ranges" in body
    assert "Allow cross-region club assignment" in body
    assert "Multi-club membership rate" in body
    assert "Name Assignment" not in body
    assert 'data-config-section="seed:seed_raw_ingest"' in body
    assert re.search(
        r'<details[^>]*data-config-section="seed:seed_raw_ingest"[^>]*open',
        body,
    )
    assert "Raw seed data root" not in body
    assert "Player and Match Generation" not in body


def test_control_panel_player_match_config_partial_renders_current_values_in_controls(session_factory):
    _seed_idle_config_state(session_factory)
    app = create_app()
    routes = _route_map(app)
    session = session_factory()
    try:
        response = routes["/control/partials/config/player-match"](
            request=_request("/control/partials/config/player-match"),
            session=session,
            queries=ControlPanelQueries(),
        )
    finally:
        session.close()

    body = response.body.decode()
    assert response.status_code == 200
    assert "Synthetic Workload Configuration" in body
    assert "Simulation Scale and Determinism" in body
    assert 'value="v1"' in body
    assert 'value="2026-03-01"' in body
    assert "Player Traits and Skill Seeding" in body
    assert "Dominant hand weights" in body
    assert "Player status weights" in body
    assert "Initial skill mean" in body
    assert "Games and Score Dynamics" in body
    assert "Games per match" in body
    assert "Win-by-two extension rate" in body
    assert "Upset probability boost" in body
    assert "Rating Initialization and Updates" in body
    assert "New-player K factor" in body
    assert "Confidence increment per match" in body
    assert "Matchmaking locality weight" in body
    assert "Match Scheduling" in body
    assert "Matches per team per month" in body
    assert "Saturday scheduling weight" in body
    assert "Max daily matches per team" in body
    assert "Generation run mode" not in body
    assert "Commit strategy" not in body
    assert "Batch retry max attempts" not in body
    assert "Allow destructive rerun" not in body
    assert "Multi-team player rate" not in body
    assert "Rating gap max" in body
    assert "Monthly team dissolution rate" not in body
    assert re.search(
        r'<details[^>]*data-config-section="synthetic:synthetic_simulation_identity"[^>]*open',
        body,
    )
    assert "Simulation version" in body
    assert "Supported raw seed datasets" not in body


def test_control_panel_generation_start_requires_destructive_confirmation(session_factory):
    _seed_idle_config_state(session_factory)
    app = create_app()
    routes = _route_map(app)
    session = session_factory()
    fake_service = FakeGenerationRunService()
    fake_runner = FakeBackgroundRunner()
    try:
        response = routes["/control/generation/start"](
            request=_request("/control/generation/start", method="POST"),
            generation_name="UI launch",
            destructive_confirm=None,
            session=session,
            queries=ControlPanelQueries(),
            run_service=fake_service,
            background_runner=fake_runner,
        )
    finally:
        session.close()

    body = response.body.decode()
    assert response.status_code == 200
    assert "Destructive reset confirmation is required before starting a generation run." in body
    assert fake_service.calls == []


def test_control_panel_seed_refresh_launches_when_allowed(session_factory):
    _seed_idle_config_state(session_factory)
    app = create_app()
    routes = _route_map(app)
    session = session_factory()
    fake_service = FakeSeedRefreshService()
    fake_runner = FakeBackgroundRunner()
    try:
        response = routes["/control/seed/refresh"](
            request=_request("/control/seed/refresh", method="POST"),
            session=session,
            queries=ControlPanelQueries(),
            seed_service=fake_service,
            background_runner=fake_runner,
        )
    finally:
        session.close()

    body = response.body.decode()
    assert response.status_code == 200
    assert "Full seed refresh started in background." in body
    assert fake_service.calls == ["refresh"]
    assert len(fake_runner.submissions) == 1


def test_control_panel_seed_refresh_surfaces_service_failure(session_factory):
    _seed_idle_config_state(session_factory)
    app = create_app()
    routes = _route_map(app)
    session = session_factory()
    fake_service = FakeSeedRefreshService(error="seed refresh failed")
    fake_runner = FakeBackgroundRunner()
    try:
        response = routes["/control/seed/normalize"](
            request=_request("/control/seed/normalize", method="POST"),
            session=session,
            queries=ControlPanelQueries(),
            seed_service=fake_service,
            background_runner=fake_runner,
        )
    finally:
        session.close()

    body = response.body.decode()
    assert response.status_code == 200
    assert "seed refresh failed" in body
    assert fake_service.calls == ["normalize"]


def test_control_panel_generation_start_launches_run_when_allowed(session_factory):
    _seed_idle_config_state(session_factory)
    app = create_app()
    routes = _route_map(app)
    session = session_factory()
    fake_service = FakeGenerationRunService()
    fake_runner = FakeBackgroundRunner()
    try:
        response = routes["/control/generation/start"](
            request=_request("/control/generation/start", method="POST"),
            generation_name="UI launch",
            destructive_confirm="yes",
            session=session,
            queries=ControlPanelQueries(),
            run_service=fake_service,
            background_runner=fake_runner,
        )
    finally:
        session.close()

    body = response.body.decode()
    assert response.status_code == 200
    assert "started in background" in body
    assert "UI launch" in body
    assert fake_service.calls == ["UI launch"]
    assert len(fake_runner.submissions) == 1


def test_control_panel_generation_start_surfaces_service_failure(session_factory):
    _seed_idle_config_state(session_factory)
    app = create_app()
    routes = _route_map(app)
    session = session_factory()
    fake_service = FakeGenerationRunService(error="pipeline failed")
    fake_runner = FakeBackgroundRunner()
    try:
        response = routes["/control/generation/start"](
            request=_request("/control/generation/start", method="POST"),
            generation_name="UI launch",
            destructive_confirm="yes",
            session=session,
            queries=ControlPanelQueries(),
            run_service=fake_service,
            background_runner=fake_runner,
        )
    finally:
        session.close()

    body = response.body.decode()
    assert response.status_code == 200
    assert "pipeline failed" in body
    assert fake_service.calls == ["UI launch"]
