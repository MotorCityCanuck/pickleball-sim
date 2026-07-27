"""Output shaping helpers for realism audit and release certification results."""
from __future__ import annotations

from typing import Any, Sequence

from .realism_audit import RealismAuditResult
from .realism_audit_assessment import assess_realism_audit_payload
from .release_certification_pillars import (
    RELEASE_CERTIFICATION_PILLAR_MAP,
    serialize_release_certification_pillars,
)
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
        "pillars": serialize_release_certification_pillars(),
        "executed_at": execution.executed_at.isoformat(),
        "generation_run_id": execution.generation_run_id,
        "batch_id": execution.batch_id,
        "batch_month": (
            execution.batch_month.isoformat()
            if execution.batch_month is not None
            else None
        ),
        "parameters": _json_value(dict(execution.parameters)),
        "results": results_to_json_ready(execution.results),
    }
    payload["implemented_pillars"] = [
        pillar["key"]
        for pillar in payload["pillars"]
        if pillar.get("implementation_status") == "implemented"
    ]
    payload["planned_pillars"] = [
        pillar["key"]
        for pillar in payload["pillars"]
        if pillar.get("implementation_status") != "implemented"
    ]
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
                "pillar": result.query.pillar,
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
    assessment = payload.get("assessment")
    if not isinstance(assessment, dict):
        assessment = assess_realism_audit_payload(payload)

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
    pillar_counts: dict[str, int] = {}
    for result in results:
        category = str(result.get("category") or "general")
        category_counts[category] = category_counts.get(category, 0) + 1
        pillar_key = str(result.get("pillar") or "operational_realism")
        pillar_counts[pillar_key] = pillar_counts.get(pillar_key, 0) + 1

    lines.extend(_executive_summary_markdown_lines(payload, assessment))
    lines.extend(
        _certification_dashboard_markdown_lines(
            assessment,
            pillar_counts,
            category_counts,
        )
    )
    lines.extend(_findings_by_pillar_markdown_lines(assessment))
    lines.extend(_recommendations_markdown_lines(assessment))
    lines.extend(_release_comparison_markdown_lines(payload, assessment))
    lines.extend(_certification_decision_markdown_lines(assessment))
    lines.extend(_assessment_markdown_lines(assessment))
    lines.extend(_query_results_markdown_lines(results))

    return "\n".join(lines).rstrip() + "\n"


def _executive_summary_markdown_lines(
    payload: dict[str, Any],
    assessment: dict[str, Any],
) -> list[str]:
    lines = ["## Executive Summary", ""]
    lines.append(
        f"- Certification decision: {_display_markdown_value(assessment.get('certification_decision'))}"
    )
    lines.append(
        f"- Certification score: {_display_markdown_value(assessment.get('certification_score'))}"
    )
    lines.append(
        f"- Policy version: {_display_markdown_value(assessment.get('policy_version'))}"
    )
    lines.append(
        f"- Overall status: {_display_markdown_value(assessment.get('overall_status'))}"
    )
    lines.append(
        f"- Findings requiring review: {_display_markdown_value(assessment.get('finding_count'))}"
    )
    lines.append(
        f"- Generation run ID: {_display_markdown_value(payload.get('generation_run_id'))}"
    )
    lines.append(f"- Batch ID: {_display_markdown_value(payload.get('batch_id'))}")
    lines.append("")
    return lines


def _certification_dashboard_markdown_lines(
    assessment: dict[str, Any],
    pillar_counts: dict[str, int],
    category_counts: dict[str, int],
) -> list[str]:
    lines = ["## Certification Dashboard", ""]
    pillar_assessments = assessment.get("pillar_assessments")
    if isinstance(pillar_assessments, list) and pillar_assessments:
        lines.append("### Pillar Scores")
        lines.append("")
        for pillar_assessment in pillar_assessments:
            if not isinstance(pillar_assessment, dict):
                continue
            lines.append(
                "- "
                f"{_display_markdown_value(pillar_assessment.get('label'))}: "
                f"score {_display_markdown_value(pillar_assessment.get('score'))}, "
                f"decision {_display_markdown_value(pillar_assessment.get('decision'))}, "
                f"queries {_display_markdown_value(pillar_assessment.get('query_count'))}, "
                f"findings {_display_markdown_value(pillar_assessment.get('finding_count'))}"
            )
        lines.append("")
    if pillar_counts:
        lines.append("### Pillar Coverage")
        lines.append("")
        for pillar_key, count in sorted(pillar_counts.items()):
            pillar = RELEASE_CERTIFICATION_PILLAR_MAP.get(pillar_key)
            pillar_label = pillar.label if pillar is not None else pillar_key
            lines.append(f"- {pillar_label}: {count} query{'ies' if count != 1 else ''}")
        lines.append("")
    lines.append("### Query Categories")
    lines.append("")
    for category, count in sorted(category_counts.items()):
        lines.append(f"- {category}: {count} query{'ies' if count != 1 else ''}")
    lines.append("")
    return lines


