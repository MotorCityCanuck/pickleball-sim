"""Rule-based assessment helpers for realism audit snapshots."""
from __future__ import annotations

from typing import Any, Mapping, Sequence

from .release_certification_pillars import RELEASE_CERTIFICATION_PILLAR_MAP


DEFAULT_REALISM_AUDIT_ASSESSMENT_THRESHOLDS: dict[str, float] = {
    "distribution_drift_warning_pct_points": 5.0,
    "distribution_drift_error_pct_points": 10.0,
    "summary_drift_warning_pct_points": 5.0,
    "summary_drift_error_pct_points": 10.0,
    "duplicate_full_name_warning_pct": 1.0,
    "name_alignment_min_reference_pct": 90.0,
    "rating_large_delta_warning_pct": 1.0,
    "rating_large_delta_error_pct": 5.0,
    "rating_outlier_warning_delta": 250.0,
    "unteamed_duration_warning_days": 30.0,
    "competitive_assignment_shortfall_warning_pct_points": 10.0,
    "competitive_assignment_shortfall_error_pct_points": 20.0,
    "historical_baseline_warning_pct": 20.0,
    "historical_baseline_error_pct": 35.0,
    "historical_trend_warning_pct": 15.0,
    "historical_trend_error_pct": 25.0,
    "chemistry_gap_warning": 0.25,
    "chemistry_gap_error": 0.40,
    "chemistry_gap_warning_with_partnership_bias": 0.35,
    "chemistry_gap_error_with_partnership_bias": 0.50,
    "fatigue_reverse_gap_warning": 0.05,
    "fatigue_reverse_gap_error": 0.10,
    "fatigue_reverse_gap_warning_with_fatigue_bias": 0.03,
    "fatigue_reverse_gap_error_with_fatigue_bias": 0.07,
    "rating_predictiveness_warning_min": 0.65,
    "rating_predictiveness_error_min": 0.55,
    "rating_predictiveness_warning_min_with_hidden_bias": 0.60,
    "rating_predictiveness_error_min_with_hidden_bias": 0.50,
    "regional_strength_spread_warning": 400.0,
    "regional_strength_spread_error": 700.0,
    "regional_strength_spread_warning_with_bias": 550.0,
    "regional_strength_spread_error_with_bias": 850.0,
}

_SEVERITY_RANK = {"info": 0, "warning": 1, "error": 2, "blocker": 3}
_SEVERITY_PENALTY = {"info": 0.0, "warning": 10.0, "error": 25.0, "blocker": 25.0}
_CERTIFICATION_POLICY_VERSION = "2026-07-27"
_PASS_SCORE_MIN = 95.0
_PASS_WITH_WARNINGS_SCORE_MIN = 80.0
_REQUIRED_PASS_PILLARS = ("structural_integrity", "export_readiness")
_BLOCKER_QUERIES = frozenset(
    {
        "club_primary_membership_integrity",
        "team_current_roster_integrity",
        "team_membership_date_integrity",
        "match_winner_integrity",
        "match_game_score_integrity",
        "daily_team_match_cap_violations",
        "missing_gold_inputs",
    }
)


def default_realism_audit_assessment_thresholds() -> dict[str, float]:
    """Return a mutable copy of the default assessment thresholds."""
    return dict(DEFAULT_REALISM_AUDIT_ASSESSMENT_THRESHOLDS)


def normalize_realism_audit_assessment_thresholds(
    thresholds: Mapping[str, Any] | None = None,
) -> dict[str, float]:
    """Merge caller-provided threshold values over assessment defaults."""
    normalized = default_realism_audit_assessment_thresholds()
    if not thresholds:
        return normalized
    for key, default_value in DEFAULT_REALISM_AUDIT_ASSESSMENT_THRESHOLDS.items():
        value = _to_float(thresholds.get(key))
        normalized[key] = default_value if value is None else value
    return normalized


