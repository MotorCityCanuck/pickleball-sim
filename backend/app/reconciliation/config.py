"""Configuration for source-level Parquet/database reconciliation."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Mapping

from sqlalchemy.engine import URL, make_url

from app.core.config import get_database_url
from app.exports.student_dataset.projection import PROJECTION_BY_TABLE, STUDENT_TABLE_ORDER


DEFAULT_OUTPUT_DIRECTORY = Path("reconciliation_output")
DEFAULT_KEY_COLUMNS: Mapping[str, tuple[str, ...]] = {
    table_name: ("player_id",) if table_name == "player_master" else ("id",)
    for table_name in STUDENT_TABLE_ORDER
}
DEFAULT_COLUMN_MAPPINGS: Mapping[str, Mapping[str, str]] = {
    "club_memberships": {"joined_date": "start_date", "left_date": "end_date"},
    "match_teams": {"team_id": "source_team_id"},
    "player_master": {"player_id": "id"},
}


class ReconciliationConfigError(ValueError):
    """Raised when reconciliation configuration is incomplete or invalid."""


@dataclass(frozen=True)
class DatabaseConfig:
    """Database target metadata."""

    url: str | None = None
    type: str = "postgresql"
    host: str | None = None
    port: int | None = None
    database: str | None = None
    schema: str | None = "public"
    user: str | None = None
    password_env_var: str | None = None

    def sqlalchemy_url(self) -> str:
        """Return a SQLAlchemy connection URL without hard-coding secrets."""

        if self.url:
            return self.url
        if not any((self.host, self.database, self.user, self.password_env_var)):
            return get_database_url()
        password = None
        if self.password_env_var:
            password = os.environ.get(self.password_env_var)
            if password is None:
                raise ReconciliationConfigError(
                    f"Database password environment variable {self.password_env_var!r} is not set."
                )
        return (
            URL.create(
                "postgresql",
                username=self.user,
                password=password,
                host=self.host or "localhost",
                port=self.port or 5432,
                database=self.database,
            ).render_as_string(hide_password=False)
        )

    def safe_dict(self) -> dict[str, Any]:
        """Return report-safe database identifiers."""

        if self.url:
            try:
                parsed = make_url(self.url)
            except Exception:
                return {"url": _mask_url(self.url), "schema": self.schema}
            return {
                "drivername": parsed.drivername,
                "host": parsed.host,
                "port": parsed.port,
                "database": parsed.database,
                "username": parsed.username,
                "schema": self.schema,
            }
        return {
            "type": self.type,
            "host": self.host,
            "port": self.port,
            "database": self.database,
            "schema": self.schema,
            "user": self.user,
            "password_env_var": self.password_env_var,
        }


@dataclass(frozen=True)
class EntityMapping:
    """One Parquet file to one database table mapping."""

    entity: str
    parquet_file: str
    table_name: str
    key_columns: tuple[str, ...]
    column_mappings: Mapping[str, str] = field(default_factory=dict)
    compare_columns: tuple[str, ...] | None = None
    critical: bool = False


@dataclass(frozen=True)
class NormalizationConfig:
    """Approved technical normalization knobs."""

    decimal_scale: int = 6
    float_tolerance: float = 0.000001
    strip_trailing_whitespace: bool = False

    def rules_for_report(self) -> list[str]:
        rules = [
            "SQL/Parquet null values normalize to null.",
            "Dates and timestamps compare using ISO-8601 string representation.",
            f"Decimal values compare after rounding to {self.decimal_scale} places.",
            f"Floating point values compare with tolerance {self.float_tolerance}.",
            "UUID and binary values compare using canonical string representation.",
        ]
        if self.strip_trailing_whitespace:
            rules.append("Trailing whitespace is stripped before string comparison.")
        return rules


@dataclass(frozen=True)
class Waiver:
    """Approved known difference."""

    entity: str
    reason: str
    approval: str
    key: Mapping[str, Any] | None = None
    field: str | None = None
    mismatch_type: str | None = None


@dataclass(frozen=True)
class ReconciliationConfig:
    """Top-level reconciliation configuration."""

    release_name: str
    parquet_root: Path
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    output_directory: Path = DEFAULT_OUTPUT_DIRECTORY
    mappings: tuple[EntityMapping, ...] = ()
    normalization: NormalizationConfig = field(default_factory=NormalizationConfig)
    waivers: tuple[Waiver, ...] = ()
    compute_file_sha256: bool = True


def default_mappings() -> tuple[EntityMapping, ...]:
    """Build default mappings from the repository's student export contract."""

    critical = {
        "player_master",
        "teams",
        "team_memberships",
        "matches",
        "match_teams",
        "match_team_players",
        "match_games",
    }
    mappings: list[EntityMapping] = []
    for table_name in STUDENT_TABLE_ORDER:
        projection = PROJECTION_BY_TABLE[table_name]
        mappings.append(
            EntityMapping(
                entity=table_name,
                parquet_file=projection.output_file,
                table_name=projection.source_table,
                key_columns=DEFAULT_KEY_COLUMNS[table_name],
                column_mappings=dict(DEFAULT_COLUMN_MAPPINGS.get(table_name, {})),
                critical=table_name in critical,
            )
        )
    return tuple(mappings)


def load_reconciliation_config(path: str | Path | None = None) -> ReconciliationConfig:
    """Load reconciliation configuration from YAML/JSON or return defaults."""

    if path is None:
        return ReconciliationConfig(
            release_name="napa_250k",
            parquet_root=Path("."),
            mappings=default_mappings(),
        )
    config_path = Path(path)
    raw = _load_mapping_file(config_path)
    return config_from_mapping(raw, base_dir=config_path.parent)


