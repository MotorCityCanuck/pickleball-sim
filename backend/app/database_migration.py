"""Filesystem-backed orchestration for database backup and migration UI flows."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import re
import signal
import shutil
import subprocess
import sys
import time
from typing import Any
from urllib.parse import urlsplit

from sqlalchemy import text

from app.core.config import load_settings
from app.db.session import create_database_engine, session_scope
from app.web.control_panel_queries import ControlPanelQueries


PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = PROJECT_ROOT / "backend"
BACKUP_ROOT = PROJECT_ROOT / "backups"
RUNTIME_ROOT = PROJECT_ROOT / "runtime" / "database_migration"
OPERATIONS_ROOT = RUNTIME_ROOT / "operations"
STATUS_FILE = RUNTIME_ROOT / "latest_status.json"
LOCK_FILE = RUNTIME_ROOT / "database_migration.lock"
LOG_ROOT = PROJECT_ROOT / "logs"
RUNNER_SCRIPT = BACKEND_DIR / "scripts" / "run_database_migration_operation.py"
DEFAULT_POSTGRES_CONTAINER = os.environ.get("POSTGRES_CONTAINER", "pickleball-postgres")
DEFAULT_POSTGRES_DB = os.environ.get("POSTGRES_DB", "pickleball")
ACTIVE_OPERATION_STATUSES = frozenset({"queued", "running"})
TERMINAL_OPERATION_STATUSES = frozenset({"succeeded", "failed"})
STALE_OPERATION_MESSAGE = (
    "Operation is no longer running. The previous attempt likely exited unexpectedly."
)
PROCESS_STOP_TIMEOUT_SECONDS = 10.0
PROCESS_STOP_POLL_INTERVAL_SECONDS = 0.25


@dataclass(frozen=True)
class ManagedProcess:
    """One app-side process that must be stopped during destructive restore."""

    pid: int
    label: str
    command: tuple[str, ...]


@dataclass(frozen=True)
class BackupPackageSummary:
    """UI-ready metadata for one discovered backup package."""

    slug: str
    path: str
    relative_path: str
    database_name: str | None
    postgres_version: str | None
    backup_timestamp: str | None
    verification_status: str | None
    certification_status: str | None
    certification_timestamp: str | None
    git_commit: str | None
    git_branch: str | None
    database_size: str | None
    total_size_bytes: int
    has_freeze_manifest: bool
    is_safety_backup: bool
    is_restore_eligible: bool
    restore_blocker: str | None


@dataclass(frozen=True)
class CurrentDatabaseSummary:
    """Current configured database identity and connection state."""

    database_name: str
    postgres_version: str | None
    docker_container: str
    database_size: str | None
    git_commit: str | None
    git_branch: str | None
    certification_status: str | None
    certification_timestamp: str | None
    connection_status: str
    connection_error: str | None


@dataclass(frozen=True)
class MigrationOperationStatus:
    """Durable UI-facing state for the latest migration operation."""

    operation_id: str
    operation_type: str
    status: str
    current_step: str | None
    message: str | None
    started_at: str | None
    updated_at: str | None
    completed_at: str | None
    incoming_backup: str | None
    created_backup: str | None
    safety_backup: str | None
    log_path: str | None
    error: str | None
    pid: int | None
    requires_manual_rollback: bool

    @property
    def is_active(self) -> bool:
        return self.status in ACTIVE_OPERATION_STATUSES

    @property
    def script_name(self) -> str | None:
        progress = _operation_progress_definition(self.operation_type)
        if progress is None:
            return None
        return progress["script_name"]

    @property
    def total_steps(self) -> int:
        progress = _operation_progress_definition(self.operation_type)
        if progress is None:
            return 0
        return len(progress["steps"])

    @property
    def current_step_index(self) -> int | None:
        progress = _operation_progress_definition(self.operation_type)
        if progress is None:
            return None
        steps = progress["steps"]
        if self.status == "succeeded":
            return len(steps)
        if not self.current_step:
            return None
        try:
            return steps.index(self.current_step) + 1
        except ValueError:
            return None

    @property
    def completed_step_count(self) -> int:
        progress = _operation_progress_definition(self.operation_type)
        if progress is None:
            return 0
        steps = progress["steps"]
        if self.status == "succeeded":
            return len(steps)
        current_index = self.current_step_index
        if current_index is None:
            return 0
        return max(current_index - 1, 0)

    @property
    def progress_summary(self) -> str | None:
        script_name = self.script_name
        total_steps = self.total_steps
        if script_name is None or total_steps == 0:
            return None
        return f"{script_name} | {self.completed_step_count} of {total_steps} completed"


class DatabaseMigrationService:
    """Coordinate migration operations without duplicating shell-script logic."""

    def __init__(
        self,
        *,
        project_root: Path = PROJECT_ROOT,
        python_executable: str | None = None,
    ) -> None:
        self.project_root = project_root
        self.backend_dir = project_root / "backend"
        self.backup_root = project_root / "backups"
        self.runtime_root = project_root / "runtime" / "database_migration"
        self.operations_root = self.runtime_root / "operations"
        self.status_file = self.runtime_root / "latest_status.json"
        self.lock_file = self.runtime_root / "database_migration.lock"
        self.log_root = project_root / "logs"
        self.runner_script = self.backend_dir / "scripts" / "run_database_migration_operation.py"
        self.python_executable = python_executable or sys.executable

    def get_current_database_summary(self) -> CurrentDatabaseSummary:
        """Return current configured database details with tolerant DB probing."""
        database_name = _configured_database_name()
        postgres_version = None
        database_size = None
        certification_status = "UNKNOWN"
        certification_timestamp = None
        connection_status = "UNAVAILABLE"
        connection_error = None

        try:
            engine = create_database_engine()
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
                postgres_version = connection.execute(
                    text("SHOW server_version")
                ).scalar_one_or_none()
                database_size = connection.execute(
                    text("SELECT pg_size_pretty(pg_database_size(current_database()))")
                ).scalar_one_or_none()
            connection_status = "HEALTHY"
        except Exception as exc:  # pragma: no cover - exercised through route tests
            connection_error = str(exc)
        finally:
            try:
                engine.dispose()  # type: ignore[name-defined]
            except Exception:
                pass

        try:
            with session_scope() as session:
                snapshot = ControlPanelQueries().get_control_panel_snapshot(session)
                latest_snapshot = snapshot.realism_audit_summary.latest_snapshot
                if latest_snapshot is not None:
                    certification_status = (
                        latest_snapshot.certification_decision
                        or latest_snapshot.overall_status
                        or certification_status
                    )
                    certification_timestamp = latest_snapshot.executed_at
        except Exception:
            pass

        return CurrentDatabaseSummary(
            database_name=database_name,
            postgres_version=str(postgres_version) if postgres_version is not None else None,
            docker_container=os.environ.get("POSTGRES_CONTAINER", DEFAULT_POSTGRES_CONTAINER),
            database_size=str(database_size) if database_size is not None else None,
            git_commit=_git_value("rev-parse", "HEAD"),
            git_branch=_git_value("rev-parse", "--abbrev-ref", "HEAD"),
            certification_status=certification_status,
            certification_timestamp=certification_timestamp,
            connection_status=connection_status,
            connection_error=connection_error,
        )

    def list_backup_packages(self) -> tuple[BackupPackageSummary, ...]:
        """Discover backup packages under the configured backup root."""
        configured_database = _configured_database_name()
        if not self.backup_root.exists():
            return ()

        packages: list[BackupPackageSummary] = []
        for manifest_path in self.backup_root.rglob("manifest.txt"):
            package_dir = manifest_path.parent
            try:
                package = self._build_package_summary(
                    package_dir,
                    configured_database=configured_database,
                )
            except ValueError:
                continue
            packages.append(package)
        packages.sort(
            key=lambda package: (
                package.backup_timestamp or "",
                package.path,
            ),
            reverse=True,
        )
        return tuple(packages)

    def load_latest_status(self) -> MigrationOperationStatus | None:
        """Return the latest persisted operation status if present."""
        payload = _read_json_file(self.status_file)
        if payload is None:
            return None
        payload = self._reconcile_stale_operation_payload(payload)
        return _status_from_payload(payload)

    def load_log_tail(
        self,
        *,
        operation: MigrationOperationStatus | None,
        max_lines: int = 120,
    ) -> str | None:
        """Return the tail of the active or latest operation log."""
        if operation is None or not operation.log_path:
            return None
        log_path = Path(operation.log_path)
        if not log_path.is_file():
            return None
        try:
            lines = log_path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return None
        if len(lines) <= max_lines:
            return "\n".join(lines)
        return "\n".join(lines[-max_lines:])

    def latest_status_view(self) -> dict[str, Any]:
        """Return current DB, package, and operation state for the migration tab."""
        operation = self.load_latest_status()
        return {
            "current_database": self.get_current_database_summary(),
            "packages": self.list_backup_packages(),
            "operation": operation,
            "operation_log_tail": self.load_log_tail(operation=operation),
            "active_operation": self.get_active_operation(),
            "restore_blockers": self.restore_blockers(),
            "backup_root": str(self.backup_root),
        }

    def restore_blockers(self) -> tuple[str, ...]:
        """Return active-job blockers that forbid destructive restore."""
        blockers: list[str] = []
        active_operation = self.get_active_operation()
        if active_operation is not None:
            blockers.append("Another database migration operation is already running.")
            return tuple(blockers)

        try:
            with session_scope() as session:
                snapshot = ControlPanelQueries().get_control_panel_snapshot(session)
        except Exception as exc:
            return (f"Could not verify control-panel job state before restore: {exc}",)

        if snapshot.active_job_summary and snapshot.active_job_summary.status in {"pending", "running"}:
            blockers.append("A write-heavy generation job is still active.")
        if snapshot.seed_data_summary.latest_seed_job_is_active:
            blockers.append("A seed preparation job is still active.")
        if snapshot.student_dataset_export_summary.latest_export_job_is_active:
            blockers.append("A student dataset export job is still active.")
        if snapshot.realism_audit_summary.latest_incomplete_job_is_active:
            blockers.append("A release certification job is still active.")
        if snapshot.generation_run_summary and snapshot.generation_run_summary.status == "running":
            blockers.append("A generation run is still active.")
        return tuple(blockers)

    def get_active_operation(self) -> MigrationOperationStatus | None:
        """Return the active operation while also cleaning stale locks."""
        lock_payload = _read_json_file(self.lock_file)
        status = self.load_latest_status()
        if lock_payload is None:
            return None

        pid = _safe_int(lock_payload.get("pid"))
        if status is not None and status.status in TERMINAL_OPERATION_STATUSES:
            self._clear_lock()
            return None
        if pid is not None and _pid_is_running(pid):
            return status
        self._clear_lock()
        return None

    def start_backup(self, *, backup_label: str | None = None) -> MigrationOperationStatus:
        """Launch a detached migration-backup operation."""
        self._ensure_no_active_operation()
        operation_id = _operation_id()
        status_payload = self._initial_status_payload(
            operation_id=operation_id,
            operation_type="backup",
            incoming_backup=None,
        )
        self._write_status(status_payload)
        try:
            process = self._launch_operation(
                operation_id=operation_id,
                operation_type="backup",
                extra_args=["--backup-label", backup_label or ""],
            )
        except Exception:
            self.clear_lock_for_operation(operation_id)
            raise
        status_payload["pid"] = process.pid
        status_payload["message"] = "Migration backup started."
        self._write_status(status_payload)
        self._write_lock(operation_id=operation_id, pid=process.pid)
        return _status_from_payload(status_payload)

    def start_restore(self, *, backup_path: str, confirm_destructive: str | None) -> MigrationOperationStatus:
        """Launch a detached same-name restore operation."""
        if confirm_destructive != "yes":
            raise ValueError(
                "Explicit confirmation is required before replacing the current database."
            )
        self._ensure_no_active_operation()
        package = self.get_package_by_path(backup_path)
        if not package.is_restore_eligible:
            raise ValueError(package.restore_blocker or "Selected package is not restore-eligible.")
        blockers = self.restore_blockers()
        if blockers:
            raise ValueError(blockers[0])

        operation_id = _operation_id()
        status_payload = self._initial_status_payload(
            operation_id=operation_id,
            operation_type="restore",
            incoming_backup=package.path,
        )
        self._write_status(status_payload)
        try:
            process = self._launch_operation(
                operation_id=operation_id,
                operation_type="restore",
                extra_args=["--backup-dir", package.path],
            )
        except Exception:
            self.clear_lock_for_operation(operation_id)
            raise
        status_payload["pid"] = process.pid
        status_payload["message"] = "Classroom database restore started."
        self._write_status(status_payload)
        self._write_lock(operation_id=operation_id, pid=process.pid)
        return _status_from_payload(status_payload)

    def get_package_by_path(self, raw_path: str) -> BackupPackageSummary:
        """Resolve and validate one discovered package path."""
        package_path = self._resolve_backup_path(raw_path)
        return self._build_package_summary(
            package_path,
            configured_database=_configured_database_name(),
        )

    def record_operation_update(self, payload: dict[str, Any]) -> None:
        """Persist one operation status update and maintain the latest pointer."""
        self._write_status(payload)

    def clear_lock_for_operation(self, operation_id: str) -> None:
        """Release the migration lock when the detached process exits."""
        lock_payload = _read_json_file(self.lock_file)
        if lock_payload is None:
            return
        if str(lock_payload.get("operation_id") or "") != operation_id:
            return
        self._clear_lock()

    def _build_package_summary(
        self,
        package_dir: Path,
        *,
        configured_database: str,
    ) -> BackupPackageSummary:
        if not package_dir.is_dir():
            raise ValueError("Backup package directory does not exist.")
        if not _is_relative_to(package_dir, self.backup_root):
            raise ValueError("Backup package path is outside the approved backup root.")

        required_files = (
            package_dir / "database.dump",
            package_dir / "postgres_globals.sql",
            package_dir / "manifest.txt",
            package_dir / "row_counts.csv",
            package_dir / "SHA256SUMS",
        )
        if any(not path.exists() for path in required_files):
            raise ValueError("Backup package is incomplete.")

        manifest = _read_manifest(package_dir / "manifest.txt")
        total_size_bytes = sum(
            path.stat().st_size for path in package_dir.iterdir() if path.is_file()
        )
        database_name = manifest.get("database_name")
        verification_status = manifest.get("verification_status")

        restore_blocker = None
        if verification_status != "VERIFIED":
            restore_blocker = "Backup manifest is not marked VERIFIED."
        elif database_name != configured_database:
            restore_blocker = (
                f"Backup database '{database_name or 'UNKNOWN'}' does not match "
                f"configured database '{configured_database}'."
            )

        return BackupPackageSummary(
            slug=package_dir.name,
            path=str(package_dir),
            relative_path=str(package_dir.relative_to(self.project_root)),
            database_name=database_name,
            postgres_version=manifest.get("postgres_version"),
            backup_timestamp=manifest.get("backup_timestamp"),
            verification_status=verification_status,
            certification_status=manifest.get("certification_status"),
            certification_timestamp=manifest.get("certification_timestamp"),
            git_commit=manifest.get("git_commit"),
            git_branch=manifest.get("git_branch"),
            database_size=manifest.get("database_size"),
            total_size_bytes=total_size_bytes,
            has_freeze_manifest=(package_dir / "FREEZE_MANIFEST.md").is_file(),
            is_safety_backup="classroom_safety" in package_dir.parts,
            is_restore_eligible=restore_blocker is None,
            restore_blocker=restore_blocker,
        )

    def _ensure_no_active_operation(self) -> None:
        active = self.get_active_operation()
        if active is not None:
            raise ValueError("Database migration already in progress.")

    def _launch_operation(
        self,
        *,
        operation_id: str,
        operation_type: str,
        extra_args: list[str],
    ) -> subprocess.Popen[str]:
        self._ensure_paths()
        log_path = self.log_root / f"database_migration_{operation_id}.log"
        command = [
            self.python_executable,
            str(self.runner_script),
            "--operation-id",
            operation_id,
            "--operation-type",
            operation_type,
            *extra_args,
        ]
        log_handle = log_path.open("a", encoding="utf-8")
        try:
            process = subprocess.Popen(
                command,
                cwd=self.project_root,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                text=True,
                start_new_session=True,
                close_fds=True,
            )
        finally:
            log_handle.close()
        return process

    def _initial_status_payload(
        self,
        *,
        operation_id: str,
        operation_type: str,
        incoming_backup: str | None,
    ) -> dict[str, Any]:
        log_path = str(self.log_root / f"database_migration_{operation_id}.log")
        now = _utc_now_iso()
        return {
            "operation_id": operation_id,
            "operation_type": operation_type,
            "status": "queued",
            "current_step": "queued",
            "message": "Operation queued.",
            "started_at": now,
            "updated_at": now,
            "completed_at": None,
            "incoming_backup": incoming_backup,
            "created_backup": None,
            "safety_backup": None,
            "log_path": log_path,
            "error": None,
            "pid": None,
            "requires_manual_rollback": False,
        }

    def _write_status(self, payload: dict[str, Any]) -> None:
        self._ensure_paths()
        payload = dict(payload)
        payload["updated_at"] = _utc_now_iso()
        _write_json_file(self.status_file, payload)
        operation_id = str(payload["operation_id"])
        _write_json_file(self.operations_root / f"{operation_id}.json", payload)

    def _write_lock(self, *, operation_id: str, pid: int | None) -> None:
        self._ensure_paths()
        _write_json_file(
            self.lock_file,
            {
                "operation_id": operation_id,
                "pid": pid,
                "updated_at": _utc_now_iso(),
            },
        )

    def _clear_lock(self) -> None:
        try:
            self.lock_file.unlink()
        except FileNotFoundError:
            pass

    def _reconcile_stale_operation_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        payload = dict(payload)
        if payload.get("status") not in ACTIVE_OPERATION_STATUSES:
            return payload

        status_operation_id = _optional_str(payload.get("operation_id"))
        lock_payload = _read_json_file(self.lock_file)
        if lock_payload is not None:
            lock_operation_id = _optional_str(lock_payload.get("operation_id"))
            if lock_operation_id == status_operation_id:
                pid = _safe_int(lock_payload.get("pid"))
                if pid is not None and _pid_is_running(pid):
                    return payload
            self._clear_lock()

        pid = _safe_int(payload.get("pid"))
        if pid is not None and _pid_is_running(pid):
            return payload

        payload["status"] = "failed"
        payload["error"] = payload.get("error") or STALE_OPERATION_MESSAGE
        payload["message"] = STALE_OPERATION_MESSAGE
        payload["completed_at"] = _optional_str(payload.get("completed_at")) or _utc_now_iso()
        self._write_status(payload)
        return payload

    def _ensure_paths(self) -> None:
        self.runtime_root.mkdir(parents=True, exist_ok=True)
        self.operations_root.mkdir(parents=True, exist_ok=True)
        self.log_root.mkdir(parents=True, exist_ok=True)
        self.backup_root.mkdir(parents=True, exist_ok=True)

    def capture_restore_managed_processes(self) -> tuple[ManagedProcess, ...]:
        """Capture local app processes that may reconnect during restore."""
        managed: list[ManagedProcess] = []
        worker_script = str(self.backend_dir / "scripts" / "run_background_worker.py")
        for pid, command in _iter_process_commands():
            if pid == os.getpid():
                continue
            if worker_script in command:
                managed.append(
                    ManagedProcess(
                        pid=pid,
                        label="durable background worker",
                        command=tuple(command),
                    )
                )
                continue
            if "app.main:app" in command and str(self.backend_dir) in command:
                managed.append(
                    ManagedProcess(
                        pid=pid,
                        label="control panel server",
                        command=tuple(command),
                    )
                )
        managed.sort(key=lambda process: (0 if process.label == "durable background worker" else 1, process.pid))
        return tuple(managed)

    def stop_managed_processes(
        self,
        processes: tuple[ManagedProcess, ...],
    ) -> tuple[ManagedProcess, ...]:
        """Stop app processes before replacing the configured database."""
        stopped: list[ManagedProcess] = []
        for process in processes:
            if not _pid_is_running(process.pid):
                continue
            _terminate_process(process.pid)
            stopped.append(process)
        return tuple(stopped)

    def restart_managed_processes(
        self,
        processes: tuple[ManagedProcess, ...],
    ) -> tuple[int, ...]:
        """Restart previously stopped app processes with their original commands."""
        restarted_pids: list[int] = []
        for process in processes:
            handle = subprocess.Popen(
                list(process.command),
                cwd=self.project_root,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                text=False,
                start_new_session=True,
                close_fds=True,
            )
            restarted_pids.append(handle.pid)
        return tuple(restarted_pids)

    def _resolve_backup_path(self, raw_path: str) -> Path:
        if not raw_path.strip():
            raise ValueError("A backup package path is required.")
        candidate = Path(raw_path)
        if not candidate.is_absolute():
            candidate = (self.project_root / candidate).resolve()
        else:
            candidate = candidate.resolve()
        if not _is_relative_to(candidate, self.backup_root):
            raise ValueError("Backup package must remain under the approved backup root.")
        return candidate


def run_database_migration_operation(
    *,
    operation_id: str,
    operation_type: str,
    backup_dir: str | None = None,
    backup_label: str | None = None,
    service: DatabaseMigrationService | None = None,
) -> int:
    """Execute one background migration operation inside the detached runner."""
    resolved_service = service or DatabaseMigrationService()
    status_payload = _read_json_file(
        resolved_service.operations_root / f"{operation_id}.json"
    ) or resolved_service._initial_status_payload(  # noqa: SLF001
        operation_id=operation_id,
        operation_type=operation_type,
        incoming_backup=backup_dir,
    )
    status_payload["status"] = "running"
    status_payload["message"] = "Operation started."
    status_payload["pid"] = os.getpid()
    resolved_service.record_operation_update(status_payload)
    resolved_service._write_lock(operation_id=operation_id, pid=os.getpid())  # noqa: SLF001

    try:
        if operation_type == "backup":
            _run_backup_operation(
                service=resolved_service,
                status_payload=status_payload,
                backup_label=backup_label,
            )
        elif operation_type == "restore":
            if not backup_dir:
                raise ValueError("backup_dir is required for restore operations.")
            _run_restore_operation(
                service=resolved_service,
                status_payload=status_payload,
                backup_dir=backup_dir,
            )
        else:
            raise ValueError(f"Unsupported operation type: {operation_type}")
    except Exception as exc:
        status_payload["status"] = "failed"
        status_payload["error"] = str(exc)
        status_payload["message"] = str(exc)
        status_payload["completed_at"] = _utc_now_iso()
        resolved_service.record_operation_update(status_payload)
        return 1
    finally:
        resolved_service.clear_lock_for_operation(operation_id)

    status_payload["status"] = "succeeded"
    status_payload["current_step"] = "completed"
    status_payload["message"] = (
        "Migration backup completed successfully."
        if operation_type == "backup"
        else "Classroom database migration completed successfully."
    )
    status_payload["completed_at"] = _utc_now_iso()
    resolved_service.record_operation_update(status_payload)
    return 0


def _run_backup_operation(
    *,
    service: DatabaseMigrationService,
    status_payload: dict[str, Any],
    backup_label: str | None,
) -> None:
    status_payload["current_step"] = "create_backup"
    status_payload["message"] = "Creating migration backup."
    service.record_operation_update(status_payload)
    command = [
        str(service.project_root / "scripts" / "backup_database.sh"),
        "--output-dir",
        str(service.backup_root),
    ]
    output = _run_script_command(
        command,
        parser=lambda line: _apply_script_progress(
            line,
            status_payload=status_payload,
            service=service,
            mapping=BACKUP_PROGRESS_MAP,
        ),
    )
    created_backup = _extract_path_from_output(output, "Backup package:")
    if created_backup is None:
        raise RuntimeError("Backup script did not report a backup package path.")
    if backup_label and backup_label.strip():
        created_backup = _rename_backup_with_label(created_backup, backup_label.strip())
    status_payload["created_backup"] = created_backup
    status_payload["current_step"] = "backup_ready"
    status_payload["message"] = "Migration backup ready."
    service.record_operation_update(status_payload)


def _run_restore_operation(
    *,
    service: DatabaseMigrationService,
    status_payload: dict[str, Any],
    backup_dir: str,
) -> None:
    status_payload["incoming_backup"] = backup_dir
    status_payload["current_step"] = "verify_incoming_backup"
    status_payload["message"] = "Verifying selected migration package."
    service.record_operation_update(status_payload)
    managed_processes = service.capture_restore_managed_processes()
    stopped_processes: tuple[ManagedProcess, ...] = ()
    if managed_processes:
        status_payload["current_step"] = "prepare_restore_environment"
        status_payload["message"] = "Stopping app services before destructive restore."
        service.record_operation_update(status_payload)
        stopped_processes = service.stop_managed_processes(managed_processes)
    command = [
        str(service.project_root / "scripts" / "migrate_classroom_database.sh"),
        "--backup-dir",
        backup_dir,
    ]
    try:
        output = _run_script_command(
            command,
            parser=lambda line: _apply_restore_progress(
                line,
                status_payload=status_payload,
                service=service,
            ),
        )
    finally:
        if stopped_processes:
            status_payload["current_step"] = "restart_application_services"
            status_payload["message"] = "Restarting local control panel services."
            service.record_operation_update(status_payload)
            service.restart_managed_processes(stopped_processes)
    safety_backup = _extract_path_from_output(output, "Safety backup:")
    if safety_backup:
        status_payload["safety_backup"] = safety_backup
    status_payload["current_step"] = "restore_validated"
    status_payload["message"] = "Restore completed and validated."
    service.record_operation_update(status_payload)


BACKUP_PROGRESS_MAP = {
    "Checking PostgreSQL container": ("check_database_connection", "Checking database connection."),
    "Capturing row counts": ("capture_row_counts", "Capturing source row counts."),
    "Creating database.dump": ("create_archive", "Creating PostgreSQL archive."),
    "Creating globals backup": ("capture_globals", "Capturing PostgreSQL globals."),
    "Writing manifest": ("write_manifest", "Writing backup manifest."),
    "Verifying archive readability": ("verify_archive", "Verifying backup archive."),
    "Generating SHA-256 checksums": ("generate_checksums", "Generating checksums."),
}

RESTORE_PROGRESS_MAP = {
    "Verifying incoming backup package": ("verify_incoming_backup", "Verifying incoming migration package."),
    "Creating safety backup of existing classroom database": ("create_safety_backup", "Creating safety backup of the current classroom database."),
    "Verifying safety backup": ("verify_safety_backup", "Verifying safety backup."),
    "Replacing existing classroom database": ("restore_database", "Replacing the configured classroom database."),
    "Validating restored classroom database": ("validate_restored_database", "Validating the restored classroom database."),
}

OPERATION_PROGRESS = {
    "backup": {
        "script_name": "backup_database.sh",
        "steps": (
            "check_database_connection",
            "capture_row_counts",
            "create_archive",
            "capture_globals",
            "write_manifest",
            "verify_archive",
            "generate_checksums",
        ),
    },
    "restore": {
        "script_name": "migrate_classroom_database.sh",
        "steps": (
            "verify_incoming_backup",
            "prepare_restore_environment",
            "create_safety_backup",
            "verify_safety_backup",
            "restore_database",
            "validate_restored_database",
            "restart_application_services",
        ),
    },
}


def _apply_restore_progress(
    line: str,
    *,
    status_payload: dict[str, Any],
    service: DatabaseMigrationService,
) -> None:
    _apply_script_progress(
        line,
        status_payload=status_payload,
        service=service,
        mapping=RESTORE_PROGRESS_MAP,
    )
    if "Safety backup:" in line:
        extracted = _extract_path_from_output(line, "Safety backup:")
        if extracted:
            status_payload["safety_backup"] = extracted
            service.record_operation_update(status_payload)
    if "Replacing existing classroom database" in line:
        status_payload["requires_manual_rollback"] = True
        service.record_operation_update(status_payload)


def _apply_script_progress(
    line: str,
    *,
    status_payload: dict[str, Any],
    service: DatabaseMigrationService,
    mapping: dict[str, tuple[str, str]],
) -> None:
    for needle, (step, message) in mapping.items():
        if needle in line:
            status_payload["current_step"] = step
            status_payload["message"] = message
            service.record_operation_update(status_payload)
            return


def _operation_progress_definition(operation_type: str) -> dict[str, Any] | None:
    return OPERATION_PROGRESS.get(operation_type)


def _run_script_command(
    command: list[str],
    *,
    parser: Any | None = None,
) -> str:
    process = subprocess.Popen(
        command,
        cwd=PROJECT_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    output_lines: list[str] = []
    assert process.stdout is not None
    for line in process.stdout:
        print(line, end="")
        output_lines.append(line)
        if parser is not None:
            parser(line.rstrip("\n"))
    return_code = process.wait()
    output = "".join(output_lines)
    if return_code != 0:
        raise RuntimeError(
            f"Command failed with exit code {return_code}: {' '.join(command)}"
        )
    return output


def _rename_backup_with_label(original_path: str, label: str) -> str:
    original_dir = Path(original_path)
    if not original_dir.is_dir():
        return original_path
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "_", label.strip()).strip("._-")
    if not slug:
        return original_path
    target_dir = original_dir.with_name(f"{slug}_{original_dir.name}")
    if target_dir.exists():
        return original_path
    shutil.move(str(original_dir), str(target_dir))
    return str(target_dir)


def _extract_path_from_output(output: str, prefix: str) -> str | None:
    for raw_line in output.splitlines():
        line = raw_line.strip()
        if prefix not in line:
            continue
        return line.split(prefix, 1)[1].strip()
    return None


def _configured_database_name() -> str:
    settings = load_settings()
    path = urlsplit(settings.database_url).path.strip("/")
    return path or DEFAULT_POSTGRES_DB


def _git_value(*args: str) -> str | None:
    result = subprocess.run(
        ["git", *args],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    value = result.stdout.strip()
    return value or None


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _operation_id() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def _write_json_file(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _read_json_file(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _read_manifest(path: Path) -> dict[str, str]:
    payload: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        if "=" not in raw_line:
            continue
        key, value = raw_line.split("=", 1)
        payload[key.strip()] = value.strip()
    return payload


def _status_from_payload(payload: dict[str, Any]) -> MigrationOperationStatus:
    return MigrationOperationStatus(
        operation_id=str(payload.get("operation_id") or ""),
        operation_type=str(payload.get("operation_type") or ""),
        status=str(payload.get("status") or ""),
        current_step=_optional_str(payload.get("current_step")),
        message=_optional_str(payload.get("message")),
        started_at=_optional_str(payload.get("started_at")),
        updated_at=_optional_str(payload.get("updated_at")),
        completed_at=_optional_str(payload.get("completed_at")),
        incoming_backup=_optional_str(payload.get("incoming_backup")),
        created_backup=_optional_str(payload.get("created_backup")),
        safety_backup=_optional_str(payload.get("safety_backup")),
        log_path=_optional_str(payload.get("log_path")),
        error=_optional_str(payload.get("error")),
        pid=_safe_int(payload.get("pid")),
        requires_manual_rollback=bool(payload.get("requires_manual_rollback")),
    )


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text_value = str(value).strip()
    return text_value or None


def _safe_int(value: Any) -> int | None:
    try:
        if value in (None, ""):
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _pid_is_running(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _iter_process_commands() -> tuple[tuple[int, tuple[str, ...]], ...]:
    processes: list[tuple[int, tuple[str, ...]]] = []
    for proc_dir in Path("/proc").iterdir():
        if not proc_dir.name.isdigit():
            continue
        cmdline_path = proc_dir / "cmdline"
        try:
            raw = cmdline_path.read_bytes()
        except OSError:
            continue
        if not raw:
            continue
        parts = tuple(part.decode("utf-8", errors="ignore") for part in raw.split(b"\0") if part)
        if parts:
            processes.append((int(proc_dir.name), parts))
    return tuple(processes)


def _terminate_process(pid: int) -> None:
    if not _pid_is_running(pid):
        return
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        return
    deadline = time.monotonic() + PROCESS_STOP_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if not _pid_is_running(pid):
            return
        time.sleep(PROCESS_STOP_POLL_INTERVAL_SECONDS)
    try:
        os.kill(pid, signal.SIGKILL)
    except OSError:
        return
    deadline = time.monotonic() + PROCESS_STOP_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if not _pid_is_running(pid):
            return
        time.sleep(PROCESS_STOP_POLL_INTERVAL_SECONDS)
    raise RuntimeError(f"Could not stop process {pid} before restore.")


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True
