"""Raw metro-area seed ingestion."""
from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from pathlib import Path
from typing import Any, Iterable

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.db.session import session_scope
from app.models import RawMetroArea, RawSeedLoadError, RawSeedLoadRun


DEFAULT_RAW_ROOT = Path(__file__).resolve().parents[3] / "data" / "raw"
SUPPORTED_DATASETS = {"metro_areas_us", "metro_areas_ca"}


@dataclass(frozen=True)
class RawSeedLoadResult:
    """Summary of a raw seed-data load."""

    load_run_id: int
    dataset_type: str
    source_file_count: int
    rows_read: int
    rows_loaded: int
    rows_rejected: int
    status: str


@dataclass(frozen=True)
class _DatasetConfig:
    dataset_type: str
    country_code: str
    source_dataset: str
    filename_tokens: tuple[str, ...]
    field_map: dict[str, str]


@dataclass(frozen=True)
class _ParsedRow:
    row: RawMetroArea | None
    error: RawSeedLoadError | None


DATASET_CONFIGS = {
    "metro_areas_us": _DatasetConfig(
        dataset_type="metro_areas_us",
        country_code="US",
        source_dataset="usa_regional_msa_data",
        filename_tokens=("usa", "us"),
        field_map={
            "country": "Country",
            "metro_area_name": "GEO",
            "state_province_code": "state",
            "population": "value",
            "selection_probability": "probability",
        },
    ),
    "metro_areas_ca": _DatasetConfig(
        dataset_type="metro_areas_ca",
        country_code="CA",
        source_dataset="can_regional_msa_data",
        filename_tokens=("can", "ca"),
        field_map={
            "country": "COUNTRY",
            "metro_area_name": "Metro Area Name",
            "state_province_code": "State/Prov",
            "population": "Population",
            "selection_probability": "Probability",
        },
    ),
}


def load_raw_seed_dataset(
    dataset_type: str,
    *,
    input_path: Path | str | None = None,
    session: Session | None = None,
) -> RawSeedLoadResult:
    """Load a supported raw seed dataset into staging tables."""
    return RawSeedIngestor().load_dataset(
        dataset_type,
        input_path=input_path,
        session=session,
    )


