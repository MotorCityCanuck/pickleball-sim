"""Compare released Parquet source files with simulator database tables."""

from __future__ import annotations

import csv
import hashlib
import json
import subprocess
from uuid import UUID, uuid4
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Iterable, Mapping

import pyarrow.parquet as pq
from sqlalchemy import MetaData, Table, create_engine, func, inspect, select
from sqlalchemy.engine import Engine

from .config import EntityMapping, ReconciliationConfig, Waiver


@dataclass(frozen=True)
class Mismatch:
    """One reconciliation mismatch."""

    mismatch_type: str
    entity: str
    key: Mapping[str, Any]
    field: str | None = None
    parquet_value: Any = None
    database_value: Any = None
    normalized_parquet_value: Any = None
    normalized_database_value: Any = None
    waived: bool = False
    waiver_reason: str | None = None


@dataclass
class EntityResult:
    """Reconciliation result for one mapped entity."""

    entity: str
    parquet_file: str
    table_name: str
    critical: bool
    parquet_exists: bool = False
    table_exists: bool = False
    parquet_count: int = 0
    database_count: int = 0
    parquet_columns: tuple[str, ...] = ()
    database_columns: tuple[str, ...] = ()
    compared_columns: tuple[str, ...] = ()
    missing_database_columns: tuple[str, ...] = ()
    unexpected_database_columns: tuple[str, ...] = ()
    parquet_file_size: int = 0
    parquet_sha256: str | None = None
    duplicate_parquet_keys: int = 0
    duplicate_database_keys: int = 0
    missing_in_database: int = 0
    extra_in_database: int = 0
    value_mismatches: int = 0
    waived_mismatches: int = 0
    mismatch_files: dict[str, str] = field(default_factory=dict)

    @property
    def failed(self) -> bool:
        return (
            not self.parquet_exists
            or not self.table_exists
            or self.parquet_count != self.database_count
            or self.duplicate_parquet_keys > 0
            or self.duplicate_database_keys > 0
            or self.missing_in_database > 0
            or self.extra_in_database > 0
            or self.value_mismatches > 0
            or bool(self.missing_database_columns)
        )


@dataclass
class ReconciliationResult:
    """Top-level reconciliation run result."""

    release_name: str
    run_timestamp: str
    output_dir: Path
    database_target: Mapping[str, Any]
    git_commit: str | None
    normalization_rules: tuple[str, ...]
    entities: list[EntityResult]
    waivers: tuple[Waiver, ...]

    @property
    def passed(self) -> bool:
        return not any(entity.failed for entity in self.entities)

    @property
    def totals(self) -> dict[str, int]:
        return {
            "missing_keys": sum(entity.missing_in_database for entity in self.entities),
            "extra_keys": sum(entity.extra_in_database for entity in self.entities),
            "value_mismatches": sum(entity.value_mismatches for entity in self.entities),
            "waived_mismatches": sum(entity.waived_mismatches for entity in self.entities),
        }


def run_reconciliation(
    config: ReconciliationConfig,
    *,
    counts_only: bool = False,
    fail_fast: bool = False,
    verbose: bool = False,
    engine: Engine | None = None,
) -> ReconciliationResult:
    """Run the configured source-level reconciliation."""

    if not config.parquet_root.exists():
        from .config import ReconciliationConfigError

        raise ReconciliationConfigError(
            f"Parquet root does not exist: {config.parquet_root}"
        )
    if not config.parquet_root.is_dir():
        from .config import ReconciliationConfigError

        raise ReconciliationConfigError(
            f"Parquet root is not a directory: {config.parquet_root}"
        )

    run_timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_dir = _new_output_dir(config.output_directory, run_timestamp, config.release_name)
    mismatches_dir = output_dir / "mismatches"
    mismatches_dir.mkdir(parents=True, exist_ok=False)

    owned_engine = engine is None
    engine = engine or create_engine(config.database.sqlalchemy_url(), future=True)
    schema = config.database.schema or None
    metadata = MetaData(schema=schema)
    inspector = inspect(engine)
    available_tables = set(inspector.get_table_names(schema=schema))
    git_commit = _git_commit()

    results: list[EntityResult] = []
    try:
        for mapping in config.mappings:
            print(f"Reconciling {mapping.entity}...", flush=True)
            result = _compare_entity(
                config=config,
                mapping=mapping,
                engine=engine,
                metadata=metadata,
                available_tables=available_tables,
                mismatches_dir=mismatches_dir,
                counts_only=counts_only,
            )
            results.append(result)
            status = "FAIL" if result.failed else "PASS"
            print(
                f"Finished {mapping.entity}: parquet={result.parquet_count:,}, "
                f"database={result.database_count:,}, status={status}",
                flush=True,
            )
            if fail_fast and result.failed:
                break
    finally:
        if owned_engine:
            engine.dispose()

    reconciliation = ReconciliationResult(
        release_name=config.release_name,
        run_timestamp=run_timestamp,
        output_dir=output_dir,
        database_target=config.database.safe_dict(),
        git_commit=git_commit,
        normalization_rules=tuple(config.normalization.rules_for_report()),
        entities=results,
        waivers=config.waivers,
    )
    _write_reports(reconciliation, config)
    return reconciliation


