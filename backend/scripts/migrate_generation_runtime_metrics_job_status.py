"""Add generation_runtime_metrics.job_status_id for job-scoped runtime attribution."""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import sys

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.config import get_database_url  # noqa: E402


@dataclass(frozen=True)
class MigrationResult:
    dialect: str
    had_job_status_id: bool
    changed: bool


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Add generation_runtime_metrics.job_status_id and supporting index "
            "for job-scoped export runtime attribution."
        )
    )
    parser.add_argument(
        "--database-url",
        default=get_database_url(),
        help="SQLAlchemy database URL. Defaults to DATABASE_URL or app default.",
    )
    parser.add_argument(
        "--report-only",
        action="store_true",
        help="Report current schema state without applying changes.",
    )
    return parser.parse_args()


def migrate_generation_runtime_metrics_job_status(
    database_url: str,
    *,
    report_only: bool = False,
) -> MigrationResult:
    engine = create_engine(database_url, future=True)
    try:
        return _migrate_engine(engine, report_only=report_only)
    finally:
        engine.dispose()


def _migrate_engine(engine: Engine, *, report_only: bool = False) -> MigrationResult:
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    if "generation_runtime_metrics" not in table_names:
        return MigrationResult(
            dialect=engine.dialect.name,
            had_job_status_id=False,
            changed=False,
        )

    column_names = {
        str(column["name"])
        for column in inspector.get_columns("generation_runtime_metrics")
    }
    had_job_status_id = "job_status_id" in column_names
    if report_only or had_job_status_id:
        return MigrationResult(
            dialect=engine.dialect.name,
            had_job_status_id=had_job_status_id,
            changed=False,
        )

    with engine.begin() as connection:
        if engine.dialect.name == "postgresql":
            _migrate_postgresql(connection)
        elif engine.dialect.name == "sqlite":
            _migrate_sqlite(connection)
        else:
            _migrate_generic(connection)

    return MigrationResult(
        dialect=engine.dialect.name,
        had_job_status_id=False,
        changed=True,
    )


def _migrate_postgresql(connection) -> None:
    connection.execute(
        text(
            """
            ALTER TABLE generation_runtime_metrics
            ADD COLUMN IF NOT EXISTS job_status_id BIGINT
            """
        )
    )
    fk_exists = bool(
        connection.execute(
            text(
                """
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'generation_runtime_metrics_job_status_id_fkey'
                """
            )
        ).scalar()
    )
    if not fk_exists:
        connection.execute(
            text(
                """
                ALTER TABLE generation_runtime_metrics
                ADD CONSTRAINT generation_runtime_metrics_job_status_id_fkey
                FOREIGN KEY (job_status_id) REFERENCES job_status (id)
                """
            )
        )
    connection.execute(
        text(
            """
            CREATE INDEX IF NOT EXISTS idx_generation_runtime_metrics_job
            ON generation_runtime_metrics (job_status_id)
            """
        )
    )


def _migrate_sqlite(connection) -> None:
    connection.execute(
        text(
            """
            ALTER TABLE generation_runtime_metrics
            ADD COLUMN job_status_id BIGINT
            """
        )
    )


def _migrate_generic(connection) -> None:
    connection.execute(
        text(
            """
            ALTER TABLE generation_runtime_metrics
            ADD COLUMN job_status_id BIGINT
            """
        )
    )


def main() -> int:
    args = _parse_args()
    result = migrate_generation_runtime_metrics_job_status(
        args.database_url,
        report_only=args.report_only,
    )
    action = "changed" if result.changed else "unchanged"
    print(
        f"generation_runtime_metrics job_status_id migration {action} "
        f"(dialect={result.dialect}, had_job_status_id={result.had_job_status_id})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
