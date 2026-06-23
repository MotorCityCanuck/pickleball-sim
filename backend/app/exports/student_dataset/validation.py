"""DuckDB validation for staged student dataset Parquet releases."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

import duckdb

from app.exports.data_quality.rules import primary_key_column

from .projection import (
    EXCLUDED_SOURCE_TABLES,
    PROJECTION_BY_TABLE,
    STUDENT_TABLE_ORDER,
)
from .release_windows import StudentDatasetReleaseWindow


BASELINE_REQUIRED_NON_EMPTY_TABLES: frozenset[str] = frozenset(
    {
        "clubs",
        "club_memberships",
        "match_games",
        "match_team_players",
        "match_teams",
        "matches",
        "monthly_batches",
        "players",
        "player_registrations",
        "regions",
        "team_memberships",
        "teams",
    }
)

INCREMENTAL_REQUIRED_NON_EMPTY_TABLES: frozenset[str] = frozenset(
    {
        "match_games",
        "match_team_players",
        "match_teams",
        "matches",
        "monthly_batches",
        "players",
        "player_registrations",
        "regions",
        "team_memberships",
        "teams",
    }
)

# Backward-compatible export surface for callers that still import the older
# single-set constant. The validator no longer uses this directly.
REQUIRED_NON_EMPTY_TABLES: frozenset[str] = BASELINE_REQUIRED_NON_EMPTY_TABLES


class StudentDatasetValidationError(RuntimeError):
    """Raised when a staged Parquet release fails DuckDB validation."""

    def __init__(self, message: str, result: "StudentDatasetValidationResult"):
        super().__init__(message)
        self.result = result


@dataclass(frozen=True)
class StudentDatasetValidationCheck:
    """Result of one DuckDB validation check."""

    name: str
    status: str
    message: str
    details: Mapping[str, Any]

    def manifest_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "message": self.message,
            "details": dict(self.details),
        }


@dataclass(frozen=True)
class StudentDatasetValidationResult:
    """Structured validation result for one staged release folder."""

    status: str
    checks: tuple[StudentDatasetValidationCheck, ...]

    @property
    def failed_checks(self) -> tuple[StudentDatasetValidationCheck, ...]:
        return tuple(check for check in self.checks if check.status != "passed")

    def manifest_dict(self) -> dict[str, Any]:
        failed = self.failed_checks
        return {
            "status": self.status,
            "check_count": len(self.checks),
            "failed_check_count": len(failed),
            "checks": [check.manifest_dict() for check in self.checks],
        }


def validate_staged_release(
    *,
    release_dir: Path,
    release_window: StudentDatasetReleaseWindow,
    manifest_row_counts: Mapping[str, int],
) -> StudentDatasetValidationResult:
    """Validate one staged release folder with DuckDB.

    Raises ``StudentDatasetValidationError`` when any validation check fails.
    """

    checks: list[StudentDatasetValidationCheck] = []
    with duckdb.connect(":memory:") as connection:
        checks.extend(_validate_expected_files(release_dir))
        if _has_failures(checks):
            return _raise_validation_error(checks)

        _create_release_views(connection, release_dir)
        checks.extend(_validate_readability(connection))
        checks.extend(_validate_schema(connection))
        checks.extend(_validate_excluded_files(release_dir))
        checks.extend(_validate_primary_key_uniqueness(connection))
        checks.extend(_validate_row_counts(connection, manifest_row_counts))
        checks.extend(_validate_required_non_empty_tables(connection, release_window))
        checks.extend(_validate_relationships(connection))
        checks.extend(_validate_players(connection, release_window))
        checks.extend(_validate_match_shape(connection))
        checks.extend(_validate_temporal_rules(connection, release_window))
        checks.extend(_validate_batch_tied_facts(connection))

    if _has_failures(checks):
        return _raise_validation_error(checks)
    return StudentDatasetValidationResult(status="passed", checks=tuple(checks))


def _validate_expected_files(release_dir: Path) -> tuple[StudentDatasetValidationCheck, ...]:
    checks: list[StudentDatasetValidationCheck] = []
    for table_name in STUDENT_TABLE_ORDER:
        file_path = release_dir / PROJECTION_BY_TABLE[table_name].output_file
        checks.append(
            _check(
                name=f"file_exists:{table_name}",
                passed=file_path.is_file(),
                passed_message=f"{file_path.name} exists.",
                failed_message=f"{file_path.name} is missing.",
                details={"file": file_path.name},
            )
        )
    return tuple(checks)


def _create_release_views(connection: duckdb.DuckDBPyConnection, release_dir: Path) -> None:
    for table_name in STUDENT_TABLE_ORDER:
        parquet_path = _duckdb_string(release_dir / PROJECTION_BY_TABLE[table_name].output_file)
        connection.execute(
            f'CREATE VIEW "{table_name}" AS SELECT * FROM read_parquet({parquet_path})'
        )


def _validate_readability(
    connection: duckdb.DuckDBPyConnection,
) -> tuple[StudentDatasetValidationCheck, ...]:
    checks: list[StudentDatasetValidationCheck] = []
    for table_name in STUDENT_TABLE_ORDER:
        try:
            connection.execute(f'SELECT COUNT(*) FROM "{table_name}"').fetchone()
            checks.append(
                _passed(
                    f"readability:{table_name}",
                    f"{table_name}.parquet can be opened by DuckDB.",
                    {"table": table_name},
                )
            )
        except duckdb.Error as exc:
            checks.append(
                _failed(
                    f"readability:{table_name}",
                    f"{table_name}.parquet cannot be opened by DuckDB.",
                    {"table": table_name, "error": str(exc)},
                )
            )
    return tuple(checks)


def _validate_schema(
    connection: duckdb.DuckDBPyConnection,
) -> tuple[StudentDatasetValidationCheck, ...]:
    checks: list[StudentDatasetValidationCheck] = []
    for table_name in STUDENT_TABLE_ORDER:
        projection = PROJECTION_BY_TABLE[table_name]
        actual_columns = _view_columns(connection, table_name)
        expected_columns = list(projection.included_columns)
        excluded_present = sorted(set(actual_columns) & set(projection.excluded_columns))
        checks.append(
            _check(
                name=f"column_order:{table_name}",
                passed=actual_columns == expected_columns,
                passed_message=f"{table_name} columns match the projection order.",
                failed_message=f"{table_name} columns do not match the projection order.",
                details={
                    "table": table_name,
                    "expected_columns": expected_columns,
                    "actual_columns": actual_columns,
                },
            )
        )
        checks.append(
            _check(
                name=f"excluded_columns:{table_name}",
                passed=not excluded_present,
                passed_message=f"{table_name} contains no excluded columns.",
                failed_message=f"{table_name} contains excluded columns.",
                details={
                    "table": table_name,
                    "excluded_columns_present": excluded_present,
                },
            )
        )
    return tuple(checks)


def _validate_excluded_files(release_dir: Path) -> tuple[StudentDatasetValidationCheck, ...]:
    expected_files = {
        PROJECTION_BY_TABLE[table_name].output_file for table_name in STUDENT_TABLE_ORDER
    }
    parquet_files = {path.name for path in release_dir.glob("*.parquet")}
    excluded_files = sorted(parquet_files & {f"{table_name}.parquet" for table_name in EXCLUDED_SOURCE_TABLES})
    unexpected_files = sorted(parquet_files - expected_files)
    return (
        _check(
            name="excluded_tables_absent",
            passed=not excluded_files,
            passed_message="No excluded source tables are emitted as Parquet files.",
            failed_message="Excluded source tables were emitted as Parquet files.",
            details={"excluded_files": excluded_files},
        ),
        _check(
            name="unexpected_parquet_files_absent",
            passed=not unexpected_files,
            passed_message="No unexpected Parquet files are present.",
            failed_message="Unexpected Parquet files are present.",
            details={"unexpected_files": unexpected_files},
        ),
    )


def _validate_primary_key_uniqueness(
    connection: duckdb.DuckDBPyConnection,
) -> tuple[StudentDatasetValidationCheck, ...]:
    checks: list[StudentDatasetValidationCheck] = []
    for table_name in STUDENT_TABLE_ORDER:
        pk_column = primary_key_column(table_name)
        duplicate_count = _count(
            connection,
            f'''
            SELECT COUNT(*)
            FROM (
                SELECT "{pk_column}"
                FROM "{table_name}"
                GROUP BY "{pk_column}"
                HAVING "{pk_column}" IS NULL OR COUNT(*) > 1
            ) duplicates
            ''',
        )
        checks.append(
            _check(
                name=f"primary_key:{table_name}.{pk_column}",
                passed=duplicate_count == 0,
                passed_message=f"{table_name}.{pk_column} remains unique and populated.",
                failed_message=f"{table_name}.{pk_column} contains null or duplicate values.",
                details={
                    "table": table_name,
                    "primary_key_column": pk_column,
                    "failure_count": duplicate_count,
                },
            )
        )
    return tuple(checks)


def _validate_row_counts(
    connection: duckdb.DuckDBPyConnection,
    manifest_row_counts: Mapping[str, int],
) -> tuple[StudentDatasetValidationCheck, ...]:
    checks: list[StudentDatasetValidationCheck] = []
    for table_name in STUDENT_TABLE_ORDER:
        actual = _count(connection, f'SELECT COUNT(*) FROM "{table_name}"')
        expected = manifest_row_counts.get(table_name)
        checks.append(
            _check(
                name=f"row_count:{table_name}",
                passed=actual == expected,
                passed_message=f"{table_name} row count matches manifest.",
                failed_message=f"{table_name} row count does not match manifest.",
                details={
                    "table": table_name,
                    "expected_count": expected,
                    "actual_count": actual,
                },
            )
        )
    return tuple(checks)


def _validate_required_non_empty_tables(
    connection: duckdb.DuckDBPyConnection,
    release_window: StudentDatasetReleaseWindow,
) -> tuple[StudentDatasetValidationCheck, ...]:
    checks: list[StudentDatasetValidationCheck] = []
    required_tables = (
        BASELINE_REQUIRED_NON_EMPTY_TABLES
        if release_window.release_type == "initial_snapshot"
        else INCREMENTAL_REQUIRED_NON_EMPTY_TABLES
    )
    for table_name in sorted(required_tables):
        row_count = _count(connection, f'SELECT COUNT(*) FROM "{table_name}"')
        checks.append(
            _check(
                name=f"required_non_empty:{table_name}",
                passed=row_count > 0,
                passed_message=f"{table_name} contains at least one row.",
                failed_message=f"{table_name} must contain at least one row.",
                details={"table": table_name, "row_count": row_count},
            )
        )
    return tuple(checks)


def _validate_relationships(
    connection: duckdb.DuckDBPyConnection,
) -> tuple[StudentDatasetValidationCheck, ...]:
    checks: list[StudentDatasetValidationCheck] = []
    for projection in PROJECTION_BY_TABLE.values():
        for relationship in projection.relationship_validations:
            null_filter = (
                ""
                if relationship.nullable
                else f' AND child."{relationship.child_column}" IS NOT NULL'
            )
            missing_count = _count(
                connection,
                f'''
                SELECT COUNT(*)
                FROM "{relationship.child_table}" child
                LEFT JOIN "{relationship.parent_table}" parent
                  ON parent."{relationship.parent_column}" = child."{relationship.child_column}"
                WHERE parent."{relationship.parent_column}" IS NULL{null_filter}
                ''',
            )
            checks.append(
                _check(
                    name=(
                        "relationship:"
                        f"{relationship.child_table}.{relationship.child_column}->"
                        f"{relationship.parent_table}.{relationship.parent_column}"
                    ),
                    passed=missing_count == 0,
                    passed_message="Relationship check passed.",
                    failed_message="Relationship check found missing parent rows.",
                    details={
                        "child_table": relationship.child_table,
                        "child_column": relationship.child_column,
                        "parent_table": relationship.parent_table,
                        "parent_column": relationship.parent_column,
                        "missing_count": missing_count,
                    },
                )
            )
    return tuple(checks)


def _validate_players(
    connection: duckdb.DuckDBPyConnection,
    release_window: StudentDatasetReleaseWindow,
) -> tuple[StudentDatasetValidationCheck, ...]:
    duplicate_player_count = _count(
        connection,
        """
        SELECT COUNT(*)
        FROM (
            SELECT player_id
            FROM "players"
            GROUP BY player_id
            HAVING player_id IS NULL OR COUNT(*) <> 1
        ) failures
        """,
    )
    snapshot_month_mismatch_count = _count(
        connection,
        f"""
        SELECT COUNT(*)
        FROM "players"
        WHERE snapshot_month <> {_duckdb_string(release_window.snapshot_month.isoformat())}
        """,
    )
    incoherent_rating_state_count = _count(
        connection,
        """
        SELECT COUNT(*)
        FROM "players"
        WHERE
            (
                rating_date IS NULL
                AND (
                    rating_batch_id IS NOT NULL
                    OR rating_value IS NOT NULL
                    OR confidence_score IS NOT NULL
                    OR volatility_score IS NOT NULL
                    OR global_percentile IS NOT NULL
                    OR match_count_used IS NOT NULL
                )
            )
            OR (
                rating_date IS NOT NULL
                AND (
                    rating_batch_id IS NULL
                    OR rating_value IS NULL
                )
            )
        """,
    )
    return (
        _check(
            name="players:one_row_per_player",
            passed=duplicate_player_count == 0,
            passed_message="players contains exactly one row per player_id.",
            failed_message="players contains duplicate or null player_id rows.",
            details={"failure_count": duplicate_player_count},
        ),
        _check(
            name="players:snapshot_month_consistent",
            passed=snapshot_month_mismatch_count == 0,
            passed_message="players snapshot_month matches the release snapshot month.",
            failed_message="players snapshot_month does not match the release snapshot month.",
            details={
                "expected_snapshot_month": release_window.snapshot_month.isoformat(),
                "failure_count": snapshot_month_mismatch_count,
            },
        ),
        _check(
            name="players:rating_state_coherent",
            passed=incoherent_rating_state_count == 0,
            passed_message="players rating fields are internally coherent.",
            failed_message="players rating fields are internally inconsistent.",
            details={"failure_count": incoherent_rating_state_count},
        ),
    )


def _validate_match_shape(
    connection: duckdb.DuckDBPyConnection,
) -> tuple[StudentDatasetValidationCheck, ...]:
    winning_team_mismatch_count = _count(
        connection,
        """
        SELECT COUNT(*)
        FROM "matches" m
        LEFT JOIN "match_teams" mt
          ON mt.id = m.winning_team_id
         AND mt.match_id = m.id
        WHERE m.winning_team_id IS NOT NULL
          AND mt.id IS NULL
        """,
    )
    match_team_count_failures = _count(
        connection,
        """
        SELECT COUNT(*)
        FROM (
            SELECT m.id, COUNT(mt.id) AS match_team_count
            FROM "matches" m
            LEFT JOIN "match_teams" mt
              ON mt.match_id = m.id
            GROUP BY m.id
            HAVING COUNT(mt.id) <> 2
        ) failures
        """,
    )
    empty_match_team_count = _count(
        connection,
        """
        SELECT COUNT(*)
        FROM (
            SELECT mt.id
            FROM "match_teams" mt
            LEFT JOIN "match_team_players" mtp
              ON mtp.match_team_id = mt.id
            GROUP BY mt.id
            HAVING COUNT(mtp.id) = 0
        ) failures
        """,
    )
    return (
        _check(
            name="relationship:matches.winning_team_id_same_match",
            passed=winning_team_mismatch_count == 0,
            passed_message="Winning teams belong to their referenced matches.",
            failed_message="Some winning teams do not belong to their referenced matches.",
            details={"mismatch_count": winning_team_mismatch_count},
        ),
        _check(
            name="match_shape:exactly_two_match_teams",
            passed=match_team_count_failures == 0,
            passed_message="Every match has exactly two match teams.",
            failed_message="Some matches do not have exactly two match teams.",
            details={"failure_count": match_team_count_failures},
        ),
        _check(
            name="match_shape:match_team_has_players",
            passed=empty_match_team_count == 0,
            passed_message="Every match team has at least one player row.",
            failed_message="Some match teams have no player rows.",
            details={"failure_count": empty_match_team_count},
        ),
    )


def _validate_temporal_rules(
    connection: duckdb.DuckDBPyConnection,
    release_window: StudentDatasetReleaseWindow,
) -> tuple[StudentDatasetValidationCheck, ...]:
    snapshot_end = release_window.snapshot_end_exclusive.isoformat()
    checks: list[StudentDatasetValidationCheck] = [
        _check(
            name="temporal:monthly_batch_sequences",
            passed=_monthly_batch_sequences(connection)
            == list(release_window.fact_batch_sequences),
            passed_message="monthly_batches.batch_sequence matches the fact window.",
            failed_message="monthly_batches.batch_sequence does not match the fact window.",
            details={
                "expected_sequences": list(release_window.fact_batch_sequences),
                "actual_sequences": _monthly_batch_sequences(connection),
            },
        ),
        _check(
            name="temporal:monthly_batch_months_unique",
            passed=_count(
                connection,
                """
                SELECT COUNT(*)
                FROM (
                    SELECT batch_month
                    FROM "monthly_batches"
                    GROUP BY batch_month
                    HAVING COUNT(*) > 1
                ) duplicate_months
                """,
            )
            == 0,
            passed_message="monthly_batches.batch_month values are unique.",
            failed_message="monthly_batches.batch_month contains duplicate values.",
            details={},
        ),
    ]
    for projection in PROJECTION_BY_TABLE.values():
        for temporal in projection.temporal_validations:
            expression = temporal.expression.replace(
                "snapshot_end_exclusive",
                _duckdb_string(snapshot_end),
            )
            failure_count = _count(
                connection,
                f'SELECT COUNT(*) FROM "{temporal.table_name}" WHERE NOT ({expression})',
            )
            checks.append(
                _check(
                    name=f"temporal:{temporal.table_name}:{temporal.expression}",
                    passed=failure_count == 0,
                    passed_message=temporal.description,
                    failed_message=f"Temporal validation failed: {temporal.description}",
                    details={
                        "table": temporal.table_name,
                        "expression": temporal.expression,
                        "snapshot_end_exclusive": snapshot_end,
                        "failure_count": failure_count,
                    },
                )
            )
    return tuple(checks)


def _validate_batch_tied_facts(
    connection: duckdb.DuckDBPyConnection,
) -> tuple[StudentDatasetValidationCheck, ...]:
    batch_tied_tables = (
        "matches",
        "player_assessment_history",
        "player_registrations",
    )
    checks: list[StudentDatasetValidationCheck] = []
    for table_name in batch_tied_tables:
        missing_count = _count(
            connection,
            f'''
            SELECT COUNT(*)
            FROM "{table_name}" fact
            LEFT JOIN "monthly_batches" batch
              ON batch.id = fact.batch_id
            WHERE batch.id IS NULL
            ''',
        )
        checks.append(
            _check(
                name=f"batch_window:{table_name}.batch_id",
                passed=missing_count == 0,
                passed_message=f"{table_name} rows reference included monthly batches.",
                failed_message=f"{table_name} rows reference batches outside the release window.",
                details={"table": table_name, "missing_count": missing_count},
            )
        )
    return tuple(checks)


def _view_columns(connection: duckdb.DuckDBPyConnection, table_name: str) -> list[str]:
    rows = connection.execute(f'DESCRIBE SELECT * FROM "{table_name}"').fetchall()
    return [str(row[0]) for row in rows]


def _monthly_batch_sequences(connection: duckdb.DuckDBPyConnection) -> list[int]:
    rows = connection.execute(
        'SELECT batch_sequence FROM "monthly_batches" ORDER BY batch_sequence'
    ).fetchall()
    return [int(row[0]) for row in rows]


def _count(connection: duckdb.DuckDBPyConnection, sql: str) -> int:
    value = connection.execute(sql).fetchone()[0]
    return int(value or 0)


def _has_failures(checks: Iterable[StudentDatasetValidationCheck]) -> bool:
    return any(check.status != "passed" for check in checks)


def _raise_validation_error(
    checks: list[StudentDatasetValidationCheck],
) -> StudentDatasetValidationResult:
    result = StudentDatasetValidationResult(status="failed", checks=tuple(checks))
    failed_names = ", ".join(check.name for check in result.failed_checks[:5])
    if len(result.failed_checks) > 5:
        failed_names += ", ..."
    raise StudentDatasetValidationError(
        f"Student dataset validation failed: {failed_names}",
        result,
    )


def _check(
    *,
    name: str,
    passed: bool,
    passed_message: str,
    failed_message: str,
    details: Mapping[str, Any],
) -> StudentDatasetValidationCheck:
    if passed:
        return _passed(name, passed_message, details)
    return _failed(name, failed_message, details)


def _passed(
    name: str,
    message: str,
    details: Mapping[str, Any],
) -> StudentDatasetValidationCheck:
    return StudentDatasetValidationCheck(
        name=name,
        status="passed",
        message=message,
        details=details,
    )


def _failed(
    name: str,
    message: str,
    details: Mapping[str, Any],
) -> StudentDatasetValidationCheck:
    return StudentDatasetValidationCheck(
        name=name,
        status="failed",
        message=message,
        details=details,
    )


def _duckdb_string(value: str | Path) -> str:
    escaped = str(value).replace("'", "''")
    return f"'{escaped}'"