def _compare_entity(
    *,
    config: ReconciliationConfig,
    mapping: EntityMapping,
    engine: Engine,
    metadata: MetaData,
    available_tables: set[str],
    mismatches_dir: Path,
    counts_only: bool,
) -> EntityResult:
    parquet_path = config.parquet_root / mapping.parquet_file
    result = EntityResult(
        entity=mapping.entity,
        parquet_file=mapping.parquet_file,
        table_name=mapping.table_name,
        critical=mapping.critical,
        parquet_exists=parquet_path.exists(),
        table_exists=mapping.table_name in available_tables,
    )
    if result.parquet_exists:
        result.parquet_file_size = parquet_path.stat().st_size
        if config.compute_file_sha256:
            result.parquet_sha256 = _sha256(parquet_path)
    if result.table_exists:
        table = Table(mapping.table_name, metadata, autoload_with=engine)
        result.database_columns = tuple(column.name for column in table.columns)
        db_count_query = select(func.count()).select_from(table)
        with engine.connect() as connection:
            result.database_count = int(connection.execute(db_count_query).scalar_one())
    if not result.parquet_exists or not result.table_exists:
        return result

    parquet_table = pq.read_table(parquet_path)
    result.parquet_columns = tuple(parquet_table.column_names)
    result.parquet_count = parquet_table.num_rows

    compare_columns = _compare_columns(mapping, result.parquet_columns, result.database_columns)
    result.compared_columns = tuple(compare_columns)
    result.missing_database_columns = tuple(
        parquet_column
        for parquet_column in compare_columns
        if _db_column(mapping, parquet_column) not in result.database_columns
    )
    result.unexpected_database_columns = tuple(
        column for column in result.database_columns if column not in {_db_column(mapping, item) for item in compare_columns}
    )
    if result.missing_database_columns or counts_only:
        return result

    parquet_rows = parquet_table.to_pylist()
    parquet_index, parquet_duplicates = _index_rows(parquet_rows, mapping.key_columns)
    result.duplicate_parquet_keys = sum(count - 1 for count in parquet_duplicates.values())
    db_rows = _database_rows(engine, table, mapping, compare_columns)
    db_index, db_duplicates = _index_rows(db_rows, mapping.key_columns)
    result.duplicate_database_keys = sum(count - 1 for count in db_duplicates.values())

    parquet_keys = set(parquet_index)
    db_keys = set(db_index)
    missing_keys = sorted(parquet_keys - db_keys)
    extra_keys = sorted(db_keys - parquet_keys)

    missing_mismatches = [
        _with_waiver(
            Mismatch("missing_in_database", mapping.entity, _key_dict(mapping.key_columns, key)),
            config.waivers,
        )
        for key in missing_keys
    ]
    extra_mismatches = [
        _with_waiver(
            Mismatch("extra_in_database", mapping.entity, _key_dict(mapping.key_columns, key)),
            config.waivers,
        )
        for key in extra_keys
    ]
    result.missing_in_database = sum(not mismatch.waived for mismatch in missing_mismatches)
    result.extra_in_database = sum(not mismatch.waived for mismatch in extra_mismatches)

    value_mismatches: list[Mismatch] = []
    for key in sorted(parquet_keys & db_keys):
        parquet_row = parquet_index[key]
        db_row = db_index[key]
        for column in compare_columns:
            left = parquet_row.get(column)
            right = db_row.get(column)
            norm_left = _normalize(left, config)
            norm_right = _normalize(right, config)
            if _values_equal(norm_left, norm_right, config):
                continue
            value_mismatches.append(
                _with_waiver(
                    Mismatch(
                        "value_mismatch",
                        mapping.entity,
                        _key_dict(mapping.key_columns, key),
                        field=column,
                        parquet_value=left,
                        database_value=right,
                        normalized_parquet_value=norm_left,
                        normalized_database_value=norm_right,
                    ),
                    config.waivers,
                )
            )

    result.value_mismatches = sum(not mismatch.waived for mismatch in value_mismatches)
    result.waived_mismatches = sum(
        mismatch.waived for mismatch in [*missing_mismatches, *extra_mismatches, *value_mismatches]
    )
    _write_mismatch_file(result, mismatches_dir, "missing_in_database", missing_mismatches)
    _write_mismatch_file(result, mismatches_dir, "extra_in_database", extra_mismatches)
    _write_mismatch_file(result, mismatches_dir, "value_mismatches", value_mismatches)
    return result


