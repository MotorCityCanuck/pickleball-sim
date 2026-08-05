"""Recreate a local development database from SQLAlchemy ORM metadata.

This is a destructive development utility. It drops the target database,
creates it again, enables required PostgreSQL extensions, and creates all
tables and indexes from `app.models.Base.metadata`.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys
from urllib.parse import urlparse, urlunparse

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.engine.reflection import Inspector
from sqlalchemy.schema import CreateSchema


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.models import Base  # noqa: E402


DEFAULT_TARGET_DATABASE_URL = "postgresql://postgres:postgres@localhost:5432/pickleball"


def _orm_schemas() -> list[str]:
    return sorted(
        {
            table.schema
            for table in Base.metadata.tables.values()
            if table.schema is not None
        }
    )


def _orm_table_count(inspector: Inspector, schemas: list[str]) -> int:
    relevant_schemas = {inspector.default_schema_name, *schemas}
    return sum(
        len(inspector.get_table_names(schema=schema)) for schema in relevant_schemas
    )


def _database_name(database_url: str) -> str:
    name = make_url(database_url).database
    if not name:
        raise ValueError("Target database URL must include a database name")
    return name


def _admin_database_url(database_url: str) -> str:
    parsed = urlparse(database_url)
    return urlunparse(parsed._replace(path="/postgres"))


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Drop and recreate a development database from ORM metadata."
    )
    parser.add_argument(
        "--database-url",
        default=os.getenv("TARGET_DATABASE_URL")
        or os.getenv("DATABASE_URL")
        or DEFAULT_TARGET_DATABASE_URL,
        help=(
            "Target database URL. Defaults to TARGET_DATABASE_URL, DATABASE_URL, "
            f"or {DEFAULT_TARGET_DATABASE_URL}."
        ),
    )
    parser.add_argument(
        "--admin-database-url",
        default=os.getenv("ADMIN_DATABASE_URL"),
        help="Admin database URL. Defaults to the target URL with database 'postgres'.",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Confirm destructive drop/recreate without an interactive prompt.",
    )
    return parser.parse_args()


def _confirm(database_name: str, assume_yes: bool) -> None:
    if assume_yes:
        return

    response = input(
        f"Drop and recreate database '{database_name}'? Type the database name to continue: "
    )
    if response != database_name:
        raise SystemExit("Aborted; confirmation did not match database name.")


def recreate_database(database_url: str, admin_database_url: str, assume_yes: bool) -> None:
    database_name = _database_name(database_url)
    _confirm(database_name, assume_yes)

    admin_engine = create_engine(admin_database_url, isolation_level="AUTOCOMMIT")
    with admin_engine.connect() as conn:
        conn.execute(
            text(
                """
                SELECT pg_terminate_backend(pid)
                FROM pg_stat_activity
                WHERE datname = :database_name
                  AND pid <> pg_backend_pid()
                """
            ),
            {"database_name": database_name},
        )
        conn.execute(text(f'DROP DATABASE IF EXISTS "{database_name}"'))
        conn.execute(text(f'CREATE DATABASE "{database_name}"'))

    engine = create_engine(database_url)
    orm_schemas = _orm_schemas()
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))
        for schema in orm_schemas:
            conn.execute(CreateSchema(schema, if_not_exists=True))

    Base.metadata.create_all(engine)

    inspector = inspect(engine)
    table_count = _orm_table_count(inspector, orm_schemas)
    explicit_index_count = sum(len(table.indexes) for table in Base.metadata.tables.values())

    print(f"recreated_database={database_name}")
    print(f"table_count={table_count}")
    print(f"metadata_index_count={explicit_index_count}")


def main() -> None:
    args = _parse_args()
    admin_database_url = args.admin_database_url or _admin_database_url(args.database_url)
    recreate_database(args.database_url, admin_database_url, args.yes)


if __name__ == "__main__":
    main()
