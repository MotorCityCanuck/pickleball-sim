from pathlib import Path
import sys

from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateSchema


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from scripts.recreate_db_from_orm import _orm_schemas, _orm_table_count  # noqa: E402


def test_orm_schemas_are_discovered_from_metadata():
    assert _orm_schemas() == ["ops"]


def test_orm_table_count_includes_default_and_metadata_schemas():
    class InspectorStub:
        default_schema_name = "public"

        def get_table_names(self, schema=None):
            return {
                "public": ["players", "teams"],
                "ops": ["background_workers"],
            }[schema]

    assert _orm_table_count(InspectorStub(), ["ops"]) == 3


def test_create_schema_uses_postgresql_identifier_quoting():
    ddl = CreateSchema('ops schema', if_not_exists=True).compile(
        dialect=postgresql.dialect()
    )

    assert str(ddl) == 'CREATE SCHEMA IF NOT EXISTS "ops schema"'