def _compare_columns(mapping: EntityMapping, parquet_columns: tuple[str, ...], database_columns: tuple[str, ...]) -> list[str]:
    if mapping.compare_columns is not None:
        return list(mapping.compare_columns)
    compare: list[str] = []
    for parquet_column in parquet_columns:
        db_column = _db_column(mapping, parquet_column)
        if db_column in database_columns or parquet_column in mapping.key_columns:
            compare.append(parquet_column)
    return compare


def _db_column(mapping: EntityMapping, parquet_column: str) -> str:
    return mapping.column_mappings.get(parquet_column, parquet_column)


def _database_rows(
    engine: Engine,
    table: Table,
    mapping: EntityMapping,
    compare_columns: Iterable[str],
) -> list[dict[str, Any]]:
    selected_columns = []
    seen: set[str] = set()
    for parquet_column in [*mapping.key_columns, *compare_columns]:
        if parquet_column in seen:
            continue
        seen.add(parquet_column)
        db_column_name = _db_column(mapping, parquet_column)
        selected_columns.append(table.c[db_column_name].label(parquet_column))
    order_by = [table.c[_db_column(mapping, column)] for column in mapping.key_columns]
    query = select(*selected_columns).order_by(*order_by)
    with engine.connect() as connection:
        return [dict(row._mapping) for row in connection.execute(query)]


def _index_rows(rows: Iterable[Mapping[str, Any]], key_columns: tuple[str, ...]) -> tuple[dict[tuple[Any, ...], Mapping[str, Any]], Counter]:
    index: dict[tuple[Any, ...], Mapping[str, Any]] = {}
    counts: Counter = Counter()
    for row in rows:
        key = tuple(_stable_key_value(row.get(column)) for column in key_columns)
        counts[key] += 1
        index.setdefault(key, row)
    duplicates = Counter({key: count for key, count in counts.items() if count > 1})
    return index, duplicates


def _stable_key_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (date, datetime, UUID)):
        return value.isoformat() if hasattr(value, "isoformat") else str(value)
    return value


def _key_dict(key_columns: tuple[str, ...], key: tuple[Any, ...]) -> dict[str, Any]:
    return dict(zip(key_columns, key))


def _normalize(value: Any, config: ReconciliationConfig) -> Any:
    if value is None:
        return None
    if isinstance(value, Decimal):
        quantum = Decimal("1").scaleb(-config.normalization.decimal_scale)
        return str(value.quantize(quantum, rounding=ROUND_HALF_UP))
    if isinstance(value, float):
        return value
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            value = value.astimezone(timezone.utc).replace(tzinfo=None)
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, bytes):
        return value.hex()
    if isinstance(value, str):
        return value.rstrip() if config.normalization.strip_trailing_whitespace else value
    return value


def _values_equal(left: Any, right: Any, config: ReconciliationConfig) -> bool:
    if left == right:
        return True
    if isinstance(left, float) or isinstance(right, float):
        try:
            return abs(float(left) - float(right)) <= config.normalization.float_tolerance
        except (TypeError, ValueError):
            return False
    return False


def _with_waiver(mismatch: Mismatch, waivers: tuple[Waiver, ...]) -> Mismatch:
    for waiver in waivers:
        if waiver.entity != mismatch.entity:
            continue
        if waiver.mismatch_type and waiver.mismatch_type != mismatch.mismatch_type:
            continue
        if waiver.field and waiver.field != mismatch.field:
            continue
        if waiver.key and dict(waiver.key) != dict(mismatch.key):
            continue
        return Mismatch(
            mismatch_type=mismatch.mismatch_type,
            entity=mismatch.entity,
            key=mismatch.key,
            field=mismatch.field,
            parquet_value=mismatch.parquet_value,
            database_value=mismatch.database_value,
            normalized_parquet_value=mismatch.normalized_parquet_value,
            normalized_database_value=mismatch.normalized_database_value,
            waived=True,
            waiver_reason=waiver.reason,
        )
    return mismatch


