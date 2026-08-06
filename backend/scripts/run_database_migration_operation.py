"""Detached runner for control-panel database migration operations."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.database_migration import run_database_migration_operation  # noqa: E402


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description="Run one detached database migration control-panel operation."
    )
    parser.add_argument("--operation-id", required=True)
    parser.add_argument(
        "--operation-type",
        required=True,
        choices=("backup", "restore"),
    )
    parser.add_argument("--backup-dir")
    parser.add_argument("--backup-label")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint."""
    args = parse_args(argv)
    return run_database_migration_operation(
        operation_id=args.operation_id,
        operation_type=args.operation_type,
        backup_dir=args.backup_dir,
        backup_label=args.backup_label,
    )


if __name__ == "__main__":
    raise SystemExit(main())
