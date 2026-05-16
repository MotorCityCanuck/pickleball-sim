"""Export PostgreSQL reference SQL from SQLAlchemy ORM metadata."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateIndex, CreateTable


BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.models import Base  # noqa: E402


DEFAULT_OUTPUT_PATH = BACKEND_DIR / "schema.sql"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate PostgreSQL schema SQL from ORM metadata."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
        help=f"Output file path. Defaults to {DEFAULT_OUTPUT_PATH}.",
    )
    parser.add_argument(
        "--stdout",
        action="store_true",
        help="Print generated SQL instead of writing it to a file.",
    )
    return parser.parse_args()


def _format_table_sql(dialect: postgresql.dialect) -> list[str]:
    statements: list[str] = []
    for table in Base.metadata.sorted_tables:
        statements.append(str(CreateTable(table).compile(dialect=dialect)).strip() + ";")
    return statements


def _format_index_sql(dialect: postgresql.dialect) -> list[str]:
    indexes = [
        index
        for table in Base.metadata.sorted_tables
        for index in sorted(table.indexes, key=lambda item: item.name or "")
    ]
    return [
        str(CreateIndex(index).compile(dialect=dialect)).strip() + ";"
        for index in sorted(indexes, key=lambda item: item.name or "")
    ]


def generate_schema_sql() -> str:
    dialect = postgresql.dialect()
    table_statements = _format_table_sql(dialect)
    index_statements = _format_index_sql(dialect)

    sections = [
        "-- ============================================",
        "-- Pickleball Simulation Platform - Database Schema",
        "-- Generated from SQLAlchemy ORM metadata",
        "-- Do not edit by hand; run backend/scripts/export_schema_from_orm.py",
        f"-- Total Tables: {len(Base.metadata.tables)}",
        f"-- Explicit Indexes: {len(index_statements)}",
        "-- PostgreSQL 16+",
        "-- ============================================",
        "",
        "-- ============================================",
        "-- TABLES",
        "-- ============================================",
        "",
        "\n\n".join(table_statements),
        "",
        "-- ============================================",
        "-- INDEXES",
        "-- ============================================",
        "",
        "\n".join(index_statements),
        "",
    ]
    return "\n".join(sections)


def main() -> None:
    args = _parse_args()
    sql = generate_schema_sql()

    if args.stdout:
        print(sql, end="")
        return

    output_path = args.output
    if not output_path.is_absolute():
        output_path = REPO_ROOT / output_path
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(sql, encoding="utf-8")
    print(f"wrote={output_path}")
    print(f"table_count={len(Base.metadata.tables)}")
    print(
        "explicit_index_count="
        f"{sum(len(table.indexes) for table in Base.metadata.tables.values())}"
    )


if __name__ == "__main__":
    main()