class RawSeedIngestor:
    """Coordinates raw seed-data ingestion into staging tables."""

    def load_dataset(
        self,
        dataset_type: str,
        *,
        input_path: Path | str | None = None,
        session: Session | None = None,
    ) -> RawSeedLoadResult:
        """Load a supported dataset.

        The first implementation intentionally supports only metro-area
        datasets and writes only Bronze staging tables.
        """
        config = self._get_config(dataset_type)
        source_path = self._resolve_source_path(input_path)
        source_files = self._discover_source_files(source_path, config)

        if session is not None:
            with session.begin_nested():
                return self._load(config, source_path, source_files, session)

        with session_scope() as active_session:
            with active_session.begin_nested():
                return self._load(config, source_path, source_files, active_session)

    def _load(
        self,
        config: _DatasetConfig,
        source_path: Path,
        source_files: list[Path],
        session: Session,
    ) -> RawSeedLoadResult:
        load_run = RawSeedLoadRun(
            dataset_type=config.dataset_type,
            source_path=str(source_path),
            source_file_count=len(source_files),
            source_checksum=self._source_checksum(source_files),
            started_at=_utc_now(),
            status="running",
            rows_read=0,
            rows_loaded=0,
            rows_rejected=0,
        )
        session.add(load_run)
        session.flush()

        session.execute(
            delete(RawMetroArea).where(
                RawMetroArea.source_dataset == config.source_dataset,
            )
        )

        for source_file in source_files:
            for source_row_number, raw_row in self._iter_csv_rows(source_file):
                load_run.rows_read += 1
                parsed = self._parse_metro_row(
                    config,
                    source_file,
                    source_row_number,
                    raw_row,
                    load_run.id,
                )
                if parsed.row is not None:
                    session.add(parsed.row)
                    load_run.rows_loaded += 1
                if parsed.error is not None:
                    session.add(parsed.error)
                    load_run.rows_rejected += 1

        load_run.status = "completed"
        load_run.completed_at = _utc_now()
        session.flush()

        return RawSeedLoadResult(
            load_run_id=load_run.id,
            dataset_type=load_run.dataset_type,
            source_file_count=load_run.source_file_count,
            rows_read=load_run.rows_read,
            rows_loaded=load_run.rows_loaded,
            rows_rejected=load_run.rows_rejected,
            status=load_run.status,
        )

    def _parse_metro_row(
        self,
        config: _DatasetConfig,
        source_file: Path,
        source_row_number: int,
        raw_row: dict[str, str],
        load_run_id: int,
    ) -> _ParsedRow:
        errors: list[str] = []
        raw_payload = dict(raw_row)

        country_value = _clean(raw_row.get(config.field_map["country"]))
        country_code = _normalize_country(country_value)
        if country_code != config.country_code:
            errors.append(
                f"country must map to {config.country_code}; got {country_value!r}"
            )

        metro_area_name = _clean(raw_row.get(config.field_map["metro_area_name"]))
        if not metro_area_name:
            errors.append("metro area name is required")

        state_province_code = _clean(
            raw_row.get(config.field_map["state_province_code"])
        ).upper()
        if not state_province_code:
            errors.append("state/province code is required")

        population = _parse_int(raw_row.get(config.field_map["population"]))
        if population is None or population <= 0:
            errors.append("population must be a positive integer")

        selection_probability = _parse_decimal(
            raw_row.get(config.field_map["selection_probability"])
        )
        if selection_probability is None or selection_probability < 0:
            errors.append("selection probability must be a non-negative decimal")

        if errors:
            return _ParsedRow(
                row=None,
                error=RawSeedLoadError(
                    load_run_id=load_run_id,
                    source_file=str(source_file),
                    source_row_number=source_row_number,
                    error_code="INVALID_METRO_AREA_ROW",
                    error_message="; ".join(errors),
                    raw_payload=raw_payload,
                ),
            )

        return _ParsedRow(
            row=RawMetroArea(
                load_run_id=load_run_id,
                source_file=str(source_file),
                source_row_number=source_row_number,
                raw_payload=raw_payload,
                country_code=config.country_code,
                state_province_code=state_province_code,
                metro_area_name=metro_area_name,
                population=population,
                selection_probability=selection_probability,
                source_dataset=config.source_dataset,
            ),
            error=None,
        )

    @staticmethod
    def _get_config(dataset_type: str) -> _DatasetConfig:
        try:
            return DATASET_CONFIGS[dataset_type]
        except KeyError as exc:
            supported = ", ".join(sorted(SUPPORTED_DATASETS))
            raise ValueError(
                f"Unsupported dataset {dataset_type!r}; supported datasets: {supported}."
            ) from exc

    @staticmethod
    def _resolve_source_path(input_path: Path | str | None) -> Path:
        if input_path is None:
            return DEFAULT_RAW_ROOT / "metro_areas"
        return Path(input_path)

    @staticmethod
    def _discover_source_files(
        source_path: Path,
        config: _DatasetConfig,
    ) -> list[Path]:
        if source_path.is_file():
            return [source_path]
        if not source_path.exists():
            raise FileNotFoundError(f"Input path does not exist: {source_path}")
        if not source_path.is_dir():
            raise ValueError(f"Input path is not a file or directory: {source_path}")

        candidates = [
            path
            for path in source_path.iterdir()
            if path.is_file()
            and path.suffix.lower() == ".csv"
            and any(token in path.name.lower() for token in config.filename_tokens)
        ]
        if not candidates:
            raise FileNotFoundError(
                f"No CSV files for {config.dataset_type} found in {source_path}"
            )
        return sorted(candidates)

    @staticmethod
    def _iter_csv_rows(source_file: Path) -> Iterable[tuple[int, dict[str, str]]]:
        for encoding in ("utf-8-sig", "cp1252", "latin-1"):
            try:
                with source_file.open("r", encoding=encoding, newline="") as handle:
                    reader = csv.DictReader(handle)
                    rows = [
                        (source_row_number, {key or "": value for key, value in row.items()})
                        for source_row_number, row in enumerate(reader, start=2)
                    ]
                yield from rows
                return
            except UnicodeDecodeError:
                continue

        raise UnicodeDecodeError(
            "utf-8-sig/cp1252/latin-1",
            b"",
            0,
            1,
            f"could not decode {source_file}",
        )

    @staticmethod
    def _source_checksum(source_files: list[Path]) -> str:
        digest = sha256()
        for source_file in source_files:
            digest.update(source_file.name.encode("utf-8"))
            digest.update(b"\0")
            digest.update(source_file.read_bytes())
            digest.update(b"\0")
        return digest.hexdigest()


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _clean(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _normalize_country(value: str) -> str:
    normalized = value.strip().upper()
    if normalized in {"USA", "US", "UNITED STATES"}:
        return "US"
    if normalized in {"CAN", "CA", "CANADA"}:
        return "CA"
    return normalized


def _parse_int(value: Any) -> int | None:
    cleaned = _clean(value).replace(",", "")
    if cleaned == "":
        return None
    try:
        return int(Decimal(cleaned))
    except (InvalidOperation, ValueError):
        return None


def _parse_decimal(value: Any) -> Decimal | None:
    cleaned = _clean(value).replace(",", "")
    if cleaned == "":
        return None
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None
