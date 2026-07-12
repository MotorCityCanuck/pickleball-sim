"""Validation helpers for injected export tables."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from .config import (
    ISSUE_TYPE_DUPLICATE_LIKE_ROWS,
    DataQualityInjectionConfig,
    level_profile,
)
from .rules import (
    CATEGORICAL_RATE_ISSUES,
    FIELD_RATE_ISSUES,
    ROW_RATE_ISSUES,
    primary_key_column,
    protected_columns,
    required_columns,
)


class DataQualityValidationError(RuntimeError):
    """Raised when injected tables violate export-layer safety rules."""

    def __init__(self, message: str, result: "DataQualityInjectionValidationResult"):
        super().__init__(message)
        self.result = result


@dataclass(frozen=True)
class DataQualityValidationCheck:
    """One export-layer validation result."""

    name: str
    status: str
    message: str
    details: Mapping[str, Any]


@dataclass(frozen=True)
class DataQualityInjectionValidationResult:
    """Structured validation result for one injected release."""

    status: str
    checks: tuple[DataQualityValidationCheck, ...]

    @property
    def failed_checks(self) -> tuple[DataQualityValidationCheck, ...]:
        return tuple(check for check in self.checks if check.status != "passed")


def validate_injected_tables(
    *,
    original_table_row_counts: Mapping[str, int],
    injected_tables: Mapping[str, list[dict[str, Any]]],
    config: DataQualityInjectionConfig,
    summary,
    manifest_entries: Iterable[Any] = (),
) -> DataQualityInjectionValidationResult:
    """Validate that injected tables remain safe and bounded."""

    checks: list[DataQualityValidationCheck] = []
    manifest_entries_tuple = tuple(manifest_entries)
    checks.extend(_validate_column_shapes(original_table_row_counts, injected_tables))
    checks.extend(_validate_row_counts(original_table_row_counts, injected_tables, summary))
    checks.extend(_validate_primary_key_uniqueness(injected_tables))
    checks.extend(_validate_required_fields(manifest_entries_tuple))
    checks.extend(_validate_protected_fields(manifest_entries_tuple))
    checks.extend(_validate_relationships(injected_tables))
    checks.extend(_validate_issue_rates(original_table_row_counts, config, summary))

    failed = [check for check in checks if check.status != "passed"]
    if failed:
        result = DataQualityInjectionValidationResult(
            status="failed",
            checks=tuple(checks),
        )
        failed_names = ", ".join(check.name for check in failed[:5])
        if len(failed) > 5:
            failed_names += ", ..."
        raise DataQualityValidationError(
            f"Data quality injection validation failed: {failed_names}",
            result,
        )
    return DataQualityInjectionValidationResult(status="passed", checks=tuple(checks))


def validate_streamed_injected_tables(
    *,
    original_table_row_counts: Mapping[str, int],
    injected_table_row_counts: Mapping[str, int],
    config: DataQualityInjectionConfig,
    summary,
    manifest_entries: Iterable[Any] = (),
) -> DataQualityInjectionValidationResult:
    """Validate streamed injection safety checks that do not require full tables."""

    checks: list[DataQualityValidationCheck] = []
    manifest_entries_tuple = tuple(manifest_entries)
    checks.extend(
        _validate_streamed_row_counts(
            original_table_row_counts,
            injected_table_row_counts,
            summary,
        )
    )
    checks.extend(_validate_required_fields(manifest_entries_tuple))
    checks.extend(_validate_protected_fields(manifest_entries_tuple))
    checks.extend(_validate_issue_rates(original_table_row_counts, config, summary))

    failed = [check for check in checks if check.status != "passed"]
    if failed:
        result = DataQualityInjectionValidationResult(
            status="failed",
            checks=tuple(checks),
        )
        failed_names = ", ".join(check.name for check in failed[:5])
        if len(failed) > 5:
            failed_names += ", ..."
        raise DataQualityValidationError(
            f"Streamed data quality injection validation failed: {failed_names}",
            result,
        )
    return DataQualityInjectionValidationResult(status="passed", checks=tuple(checks))


def _validate_column_shapes(
    original_table_row_counts: Mapping[str, int],
    injected_tables: Mapping[str, list[dict[str, Any]]],
) -> tuple[DataQualityValidationCheck, ...]:
    checks: list[DataQualityValidationCheck] = []
    for table_name, original_row_count in original_table_row_counts.items():
        expected_columns = set(_projection_by_table()[table_name].included_columns)
        injected_rows = injected_tables[table_name]
        actual_columns = set(injected_rows[0].keys()) if injected_rows else expected_columns
        checks.append(
            _check(
                name=f"shape:{table_name}",
                passed=actual_columns == expected_columns,
                passed_message="Injected rows preserve the projected column set.",
                failed_message="Injected rows changed the projected column set.",
                details={
                    "table": table_name,
                    "expected_columns": sorted(expected_columns),
                    "actual_columns": sorted(actual_columns),
                    "original_row_count": original_row_count,
                    "injected_row_count": len(injected_rows),
                },
            )
        )
    return tuple(checks)


def _validate_row_counts(
    original_table_row_counts: Mapping[str, int],
    injected_tables: Mapping[str, list[dict[str, Any]]],
    summary,
) -> tuple[DataQualityValidationCheck, ...]:
    checks: list[DataQualityValidationCheck] = []
    for table_name, original_row_count in original_table_row_counts.items():
        row_delta = summary.table_row_deltas.get(table_name, 0)
        expected_row_count = original_row_count + row_delta
        injected_row_count = len(injected_tables[table_name])
        checks.append(
            _check(
                name=f"rows:{table_name}",
                passed=injected_row_count == expected_row_count,
                passed_message="Injected row count matches the expected table delta.",
                failed_message="Injected row count does not match the expected table delta.",
                details={
                    "table": table_name,
                    "original_row_count": original_row_count,
                    "expected_row_count": expected_row_count,
                    "injected_row_count": injected_row_count,
                    "row_delta": row_delta,
                },
            )
        )
    return tuple(checks)


def _validate_streamed_row_counts(
    original_table_row_counts: Mapping[str, int],
    injected_table_row_counts: Mapping[str, int],
    summary,
) -> tuple[DataQualityValidationCheck, ...]:
    checks: list[DataQualityValidationCheck] = []
    for table_name, original_row_count in original_table_row_counts.items():
        row_delta = summary.table_row_deltas.get(table_name, 0)
        expected_row_count = original_row_count + row_delta
        injected_row_count = injected_table_row_counts.get(table_name)
        checks.append(
            _check(
                name=f"rows:{table_name}",
                passed=injected_row_count == expected_row_count,
                passed_message="Injected row count matches the expected table delta.",
                failed_message="Injected row count does not match the expected table delta.",
                details={
                    "table": table_name,
                    "original_row_count": original_row_count,
                    "expected_row_count": expected_row_count,
                    "injected_row_count": injected_row_count,
                    "row_delta": row_delta,
                },
            )
        )
    return tuple(checks)


def _validate_primary_key_uniqueness(
    injected_tables: Mapping[str, list[dict[str, Any]]],
) -> tuple[DataQualityValidationCheck, ...]:
    checks: list[DataQualityValidationCheck] = []
    for table_name, rows in injected_tables.items():
        pk_column = primary_key_column(table_name)
        values = [row.get(pk_column) for row in rows]
        non_null_values = [value for value in values if value is not None]
        duplicate_count = len(non_null_values) - len(set(non_null_values))
        checks.append(
            _check(
                name=f"pk:{table_name}",
                passed=duplicate_count == 0 and len(non_null_values) == len(values),
                passed_message="Primary keys remain unique and populated.",
                failed_message="Primary keys became null or duplicated.",
                details={
                    "table": table_name,
                    "primary_key_column": pk_column,
                    "duplicate_count": duplicate_count,
                    "null_count": len(values) - len(non_null_values),
                },
            )
        )
    return tuple(checks)


def _validate_required_fields(
    manifest_entries: Iterable[Any],
) -> tuple[DataQualityValidationCheck, ...]:
    checks: list[DataQualityValidationCheck] = []
    null_counts: dict[tuple[str, str], int] = {}
    for entry in manifest_entries:
        table_name = getattr(entry, "table_name", None)
        column_name = getattr(entry, "column_name", None)
        injected_value = getattr(entry, "injected_value", None)
        if table_name is None or column_name is None:
            continue
        if column_name in required_columns(table_name) and injected_value is None:
            key = (table_name, column_name)
            null_counts[key] = null_counts.get(key, 0) + 1

    for table_name in _projection_by_table():
        for column_name in required_columns(table_name):
            null_count = null_counts.get((table_name, column_name), 0)
            checks.append(
                _check(
                    name=f"required:{table_name}.{column_name}",
                    passed=null_count == 0,
                    passed_message="Required field was not targeted with injected null values.",
                    failed_message="Required field was targeted with injected null values.",
                    details={
                        "table": table_name,
                        "column": column_name,
                        "injected_null_count": null_count,
                    },
                )
            )
    return tuple(checks)


def _validate_protected_fields(
    manifest_entries: Iterable[Any],
) -> tuple[DataQualityValidationCheck, ...]:
    checks: list[DataQualityValidationCheck] = []
    mutated_counts: dict[tuple[str, str], int] = {}
    for entry in manifest_entries:
        table_name = getattr(entry, "table_name", None)
        column_name = getattr(entry, "column_name", None)
        if table_name is None or column_name is None:
            continue
        if column_name in protected_columns(table_name):
            key = (table_name, column_name)
            mutated_counts[key] = mutated_counts.get(key, 0) + 1

    for table_name in _projection_by_table():
        for column_name in sorted(protected_columns(table_name)):
            mutated_count = mutated_counts.get((table_name, column_name), 0)
            checks.append(
                _check(
                    name=f"protected:{table_name}.{column_name}",
                    passed=mutated_count == 0,
                    passed_message="Protected field was not targeted by injection.",
                    failed_message="Protected field was targeted by injection.",
                    details={
                        "table": table_name,
                        "column": column_name,
                        "mutated_count": mutated_count,
                    },
                )
            )
    return tuple(checks)


def _validate_relationships(
    injected_tables: Mapping[str, list[dict[str, Any]]],
) -> tuple[DataQualityValidationCheck, ...]:
    checks: list[DataQualityValidationCheck] = []
    lookup = {
        table_name: {
            row[primary_key_column(table_name)]: row
            for row in rows
            if row.get(primary_key_column(table_name)) is not None
        }
        for table_name, rows in injected_tables.items()
    }
    for projection in _projection_by_table().values():
        for relationship in projection.relationship_validations:
            missing_count = 0
            parent_lookup = lookup[relationship.parent_table]
            for row in injected_tables[relationship.child_table]:
                value = row.get(relationship.child_column)
                if value is None and relationship.nullable:
                    continue
                if value not in parent_lookup:
                    missing_count += 1
            checks.append(
                _check(
                    name=(
                        "relationship:"
                        f"{relationship.child_table}.{relationship.child_column}->"
                        f"{relationship.parent_table}.{relationship.parent_column}"
                    ),
                    passed=missing_count == 0,
                    passed_message="Foreign-key relationship remains valid.",
                    failed_message="Injected rows created orphaned relationships.",
                    details={
                        "child_table": relationship.child_table,
                        "child_column": relationship.child_column,
                        "parent_table": relationship.parent_table,
                        "missing_count": missing_count,
                    },
                )
            )
    return tuple(checks)


def _validate_issue_rates(
    original_table_row_counts: Mapping[str, int],
    config: DataQualityInjectionConfig,
    summary,
) -> tuple[DataQualityValidationCheck, ...]:
    checks: list[DataQualityValidationCheck] = []
    total_original_rows = sum(original_table_row_counts.values())
    overall_ratio = (
        0.0 if total_original_rows == 0 else summary.total_affected_rows / total_original_rows
    )
    checks.append(
        _check(
            name="limits:max_total_affected_rows_pct",
            passed=overall_ratio <= (config.global_limits.max_total_affected_rows_pct / 100.0),
            passed_message="Total affected rows stayed within the configured cap.",
            failed_message="Total affected rows exceeded the configured cap.",
            details={
                "affected_rows": summary.total_affected_rows,
                "total_rows": total_original_rows,
                "actual_ratio": overall_ratio,
                "max_ratio": config.global_limits.max_total_affected_rows_pct / 100.0,
            },
        )
    )
    for table_name, issue_counts in summary.table_issue_type_affected_rows.items():
        table_rule = config.table_rules.get(table_name)
        profile_name = table_rule.issue_profile if table_rule is not None else None
        profile = level_profile(profile_name or summary.effective_level)
        band_limits = {
            "field": profile.field_level_issue_rate.max_ratio,
            "categorical": profile.categorical_variant_rate.max_ratio,
            "row": profile.duplicate_like_row_rate.max_ratio,
        }
        for issue_type, affected_rows in issue_counts.items():
            candidate_total = summary.table_issue_type_candidate_rows.get(
                table_name,
                {},
            ).get(issue_type, 0)
            actual_ratio = 0.0 if candidate_total == 0 else affected_rows / candidate_total
            family = _issue_family(issue_type)
            max_ratio = band_limits[family]
            checks.append(
                _check(
                    name=f"limits:issue_rate:{table_name}:{issue_type}",
                    passed=actual_ratio <= max_ratio,
                    passed_message="Issue rate stayed within the configured band.",
                    failed_message="Issue rate exceeded the configured band.",
                    details={
                        "table_name": table_name,
                        "issue_type": issue_type,
                        "affected_rows": affected_rows,
                        "candidate_rows": candidate_total,
                        "actual_ratio": actual_ratio,
                        "max_ratio": max_ratio,
                    },
                )
            )
    return tuple(checks)


def _issue_family(issue_type: str) -> str:
    if issue_type in FIELD_RATE_ISSUES:
        return "field"
    if issue_type in CATEGORICAL_RATE_ISSUES:
        return "categorical"
    if issue_type in ROW_RATE_ISSUES or issue_type == ISSUE_TYPE_DUPLICATE_LIKE_ROWS:
        return "row"
    return "field"


def _check(
    *,
    name: str,
    passed: bool,
    passed_message: str,
    failed_message: str,
    details: Mapping[str, Any],
) -> DataQualityValidationCheck:
    return DataQualityValidationCheck(
        name=name,
        status="passed" if passed else "failed",
        message=passed_message if passed else failed_message,
        details=details,
    )


def _projection_by_table():
    from app.exports.student_dataset.projection import PROJECTION_BY_TABLE

    return PROJECTION_BY_TABLE
