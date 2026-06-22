"""Migrate student dataset release types from historical_baseline to initial_snapshot."""
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


LEGACY_RELEASE_TYPE = "historical_baseline"
CURRENT_RELEASE_TYPE = "initial_snapshot"
INCREMENTAL_RELEASE_TYPE = "monthly_incremental"


@dataclass(frozen=True)
class MigrationResult:
    inspected_release_count: int
    updated_release_count: int
    dialect: str
    release_type_counts: tuple[tuple[str, int], ...] = ()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Rewrite student_dataset_releases.release_type from "
            "'historical_baseline' to 'initial_snapshot'."
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
        help="Report current release-type counts without applying changes.",
    )
    return parser.parse_args()


def migrate_student_dataset_release_types(
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
    if "student_dataset_releases" not in inspector.get_table_names():
        return MigrationResult(
            inspected_release_count=0,
            updated_release_count=0,
            dialect=engine.dialect.name,
            release_type_counts=(),
        )

    with engine.begin() as connection:
        release_count = int(
            connection.execute(
                text("SELECT COUNT(*) FROM student_dataset_releases")
            ).scalar_one()
        )
        legacy_count = int(
            connection.execute(
                text(
                    """
                    SELECT COUNT(*)
                    FROM student_dataset_releases
                    WHERE release_type = :legacy_release_type
                    """
                ),
                {"legacy_release_type": LEGACY_RELEASE_TYPE},
            ).scalar_one()
        )
        if not report_only:
            if engine.dialect.name == "postgresql":
                _migrate_postgresql(connection)
            elif engine.dialect.name == "sqlite":
                _migrate_sqlite(connection)
            else:
                _migrate_generic(connection)
        release_type_counts = tuple(
            (str(row[0]), int(row[1]))
            for row in connection.execute(
                text(
                    """
                    SELECT release_type, COUNT(*)
                    FROM student_dataset_releases
                    GROUP BY release_type
                    ORDER BY release_type
                    """
                )
            ).fetchall()
        )

    return MigrationResult(
        inspected_release_count=release_count,
        updated_release_count=0 if report_only else legacy_count,
        dialect=engine.dialect.name,
        release_type_counts=release_type_counts,
    )


def _migrate_postgresql(connection) -> None:
    connection.execute(
        text(
            """
            ALTER TABLE student_dataset_releases
            DROP CONSTRAINT IF EXISTS chk_student_release_type
            """
        )
    )
    connection.execute(
        text(
            """
            UPDATE student_dataset_releases
            SET release_type = :current_release_type
            WHERE release_type = :legacy_release_type
            """
        ),
        {
            "current_release_type": CURRENT_RELEASE_TYPE,
            "legacy_release_type": LEGACY_RELEASE_TYPE,
        },
    )
    connection.execute(
        text(
            """
            ALTER TABLE student_dataset_releases
            ADD CONSTRAINT chk_student_release_type
            CHECK (release_type IN ('initial_snapshot', 'monthly_incremental'))
            """
        )
    )


def _migrate_sqlite(connection) -> None:
    connection.execute(text("PRAGMA foreign_keys=OFF"))
    connection.execute(
        text(
            """
            CREATE TABLE student_dataset_releases__new (
                id integer primary key,
                release_name varchar(255) not null,
                release_type varchar(50) not null,
                release_month date,
                generation_run_id bigint not null,
                data_quality_level varchar(50),
                output_path text not null,
                status varchar(30) not null default 'pending',
                completed_at datetime,
                error_message text,
                created_at datetime default current_timestamp not null,
                updated_at datetime default current_timestamp not null,
                CONSTRAINT chk_student_release_type
                    CHECK (release_type IN ('initial_snapshot', 'monthly_incremental')),
                CONSTRAINT chk_student_release_status
                    CHECK (status IN ('pending', 'running', 'succeeded', 'failed')),
                FOREIGN KEY(generation_run_id) REFERENCES generation_runs (id)
            )
            """
        )
    )
    connection.execute(
        text(
            """
            INSERT INTO student_dataset_releases__new (
                id,
                release_name,
                release_type,
                release_month,
                generation_run_id,
                data_quality_level,
                output_path,
                status,
                completed_at,
                error_message,
                created_at,
                updated_at
            )
            SELECT
                id,
                release_name,
                CASE
                    WHEN release_type = :legacy_release_type THEN :current_release_type
                    ELSE release_type
                END,
                release_month,
                generation_run_id,
                data_quality_level,
                output_path,
                status,
                completed_at,
                error_message,
                created_at,
                updated_at
            FROM student_dataset_releases
            """
        ),
        {
            "legacy_release_type": LEGACY_RELEASE_TYPE,
            "current_release_type": CURRENT_RELEASE_TYPE,
        },
    )
    connection.execute(text("DROP TABLE student_dataset_releases"))
    connection.execute(
        text("ALTER TABLE student_dataset_releases__new RENAME TO student_dataset_releases")
    )
    connection.execute(
        text(
            """
            CREATE INDEX idx_student_dataset_releases_generation_run
            ON student_dataset_releases (generation_run_id)
            """
        )
    )
    connection.execute(
        text(
            """
            CREATE INDEX idx_student_dataset_releases_status
            ON student_dataset_releases (status)
            """
        )
    )
    connection.execute(text("PRAGMA foreign_keys=ON"))


def _migrate_generic(connection) -> None:
    connection.execute(
        text(
            """
            UPDATE student_dataset_releases
            SET release_type = :current_release_type
            WHERE release_type = :legacy_release_type
            """
        ),
        {
            "current_release_type": CURRENT_RELEASE_TYPE,
            "legacy_release_type": LEGACY_RELEASE_TYPE,
        },
    )


def main() -> None:
    args = _parse_args()
    result = migrate_student_dataset_release_types(
        args.database_url,
        report_only=args.report_only,
    )
    print(f"dialect={result.dialect}")
    print(f"inspected_release_count={result.inspected_release_count}")
    print(f"updated_release_count={result.updated_release_count}")
    for release_type, row_count in result.release_type_counts:
        print(f"release_type_count[{release_type}]={row_count}")


if __name__ == "__main__":
    main()
