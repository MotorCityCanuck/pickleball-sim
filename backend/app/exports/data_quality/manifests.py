"""Structured manifest records for injected data quality issues."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from typing import Any, Iterable

import pyarrow as pa


INSTRUCTOR_MANIFEST_FILE_NAME = "data_quality_injection_manifest.parquet"


@dataclass(frozen=True)
class DataQualityInjectionManifestEntry:
    """One instructor-visible mutation record."""

    release_id: str
    release_name: str
    table_name: str
    record_primary_key: str
    column_name: str
    issue_type: str
    original_value: str | None
    injected_value: str | None
    injection_level: str
    random_seed: int
    rule_id: str
    injected_at: str

    @classmethod
    def create(
        cls,
        *,
        release_id: str,
        release_name: str,
        table_name: str,
        record_primary_key: object,
        column_name: str,
        issue_type: str,
        original_value: Any,
        injected_value: Any,
        injection_level: str,
        random_seed: int,
        rule_id: str,
    ) -> "DataQualityInjectionManifestEntry":
        return cls(
            release_id=release_id,
            release_name=release_name,
            table_name=table_name,
            record_primary_key=str(record_primary_key),
            column_name=column_name,
            issue_type=issue_type,
            original_value=_encode_manifest_value(original_value),
            injected_value=_encode_manifest_value(injected_value),
            injection_level=injection_level,
            random_seed=random_seed,
            rule_id=rule_id,
            injected_at=_utc_timestamp(),
        )

    def manifest_dict(self) -> dict[str, Any]:
        return {
            "release_id": self.release_id,
            "release_name": self.release_name,
            "table_name": self.table_name,
            "record_primary_key": self.record_primary_key,
            "column_name": self.column_name,
            "issue_type": self.issue_type,
            "original_value": self.original_value,
            "injected_value": self.injected_value,
            "injection_level": self.injection_level,
            "random_seed": self.random_seed,
            "rule_id": self.rule_id,
            "injected_at": self.injected_at,
        }


def manifest_table(
    entries: Iterable[DataQualityInjectionManifestEntry],
) -> pa.Table:
    """Build a Parquet-safe table for the instructor-only manifest."""

    rows = [entry.manifest_dict() for entry in entries]
    schema = pa.schema(
        [
            pa.field("release_id", pa.string()),
            pa.field("release_name", pa.string()),
            pa.field("table_name", pa.string()),
            pa.field("record_primary_key", pa.string()),
            pa.field("column_name", pa.string()),
            pa.field("issue_type", pa.string()),
            pa.field("original_value", pa.string()),
            pa.field("injected_value", pa.string()),
            pa.field("injection_level", pa.string()),
            pa.field("random_seed", pa.int64()),
            pa.field("rule_id", pa.string()),
            pa.field("injected_at", pa.string()),
        ]
    )
    if not rows:
        return pa.Table.from_pylist([], schema=schema)
    return pa.Table.from_pylist(rows, schema=schema)


def _encode_manifest_value(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return json.dumps(value, sort_keys=True, default=str)


def _utc_timestamp() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )
