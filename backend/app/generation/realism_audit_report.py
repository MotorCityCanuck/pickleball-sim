"""Output shaping helpers for realism audit results."""
from __future__ import annotations

from typing import Any, Sequence

from .realism_audit import RealismAuditResult
from .realism_audit_service import RealismAuditExecution


def execution_to_json_ready(
    execution: RealismAuditExecution,
) -> dict[str, Any]:
    """Serialize one realism-audit execution with scope metadata."""
    return {
        "executed_at": execution.executed_at.isoformat(),
        "generation_run_id": execution.generation_run_id,
        "batch_id": execution.batch_id,
        "batch_month": (
            execution.batch_month.isoformat()
            if execution.batch_month is not None
            else None
        ),
        "results": results_to_json_ready(execution.results),
    }


def results_to_json_ready(
    results: Sequence[RealismAuditResult],
) -> list[dict[str, Any]]:
    """Serialize realism-audit results to JSON-compatible values."""
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


def format_table(rows: Sequence[dict[str, Any]]) -> str:
    """Render rows as a simple aligned plain-text table."""
    headers = list(rows[0].keys())
    normalized_rows = [
        [
            "" if value is None else _display_value(value)
            for value in (row.get(header) for header in headers)
        ]
        for row in rows
    ]
    widths = [
        max(len(str(header)), *(len(str(row[index])) for row in normalized_rows))
        for index, header in enumerate(headers)
    ]
    header_row = " | ".join(
        str(header).ljust(widths[index]) for index, header in enumerate(headers)
    )
    separator = "-+-".join("-" * widths[index] for index in range(len(headers)))
    body = [
        " | ".join(
            str(row[index]).ljust(widths[index]) for index in range(len(headers))
        )
        for row in normalized_rows
    ]
    return "\n".join([header_row, separator, *body])


def _json_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return (
        str(value)
        if not isinstance(value, (str, int, float, bool)) and value is not None
        else value
    )


def _display_value(value: Any) -> str:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)
