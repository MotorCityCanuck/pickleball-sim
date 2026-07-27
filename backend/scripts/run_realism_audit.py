"""Run the legacy realism-audit entry point for release certification."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.db.session import session_scope  # noqa: E402
from app.generation import (  # noqa: E402
    DEFAULT_REALISM_AUDIT_SNAPSHOT_DIR,
    RealismAuditService,
    format_table,
    results_to_json_ready,
    save_realism_audit_snapshot,
)


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run named release-certification SQL checks against generated pickleball data."
        )
    )
    parser.add_argument(
        "--query",
        action="append",
        dest="queries",
        help="Named certification query to run. Repeat to run multiple named queries.",
    )
    parser.add_argument(
        "--format",
        choices=("table", "json"),
        default="table",
        help="Output format for results.",
    )
    parser.add_argument(
        "--list-queries",
        action="store_true",
        help="List available certification queries and exit.",
    )
    parser.add_argument(
        "--snapshot-dir",
        default=str(DEFAULT_REALISM_AUDIT_SNAPSHOT_DIR),
        help=(
            "Directory where JSON release-certification snapshots should be saved. "
            "Defaults to data/realism_audit_snapshots."
        ),
    )
    parser.add_argument(
        "--no-save-snapshot",
        action="store_true",
        help="Run certification without persisting a JSON snapshot to disk.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    with session_scope() as session:
        service = RealismAuditService(session)
        if args.list_queries:
            for query in service.available_queries():
                print(
                    f"{query.name}\t{query.scope}\t{query.category}\t{query.description}"
                )
            return

        execution = service.run(
            query_names=args.queries,
        )
        snapshot_path = None
        if not args.no_save_snapshot:
            snapshot_path = save_realism_audit_snapshot(
                execution,
                snapshot_dir=args.snapshot_dir,
            )
        if args.format == "json":
            print(
                json.dumps(
                    results_to_json_ready(execution.results),
                    indent=2,
                    sort_keys=True,
                )
            )
            if snapshot_path is not None:
                print(
                    f"[release-certification] snapshot saved to {snapshot_path}",
                    file=sys.stderr,
                )
            return

        for result in execution.results:
            print(f"[{result.query.name}] {result.query.description}")
            if not result.rows:
                print("(no rows)")
                continue
            print(format_table(result.rows))
            print("")
        if snapshot_path is not None:
            print(
                f"[release-certification] snapshot saved to {snapshot_path}",
                file=sys.stderr,
            )


if __name__ == "__main__":
    main()
