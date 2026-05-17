"""Raw last-name seed ingestion."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.models import RawLastName, RawSeedLoadError

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
    parse_int,
    run_in_transaction,
)


SUPPORTED_DATASETS = {"last_names_us", "last_names_ca"}


@dataclass(frozen=True)
class _LastNameConfig:
    dataset_type: str
    country_code: str
    source_dataset: str
    filename_tokens: tuple[str, ...]


DATASET_CONFIGS = {
    "last_names_us": _LastNameConfig(
        dataset_type="last_names_us",
        country_code="US",
        source_dataset="usa_last_names",
        filename_tokens=("usa", "us"),
    ),
    "last_names_ca": _LastNameConfig(
        dataset_type="last_names_ca",
        country_code="CA",
        source_dataset="can_last_names",
        filename_tokens=("can", "ca"),
    ),
}


def load_raw_seed_dataset(
    dataset_type: str,
    *,
    input_path: Path | str | None = None,
    session: Session | None = None,
) -> RawSeedLoadResult:
    """Load a supported raw last-name dataset."""
    return LastNameIngestor().load_dataset(
        dataset_type,
        input_path=input_path,
        session=session,
    )


class LastNameIngestor:
    """Loads raw country-level last-name frequency rows."""

    def load_dataset(
        self,
        dataset_type: str,
        *,
        input_path: Path | str | None = None,
        session: Session | None = None,
    ) -> RawSeedLoadResult:
        """Load a supported raw last-name dataset."""
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
            ),
            session=session,
        )

    def _load(
        self,
        config: _LastNameConfig,
        source_path: Path,
        source_files: list[Path],
        session: Session,
    ) -> RawSeedLoadResult:
        load_run = create_load_run(
            session,
            dataset_type=config.dataset_type,
            source_path=source_path,
            source_files=source_files,
        )

        session.execute(
            delete(RawLastName).where(RawLastName.source_dataset == config.source_dataset)
        )

        for source_file in source_files:
            for source_row_number, raw_row in iter_delimited_rows(source_file):
                load_run.rows_read += 1
                parsed = self._parse_last_name_row(
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

    def _parse_last_name_row(
        self,
        config: _LastNameConfig,
        source_file: Path,
        source_row_number: int,
        raw_row: dict[str, str],
        load_run_id: int,
    ) -> ParsedRow:
        errors: list[str] = []
        raw_payload = dict(raw_row)

        last_name = clean(raw_row.get("name")).upper()
        if not last_name:
            errors.append("last name is required")

        frequency_count = parse_int(
            raw_row.get("count")
            if "count" in raw_row
            else raw_row.get("num_of_occurrences")
        )
        if frequency_count is None or frequency_count <= 0:
            errors.append("frequency count must be a positive integer")

        if errors:
            return ParsedRow(
                row=None,
                error=RawSeedLoadError(
                    load_run_id=load_run_id,
                    source_file=str(source_file),
                    source_row_number=source_row_number,
                    error_code="INVALID_LAST_NAME_ROW",
                    error_message="; ".join(errors),
                    raw_payload=raw_payload,
                ),
            )

        return ParsedRow(
            row=RawLastName(
                load_run_id=load_run_id,
                source_file=str(source_file),
                source_row_number=source_row_number,
                raw_payload=raw_payload,
                country_code=config.country_code,
                last_name=last_name,
                frequency_count=frequency_count,
                source_dataset=config.source_dataset,
            ),
            error=None,
        )

    @staticmethod
    def _get_config(dataset_type: str) -> _LastNameConfig:
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
            return DEFAULT_RAW_ROOT / "last_names"
        return Path(input_path)