def _write_mismatch_file(
    result: EntityResult,
    mismatches_dir: Path,
    suffix: str,
    mismatches: list[Mismatch],
) -> None:
    if not mismatches:
        return
    path = mismatches_dir / f"{result.entity}_{suffix}.csv"
    result.mismatch_files[suffix] = str(path.relative_to(mismatches_dir.parent))
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=(
                "mismatch_type",
                "entity",
                "key",
                "field",
                "parquet_value",
                "database_value",
                "normalized_parquet_value",
                "normalized_database_value",
                "waived",
                "waiver_reason",
            ),
        )
        writer.writeheader()
        for mismatch in mismatches:
            writer.writerow(
                {
                    "mismatch_type": mismatch.mismatch_type,
                    "entity": mismatch.entity,
                    "key": json.dumps(_jsonable(mismatch.key), sort_keys=True),
                    "field": mismatch.field,
                    "parquet_value": _stringify(mismatch.parquet_value),
                    "database_value": _stringify(mismatch.database_value),
                    "normalized_parquet_value": _stringify(mismatch.normalized_parquet_value),
                    "normalized_database_value": _stringify(mismatch.normalized_database_value),
                    "waived": mismatch.waived,
                    "waiver_reason": mismatch.waiver_reason,
                }
            )


def _write_reports(result: ReconciliationResult, config: ReconciliationConfig) -> None:
    summary_json = result.output_dir / "reconciliation_summary.json"
    summary_md = result.output_dir / "reconciliation_summary.md"
    summary_json.write_text(json.dumps(_summary_dict(result, config), indent=2, default=_stringify), encoding="utf-8")
    summary_md.write_text(_summary_markdown(result, config), encoding="utf-8")


def _summary_dict(result: ReconciliationResult, config: ReconciliationConfig) -> dict[str, Any]:
    return {
        "release_name": result.release_name,
        "status": "PASS" if result.passed else "FAIL",
        "run_timestamp": result.run_timestamp,
        "parquet_root": str(config.parquet_root),
        "database_target": result.database_target,
        "git_commit": result.git_commit,
        "normalization_rules": list(result.normalization_rules),
        "totals": result.totals,
        "waiver_count": len(result.waivers),
        "waivers": [_waiver_dict(waiver) for waiver in result.waivers],
        "entities": [_entity_dict(entity) for entity in result.entities],
        "certification_statement": _certification_statement(result),
    }


