"""Raw metro-area seed ingestion."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.models import RawMetroArea, RawSeedLoadError

from .base import (
    DEFAULT_RAW_ROOT,
    ParsedRow,
    RawSeedLoadResult,
    add_parsed_row,
    clean,
    complete_load_run,
    create_load_run,
    discover_source_files,
    iter_delimited_rows,
    normalize_country,
    parse_decimal,
    parse_int,
    run_in_transaction,
)


SUPPORTED_DATASETS = {"metro_areas_us", "metro_areas_ca"}


@dataclass(frozen=True)
class _DatasetConfig:
    dataset_type: str
    country_code: str
    source_dataset: str
    filename_tokens: tuple[str, ...]
    field_map: dict[str, str]


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
    job_status_id: int | None = None,
) -> RawSeedLoadResult:
    """Load a supported raw seed dataset into staging tables."""
    return RawSeedIngestor().load_dataset(
        dataset_type,
        input_path=input_path,
        session=session,
        job_status_id=job_status_id,
    )


class RawSeedIngestor:
    """Coordinates raw metro-area ingestion into staging tables."""

    def load_dataset(
        self,
        dataset_type: str,
        *,
        input_path: Path | str | None = None,
        session: Session | None = None,
        job_status_id: int | None = None,
    ) -> RawSeedLoadResult:
        """Load a supported metro-area dataset."""
        config = self._get_config(dataset_type)
        source_path = self._resolve_source_path(input_path)
        source_files = self._discover_source_files(source_path, config)

        return run_in_transaction(
            lambda active_session: self._load(
                config,
                source_path,
                source_files,
                active_session,
                job_status_id=job_status_id,
            ),
            session=session,
        )

    def _load(
        self,
        config: _DatasetConfig,
        source_path: Path,
        source_files: list[Path],
        session: Session,
        *,
        job_status_id: int | None = None,
    ) -> RawSeedLoadResult:
        load_run = create_load_run(
            session,
            job_status_id=job_status_id,
            dataset_type=config.dataset_type,
            source_path=source_path,
            source_files=source_files,
        )

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
                add_parsed_row(session, load_run, parsed)

        result = complete_load_run(load_run)
        session.flush()
        return result

    def _parse_metro_row(
        self,
        config: _DatasetConfig,
        source_file: Path,
        source_row_number: int,
        raw_row: dict[str, str],
        load_run_id: int,
    ) -> ParsedRow:
        errors: list[str] = []
        raw_payload = dict(raw_row)

        country_value = clean(raw_row.get(config.field_map["country"]))
        country_code = normalize_country(country_value)
        if country_code != config.country_code:
            errors.append(
                f"country must map to {config.country_code}; got {country_value!r}"
            )

        metro_area_name = clean(raw_row.get(config.field_map["metro_area_name"]))
        if not metro_area_name:
            errors.append("metro area name is required")

        state_province_code = clean(
            raw_row.get(config.field_map["state_province_code"])
        ).upper()
        if not state_province_code:
            errors.append("state/province code is required")

        population = parse_int(raw_row.get(config.field_map["population"]))
        if population is None or population <= 0:
            errors.append("population must be a positive integer")

        selection_probability = parse_decimal(
            raw_row.get(config.field_map["selection_probability"])
        )
        if selection_probability is None or selection_probability < 0:
            errors.append("selection probability must be a non-negative decimal")

        if errors:
            return ParsedRow(
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

        return ParsedRow(
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
        return discover_source_files(
            source_path,
            dataset_type=config.dataset_type,
            filename_tokens=config.filename_tokens,
        )

    @staticmethod
    def _iter_csv_rows(source_file: Path):
        return iter_delimited_rows(source_file)
