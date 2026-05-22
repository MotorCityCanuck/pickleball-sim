"""Filesystem-backed persistence helpers for realism audit snapshots."""
from __future__ import annotations

import json
from pathlib import Path

from .realism_audit_report import execution_to_json_ready
from .realism_audit_service import RealismAuditExecution


DEFAULT_REALISM_AUDIT_SNAPSHOT_DIR = Path("data/realism_audit_snapshots")


def save_realism_audit_snapshot(
    execution: RealismAuditExecution,
    *,
    snapshot_dir: str | Path = DEFAULT_REALISM_AUDIT_SNAPSHOT_DIR,
) -> Path:
    """Persist one realism-audit execution as a JSON snapshot."""
    base_dir = Path(snapshot_dir)
    target_dir = base_dir / _generation_run_dirname(execution.generation_run_id)
    target_dir.mkdir(parents=True, exist_ok=True)

    snapshot_path = target_dir / build_realism_audit_snapshot_filename(execution)
    payload = execution_to_json_ready(execution)
    payload["snapshot_path"] = str(snapshot_path)
    payload["snapshot_version"] = 1
    payload["query_count"] = len(execution.results)

    snapshot_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return snapshot_path


def build_realism_audit_snapshot_filename(execution: RealismAuditExecution) -> str:
    """Return a stable filename keyed to run, batch, batch month, and execution time."""
    run_token = (
        f"run_{execution.generation_run_id:06d}"
        if execution.generation_run_id is not None
        else "run_unknown"
    )
    batch_token = (
        f"batch_{execution.batch_id:06d}"
        if execution.batch_id is not None
        else "batch_unknown"
    )
    month_token = (
        execution.batch_month.isoformat()
        if execution.batch_month is not None
        else "batch-month-unknown"
    )
    timestamp_token = execution.executed_at.strftime("%Y%m%dT%H%M%SZ")
    return f"{run_token}_{batch_token}_{month_token}_{timestamp_token}.json"


def _generation_run_dirname(generation_run_id: int | None) -> str:
    if generation_run_id is None:
        return "generation_run_unknown"
    return f"generation_run_{generation_run_id:06d}"