def config_from_mapping(raw: Mapping[str, Any], *, base_dir: Path | None = None) -> ReconciliationConfig:
    """Create a reconciliation config from a plain mapping."""

    base_dir = base_dir or Path.cwd()
    release_name = str(raw.get("release_name") or "napa_250k")
    parquet_root = _path(raw.get("parquet_root") or ".", base_dir)
    output_directory = _path(raw.get("output_directory") or DEFAULT_OUTPUT_DIRECTORY, base_dir)
    database = _database_from_mapping(raw.get("database") or {})
    normalization = _normalization_from_mapping(raw.get("normalization") or {})
    mappings = _mappings_from_raw(raw.get("mappings"))
    waivers = tuple(_waiver_from_mapping(item) for item in raw.get("waivers") or ())
    return ReconciliationConfig(
        release_name=release_name,
        parquet_root=parquet_root,
        database=database,
        output_directory=output_directory,
        mappings=mappings,
        normalization=normalization,
        waivers=waivers,
        compute_file_sha256=bool(raw.get("compute_file_sha256", True)),
    )


def with_overrides(
    config: ReconciliationConfig,
    *,
    entities: tuple[str, ...] = (),
    output_directory: Path | None = None,
) -> ReconciliationConfig:
    """Apply CLI overrides."""

    mappings = config.mappings
    if entities:
        requested = set(entities)
        mappings = tuple(mapping for mapping in mappings if mapping.entity in requested)
    if output_directory is not None:
        config = replace(config, output_directory=output_directory)
    return replace(config, mappings=mappings)


def _mappings_from_raw(raw: Any) -> tuple[EntityMapping, ...]:
    defaults = {mapping.entity: mapping for mapping in default_mappings()}
    if raw is None:
        return tuple(defaults[table_name] for table_name in STUDENT_TABLE_ORDER)
    if isinstance(raw, Mapping):
        merged: list[EntityMapping] = []
        for file_name, table_config in raw.items():
            entity = str(file_name).removesuffix(".parquet")
            default = defaults.get(entity)
            if isinstance(table_config, str):
                mapping_data: Mapping[str, Any] = {"table_name": table_config}
            else:
                mapping_data = table_config or {}
            merged.append(_entity_mapping_from_mapping(entity, file_name, mapping_data, default))
        return tuple(merged)
    return tuple(_entity_mapping_from_mapping(str(item["entity"]), None, item, defaults.get(str(item["entity"]))) for item in raw)


def _entity_mapping_from_mapping(
    entity: str,
    file_name: str | None,
    raw: Mapping[str, Any],
    default: EntityMapping | None,
) -> EntityMapping:
    parquet_file = str(raw.get("parquet_file") or file_name or (default.parquet_file if default else f"{entity}.parquet"))
    table_name = str(raw.get("table_name") or raw.get("table") or (default.table_name if default else entity))
    key_columns = tuple(raw.get("key_columns") or raw.get("key") or (default.key_columns if default else ("id",)))
    column_mappings = dict(default.column_mappings if default else {})
    column_mappings.update(raw.get("column_mappings") or {})
    compare_columns = raw.get("compare_columns")
    return EntityMapping(
        entity=entity,
        parquet_file=parquet_file,
        table_name=table_name,
        key_columns=key_columns,
        column_mappings=column_mappings,
        compare_columns=tuple(compare_columns) if compare_columns else None,
        critical=bool(raw.get("critical", default.critical if default else False)),
    )


def _database_from_mapping(raw: Mapping[str, Any]) -> DatabaseConfig:
    return DatabaseConfig(
        url=raw.get("url") or raw.get("database_url"),
        type=str(raw.get("type") or "postgresql"),
        host=raw.get("host"),
        port=int(raw["port"]) if raw.get("port") else None,
        database=raw.get("database"),
        schema=str(raw.get("schema") or "public"),
        user=raw.get("user"),
        password_env_var=raw.get("password_env_var"),
    )


def _normalization_from_mapping(raw: Mapping[str, Any]) -> NormalizationConfig:
    return NormalizationConfig(
        decimal_scale=int(raw.get("decimal_scale", 6)),
        float_tolerance=float(raw.get("float_tolerance", 0.000001)),
        strip_trailing_whitespace=bool(raw.get("strip_trailing_whitespace", False)),
    )


def _waiver_from_mapping(raw: Mapping[str, Any]) -> Waiver:
    return Waiver(
        entity=str(raw["entity"]),
        key=raw.get("key"),
        field=raw.get("field"),
        mismatch_type=raw.get("mismatch_type"),
        reason=str(raw["reason"]),
        approval=str(raw["approval"]),
    )


def _load_mapping_file(path: Path) -> Mapping[str, Any]:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        return json.loads(text)
    try:
        import yaml
    except ImportError as exc:
        raise RuntimeError(
            "YAML config requires PyYAML. Install PyYAML or use a JSON config file."
        ) from exc
    return yaml.safe_load(text) or {}


def _path(value: Any, base_dir: Path) -> Path:
    path = Path(str(value)).expanduser()
    if path.is_absolute():
        return path
    return (base_dir / path).resolve()


def _mask_url(url: str) -> str:
    if "@" not in url or ":" not in url:
        return url
    prefix, suffix = url.rsplit("@", 1)
    user = prefix.split("//", 1)[-1].split(":", 1)[0]
    scheme = prefix.split("//", 1)[0]
    return f"{scheme}//{user}:***@{suffix}"
