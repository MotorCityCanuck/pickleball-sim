"""Tests for Parquet/database release reconciliation."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
import sys

import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from sqlalchemy import Column, Date, Integer, MetaData, Numeric, String, Table, create_engine, insert


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.reconciliation.comparator import run_reconciliation  # noqa: E402
from app.reconciliation.config import (  # noqa: E402
    DatabaseConfig,
    EntityMapping,
    ReconciliationConfigError,
    ReconciliationConfig,
    Waiver,
)


def test_exact_match_passes(tmp_path):
    engine = _engine_with_table(
        "teams",
        [
            {"id": 1, "country_code": "US", "team_division": "mixed_doubles"},
            {"id": 2, "country_code": "CA", "team_division": "mens_doubles"},
        ],
    )
    _write_parquet(
        tmp_path / "teams.parquet",
        [
            {"id": 1, "country_code": "US", "team_division": "mixed_doubles"},
            {"id": 2, "country_code": "CA", "team_division": "mens_doubles"},
        ],
    )

    result = run_reconciliation(_config(tmp_path, "teams"), engine=engine)

    assert result.passed
    assert result.entities[0].value_mismatches == 0


def test_missing_database_record_fails(tmp_path):
    engine = _engine_with_table("teams", [{"id": 1, "country_code": "US", "team_division": "mixed_doubles"}])
    _write_parquet(
        tmp_path / "teams.parquet",
        [
            {"id": 1, "country_code": "US", "team_division": "mixed_doubles"},
            {"id": 2, "country_code": "CA", "team_division": "mens_doubles"},
        ],
    )

    result = run_reconciliation(_config(tmp_path, "teams"), engine=engine)

    assert not result.passed
    assert result.entities[0].missing_in_database == 1


def test_extra_database_record_fails(tmp_path):
    engine = _engine_with_table(
        "teams",
        [
            {"id": 1, "country_code": "US", "team_division": "mixed_doubles"},
            {"id": 2, "country_code": "CA", "team_division": "mens_doubles"},
        ],
    )
    _write_parquet(tmp_path / "teams.parquet", [{"id": 1, "country_code": "US", "team_division": "mixed_doubles"}])

    result = run_reconciliation(_config(tmp_path, "teams"), engine=engine)

    assert not result.passed
    assert result.entities[0].extra_in_database == 1


def test_changed_field_fails_and_writes_mismatch_file(tmp_path):
    engine = _engine_with_table("teams", [{"id": 1, "country_code": "CA", "team_division": "mixed_doubles"}])
    _write_parquet(tmp_path / "teams.parquet", [{"id": 1, "country_code": "US", "team_division": "mixed_doubles"}])

    result = run_reconciliation(_config(tmp_path, "teams"), engine=engine)

    assert not result.passed
    assert result.entities[0].value_mismatches == 1
    assert (result.output_dir / result.entities[0].mismatch_files["value_mismatches"]).exists()


def test_team_membership_mismatch_fails(tmp_path):
    engine = _engine_with_table(
        "team_memberships",
        [{"id": 1, "team_id": 10, "player_id": 100, "player_position": 2}],
    )
    _write_parquet(
        tmp_path / "team_memberships.parquet",
        [{"id": 1, "team_id": 10, "player_id": 100, "player_position": 1}],
    )

    result = run_reconciliation(_config(tmp_path, "team_memberships"), engine=engine)

    assert not result.passed
    assert result.entities[0].critical
    assert result.entities[0].value_mismatches == 1


def test_country_and_category_mismatch_fails(tmp_path):
    engine = _engine_with_table("teams", [{"id": 1, "country_code": "CA", "team_division": "mens_doubles"}])
    _write_parquet(tmp_path / "teams.parquet", [{"id": 1, "country_code": "US", "team_division": "mixed_doubles"}])

    result = run_reconciliation(_config(tmp_path, "teams"), engine=engine)

    assert not result.passed
    assert result.entities[0].value_mismatches == 2


def test_equivalent_null_date_and_numeric_representation_passes(tmp_path):
    engine = _engine_with_table(
        "players",
        [
            {
                "id": 1,
                "first_name": "Alex",
                "dominant_hand": None,
                "birth_date": date(2000, 1, 2),
                "rating": Decimal("4.1234561"),
            }
        ],
        table_columns=(
            Column("id", Integer, primary_key=True),
            Column("first_name", String),
            Column("dominant_hand", String),
            Column("birth_date", Date),
            Column("rating", Numeric(10, 7)),
        ),
    )
    _write_parquet(
        tmp_path / "players.parquet",
        [
            {
                "id": 1,
                "first_name": "Alex",
                "dominant_hand": None,
                "birth_date": date(2000, 1, 2),
                "rating": Decimal("4.1234560"),
            }
        ],
    )

    result = run_reconciliation(_config(tmp_path, "players"), engine=engine)

    assert result.passed


def test_defective_source_record_that_matches_database_passes(tmp_path):
    engine = _engine_with_table("teams", [{"id": 1, "country_code": "XX", "team_division": "unknown"}])
    _write_parquet(tmp_path / "teams.parquet", [{"id": 1, "country_code": "XX", "team_division": "unknown"}])

    result = run_reconciliation(_config(tmp_path, "teams"), engine=engine)

    assert result.passed


def test_known_difference_waiver_passes_with_visible_count(tmp_path):
    engine = _engine_with_table("teams", [{"id": 1, "country_code": "CA", "team_division": "mixed_doubles"}])
    _write_parquet(tmp_path / "teams.parquet", [{"id": 1, "country_code": "US", "team_division": "mixed_doubles"}])
    config = _config(
        tmp_path,
        "teams",
        waivers=(
            Waiver(
                entity="teams",
                key={"id": 1},
                field="country_code",
                mismatch_type="value_mismatch",
                reason="Approved classroom environment exception.",
                approval="Instructor approval for test fixture.",
            ),
        ),
    )

    result = run_reconciliation(config, engine=engine)

    assert result.passed
    assert result.entities[0].waived_mismatches == 1


def test_missing_password_environment_variable_fails_before_connect(monkeypatch):
    monkeypatch.delenv("NAPA_DB_PASSWORD", raising=False)
    database = DatabaseConfig(
        host="localhost",
        port=5432,
        database="pickleball",
        user="postgres",
        password_env_var="NAPA_DB_PASSWORD",
    )

    with pytest.raises(ReconciliationConfigError, match="NAPA_DB_PASSWORD"):
        database.sqlalchemy_url()


def test_missing_parquet_root_fails_before_database_connection(tmp_path):
    config = ReconciliationConfig(
        release_name="test_release",
        parquet_root=tmp_path / "does_not_exist",
        database=DatabaseConfig(schema=None),
        output_directory=tmp_path / "out",
        mappings=(
            EntityMapping(
                entity="teams",
                parquet_file="teams.parquet",
                table_name="teams",
                key_columns=("id",),
            ),
        ),
        compute_file_sha256=False,
    )

    with pytest.raises(ReconciliationConfigError, match="Parquet root does not exist"):
        run_reconciliation(config, engine=create_engine("sqlite+pysqlite:///:memory:", future=True))


def test_database_config_preserves_password_in_sqlalchemy_url(monkeypatch):
    monkeypatch.setenv("NAPA_DB_PASSWORD", "postgres")
    database = DatabaseConfig(
        host="localhost",
        port=5432,
        database="pickleball",
        user="postgres",
        password_env_var="NAPA_DB_PASSWORD",
    )

    assert database.sqlalchemy_url() == "postgresql://postgres:postgres@localhost:5432/pickleball"


def _config(tmp_path: Path, entity: str, *, waivers: tuple[Waiver, ...] = ()) -> ReconciliationConfig:
    return ReconciliationConfig(
        release_name="test_release",
        parquet_root=tmp_path,
        database=DatabaseConfig(schema=None),
        output_directory=tmp_path / "out",
        mappings=(
            EntityMapping(
                entity=entity,
                parquet_file=f"{entity}.parquet",
                table_name=entity,
                key_columns=("id",),
                critical=entity in {"teams", "team_memberships"},
            ),
        ),
        waivers=waivers,
        compute_file_sha256=False,
    )


def _engine_with_table(
    table_name: str,
    rows: list[dict],
    *,
    table_columns: tuple[Column, ...] | None = None,
):
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    metadata = MetaData()
    columns = table_columns or tuple(_column_for(name) for name in rows[0])
    table = Table(table_name, metadata, *columns)
    metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(insert(table), rows)
    return engine


def _column_for(name: str) -> Column:
    column_type = Integer if name in {"id", "team_id", "player_id", "player_position"} else String
    return Column(name, column_type, primary_key=name == "id")


def _write_parquet(path: Path, rows: list[dict]) -> None:
    if not rows:
        pytest.fail("test helper requires at least one row")
    columns = list(rows[0])
    table = pa.table({column: pa.array([row.get(column) for row in rows]) for column in columns})
    pq.write_table(table, path)
