"""Raw state/province surname-bias seed ingestion."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.models import RawSeedLoadError, RawStateProvBias

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
    parse_decimal,
    run_in_transaction,
)


SUPPORTED_DATASETS = {"state_prov_biases_us", "state_prov_biases_ca"}


@dataclass(frozen=True)
class _BiasConfig:
    dataset_type: str
    country_code: str
    source_dataset: str
    filename_tokens: tuple[str, ...]
    state_field: str


DATASET_CONFIGS = {
    "state_prov_biases_us": _BiasConfig(
        dataset_type="state_prov_biases_us",
        country_code="US",
        source_dataset="usa_state_surname_bias",
        filename_tokens=("usa",),
        state_field="state_code",
    ),
    "state_prov_biases_ca": _BiasConfig(
        dataset_type="state_prov_biases_ca",
        country_code="CA",
        source_dataset="canada_province_surname_bias",
        filename_tokens=("canada",),
        state_field="province_code",
    ),
}


def load_raw_seed_dataset(
    dataset_type: str,
    *,
    input_path: Path | str | None = None,
    session: Session | None = None,
    job_status_id: int | None = None,
) -> RawSeedLoadResult:
    """Load a supported raw state/province surname-bias dataset."""
    return StateProvBiasIngestor().load_dataset(
        dataset_type,
        input_path=input_path,
        session=session,
        job_status_id=job_status_id,
    )


class StateProvBiasIngestor:
    """Loads raw state/province surname-bias rows."""

    def load_dataset(
        self,
        dataset_type: str,
        *,
        input_path: Path | str | None = None,
        session: Session | None = None,
        job_status_id: int | None = None,
    ) -> RawSeedLoadResult:
        """Load a supported raw state/province surname-bias dataset."""
        config = self._get_config(dataset_type)
        source_path = self._resolve_source_path(input_path)
        source_files = discover_source_files(
            source_path,
            dataset_type=config.dataset_type,
            filename_tokens=config.filename_tokens,
        )

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
        config: _BiasConfig,
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
            delete(RawStateProvBias).where(
                RawStateProvBias.source_dataset == config.source_dataset
            )
        )

        for source_file in source_files:
            for source_row_number, raw_row in iter_delimited_rows(source_file):
                load_run.rows_read += 1
                parsed = self._parse_bias_row(
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

    def _parse_bias_row(
        self,
        config: _BiasConfig,
        source_file: Path,
        source_row_number: int,
        raw_row: dict[str, str],
        load_run_id: int,
    ) -> ParsedRow:
        errors: list[str] = []
        raw_payload = dict(raw_row)

        state_province_code = clean(
            raw_row.get(config.state_field) or raw_row.get("state_prov")
        ).upper()
        if not state_province_code:
            errors.append("state/province code is required")

        last_name = clean(raw_row.get("last_name")).upper()
        if not last_name:
            errors.append("last name is required")

        bias_multiplier = parse_decimal(raw_row.get("bias_multiplier"))
        if bias_multiplier is None or bias_multiplier <= 0:
            errors.append("bias multiplier must be a positive decimal")

        bias_reason = clean(raw_row.get("bias_reason")) or None

        if errors:
            return ParsedRow(
                row=None,
                error=RawSeedLoadError(
                    load_run_id=load_run_id,
                    source_file=str(source_file),
                    source_row_number=source_row_number,
                    error_code="INVALID_STATE_PROV_BIAS_ROW",
                    error_message="; ".join(errors),
                    raw_payload=raw_payload,
                ),
            )

        return ParsedRow(
            row=RawStateProvBias(
                load_run_id=load_run_id,
                source_file=str(source_file),
                source_row_number=source_row_number,
                raw_payload=raw_payload,
                country_code=config.country_code,
                state_province_code=state_province_code,
                last_name=last_name,
                bias_multiplier=bias_multiplier,
                bias_reason=bias_reason,
                source_dataset=config.source_dataset,
            ),
            error=None,
        )

    @staticmethod
    def _get_config(dataset_type: str) -> _BiasConfig:
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
            return DEFAULT_RAW_ROOT / "last_names" / "state_prov_biases"
        return Path(input_path)
