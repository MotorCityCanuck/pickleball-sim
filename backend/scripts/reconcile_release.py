"""Reconcile a released Parquet dataset with the simulator database."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sqlalchemy.exc import OperationalError

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.reconciliation import (  # noqa: E402
    ReconciliationConfigError,
    load_reconciliation_config,
    run_reconciliation,
)
from app.reconciliation.comparator import print_console_summary  # noqa: E402
from app.reconciliation.config import with_overrides  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Reconcile released NAPA Parquet source files against PostgreSQL."
    )
    parser.add_argument("--config", required=True, help="YAML or JSON reconciliation config path.")
    parser.add_argument("--entity", action="append", default=[], help="Limit to one entity; may be repeated.")
    parser.add_argument("--tournament-only", action="store_true", help="Limit to tournament-critical entities.")
    parser.add_argument("--counts-only", action="store_true", help="Only compare file/table presence and counts.")
    parser.add_argument("--output-dir", help="Override result output directory.")
    parser.add_argument("--fail-fast", action="store_true", help="Stop after the first failing entity.")
    parser.add_argument("--verbose", action="store_true", help="Print per-entity progress.")
    args = parser.parse_args(argv)

    config = load_reconciliation_config(args.config)
    entities = tuple(args.entity)
    if args.tournament_only:
        critical_entities = tuple(mapping.entity for mapping in config.mappings if mapping.critical)
        entities = tuple(dict.fromkeys([*entities, *critical_entities])) if entities else critical_entities
    config = with_overrides(
        config,
        entities=entities,
        output_directory=Path(args.output_dir).expanduser().resolve() if args.output_dir else None,
    )
    try:
        result = run_reconciliation(
            config,
            counts_only=args.counts_only,
            fail_fast=args.fail_fast,
            verbose=args.verbose,
        )
    except ReconciliationConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2
    except OperationalError as exc:
        print("Database connection error:", file=sys.stderr)
        print(str(exc.orig or exc).strip(), file=sys.stderr)
        print(
            "Check the database host, port, user, database name, and NAPA_DB_PASSWORD.",
            file=sys.stderr,
        )
        return 2
    print_console_summary(result)
    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
