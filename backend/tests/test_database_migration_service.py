"""Tests for database migration orchestration service."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import sys


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.database_migration import DatabaseMigrationService  # noqa: E402


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