def _summary_markdown(result: ReconciliationResult, config: ReconciliationConfig) -> str:
    lines = [
        f"# NAPA Dataset / Simulator Reconciliation: {result.release_name}",
        "",
        f"Overall status: **{'PASS' if result.passed else 'FAIL'}**",
        f"Run timestamp: `{result.run_timestamp}`",
        f"Parquet root: `{config.parquet_root}`",
        f"Output directory: `{result.output_dir}`",
        f"Git commit: `{result.git_commit or 'unavailable'}`",
        "",
        "## Database Target",
        "",
        "```json",
        json.dumps(result.database_target, indent=2, default=_stringify),
        "```",
        "",
        "## Entity Results",
        "",
        "| Entity | Parquet | Database | Missing | Extra | Value mismatches | Waived | Status |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for entity in result.entities:
        lines.append(
            f"| {entity.entity} | {entity.parquet_count} | {entity.database_count} | "
            f"{entity.missing_in_database} | {entity.extra_in_database} | "
            f"{entity.value_mismatches} | {entity.waived_mismatches} | "
            f"{'FAIL' if entity.failed else 'PASS'} |"
        )
    lines.extend(
        [
            "",
            "## Tournament-Critical Results",
            "",
            "| Entity | Critical | Status |",
            "| --- | --- | --- |",
        ]
    )
    for entity in result.entities:
        if entity.critical:
            lines.append(f"| {entity.entity} | yes | {'FAIL' if entity.failed else 'PASS'} |")
    lines.extend(
        [
            "",
            "## Normalization Rules",
            "",
            *[f"- {rule}" for rule in result.normalization_rules],
            "",
            "## Waivers",
            "",
        ]
    )
    if result.waivers:
        lines.extend(f"- {waiver.entity}: {waiver.reason} ({waiver.approval})" for waiver in result.waivers)
    else:
        lines.append("- None")
    lines.extend(["", "## Certification Statement", "", _certification_statement(result), ""])
    return "\n".join(lines)


def _entity_dict(entity: EntityResult) -> dict[str, Any]:
    return {
        "entity": entity.entity,
        "parquet_file": entity.parquet_file,
        "table_name": entity.table_name,
        "critical": entity.critical,
        "status": "FAIL" if entity.failed else "PASS",
        "parquet_exists": entity.parquet_exists,
        "table_exists": entity.table_exists,
        "parquet_count": entity.parquet_count,
        "database_count": entity.database_count,
        "compared_columns": list(entity.compared_columns),
        "missing_database_columns": list(entity.missing_database_columns),
        "unexpected_database_columns": list(entity.unexpected_database_columns),
        "parquet_file_size": entity.parquet_file_size,
        "parquet_sha256": entity.parquet_sha256,
        "duplicate_parquet_keys": entity.duplicate_parquet_keys,
        "duplicate_database_keys": entity.duplicate_database_keys,
        "missing_in_database": entity.missing_in_database,
        "extra_in_database": entity.extra_in_database,
        "value_mismatches": entity.value_mismatches,
        "waived_mismatches": entity.waived_mismatches,
        "mismatch_files": entity.mismatch_files,
    }


def _waiver_dict(waiver: Waiver) -> dict[str, Any]:
    return {
        "entity": waiver.entity,
        "key": waiver.key,
        "field": waiver.field,
        "mismatch_type": waiver.mismatch_type,
        "reason": waiver.reason,
        "approval": waiver.approval,
    }


def _certification_statement(result: ReconciliationResult) -> str:
    if result.passed:
        return (
            "The NAPA 250K Parquet release has been reconciled against the configured "
            "tournament simulator database. The mapped source entities, identifiers, "
            "relationships, tournament teams, team memberships, and compared source "
            "values are equivalent within the documented normalization rules. This "
            "confirms source-level compatibility between the student release and the "
            "instructor simulator environment at the time of certification."
        )
    return (
        "The NAPA Parquet release is not certified against the configured tournament "
        "simulator database. One or more source-level record populations, identifiers, "
        "relationships, tournament-critical mappings, or compared source values differ."
    )


def print_console_summary(result: ReconciliationResult) -> None:
    """Print the concise certification block expected by the CLI."""

    print("=" * 60)
    print("NAPA 250K DATASET / SIMULATOR RECONCILIATION")
    print("=" * 60)
    print(f"Release: {result.release_name}")
    print("")
    print(f"{'Entity':30} {'Parquet':>12} {'Database':>12} {'Status':>8}")
    for entity in result.entities:
        reason = "FAIL" if entity.failed else "PASS"
        if not entity.parquet_exists:
            reason = "NO FILE"
        elif not entity.table_exists:
            reason = "NO TABLE"
        elif entity.missing_database_columns:
            reason = "SCHEMA"
        elif entity.failed:
            reason = "FAIL"
        print(
            f"{entity.entity:30} {entity.parquet_count:12,} "
            f"{entity.database_count:12,} {reason:>8}"
        )
    totals = result.totals
    print("")
    print(f"Missing keys:{totals['missing_keys']:>28,}")
    print(f"Extra keys:{totals['extra_keys']:>30,}")
    print(f"Value mismatches:{totals['value_mismatches']:>23,}")
    print(f"Waived mismatches:{totals['waived_mismatches']:>22,}")
    print("")
    print(f"OVERALL RELEASE CERTIFICATION: {'PASS' if result.passed else 'FAIL'}")
    print(f"Output: {result.output_dir}")
    print("=" * 60)


def _new_output_dir(output_root: Path, run_timestamp: str, release_name: str) -> Path:
    output_dir = output_root / f"{run_timestamp}_{release_name}"
    if not output_dir.exists():
        return output_dir
    return output_root / f"{run_timestamp}_{release_name}_{uuid4().hex[:8]}"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _git_commit() -> str | None:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
    except Exception:
        return None
    return completed.stdout.strip() or None


def _jsonable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, (date, datetime, Decimal, UUID)):
        return str(value)
    return value


def _stringify(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, (date, datetime, Decimal, UUID)):
        return str(value)
    return str(value)