def assess_realism_audit_payload(
    payload: Mapping[str, Any],
    *,
    thresholds: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Assess realism audit query results and return UI/report-ready findings."""
    bias_context = _bias_context_from_payload(payload)
    assessment_parameters = _assessment_parameters_from_payload(payload)
    active_thresholds = _apply_bias_aware_threshold_overrides(
        normalize_realism_audit_assessment_thresholds(thresholds),
        bias_context,
    )
    query_assessments = [
        _assess_query_result(
            result,
            active_thresholds,
            bias_context,
            assessment_parameters,
        )
        for result in _iter_query_results(payload.get("results"))
    ]
    query_assessments = [
        _apply_query_policy(assessment)
        for assessment in query_assessments
    ]
    pillar_assessments = _build_pillar_assessments(query_assessments)
    findings = [
        assessment
        for assessment in query_assessments
        if assessment.get("severity") != "info"
    ]
    severity_counts = {"info": 0, "warning": 0, "error": 0, "blocker": 0}
    category_counts: dict[str, int] = {}
    pillar_counts: dict[str, int] = {}
    finding_pillar_counts: dict[str, int] = {}
    for assessment in query_assessments:
        severity = str(assessment.get("severity") or "info")
        severity_counts[severity] = severity_counts.get(severity, 0) + 1
        pillar = str(assessment.get("pillar") or "operational_realism")
        pillar_counts[pillar] = pillar_counts.get(pillar, 0) + 1
        if severity != "info":
            category = str(assessment.get("category") or "general")
            category_counts[category] = category_counts.get(category, 0) + 1
            finding_pillar_counts[pillar] = finding_pillar_counts.get(pillar, 0) + 1

    certification_score = _overall_certification_score(pillar_assessments)
    certification_decision, policy_reasons = _certification_decision_from_policy(
        pillar_assessments,
        query_assessments,
        certification_score,
    )
    overall_status = {
        "FAIL": "significant_realism_concerns",
        "PASS_WITH_WARNINGS": "review_recommended",
        "PASS": "no_material_issues",
    }[certification_decision]
    return {
        "overall_status": overall_status,
        "finding_count": len(findings),
        "severity_counts": severity_counts,
        "pillar_counts": dict(sorted(pillar_counts.items())),
        "finding_pillar_counts": dict(sorted(finding_pillar_counts.items())),
        "category_counts": dict(sorted(category_counts.items())),
        "pillar_assessments": pillar_assessments,
        "certification_score": certification_score,
        "certification_decision": certification_decision,
        "policy_version": _CERTIFICATION_POLICY_VERSION,
        "required_pass_pillars": list(_REQUIRED_PASS_PILLARS),
        "blocker_queries": sorted(_BLOCKER_QUERIES),
        "policy_reasons": policy_reasons,
        "thresholds": active_thresholds,
        "bias_context": bias_context,
        "findings": findings,
        "query_assessments": query_assessments,
    }


def _assess_query_result(
    result: Mapping[str, Any],
    thresholds: Mapping[str, float],
    bias_context: Mapping[str, Any],
    assessment_parameters: Mapping[str, Any],
) -> dict[str, Any]:
    query_name = str(result.get("query") or "unnamed_query")
    category = str(result.get("category") or "general")
    pillar = str(result.get("pillar") or "operational_realism")
    rows = [row for row in result.get("rows") or [] if isinstance(row, Mapping)]
    severity = "info"
    summary = "No material issue detected by the current assessment rules."
    evidence = f"{len(rows)} row{'s' if len(rows) != 1 else ''} returned."
    recommendation = "No action required."

    drift_assessment = _assess_drift(query_name, rows, thresholds)
    if drift_assessment is not None:
        severity, summary, evidence, recommendation = drift_assessment

    configured_assessment = _assess_config_bounds(query_name, rows)
    severity, summary, evidence, recommendation = _pick_assessment(
        (severity, summary, evidence, recommendation),
        configured_assessment,
    )

    name_assessment = _assess_name_quality(query_name, rows, thresholds)
    severity, summary, evidence, recommendation = _pick_assessment(
        (severity, summary, evidence, recommendation),
        name_assessment,
    )

    team_assessment = _assess_team_readiness(
        query_name,
        rows,
        thresholds,
        assessment_parameters,
    )
    severity, summary, evidence, recommendation = _pick_assessment(
        (severity, summary, evidence, recommendation),
        team_assessment,
    )

    simulation_assessment = _assess_simulation_fidelity(
        query_name,
        rows,
        thresholds,
        bias_context,
    )
    severity, summary, evidence, recommendation = _pick_assessment(
        (severity, summary, evidence, recommendation),
        simulation_assessment,
    )

    assignment_assessment = _assess_assignment_readiness(query_name, rows)
    severity, summary, evidence, recommendation = _pick_assessment(
        (severity, summary, evidence, recommendation),
        assignment_assessment,
    )

    export_assessment = _assess_export_readiness(query_name, rows)
    severity, summary, evidence, recommendation = _pick_assessment(
        (severity, summary, evidence, recommendation),
        export_assessment,
    )

    historical_assessment = _assess_historical_regression(
        query_name,
        rows,
        thresholds,
    )
    severity, summary, evidence, recommendation = _pick_assessment(
        (severity, summary, evidence, recommendation),
        historical_assessment,
    )

    rating_assessment = _assess_rating_movement(query_name, rows, thresholds)
    severity, summary, evidence, recommendation = _pick_assessment(
        (severity, summary, evidence, recommendation),
        rating_assessment,
    )

    integrity_assessment = _assess_integrity_counts(query_name, rows)
    severity, summary, evidence, recommendation = _pick_assessment(
        (severity, summary, evidence, recommendation),
        integrity_assessment,
    )

    status = "no_issue" if severity == "info" else "review"
    return {
        "query": query_name,
        "category": category,
        "pillar": pillar,
        "severity": severity,
        "status": status,
        "title": _title_for_query(query_name),
        "summary": summary,
        "evidence": evidence,
        "recommendation": recommendation,
    }


def _assessment_parameters_from_payload(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    parameters = payload.get("parameters")
    return parameters if isinstance(parameters, Mapping) else {}


def _build_pillar_assessments(
    query_assessments: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    assessments_by_pillar: dict[str, list[Mapping[str, Any]]] = {}
    for assessment in query_assessments:
        pillar_key = str(assessment.get("pillar") or "operational_realism")
        assessments_by_pillar.setdefault(pillar_key, []).append(assessment)

    serialized: list[dict[str, Any]] = []
    for pillar_key, pillar in RELEASE_CERTIFICATION_PILLAR_MAP.items():
        pillar_query_assessments = assessments_by_pillar.get(pillar_key, [])
        severity_counts = {"info": 0, "warning": 0, "error": 0, "blocker": 0}
        finding_count = 0
        for assessment in pillar_query_assessments:
            severity = str(assessment.get("severity") or "info")
            severity_counts[severity] = severity_counts.get(severity, 0) + 1
            if severity != "info":
                finding_count += 1
        max_severity = _max_severity(pillar_query_assessments)
        score = _pillar_score(pillar_query_assessments)
        serialized.append(
            {
                "pillar": pillar_key,
                "label": pillar.label,
                "implementation_status": pillar.implementation_status,
                "required_for_pass": pillar_key in _REQUIRED_PASS_PILLARS,
                "query_count": len(pillar_query_assessments),
                "finding_count": finding_count,
                "severity_counts": severity_counts,
                "max_severity": max_severity,
                "score": score,
                "decision": (
                    _certification_decision_for_severity(max_severity)
                    if pillar_query_assessments
                    else "NOT_ASSESSED"
                ),
            }
        )
    return serialized


def _pillar_score(query_assessments: Sequence[Mapping[str, Any]]) -> float | None:
    if not query_assessments:
        return None
    total_penalty = 0.0
    for assessment in query_assessments:
        severity = str(assessment.get("severity") or "info")
        total_penalty += _SEVERITY_PENALTY.get(severity, 0.0)
    average_penalty = total_penalty / len(query_assessments)
    return round(max(0.0, 100.0 - average_penalty), 1)


def _overall_certification_score(
    pillar_assessments: Sequence[Mapping[str, Any]],
) -> float | None:
    weighted_score_total = 0.0
    weighted_query_total = 0
    for assessment in pillar_assessments:
        query_count = int(assessment.get("query_count") or 0)
        score = assessment.get("score")
        implementation_status = str(assessment.get("implementation_status") or "planned")
        if implementation_status != "implemented" or query_count <= 0 or score is None:
            continue
        weighted_score_total += float(score) * query_count
        weighted_query_total += query_count
    if weighted_query_total <= 0:
        return None
    return round(weighted_score_total / weighted_query_total, 1)


def _certification_decision_for_severity(max_severity: str) -> str:
    return {
        "info": "PASS",
        "warning": "PASS_WITH_WARNINGS",
        "error": "FAIL",
        "blocker": "FAIL",
    }[max_severity]


def _certification_decision_from_policy(
    pillar_assessments: Sequence[Mapping[str, Any]],
    query_assessments: Sequence[Mapping[str, Any]],
    certification_score: float | None,
) -> tuple[str, list[str]]:
    reasons: list[str] = []
    decision = "PASS"

    blocker_findings = [
        str(assessment.get("query") or "")
        for assessment in query_assessments
        if str(assessment.get("severity") or "info") == "blocker"
    ]
    if blocker_findings:
        reasons.append(
            "Blocker findings were detected in: " + ", ".join(sorted(blocker_findings)) + "."
        )
        decision = "FAIL"

    assessments_by_pillar = {
        str(assessment.get("pillar") or ""): assessment for assessment in pillar_assessments
    }
    failing_pillars = [
        str(assessment.get("label") or assessment.get("pillar") or "")
        for assessment in pillar_assessments
        if str(assessment.get("implementation_status") or "planned") == "implemented"
        and str(assessment.get("decision") or "NOT_ASSESSED") == "FAIL"
    ]
    if failing_pillars:
        reasons.append(
            "Implemented certification pillars failed: " + ", ".join(sorted(failing_pillars)) + "."
        )
        decision = "FAIL"

    if certification_score is not None and certification_score < _PASS_WITH_WARNINGS_SCORE_MIN:
        reasons.append(
            f"Certification score {certification_score:.1f} is below the fail threshold of {_PASS_WITH_WARNINGS_SCORE_MIN:.1f}."
        )
        decision = "FAIL"

    required_warning = False
    for pillar_key in _REQUIRED_PASS_PILLARS:
        assessment = assessments_by_pillar.get(pillar_key)
        if assessment is None:
            continue
        if int(assessment.get("query_count") or 0) <= 0:
            continue
        pillar_decision = str(assessment.get("decision") or "NOT_ASSESSED")
        label = str(assessment.get("label") or pillar_key)
        if pillar_decision == "FAIL":
            reasons.append(f"Required pillar {label} failed.")
            return "FAIL", reasons
        if pillar_decision != "PASS":
            required_warning = True
            reasons.append(f"Required pillar {label} did not achieve a clean pass.")

    if certification_score is not None and certification_score < _PASS_SCORE_MIN:
        reasons.append(
            f"Certification score {certification_score:.1f} is below the clean pass threshold of {_PASS_SCORE_MIN:.1f}."
        )
        if decision != "FAIL":
            decision = "PASS_WITH_WARNINGS"

    if any(str(assessment.get("severity") or "info") != "info" for assessment in query_assessments):
        reasons.append("One or more non-blocker findings require operator review.")
        if decision != "FAIL":
            decision = "PASS_WITH_WARNINGS"

    if required_warning:
        if decision != "FAIL":
            decision = "PASS_WITH_WARNINGS"

    if not reasons:
        reasons.append("All implemented pillars passed and no blocking findings were detected.")
    return decision, reasons


def _apply_query_policy(assessment: Mapping[str, Any]) -> dict[str, Any]:
    normalized = dict(assessment)
    query_name = str(normalized.get("query") or "")
    severity = str(normalized.get("severity") or "info")
    if query_name not in _BLOCKER_QUERIES or severity not in {"warning", "error"}:
        return normalized

    normalized["severity"] = "blocker"
    normalized["status"] = "review"
    normalized["policy_blocker"] = True

    summary = str(normalized.get("summary") or "").rstrip()
    if summary:
        normalized["summary"] = (
            summary + " This query is release-blocking under the certification policy."
        )

    recommendation = str(normalized.get("recommendation") or "").rstrip()
    blocker_recommendation = "Resolve this issue before certifying the release."
    if recommendation:
        if blocker_recommendation not in recommendation:
            normalized["recommendation"] = recommendation + " " + blocker_recommendation
    else:
        normalized["recommendation"] = blocker_recommendation

    return normalized


def _assess_drift(
    query_name: str,
    rows: Sequence[Mapping[str, Any]],
    thresholds: Mapping[str, float],
) -> tuple[str, str, str, str] | None:
    drift_values: list[float] = []
    for row in rows:
        for key, value in row.items():
            if key.endswith("pct_point_drift"):
                drift = _to_float(value)
                if drift is not None:
                    drift_values.append(abs(drift))
    if not drift_values:
        return None

    max_drift = max(drift_values)
    if query_name.endswith("_summary") or "summary" in query_name:
        warning = thresholds["summary_drift_warning_pct_points"]
        error = thresholds["summary_drift_error_pct_points"]
    else:
        warning = thresholds["distribution_drift_warning_pct_points"]
        error = thresholds["distribution_drift_error_pct_points"]
    severity = _severity_for_thresholds(max_drift, warning=warning, error=error)
    if severity == "info":
        return (
            "info",
            "Observed percentages are within configured assessment drift tolerance.",
            f"Maximum absolute drift is {max_drift:.2f} percentage points.",
            "No action required.",
        )
    return (
        severity,
        "Observed distribution drift exceeds the assessment tolerance.",
        f"Maximum absolute drift is {max_drift:.2f} percentage points; warning starts at {warning:.2f}, error at {error:.2f}.",
        "Review the related generation weights or verify that this amount of sampling variance is acceptable.",
    )


def _assess_config_bounds(
    query_name: str,
    rows: Sequence[Mapping[str, Any]],
) -> tuple[str, str, str, str] | None:
    outside_rows = sum(1 for row in rows if _to_bool(row.get("outside_config_range")))
    if outside_rows:
        return (
            "warning",
            "A measured value is outside its configured realism bounds.",
            f"{outside_rows} row{'s' if outside_rows != 1 else ''} reported outside_config_range.",
            "Review the configuration bounds and the generated batch distribution.",
        )

    if query_name == "club_fill_ratio_summary":
        over_capacity = max((_to_float(row.get("over_capacity_club_count")) or 0 for row in rows), default=0)
        if over_capacity > 0:
            return (
                "warning",
                "One or more clubs exceed the configured maximum fill ratio.",
                f"{int(over_capacity)} club{'s' if int(over_capacity) != 1 else ''} are over capacity.",
                "Review club capacity settings or player club allocation behavior.",
            )
    if query_name == "club_fill_ratio_outliers":
        over_limit = 0
        for row in rows:
            fill_ratio = _to_float(row.get("fill_ratio"))
            configured = _to_float(row.get("configured_max_fill_ratio"))
            if fill_ratio is not None and configured is not None and fill_ratio > configured:
                over_limit += 1
        if over_limit:
            return (
                "warning",
                "The highest-loaded club outliers exceed the configured fill ratio.",
                f"{over_limit} displayed outlier row{'s' if over_limit != 1 else ''} exceed the configured maximum.",
                "Review the outlier clubs before export if club capacity realism matters for this dataset.",
            )
    return None


def _assess_name_quality(
    query_name: str,
    rows: Sequence[Mapping[str, Any]],
    thresholds: Mapping[str, float],
) -> tuple[str, str, str, str] | None:
    if query_name == "player_name_uniqueness_summary":
        duplicate_pct = max(
            (
                _to_float(row.get("duplicate_full_name_pct"))
                or _to_float(row.get("max_full_name_player_pct"))
                or 0
                for row in rows
            ),
            default=0,
        )
        warning = thresholds["duplicate_full_name_warning_pct"]
        if duplicate_pct >= warning:
            return (
                "warning",
                "Duplicate full-name concentration exceeds the assessment tolerance.",
                f"Duplicate full-name share is {duplicate_pct:.2f}%; warning starts at {warning:.2f}%.",
                "Review generated name diversity and the first/last-name reference mix.",
            )
        return (
            "info",
            "Duplicate full-name concentration is within assessment tolerance.",
            f"Duplicate full-name share is {duplicate_pct:.2f}%.",
            "No action required.",
        )
    if query_name in {"player_first_name_alignment", "player_last_name_alignment"}:
        reference_pct = _alignment_reference_pct(rows)
        warning = thresholds["name_alignment_min_reference_pct"]
        if reference_pct is not None and reference_pct < warning:
            return (
                "warning",
                "Name reference alignment is below the assessment minimum.",
                f"Reference-aligned share is {reference_pct:.2f}%; expected at least {warning:.2f}%.",
                "Review state/year/gender name reference coverage and fallback usage.",
            )
        if reference_pct is not None:
            return (
                "info",
                "Name reference alignment meets the assessment minimum.",
                f"Reference-aligned share is {reference_pct:.2f}%.",
                "No action required.",
            )
    return None


def _assess_team_readiness(
    query_name: str,
    rows: Sequence[Mapping[str, Any]],
    thresholds: Mapping[str, float],
    parameters: Mapping[str, Any],
) -> tuple[str, str, str, str] | None:
    if query_name == "team_assignment_delay_summary":
        player_count = max(
            (_to_float(row.get("player_count")) or 0.0 for row in rows),
            default=0.0,
        )
        ever_teamed = max(
            (_to_float(row.get("ever_teamed_player_count")) or 0.0 for row in rows),
            default=0.0,
        )
        unresolved = max(
            (_to_float(row.get("still_unteamed_player_count")) or 0.0 for row in rows),
            default=0.0,
        )
        avg_days = max(
            (_to_float(row.get("avg_days_to_first_team")) or 0.0 for row in rows),
            default=0.0,
        )
        target_rate = (
            (_to_float(parameters.get("player_team_participation_rate")) or 0.0)
            * (_to_float(parameters.get("competitive_team_rate")) or 0.0)
        )
        observed_rate = 0.0 if player_count <= 0 else ever_teamed / player_count
        shortfall_pct_points = max(0.0, (target_rate - observed_rate) * 100.0)
        duration_warning = thresholds["unteamed_duration_warning_days"]
        shortfall_warning = thresholds[
            "competitive_assignment_shortfall_warning_pct_points"
        ]
        shortfall_error = thresholds[
            "competitive_assignment_shortfall_error_pct_points"
        ]
        shortfall_severity = _severity_for_thresholds(
            shortfall_pct_points,
            warning=shortfall_warning,
            error=shortfall_error,
        )
        if shortfall_severity != "info":
            return (
                shortfall_severity,
                "Competitive-team assignment coverage is below the configured model target.",
                (
                    f"Observed competitive assignment rate is {observed_rate * 100.0:.2f}% "
                    f"versus configured target {target_rate * 100.0:.2f}%; "
                    f"{int(unresolved)} active players remain outside competitive teams as of the batch."
                ),
                "Review competitive-team formation volume and assignment eligibility against the configured competitive-team share.",
            )
        if ever_teamed > 0 and avg_days >= duration_warning:
            return (
                "warning",
                "Competitive-team assignment is slower than the assessment tolerance for players who do enter the competitive roster pool.",
                (
                    f"Average time to first competitive team is {avg_days:.0f} days; "
                    f"configured warning threshold is {duration_warning:.0f} days."
                ),
                "Review competitive-team onboarding cadence rather than treating unresolved non-competitive players as defects.",
            )
        return (
            "info",
            "Competitive-team assignment coverage is consistent with the configured team-formation model.",
            (
                f"Observed competitive assignment rate is {observed_rate * 100.0:.2f}% "
                f"versus configured target {target_rate * 100.0:.2f}%."
            ),
            "No action required.",
        )
    return None


def _assess_simulation_fidelity(
    query_name: str,
    rows: Sequence[Mapping[str, Any]],
    thresholds: Mapping[str, float],
    bias_context: Mapping[str, Any],
) -> tuple[str, str, str, str] | None:
    if query_name == "chemistry_effectiveness":
        max_gap = max(
            (abs(_to_float(row.get("win_rate_minus_expected")) or 0.0) for row in rows),
            default=0.0,
        )
        severity = _severity_for_thresholds(
            max_gap,
            warning=thresholds["chemistry_gap_warning"],
            error=thresholds["chemistry_gap_error"],
        )
        if severity != "info":
            suffix = (
                " Partnership-affinity bias is active, so certification is using wider chemistry tolerances."
                if bias_context.get("partnership_affinity_bias_enabled")
                else ""
            )
            return (
                severity,
                "Observed chemistry effects diverge materially from expected match outcomes.",
                f"Maximum absolute win-rate gap versus expectation is {max_gap:.3f}.",
                "Review chemistry weighting and whether partnership effects are over- or under-expressed."
                + suffix,
            )
        return (
            "info",
            "Observed chemistry effects are directionally consistent with expected outcomes.",
            f"Maximum absolute win-rate gap versus expectation is {max_gap:.3f}.",
            "No action required.",
        )
    if query_name == "fatigue_effectiveness":
        load_map = {str(row.get("workload_band")): _to_float(row.get("avg_score_share_delta")) for row in rows}
        low = load_map.get("0")
        high = load_map.get("2_plus")
        if low is not None and high is not None:
            reverse_gap = high - low
            severity = _severity_for_thresholds(
                reverse_gap,
                warning=thresholds["fatigue_reverse_gap_warning"],
                error=thresholds["fatigue_reverse_gap_error"],
            )
            if severity != "info":
                suffix = (
                    " Fatigue bias is active, so certification is using stricter fatigue tolerances."
                    if bias_context.get("fatigue_bias_enabled")
                    else ""
                )
                return (
                    severity,
                    "Higher recent match load is not reducing performance as expected by the fatigue model.",
                    f"High-load score-share delta exceeds zero-load delta by {reverse_gap:.4f}.",
                    "Review fatigue penalties and recent-load lookback behavior."
                    + suffix,
                )
        return None
    if query_name == "confidence_stability":
        delta_024 = _row_value_for_key(rows, "confidence_band", "0_24", "avg_abs_rating_delta")
        delta_75 = _row_value_for_key(rows, "confidence_band", "75_plus", "avg_abs_rating_delta")
        if delta_024 is not None and delta_75 is not None:
            reverse_gap = delta_75 - delta_024
            severity = _severity_for_thresholds(reverse_gap, warning=5.0, error=15.0)
            if severity != "info":
                return (
                    severity,
                    "High-confidence players are not showing more stable rating movement than low-confidence players.",
                    f"High-confidence average absolute rating delta exceeds low-confidence delta by {reverse_gap:.3f}.",
                    "Review confidence stabilization and rating-update damping behavior.",
                )
        return None
    if query_name == "volatility_decay":
        novice = _row_value_for_key(rows, "experience_band", "0_4", "avg_volatility_score")
        veteran = _row_value_for_key(rows, "experience_band", "10_plus", "avg_volatility_score")
        if novice is not None and veteran is not None:
            reverse_gap = veteran - novice
            severity = _severity_for_thresholds(reverse_gap, warning=0.01, error=0.05)
            if severity != "info":
                return (
                    severity,
                    "Observed volatility is not decaying with player experience.",
                    f"Veteran volatility exceeds novice volatility by {reverse_gap:.4f}.",
                    "Review volatility decay and match-count experience handling.",
                )
        return None
    if query_name == "rating_predictiveness":
        high_bucket = _row_value_for_key(rows, "prediction_bucket", "80_plus", "favorite_win_rate")
        if high_bucket is not None:
            if high_bucket < thresholds["rating_predictiveness_error_min"]:
                return (
                    "error",
                    "High-confidence rating predictions are performing poorly.",
                    f"Favorite win rate in the 80+ bucket is {high_bucket:.3f}.",
                    "Review prediction calibration and the rating-to-match simulation bridge."
                    + (
                        " Hidden performance biases are active, so certification is allowing a lower prediction floor."
                        if bias_context.get("hidden_bias_enabled")
                        else ""
                    ),
                )
            if high_bucket < thresholds["rating_predictiveness_warning_min"]:
                return (
                    "warning",
                    "High-confidence rating predictions are weaker than expected.",
                    f"Favorite win rate in the 80+ bucket is {high_bucket:.3f}.",
                    "Review rating predictiveness and probability calibration."
                    + (
                        " Hidden performance biases are active, so certification is allowing a lower prediction floor."
                        if bias_context.get("hidden_bias_enabled")
                        else ""
                    ),
                )
        return None
    if query_name == "regional_strength_balance":
        avg_ratings = [
            _to_float(row.get("avg_rating"))
            for row in rows
            if _to_float(row.get("avg_rating")) is not None
        ]
        if len(avg_ratings) >= 2:
            spread = max(avg_ratings) - min(avg_ratings)
            severity = _severity_for_thresholds(
                spread,
                warning=thresholds["regional_strength_spread_warning"],
                error=thresholds["regional_strength_spread_error"],
            )
            if severity != "info":
                return (
                    severity,
                    "Regional strength spread is wider than expected.",
                    f"Average rating spread across rated regions is {spread:.1f}.",
                    "Review regional multipliers and geographic strength calibration."
                    + (
                        " Regional-strength bias is active, so certification is using wider regional spread tolerances."
                        if bias_context.get("regional_strength_bias_enabled")
                        else ""
                    ),
                )
        return None
    if query_name == "team_dissolution_rate":
        max_event_pct = max(
            (_to_float(row.get("event_pct_of_formed_teams")) or 0.0 for row in rows),
            default=0.0,
        )
        severity = _severity_for_thresholds(max_event_pct, warning=50.0, error=75.0)
        if severity != "info":
            return (
                severity,
                "Team lifecycle churn is unusually high relative to formed teams.",
                f"Maximum lifecycle event rate is {max_event_pct:.2f}% of formed teams.",
                "Review team persistence, dormancy, and retirement logic.",
            )
        return None
    if query_name == "repeat_partner_frequency":
        one_match_pct = _row_value_for_key(rows, "repeat_match_count", 1, "partnership_pct")
        has_repeat_partnerships = any((_to_float(row.get("repeat_match_count")) or 0) > 1 for row in rows)
        if one_match_pct is not None and one_match_pct >= 80.0 and not has_repeat_partnerships:
            return (
                "warning",
                "Partnership continuity is low across the generated match set.",
                f"{one_match_pct:.2f}% of partnerships appear only once and no repeat partnerships were observed.",
                "Review persistence, partner selection, and candidate reuse behavior.",
            )
        return None
    if query_name == "repeat_opponent_rate":
        repeated_pct = sum(
            _to_float(row.get("matchup_pair_pct")) or 0.0
            for row in rows
            if (_to_float(row.get("meeting_count")) or 0.0) >= 3
        )
        severity = _severity_for_thresholds(repeated_pct, warning=20.0, error=40.0)
        if severity != "info":
            return (
                severity,
                "Repeated opponent matchups are too concentrated.",
                f"{repeated_pct:.2f}% of matchup pairs meet three or more times.",
                "Review opponent selection and match-pairing variety.",
            )
        return None
    return None


def _bias_context_from_payload(payload: Mapping[str, Any]) -> dict[str, bool]:
    parameters = payload.get("parameters")
    if not isinstance(parameters, Mapping):
        parameters = {}
    return {
        "hidden_bias_enabled": bool(parameters.get("hidden_bias_enabled")),
        "fatigue_bias_enabled": bool(parameters.get("fatigue_bias_enabled")),
        "regional_strength_bias_enabled": bool(parameters.get("regional_strength_bias_enabled")),
        "partnership_affinity_bias_enabled": bool(parameters.get("partnership_affinity_bias_enabled")),
        "age_advantage_bias_enabled": bool(parameters.get("age_advantage_bias_enabled")),
        "experience_bias_enabled": bool(parameters.get("experience_bias_enabled")),
    }


def _apply_bias_aware_threshold_overrides(
    thresholds: dict[str, float],
    bias_context: Mapping[str, Any],
) -> dict[str, float]:
    adjusted = dict(thresholds)
    if bias_context.get("partnership_affinity_bias_enabled"):
        adjusted["chemistry_gap_warning"] = adjusted[
            "chemistry_gap_warning_with_partnership_bias"
        ]
        adjusted["chemistry_gap_error"] = adjusted[
            "chemistry_gap_error_with_partnership_bias"
        ]
    if bias_context.get("fatigue_bias_enabled"):
        adjusted["fatigue_reverse_gap_warning"] = adjusted[
            "fatigue_reverse_gap_warning_with_fatigue_bias"
        ]
        adjusted["fatigue_reverse_gap_error"] = adjusted[
            "fatigue_reverse_gap_error_with_fatigue_bias"
        ]
    if bias_context.get("hidden_bias_enabled"):
        adjusted["rating_predictiveness_warning_min"] = adjusted[
            "rating_predictiveness_warning_min_with_hidden_bias"
        ]
        adjusted["rating_predictiveness_error_min"] = adjusted[
            "rating_predictiveness_error_min_with_hidden_bias"
        ]
    if bias_context.get("regional_strength_bias_enabled"):
        adjusted["regional_strength_spread_warning"] = adjusted[
            "regional_strength_spread_warning_with_bias"
        ]
        adjusted["regional_strength_spread_error"] = adjusted[
            "regional_strength_spread_error_with_bias"
        ]
    return adjusted


def _assess_assignment_readiness(
    query_name: str,
    rows: Sequence[Mapping[str, Any]],
) -> tuple[str, str, str, str] | None:
    if query_name == "candidate_depth_by_country_division":
        min_depth = min(
            (_to_float(row.get("candidate_team_count")) or 0.0 for row in rows),
            default=0.0,
        )
        if min_depth < 1:
            return (
                "error",
                "At least one country/division candidate pool has no eligible teams.",
                f"Minimum candidate-team depth is {min_depth:.0f}.",
                "Review team generation and candidate eligibility before assignment workflows use this release.",
            )
        if min_depth < 2:
            return (
                "warning",
                "At least one country/division candidate pool has shallow team depth.",
                f"Minimum candidate-team depth is {min_depth:.0f}.",
                "Review candidate-pool depth and whether alternates are sufficient.",
            )
        return None
    if query_name == "elite_player_depth":
        min_count = min(
            (_to_float(row.get("elite_player_count")) or 0.0 for row in rows),
            default=0.0,
        )
        if min_count < 1:
            return (
                "warning",
                "One or more country/division pools have no elite players.",
                f"Minimum elite-player depth is {min_count:.0f}.",
                "Review upper-tail player strength and roster depth for assignment use cases.",
            )
        return None
    if query_name == "elite_team_depth":
        min_count = min(
            (_to_float(row.get("elite_team_count")) or 0.0 for row in rows),
            default=0.0,
        )
        if min_count < 1:
            return (
                "warning",
                "One or more country/division pools have no elite teams.",
                f"Minimum elite-team depth is {min_count:.0f}.",
                "Review team-strength concentration and partnership formation quality.",
            )
        return None
    if query_name == "alternate_candidate_depth":
        min_count = min(
            (_to_float(row.get("alternate_team_count")) or 0.0 for row in rows),
            default=0.0,
        )
        if min_count < 1:
            return (
                "warning",
                "One or more country/division pools lack alternate teams beyond the top slot.",
                f"Minimum alternate-team depth is {min_count:.0f}.",
                "Review candidate depth and fallback coverage for assignment workflows.",
            )
        return None
    return None


def _assess_export_readiness(
    query_name: str,
    rows: Sequence[Mapping[str, Any]],
) -> tuple[str, str, str, str] | None:
    if query_name == "missing_gold_inputs":
        missing = [str(row.get("table_name")) for row in rows if _to_float(row.get("missing_flag")) == 1.0]
        if missing:
            return (
                "error",
                "Required Gold or export input tables are missing data.",
                f"Missing coverage detected for: {', '.join(sorted(missing))}.",
                "Complete source-data generation before treating this release as export-ready.",
            )
        return None
    if query_name == "student_candidate_availability":
        min_pct = min(
            (_to_float(row.get("fully_rated_team_pct")) or 0.0 for row in rows),
            default=100.0,
        )
        min_count = min(
            (_to_float(row.get("fully_rated_team_count")) or 0.0 for row in rows),
            default=0.0,
        )
        if min_count < 1:
            return (
                "error",
                "At least one country/division has no fully rated candidate teams for student release workflows.",
                f"Minimum fully rated team count is {min_count:.0f}.",
                "Review rating coverage and candidate roster completeness before export.",
            )
        if min_pct < 100.0:
            return (
                "warning",
                "Some candidate pools are only partially rated for student release workflows.",
                f"Minimum fully rated candidate-team coverage is {min_pct:.2f}%.",
                "Review rating completeness for active candidate rosters.",
            )
        return None
    if query_name == "division_balance":
        max_share = max(
            (_to_float(row.get("team_pct_within_country")) or 0.0 for row in rows),
            default=0.0,
        )
        severity = _severity_for_thresholds(max_share, warning=85.0, error=95.0)
        if severity != "info":
            return (
                severity,
                "Active-team distribution is heavily concentrated in a single division within at least one country.",
                f"Maximum within-country division share is {max_share:.2f}%.",
                "Review division balance before releasing the dataset to students.",
            )
        return None
    return None


def _assess_historical_regression(
    query_name: str,
    rows: Sequence[Mapping[str, Any]],
    thresholds: Mapping[str, float],
) -> tuple[str, str, str, str] | None:
    if query_name == "historical_run_size_regression":
        growth_values: list[float] = []
        for row in rows:
            for key in ("player_growth_pct", "team_growth_pct", "match_growth_pct"):
                value = _to_float(row.get(key))
                if value is not None:
                    growth_values.append(abs(value))
        max_growth = max(growth_values, default=0.0)
        severity = _severity_for_thresholds(max_growth, warning=25.0, error=50.0)
        if severity != "info":
            return (
                severity,
                "Current run size differs materially from prior runs.",
                f"Maximum absolute growth across player, team, and match counts is {max_growth:.2f}%.",
                "Review whether current release scale is intentionally different from the established baseline.",
            )
        return None
    if query_name == "historical_baseline_scale_regression":
        if not rows:
            return (
                "warning",
                "No baseline release comparison data was available.",
                "The historical baseline regression query returned no rows.",
                "Confirm that at least one prior successful baseline release exists before relying on historical certification checks.",
            )

        row = rows[0]
        baseline_run_id = _to_float(row.get("baseline_generation_run_id"))
        baseline_release_name = str(row.get("baseline_release_name") or "prior baseline release")
        if baseline_run_id is None:
            return (
                "warning",
                "No prior baseline release is available for regression comparison.",
                "The current release does not have a completed earlier baseline release to compare against.",
                "Create or retain a successful baseline release before using baseline regression as a certification signal.",
            )

        baseline_deltas = [
            abs(value)
            for value in (
                _to_float(row.get("player_delta_vs_baseline_pct")),
                _to_float(row.get("team_delta_vs_baseline_pct")),
                _to_float(row.get("match_delta_vs_baseline_pct")),
            )
            if value is not None
        ]
        trend_deltas = [
            abs(value)
            for value in (
                _to_float(row.get("player_delta_vs_trend_pct")),
                _to_float(row.get("team_delta_vs_trend_pct")),
                _to_float(row.get("match_delta_vs_trend_pct")),
            )
            if value is not None
        ]
        max_baseline_delta = max(baseline_deltas, default=0.0)
        max_trend_delta = max(trend_deltas, default=0.0)

        baseline_severity = _severity_for_thresholds(
            max_baseline_delta,
            warning=thresholds["historical_baseline_warning_pct"],
            error=thresholds["historical_baseline_error_pct"],
        )
        trend_severity = _severity_for_thresholds(
            max_trend_delta,
            warning=thresholds["historical_trend_warning_pct"],
            error=thresholds["historical_trend_error_pct"],
        )
        severity = baseline_severity
        if _SEVERITY_RANK[trend_severity] > _SEVERITY_RANK[severity]:
            severity = trend_severity

        prior_run_count = int(_to_float(row.get("prior_run_count")) or 0)
        evidence = (
            f"Baseline release {baseline_release_name} compared player/team/match deltas of "
            f"{_display_number(_to_float(row.get('player_delta_vs_baseline_pct')))}%, "
            f"{_display_number(_to_float(row.get('team_delta_vs_baseline_pct')))}%, "
            f"and {_display_number(_to_float(row.get('match_delta_vs_baseline_pct')))}%; "
            f"trend comparison uses {prior_run_count} prior run{'s' if prior_run_count != 1 else ''} "
            f"with max delta {_display_number(max_trend_delta)}%."
        )
        if severity != "info":
            return (
                severity,
                "Current release scale differs materially from the historical baseline or recent trend.",
                evidence,
                "Review whether the current release intentionally diverges from the baseline package and recent run trend before certification.",
            )
        return (
            "info",
            "Current release scale remains within configured historical regression tolerances.",
            evidence,
            "No action required.",
        )
    if query_name == "historical_release_file_coverage":
        if any(str(row.get("status") or "") != "succeeded" for row in rows):
            return (
                "error",
                "Historical release file coverage includes incomplete releases.",
                "At least one historical release is not marked succeeded.",
                "Review release history and baseline selection before using regression comparisons.",
            )
        if any((_to_float(row.get("file_count")) or 0.0) <= 0 for row in rows):
            return (
                "error",
                "Historical release file coverage includes releases with no exported files.",
                "At least one historical release has zero exported files.",
                "Repair or exclude incomplete historical releases before regression comparisons.",
            )
        if any((_to_float(row.get("total_row_count")) or 0.0) <= 0 for row in rows):
            return (
                "error",
                "Historical release file coverage includes releases with zero exported rows.",
                "At least one historical release has zero total exported rows.",
                "Repair or exclude incomplete historical releases before regression comparisons.",
            )
        return None
    return None


def _display_number(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.2f}"


def _assess_rating_movement(
    query_name: str,
    rows: Sequence[Mapping[str, Any]],
    thresholds: Mapping[str, float],
) -> tuple[str, str, str, str] | None:
    if query_name == "rating_delta_summary":
        large_delta_pct = max((_to_float(row.get("large_delta_pct")) or 0 for row in rows), default=0)
        warning = thresholds["rating_large_delta_warning_pct"]
        error = thresholds["rating_large_delta_error_pct"]
        severity = _severity_for_thresholds(large_delta_pct, warning=warning, error=error)
        if severity != "info":
            return (
                severity,
                "Large rating movements exceed the assessment tolerance.",
                f"Large-delta share is {large_delta_pct:.2f}%; warning starts at {warning:.2f}%, error at {error:.2f}%.",
                "Review rating volatility settings and rating update logs for the batch.",
            )
        return (
            "info",
            "Large rating movements are within assessment tolerance.",
            f"Large-delta share is {large_delta_pct:.2f}%.",
            "No action required.",
        )
    if query_name == "rating_outlier_players":
        max_delta = max(
            (
                _to_float(row.get("abs_rating_delta"))
                or _to_float(row.get("max_abs_rating_delta"))
                or 0
                for row in rows
            ),
            default=0,
        )
        configured = max(
            (_to_float(row.get("configured_warning_threshold")) or 0 for row in rows),
            default=0,
        )
        warning = configured or thresholds["rating_outlier_warning_delta"]
        if max_delta >= warning:
            return (
                "warning",
                "Rating outliers exceed the configured or assessment warning threshold.",
                f"Maximum absolute rating delta is {max_delta:.2f}; warning starts at {warning:.2f}.",
                "Inspect the largest outlier players and confirm rating volatility is intentional.",
            )
    return None


def _assess_integrity_counts(
    query_name: str,
    rows: Sequence[Mapping[str, Any]],
) -> tuple[str, str, str, str] | None:
    if query_name == "club_primary_membership_integrity":
        issue_count = 0
        for row in rows:
            issue_count += int(_to_float(row.get("multi_primary_player_count")) or 0)
        if issue_count:
            return (
                "error",
                "Primary club membership integrity issues were found.",
                f"{issue_count} player{'s' if issue_count != 1 else ''} have multiple primary club memberships.",
                "Fix multi-primary club assignment logic or review the generated memberships before export.",
            )
    if query_name == "daily_team_match_cap_violations" and rows:
        return (
            "error",
            "Teams exceeded the configured same-day match cap.",
            f"{len(rows)} violation row{'s' if len(rows) != 1 else ''} returned.",
            "Review match scheduling constraints before relying on this batch for student-facing data.",
        )
    if query_name in {
        "team_current_roster_integrity",
        "team_membership_date_integrity",
        "match_winner_integrity",
        "match_game_score_integrity",
    }:
        if rows:
            return (
                "error",
                "Structural integrity violations were found in the generated dataset.",
                f"{len(rows)} integrity issue row{'s' if len(rows) != 1 else ''} returned.",
                "Review the affected lifecycle or score-consistency records before certifying this release.",
            )
        return (
            "info",
            "No structural integrity violations were detected by this query.",
            "0 integrity issue rows returned.",
            "No action required.",
        )
    return None


def _pick_assessment(
    current: tuple[str, str, str, str],
    candidate: tuple[str, str, str, str] | None,
) -> tuple[str, str, str, str]:
    if candidate is None:
        return current
    if _SEVERITY_RANK[candidate[0]] > _SEVERITY_RANK[current[0]]:
        return candidate
    if current[0] == "info" and candidate[0] == "info" and current[1].startswith("No material"):
        return candidate
    return current


def _iter_query_results(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _alignment_reference_pct(rows: Sequence[Mapping[str, Any]]) -> float | None:
    total = 0.0
    reference = 0.0
    for row in rows:
        count = _to_float(row.get("player_count") or row.get("count"))
        pct = _to_float(row.get("player_pct") or row.get("pct"))
        bucket = str(row.get("alignment_bucket") or "").lower()
        if count is not None:
            total += count
            if "reference" in bucket or "exact" in bucket or "state" in bucket:
                reference += count
        elif pct is not None and ("reference" in bucket or "exact" in bucket or "state" in bucket):
            reference += pct
    if total > 0:
        return reference * 100.0 / total
    return reference if reference > 0 else None


def _row_value_for_key(
    rows: Sequence[Mapping[str, Any]],
    key_field: str,
    key_value: object,
    value_field: str,
) -> float | None:
    for row in rows:
        if row.get(key_field) == key_value:
            return _to_float(row.get(value_field))
    return None


def _severity_for_thresholds(value: float, *, warning: float, error: float) -> str:
    if value >= error:
        return "error"
    if value >= warning:
        return "warning"
    return "info"


def _max_severity(assessments: Sequence[Mapping[str, Any]]) -> str:
    max_seen = "info"
    for assessment in assessments:
        severity = str(assessment.get("severity") or "info")
        if _SEVERITY_RANK.get(severity, 0) > _SEVERITY_RANK[max_seen]:
            max_seen = severity
    return max_seen


def _title_for_query(query_name: str) -> str:
    return query_name.replace("_", " ").title()


def _to_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return False