def _findings_by_pillar_markdown_lines(assessment: dict[str, Any]) -> list[str]:
    lines = ["## Findings by Pillar", ""]
    findings = assessment.get("findings")
    if not isinstance(findings, list) or not findings:
        lines.extend(["No assessment findings exceeded the configured thresholds.", ""])
        return lines

    findings_by_pillar: dict[str, list[dict[str, Any]]] = {}
    for finding in findings:
        if not isinstance(finding, dict):
            continue
        pillar_key = str(finding.get("pillar") or "operational_realism")
        findings_by_pillar.setdefault(pillar_key, []).append(finding)

    for pillar_key, pillar_findings in sorted(findings_by_pillar.items()):
        lines.append(f"### {_display_pillar_label(pillar_key)}")
        lines.append("")
        for finding in pillar_findings:
            lines.append(
                "- "
                f"{_display_markdown_value(finding.get('title'))} "
                f"({_display_markdown_value(finding.get('severity'))})"
            )
            lines.append(
                f"  - Query: `{_display_markdown_value(finding.get('query'))}`"
            )
            lines.append(
                f"  - Summary: {_display_markdown_value(finding.get('summary'))}"
            )
            lines.append(
                f"  - Evidence: {_display_markdown_value(finding.get('evidence'))}"
            )
        lines.append("")
    return lines


def _recommendations_markdown_lines(assessment: dict[str, Any]) -> list[str]:
    lines = ["## Recommendations", ""]
    findings = assessment.get("findings")
    if not isinstance(findings, list) or not findings:
        lines.extend(
            ["No recommendations were generated because no material findings were detected.", ""]
        )
        return lines

    recommendations: list[str] = []
    seen: set[str] = set()
    for finding in findings:
        if not isinstance(finding, dict):
            continue
        recommendation = str(finding.get("recommendation") or "").strip()
        if not recommendation or recommendation in seen:
            continue
        seen.add(recommendation)
        recommendations.append(recommendation)

    if not recommendations:
        lines.extend(["No recommendations were generated from the current findings.", ""])
        return lines

    for recommendation in recommendations:
        lines.append(f"- {recommendation}")
    lines.append("")
    return lines


def _release_comparison_markdown_lines(
    payload: dict[str, Any],
    assessment: dict[str, Any],
) -> list[str]:
    lines = ["## Release Comparison", ""]
    release_comparison = payload.get("release_comparison")
    if isinstance(release_comparison, list) and release_comparison:
        for item in release_comparison:
            if not isinstance(item, dict):
                continue
            lines.append(
                "- "
                f"{_display_markdown_value(item.get('label'))}: "
                f"{_display_markdown_value(item.get('summary'))}"
            )
        lines.append("")
        return lines

    synthesized_release_comparison = _release_comparison_from_results(
        payload.get("results")
    )
    if synthesized_release_comparison:
        for item in synthesized_release_comparison:
            lines.append(
                "- "
                f"{_display_markdown_value(item.get('label'))}: "
                f"{_display_markdown_value(item.get('summary'))}"
            )
        lines.append("")
        return lines

    historical_findings = [
        finding
        for finding in assessment.get("findings") or []
        if isinstance(finding, dict)
        and str(finding.get("pillar") or "") == "historical_regression"
    ]
    if historical_findings:
        for finding in historical_findings:
            lines.append(
                "- "
                f"{_display_markdown_value(finding.get('title'))}: "
                f"{_display_markdown_value(finding.get('summary'))}"
            )
        lines.append("")
        return lines

    lines.extend(["No release comparison data is included in this snapshot.", ""])
    return lines


