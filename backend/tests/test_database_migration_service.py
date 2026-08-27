"""Tests for database migration orchestration service."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import sys


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app import database_migration  # noqa: E402
from app.database_migration import DatabaseMigrationService, ManagedProcess  # noqa: E402


def _write_backup_package(
    root: Path,
    name: str,
    *,
    database_name: str = "pickleball",
    verification_status: str = "VERIFIED",
) -> Path:
    package_dir = root / "backups" / name
    package_dir.mkdir(parents=True, exist_ok=True)
    (package_dir / "database.dump").write_text("dump", encoding="utf-8")
    (package_dir / "postgres_globals.sql").write_text("globals", encoding="utf-8")
    (package_dir / "row_counts.csv").write_text(
        "schema,table,row_count\npublic,players,1\n",
        encoding="utf-8",
    )
    (package_dir / "SHA256SUMS").write_text("checksum", encoding="utf-8")
    (package_dir / "manifest.txt").write_text(
        "\n".join(
            (
                "backup_timestamp=20260805T120000Z",
                f"database_name={database_name}",
                "postgres_version=16.1",
                f"verification_status={verification_status}",
                "certification_status=PASS",
            )
        ),
        encoding="utf-8",
    )
    return package_dir


def test_list_backup_packages_marks_restore_eligibility(tmp_path):
    _write_backup_package(tmp_path, "eligible")
    _write_backup_package(
        tmp_path,
        "wrong_db",
        database_name="other_database",
    )
    _write_backup_package(
        tmp_path,
        "not_verified",
        verification_status="PENDING",
    )

    service = DatabaseMigrationService(project_root=tmp_path)

    packages = service.list_backup_packages()

    assert [package.slug for package in packages] == [
        "wrong_db",
        "not_verified",
        "eligible",
    ]
    assert packages[-1].is_restore_eligible is True
    assert "configured database" in (packages[0].restore_blocker or "")
    assert "VERIFIED" in (packages[1].restore_blocker or "")


def test_get_active_operation_clears_terminal_lock(tmp_path):
    service = DatabaseMigrationService(project_root=tmp_path)
    service.runtime_root.mkdir(parents=True, exist_ok=True)
    service.status_file.write_text(
        """
        {
          "operation_id": "op-1",
          "operation_type": "restore",
          "status": "succeeded",
          "current_step": "completed"
        }
        """.strip(),
        encoding="utf-8",
    )
    service.lock_file.write_text(
        """
        {
          "operation_id": "op-1",
          "pid": 999999
        }
        """.strip(),
        encoding="utf-8",
    )

    active = service.get_active_operation()

    assert active is None
    assert not service.lock_file.exists()


def test_load_latest_status_marks_stale_active_operation_failed(tmp_path):
    service = DatabaseMigrationService(project_root=tmp_path)
    service.runtime_root.mkdir(parents=True, exist_ok=True)
    service.status_file.write_text(
        """
        {
          "operation_id": "op-2",
          "operation_type": "backup",
          "status": "running",
          "current_step": "create_archive",
          "message": "Creating PostgreSQL archive.",
          "pid": 999999,
          "started_at": "2026-08-08T00:46:51Z",
          "updated_at": "2026-08-08T00:47:14Z",
          "completed_at": null
        }
        """.strip(),
        encoding="utf-8",
    )
    service.lock_file.write_text(
        """
        {
          "operation_id": "op-2",
          "pid": 999999
        }
        """.strip(),
        encoding="utf-8",
    )

    latest_status = service.load_latest_status()

    assert latest_status is not None
    assert latest_status.status == "failed"
    assert latest_status.completed_at is not None
    assert latest_status.message == (
        "Operation is no longer running. The previous attempt likely exited unexpectedly."
    )
    assert not service.lock_file.exists()


def test_load_latest_status_exposes_progress_summary(tmp_path):
    service = DatabaseMigrationService(project_root=tmp_path)
    service.runtime_root.mkdir(parents=True, exist_ok=True)
    service.status_file.write_text(
        """
        {
          "operation_id": "op-3",
          "operation_type": "backup",
          "status": "running",
          "current_step": "create_archive",
          "message": "Creating PostgreSQL archive.",
          "pid": null
        }
        """.strip(),
        encoding="utf-8",
    )
    service.lock_file.write_text(
        """
        {
          "operation_id": "op-3",
          "pid": 1
        }
        """.strip(),
        encoding="utf-8",
    )

    latest_status = service.load_latest_status()

    assert latest_status is not None
    assert latest_status.script_name == "backup_database.sh"
    assert latest_status.current_step_index == 3
    assert latest_status.total_steps == 7
    assert latest_status.completed_step_count == 2
    assert latest_status.progress_summary == "backup_database.sh | 2 of 7 completed"


def test_start_restore_records_pid_and_lock(tmp_path, monkeypatch):
    package_dir = _write_backup_package(tmp_path, "restore_me")
    service = DatabaseMigrationService(project_root=tmp_path)

    monkeypatch.setattr(service, "restore_blockers", lambda: ())
    monkeypatch.setattr(
        service,
        "_launch_operation",
        lambda **_: SimpleNamespace(pid=4321),
    )

    operation = service.start_restore(
        backup_path=str(package_dir),
        confirm_destructive="yes",
    )

    assert operation.operation_type == "restore"
    assert operation.pid == 4321
    assert service.lock_file.exists()
    latest_status = service.load_latest_status()
    assert latest_status is not None
    assert latest_status.incoming_backup == str(package_dir)
    assert latest_status.pid == 4321


def test_capture_restore_managed_processes_filters_repo_server_and_worker(tmp_path, monkeypatch):
    service = DatabaseMigrationService(project_root=tmp_path)
    backend_dir = tmp_path / "backend"
    worker_script = backend_dir / "scripts" / "run_background_worker.py"

    monkeypatch.setattr(
        database_migration,
        "_iter_process_commands",
        lambda: (
            (101, ("python", str(worker_script), "--queues", "realism_audit")),
            (202, ("python", "-m", "uvicorn", "app.main:app", "--app-dir", str(backend_dir), "--port", "8000")),
            (303, ("python", "-m", "uvicorn", "other.main:app", "--app-dir", "/tmp/other")),
        ),
    )

    managed = service.capture_restore_managed_processes()

    assert [(process.pid, process.label) for process in managed] == [
        (101, "durable background worker"),
        (202, "control panel server"),
    ]


def test_run_restore_operation_stops_and_restarts_managed_processes(tmp_path, monkeypatch):
    service = DatabaseMigrationService(project_root=tmp_path)
    managed = (
        ManagedProcess(
            pid=101,
            label="durable background worker",
            command=("python", "backend/scripts/run_background_worker.py"),
        ),
        ManagedProcess(
            pid=202,
            label="control panel server",
            command=("python", "-m", "uvicorn", "app.main:app"),
        ),
    )
    calls: list[tuple[str, object]] = []

    monkeypatch.setattr(service, "capture_restore_managed_processes", lambda: managed)
    monkeypatch.setattr(
        service,
        "stop_managed_processes",
        lambda processes: calls.append(("stop", processes)) or processes,
    )
    monkeypatch.setattr(
        service,
        "restart_managed_processes",
        lambda processes: calls.append(("restart", processes)) or (1001, 1002),
    )
    monkeypatch.setattr(
        database_migration,
        "_run_script_command",
        lambda command, parser=None: (
            parser("[migrate_classroom_database] Safety backup: /tmp/safety")
            if parser is not None
            else None
        )
        or "[migrate_classroom_database] Safety backup: /tmp/safety\n",
    )

    status_payload = service._initial_status_payload(  # noqa: SLF001
        operation_id="op-restore",
        operation_type="restore",
        incoming_backup=None,
    )
    database_migration._run_restore_operation(  # noqa: SLF001
        service=service,
        status_payload=status_payload,
        backup_dir=str(tmp_path / "backups" / "restore_me"),
    )

    assert calls == [
        ("stop", managed),
        ("restart", managed),
    ]
    assert status_payload["safety_backup"] == "/tmp/safety"
    assert status_payload["current_step"] == "restore_validated"


def test_run_restore_operation_restarts_services_after_failure(tmp_path, monkeypatch):
    service = DatabaseMigrationService(project_root=tmp_path)
    managed = (
        ManagedProcess(
            pid=101,
            label="durable background worker",
            command=("python", "backend/scripts/run_background_worker.py"),
        ),
    )
    calls: list[tuple[str, object]] = []

    monkeypatch.setattr(service, "capture_restore_managed_processes", lambda: managed)
    monkeypatch.setattr(service, "stop_managed_processes", lambda processes: processes)
    monkeypatch.setattr(
        service,
        "restart_managed_processes",
        lambda processes: calls.append(("restart", processes)) or (1001,),
    )

    def _raise_failure(command, parser=None):
        raise RuntimeError("restore failed")

    monkeypatch.setattr(database_migration, "_run_script_command", _raise_failure)

    status_payload = service._initial_status_payload(  # noqa: SLF001
        operation_id="op-restore-fail",
        operation_type="restore",
        incoming_backup=None,
    )

    try:
        database_migration._run_restore_operation(  # noqa: SLF001
            service=service,
            status_payload=status_payload,
            backup_dir=str(tmp_path / "backups" / "restore_me"),
        )
    except RuntimeError as exc:
        assert str(exc) == "restore failed"
    else:
        raise AssertionError("Expected restore failure.")

    assert calls == [("restart", managed)]
    assert status_payload["current_step"] == "restart_application_services"
