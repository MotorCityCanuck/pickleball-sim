"""Comparison helpers for clean vs injected student dataset exports."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import json
from pathlib import Path
import re
from typing import Any, Mapping

import pyarrow.parquet as pq

from .config import (
    ISSUE_TYPE_CATEGORICAL_VARIANTS,
    ISSUE_TYPE_FORMATTING_VARIANTS,
    ISSUE_TYPE_MISSING_OPTIONAL_VALUES,
    ISSUE_TYPE_NAME_CASE_VARIANTS,
    ISSUE_TYPE_NUMERIC_OUTLIERS,
    ISSUE_TYPE_ROUNDING_VARIANTS,
    ISSUE_TYPE_SOFT_JOIN_AMBIGUITY,
    ISSUE_TYPE_TIMESTAMP_JITTER,
)
from .rules import eligible_columns, primary_key_column, protected_columns


class DataQualityComparisonError(RuntimeError):
    """Raised when two exported release sets cannot be compared."""


@dataclass(frozen=True)
class DataQualityColumnComparison:
    """One detected issue bucket for a table column."""

    column_name: str
    issue_type: str
    affected_row_count: int


@dataclass(frozen=True)
class DataQualityTableComparison:
    """Comparison summary for one exported table."""

    table_name: str
    clean_row_count: int
    tainted_row_count: int
    row_delta: int
    schema_match: bool
    protected_field_change_count: int
    duplicate_like_extra_row_count: int
    column_issues: tuple[DataQualityColumnComparison, ...]

    @property
    def issue_count(self) -> int:
        return (
            self.protected_field_change_count
            + self.duplicate_like_extra_row_count
            + sum(issue.affected_row_count for issue in self.column_issues)
        )

    @property
    def issue_labels(self) -> tuple[str, ...]:
        labels = [
            f"{issue.column_name}: {issue.issue_type} ({issue.affected_row_count})"
            for issue in self.column_issues
        ]
        if self.duplicate_like_extra_row_count:
            labels.append(
                "duplicate_like_rows "
                f"({self.duplicate_like_extra_row_count})"
            )
        if self.protected_field_change_count:
            labels.append(
                "protected_field_changes "
                f"({self.protected_field_change_count})"
            )
        if not self.schema_match:
            labels.append("schema_mismatch")
        return tuple(labels)


@dataclass(frozen=True)
class DataQualityReleaseComparison:
    """Comparison summary for one matched release pair."""

    comparison_key: str
    release_type: str
    snapshot_month: str | None
    clean_release_path: str
    tainted_release_path: str
    tables: tuple[DataQualityTableComparison, ...]

    @property
    def issue_count(self) -> int:
        return sum(table.issue_count for table in self.tables)


@dataclass(frozen=True)
class DataQualityExportComparisonResult:
    """Top-level comparison result for two export locations."""

    clean_path: str
    tainted_path: str
    releases: tuple[DataQualityReleaseComparison, ...]
    missing_clean_releases: tuple[str, ...]
    missing_tainted_releases: tuple[str, ...]

    @property
    def compared_release_count(self) -> int:
        return len(self.releases)

    @property
    def total_issue_count(self) -> int:
        return sum(release.issue_count for release in self.releases)


@dataclass(frozen=True)
class _ReleaseDescriptor:
    comparison_key: str
    release_type: str
    snapshot_month: str | None
    release_path: Path


def compare_export_locations(
    *,
    clean_path: Path,
    tainted_path: Path,
) -> DataQualityExportComparisonResult:
    """Compare two release folders or release-family roots."""

    clean_releases = _discover_release_descriptors(clean_path)
    tainted_releases = _discover_release_descriptors(tainted_path)
    common_keys = sorted(set(clean_releases) & set(tainted_releases))
    if not common_keys:
        raise DataQualityComparisonError(
            "No comparable release folders were found between the two locations."
        )

    releases = tuple(
        _compare_release_pair(
            clean_release=clean_releases[key],
            tainted_release=tainted_releases[key],
        )
        for key in common_keys
    )
    return DataQualityExportComparisonResult(
        clean_path=str(clean_path),
        tainted_path=str(tainted_path),
        releases=releases,
        missing_clean_releases=tuple(sorted(set(tainted_releases) - set(clean_releases))),
        missing_tainted_releases=tuple(sorted(set(clean_releases) - set(tainted_releases))),
    )


def _discover_release_descriptors(path: Path) -> dict[str, _ReleaseDescriptor]:
    resolved = path.expanduser().resolve()
    if not resolved.is_dir():
        raise DataQualityComparisonError(f"Export location does not exist: {resolved}")

    direct_manifest = resolved / "manifest.json"
    if direct_manifest.is_file():
        descriptor = _descriptor_from_manifest(resolved)
        return {descriptor.comparison_key: descriptor}

    descriptors: dict[str, _ReleaseDescriptor] = {}
    for child in sorted(resolved.iterdir()):
        if not child.is_dir():
            continue
        manifest_path = child / "manifest.json"
        if not manifest_path.is_file():
            continue
        descriptor = _descriptor_from_manifest(child)
        descriptors[descriptor.comparison_key] = descriptor
    if not descriptors:
        raise DataQualityComparisonError(
            f"No release folders with manifest.json were found under {resolved}"
        )
    return descriptors


def _descriptor_from_manifest(release_path: Path) -> _ReleaseDescriptor:
    manifest = json.loads((release_path / "manifest.json").read_text(encoding="utf-8"))
    release_type = str(manifest.get("release_type") or "unknown")
    snapshot_month = manifest.get("snapshot_month")
    comparison_key = f"{release_type}:{snapshot_month or release_path.name}"
    return _ReleaseDescriptor(
        comparison_key=comparison_key,
        release_type=release_type,
        snapshot_month=str(snapshot_month) if snapshot_month is not None else None,
        release_path=release_path,
    )


def _compare_release_pair(
    *,
    clean_release: _ReleaseDescriptor,
    tainted_release: _ReleaseDescriptor,
) -> DataQualityReleaseComparison:
    tables = tuple(
        _compare_table(
            table_name=table_name,
            clean_file=clean_release.release_path / f"{table_name}.parquet",
            tainted_file=tainted_release.release_path / f"{table_name}.parquet",
        )
        for table_name in _student_table_order()
    )
    return DataQualityReleaseComparison(
        comparison_key=clean_release.comparison_key,
        release_type=clean_release.release_type,
        snapshot_month=clean_release.snapshot_month,
        clean_release_path=str(clean_release.release_path),
        tainted_release_path=str(tainted_release.release_path),
        tables=tables,
    )


def _compare_table(
    *,
    table_name: str,
    clean_file: Path,
    tainted_file: Path,
) -> DataQualityTableComparison:
    if not clean_file.is_file():
        raise DataQualityComparisonError(f"Missing clean parquet file: {clean_file}")
    if not tainted_file.is_file():
        raise DataQualityComparisonError(f"Missing tainted parquet file: {tainted_file}")

    clean_rows = pq.read_table(clean_file).to_pylist()
    tainted_rows = pq.read_table(tainted_file).to_pylist()
    clean_columns = tuple(pq.read_table(clean_file).column_names)
    tainted_columns = tuple(pq.read_table(tainted_file).column_names)
    schema_match = clean_columns == tainted_columns

    pk_column = primary_key_column(table_name)
    clean_by_pk = {row[pk_column]: row for row in clean_rows if row.get(pk_column) is not None}
    tainted_by_pk = {
        row[pk_column]: row for row in tainted_rows if row.get(pk_column) is not None
    }
    common_pks = sorted(set(clean_by_pk) & set(tainted_by_pk))

    column_issues: list[DataQualityColumnComparison] = []
    for issue_type in (
        ISSUE_TYPE_MISSING_OPTIONAL_VALUES,
        ISSUE_TYPE_CATEGORICAL_VARIANTS,
        ISSUE_TYPE_FORMATTING_VARIANTS,
        ISSUE_TYPE_NAME_CASE_VARIANTS,
        ISSUE_TYPE_SOFT_JOIN_AMBIGUITY,
        ISSUE_TYPE_ROUNDING_VARIANTS,
        ISSUE_TYPE_NUMERIC_OUTLIERS,
        ISSUE_TYPE_TIMESTAMP_JITTER,
    ):
        for column_name in eligible_columns(table_name, issue_type):
            affected = _compare_column_issue(
                issue_type=issue_type,
                column_name=column_name,
                clean_by_pk=clean_by_pk,
                tainted_by_pk=tainted_by_pk,
                common_pks=common_pks,
            )
            if affected > 0:
                column_issues.append(
                    DataQualityColumnComparison(
                        column_name=column_name,
                        issue_type=issue_type,
                        affected_row_count=affected,
                    )
                )

    protected_change_count = _protected_field_change_count(
        table_name=table_name,
        clean_by_pk=clean_by_pk,
        tainted_by_pk=tainted_by_pk,
        common_pks=common_pks,
    )
    duplicate_like_extra_row_count = _duplicate_like_extra_row_count(
        table_name=table_name,
        clean_rows=clean_rows,
        clean_by_pk=clean_by_pk,
        tainted_rows=tainted_rows,
        tainted_by_pk=tainted_by_pk,
    )

    return DataQualityTableComparison(
        table_name=table_name,
        clean_row_count=len(clean_rows),
        tainted_row_count=len(tainted_rows),
        row_delta=len(tainted_rows) - len(clean_rows),
        schema_match=schema_match,
        protected_field_change_count=protected_change_count,
        duplicate_like_extra_row_count=duplicate_like_extra_row_count,
        column_issues=tuple(sorted(column_issues, key=lambda issue: (issue.column_name, issue.issue_type))),
    )


def _compare_column_issue(
    *,
    issue_type: str,
    column_name: str,
    clean_by_pk: Mapping[Any, Mapping[str, Any]],
    tainted_by_pk: Mapping[Any, Mapping[str, Any]],
    common_pks: list[Any],
) -> int:
    count = 0
    for pk_value in common_pks:
        clean_value = clean_by_pk[pk_value].get(column_name)
        tainted_value = tainted_by_pk[pk_value].get(column_name)
        if issue_type == ISSUE_TYPE_MISSING_OPTIONAL_VALUES:
            if clean_value is not None and tainted_value is None:
                count += 1
        elif issue_type in {
            ISSUE_TYPE_CATEGORICAL_VARIANTS,
            ISSUE_TYPE_FORMATTING_VARIANTS,
            ISSUE_TYPE_NAME_CASE_VARIANTS,
            ISSUE_TYPE_SOFT_JOIN_AMBIGUITY,
        }:
            if (
                clean_value is not None
                and tainted_value is not None
                and clean_value != tainted_value
                and _normalize_text(clean_value) == _normalize_text(tainted_value)
            ):
                count += 1
        elif issue_type == ISSUE_TYPE_ROUNDING_VARIANTS:
            if _looks_like_rounding_variant(clean_value, tainted_value):
                count += 1
        elif issue_type == ISSUE_TYPE_NUMERIC_OUTLIERS:
            if _looks_like_numeric_outlier_change(clean_value, tainted_value):
                count += 1
        elif issue_type == ISSUE_TYPE_TIMESTAMP_JITTER:
            if _looks_like_timestamp_jitter(clean_value, tainted_value):
                count += 1
    return count


def _protected_field_change_count(
    *,
    table_name: str,
    clean_by_pk: Mapping[Any, Mapping[str, Any]],
    tainted_by_pk: Mapping[Any, Mapping[str, Any]],
    common_pks: list[Any],
) -> int:
    protected = protected_columns(table_name)
    count = 0
    for pk_value in common_pks:
        clean_row = clean_by_pk[pk_value]
        tainted_row = tainted_by_pk[pk_value]
        if any(clean_row.get(column_name) != tainted_row.get(column_name) for column_name in protected):
            count += 1
    return count


def _duplicate_like_extra_row_count(
    *,
    table_name: str,
    clean_rows: list[dict[str, Any]],
    clean_by_pk: Mapping[Any, Mapping[str, Any]],
    tainted_rows: list[dict[str, Any]],
    tainted_by_pk: Mapping[Any, Mapping[str, Any]],
) -> int:
    pk_column = primary_key_column(table_name)
    extra_rows = [
        row
        for row in tainted_rows
        if row.get(pk_column) not in clean_by_pk
    ]
    if not extra_rows:
        return 0
    clean_signatures = {
        _duplicate_signature(table_name, row)
        for row in clean_rows
    }
    return sum(
        1
        for row in extra_rows
        if _duplicate_signature(table_name, row) in clean_signatures
    )


def _duplicate_signature(table_name: str, row: Mapping[str, Any]) -> tuple[Any, ...]:
    pk_column = primary_key_column(table_name)
    parts: list[Any] = []
    for column_name in sorted(row):
        if column_name == pk_column or column_name.endswith("_id"):
            continue
        value = row.get(column_name)
        if isinstance(value, str):
            parts.append(_normalize_text(value))
        else:
            parts.append(value)
    return tuple(parts)


def _normalize_text(value: Any) -> str:
    text = str(value).strip().lower()
    text = text.replace("_", " ")
    text = text.replace("-", " ")
    text = text.replace("&", "and")
    text = text.replace(".", "")
    text = re.sub(r"\s+", " ", text)
    return text


def _looks_like_rounding_variant(clean_value: Any, tainted_value: Any) -> bool:
    if clean_value is None or tainted_value is None:
        return False
    if clean_value == tainted_value:
        return False
    if not isinstance(clean_value, (int, float)) or not isinstance(tainted_value, (int, float)):
        return False
    clean_float = float(clean_value)
    tainted_float = float(tainted_value)
    return any(
        round(clean_float, decimals) == tainted_float
        or round(tainted_float, decimals) == clean_float
        for decimals in (1, 2, 3)
    )


def _looks_like_numeric_outlier_change(clean_value: Any, tainted_value: Any) -> bool:
    if clean_value is None or tainted_value is None:
        return False
    if clean_value == tainted_value:
        return False
    if not isinstance(clean_value, (int, float)) or not isinstance(tainted_value, (int, float)):
        return False
    if _looks_like_rounding_variant(clean_value, tainted_value):
        return False
    clean_float = float(clean_value)
    tainted_float = float(tainted_value)
    threshold = max(1.0, abs(clean_float) * 0.10)
    return abs(tainted_float - clean_float) >= threshold


def _looks_like_timestamp_jitter(clean_value: Any, tainted_value: Any) -> bool:
    clean_dt = _parse_iso_temporal(clean_value)
    tainted_dt = _parse_iso_temporal(tainted_value)
    if clean_dt is None or tainted_dt is None or clean_dt == tainted_dt:
        return False
    return abs((tainted_dt - clean_dt).days) <= 1


def _parse_iso_temporal(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if not isinstance(value, str):
        return None
    candidate = value.replace("Z", "+00:00")
    try:
        if "T" in candidate:
            return datetime.fromisoformat(candidate).date()
        return date.fromisoformat(candidate)
    except ValueError:
        return None


def _student_table_order() -> tuple[str, ...]:
    from app.exports.student_dataset.projection import STUDENT_TABLE_ORDER

    return STUDENT_TABLE_ORDER