def _release_comparison_from_results(results: Any) -> list[dict[str, str]]:
    if not isinstance(results, list):
        return []
    for result in results:
        if not isinstance(result, dict):
            continue
        if str(result.get("query") or "") != "historical_baseline_scale_regression":
            continue
        rows = result.get("rows")
        if not isinstance(rows, list) or not rows:
            continue
        row = rows[0]
        if not isinstance(row, dict):
            continue

        baseline_name = row.get("baseline_release_name")
        baseline_run_id = row.get("baseline_generation_run_id")
        if baseline_name is None and baseline_run_id is None:
            return [
                {
                    "label": "Historical baseline",
                    "summary": "No prior successful baseline release was available for comparison.",
                }
            ]

        return [
            {
                "label": "Previous baseline release",
                "summary": (
                    f"{_display_markdown_value(baseline_name)} "
                    f"(run {_display_markdown_value(baseline_run_id)})"
                ),
            },
            {
                "label": "Scale delta vs baseline",
                "summary": (
                    "players "
                    f"{_display_pct(row.get('player_delta_vs_baseline_pct'))}, "
                    "teams "
                    f"{_display_pct(row.get('team_delta_vs_baseline_pct'))}, "
                    "matches "
                    f"{_display_pct(row.get('match_delta_vs_baseline_pct'))}"
                ),
            },
            {
                "label": "Scale delta vs recent trend",
                "summary": (
                    f"compared against {_display_markdown_value(row.get('prior_run_count'))} prior runs: "
                    "players "
                    f"{_display_pct(row.get('player_delta_vs_trend_pct'))}, "
                    "teams "
                    f"{_display_pct(row.get('team_delta_vs_trend_pct'))}, "
                    "matches "
                    f"{_display_pct(row.get('match_delta_vs_trend_pct'))}"
                ),
            },
        ]
    return []


def _certification_decision_markdown_lines(assessment: dict[str, Any]) -> list[str]:
    lines = ["## Certification Decision", ""]
    lines.append(
        f"- Decision: {_display_markdown_value(assessment.get('certification_decision'))}"
    )
    lines.append(
        f"- Score: {_display_markdown_value(assessment.get('certification_score'))}"
    )
    lines.append(
        f"- Status basis: {_display_markdown_value(assessment.get('overall_status'))}"
    )
    lines.append("")
    return lines


def _query_results_markdown_lines(results: Sequence[dict[str, Any]]) -> list[str]:
    lines = ["## Query Results", ""]
    for result in results:
        query_name = str(result.get("query") or "unnamed_query")
        description = str(result.get("description") or "")
        category = str(result.get("category") or "general")
        pillar_key = str(result.get("pillar") or "operational_realism")
        pillar = RELEASE_CERTIFICATION_PILLAR_MAP.get(pillar_key)
        scope = str(result.get("scope") or "")
        rows = result.get("rows") or []

        lines.append(f"## {query_name}")
        lines.append("")
        if description:
            lines.append(description)
            lines.append("")
        if pillar is not None:
            lines.append(f"- Pillar: {pillar.label}")
        else:
            lines.append(f"- Pillar: {pillar_key}")
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
    return lines


def _assessment_markdown_lines(assessment: dict[str, Any]) -> list[str]:
    lines = ["## Assessment Summary", ""]
    lines.append(
        f"- Certification decision: {_display_markdown_value(assessment.get('certification_decision'))}"
    )
    lines.append(
        f"- Certification score: {_display_markdown_value(assessment.get('certification_score'))}"
    )
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
    policy_reasons = assessment.get("policy_reasons")
    if isinstance(policy_reasons, list) and policy_reasons:
        lines.append("- Policy reasons:")
        for reason in policy_reasons:
            lines.append(f"  - {_display_markdown_value(reason)}")
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
            lines.append(f"- Pillar: {_display_markdown_value(_display_pillar_label(finding.get('pillar')))}")
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
                f"{_display_markdown_value(_display_pillar_label(query_assessment.get('pillar')))} / "
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


def _display_pillar_label(value: Any) -> str:
    pillar_key = str(value or "operational_realism")
    pillar = RELEASE_CERTIFICATION_PILLAR_MAP.get(pillar_key)
    return pillar.label if pillar is not None else pillar_key


def _display_pct(value: Any) -> str:
    rendered = _display_markdown_value(value)
    if rendered == "n/a":
        return rendered
    return f"{rendered}%"
