"""Run reusable realism-audit SQL checks against generated data."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Sequence


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.db.session import session_scope  # noqa: E402
from app.generation import RealismAuditRunner  # noqa: E402


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run named realism-audit SQL checks against generated pickleball data."
        )
    )
    parser.add_argument(
        "--query",
        action="append",
        dest="queries",
        help="Named audit query to run. Repeat to run multiple named queries.",
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
        help="List available audit queries and exit.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    with session_scope() as session:
        runner = RealismAuditRunner(session)
        if args.list_queries:
            for query in runner.available_queries():
                print(
                    f"{query.name}\t{query.scope}\t{query.category}\t{query.description}"
                )
            return

        results = runner.run(
            query_names=args.queries,
        )
        if args.format == "json":
            print(json.dumps(_json_ready(results), indent=2, sort_keys=True))
            return

        for result in results:
            print(f"[{result.query.name}] {result.query.description}")
            if not result.rows:
                print("(no rows)")
                continue
            print(_format_table(result.rows))
            print("")


def _json_ready(results: Sequence[Any]) -> list[dict[str, Any]]:
    serialized: list[dict[str, Any]] = []
    for result in results:
        serialized.append(
            {
                "query": result.query.name,
                "scope": result.query.scope,
                "category": result.query.category,
                "description": result.query.description,
                "tags": list(result.query.tags),
                "related_config_keys": list(result.query.related_config_keys),
                "rows": [_json_value(row) for row in result.rows],
            }
        )
    return serialized


def _json_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value) if not isinstance(value, (str, int, float, bool)) and value is not None else value


def _format_table(rows: Sequence[dict[str, Any]]) -> str:
    headers = list(rows[0].keys())
    normalized_rows = [
        ["" if value is None else _display_value(value) for value in (row.get(header) for header in headers)]
        for row in rows
    ]
    widths = [
        max(len(str(header)), *(len(str(row[index])) for row in normalized_rows))
        for index, header in enumerate(headers)
    ]
    header_row = " | ".join(str(header).ljust(widths[index]) for index, header in enumerate(headers))
    separator = "-+-".join("-" * widths[index] for index in range(len(headers)))
    body = [
        " | ".join(str(row[index]).ljust(widths[index]) for index in range(len(headers)))
        for row in normalized_rows
    ]
    return "\n".join([header_row, separator, *body])


def _display_value(value: Any) -> str:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


if __name__ == "__main__":
    main()
