"""Output shaping helpers for realism audit and release certification results."""
from __future__ import annotations

from typing import Any, Sequence

from .realism_audit import RealismAuditResult
from .realism_audit_assessment import assess_realism_audit_payload
from .realism_audit_service import RealismAuditExecution


def execution_to_json_ready(
    execution: RealismAuditExecution,
    *,
    assessment_thresholds: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Serialize one release-certification execution with scope metadata."""
    payload = {
        "process_type": "release_certification",
        "framework_name": "NAPA Release Certification Framework",
        "framework_version": "2.0",
        "implemented_pillars": ["operational_realism"],
        "planned_pillars": [
            "structural_integrity",
            "simulation_fidelity",
            "assignment_readiness",
            "export_readiness",
            "historical_regression",
        ],
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
    payload["assessment"] = assess_realism_audit_payload(
        payload,
        thresholds=assessment_thresholds,
    )
    return payload


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


def execution_to_markdown(
    execution: RealismAuditExecution,
    *,
    assessment_thresholds: dict[str, Any] | None = None,
) -> str:
    """Render one release-certification execution as a markdown report."""
    return snapshot_payload_to_markdown(
        execution_to_json_ready(
            execution,
            assessment_thresholds=assessment_thresholds,
        )
    )


def snapshot_payload_to_markdown(payload: dict[str, Any]) -> str:
    """Render a JSON-ready release-certification payload as a markdown report."""
    lines = [
        "# Release Certification Report",
        "",
        f"- Framework: {_display_markdown_value(payload.get('framework_name') or 'NAPA Release Certification Framework')}",
        f"- Framework version: {_display_markdown_value(payload.get('framework_version') or '2.0')}",
        f"- Process type: {_display_markdown_value(payload.get('process_type') or 'release_certification')}",
        f"- Executed at: {_display_markdown_value(payload.get('executed_at'))}",
        f"- Generation run ID: {_display_markdown_value(payload.get('generation_run_id'))}",
        f"- Batch ID: {_display_markdown_value(payload.get('batch_id'))}",
        f"- Batch month: {_display_markdown_value(payload.get('batch_month'))}",
        f"- Query count: {_display_markdown_value(payload.get('query_count', len(payload.get('results') or [])))}",
    ]
    snapshot_path = payload.get("snapshot_path")
    if snapshot_path:
        lines.append(f"- Source snapshot: `{snapshot_path}`")
    implemented_pillars = payload.get("implemented_pillars")
    if isinstance(implemented_pillars, list) and implemented_pillars:
        lines.append(
            "- Implemented pillars: "
            + ", ".join(str(pillar) for pillar in implemented_pillars)
        )
    planned_pillars = payload.get("planned_pillars")
    if isinstance(planned_pillars, list) and planned_pillars:
        lines.append(
            "- Planned pillars: "
            + ", ".join(str(pillar) for pillar in planned_pillars)
        )
    lines.append("")

    results = payload.get("results") or []
    if not results:
        lines.extend(["No certification results were found.", ""])
        return "\n".join(lines).rstrip() + "\n"

    category_counts: dict[str, int] = {}
    for result in results:
        category = str(result.get("category") or "general")
        category_counts[category] = category_counts.get(category, 0) + 1

    lines.append("## Certification Summary")
    lines.append("")
    for category, count in sorted(category_counts.items()):
        lines.append(f"- {category}: {count} query{'ies' if count != 1 else ''}")
    lines.append("")

    assessment = payload.get("assessment")
    if not isinstance(assessment, dict):
        assessment = assess_realism_audit_payload(payload)
    lines.extend(_assessment_markdown_lines(assessment))

    for result in results:
        query_name = str(result.get("query") or "unnamed_query")
        description = str(result.get("description") or "")
        category = str(result.get("category") or "general")
        scope = str(result.get("scope") or "")
        rows = result.get("rows") or []

        lines.append(f"## {query_name}")
        lines.append("")
        if description:
            lines.append(description)
            lines.append("")
        lines.append(f"- Category: {category}")
        if scope:
            lines.append(f"- Scope: {scope}")
        lines.append(f"- Row count: {len(rows)}")
        lines.append("")
        if rows:
            normalized_rows = [
                {
                    str(key): _display_value(value)
                    for key, value in dict(row).items()
                }
                for row in rows
                if isinstance(row, dict)
            ]
            if normalized_rows:
                lines.append("```text")
                lines.append(format_table(normalized_rows))
                lines.append("```")
                lines.append("")
        else:
            lines.append("(no rows)")
            lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _assessment_markdown_lines(assessment: dict[str, Any]) -> list[str]:
    lines = ["## Assessment Summary", ""]
    lines.append(
        f"- Overall status: {_display_markdown_value(assessment.get('overall_status'))}"
    )
    lines.append(
        f"- Finding count: {_display_markdown_value(assessment.get('finding_count'))}"
    )
    severity_counts = assessment.get("severity_counts")
    if isinstance(severity_counts, dict):
        lines.append(
            "- Severity counts: "
            + ", ".join(
                f"{severity}: {count}"
                for severity, count in sorted(severity_counts.items())
            )
        )
    lines.append("")

    findings = assessment.get("findings")
    if isinstance(findings, list) and findings:
        lines.append("## Assessment Findings")
        lines.append("")
        for finding in findings:
            if not isinstance(finding, dict):
                continue
            lines.append(
                f"### {_display_markdown_value(finding.get('title'))}"
            )
            lines.append("")
            lines.append(f"- Severity: {_display_markdown_value(finding.get('severity'))}")
            lines.append(f"- Category: {_display_markdown_value(finding.get('category'))}")
            lines.append(f"- Query: `{_display_markdown_value(finding.get('query'))}`")
            lines.append(f"- Summary: {_display_markdown_value(finding.get('summary'))}")
            lines.append(f"- Evidence: {_display_markdown_value(finding.get('evidence'))}")
            lines.append(
                f"- Recommendation: {_display_markdown_value(finding.get('recommendation'))}"
            )
            lines.append("")
    else:
        lines.extend(["No assessment findings exceeded the configured thresholds.", ""])

    query_assessments = assessment.get("query_assessments")
    if isinstance(query_assessments, list) and query_assessments:
        lines.append("## Query Assessment Index")
        lines.append("")
        for query_assessment in query_assessments:
            if not isinstance(query_assessment, dict):
                continue
            lines.append(
                "- "
                f"`{_display_markdown_value(query_assessment.get('query'))}`: "
                f"{_display_markdown_value(query_assessment.get('severity'))} - "
                f"{_display_markdown_value(query_assessment.get('summary'))}"
            )
        lines.append("")
    return lines


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


def _display_markdown_value(value: Any) -> str:
    if value is None:
        return "n/a"
    return _display_value(value)
