"""Raw first-name seed ingestion."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.models import RawFirstName, RawSeedLoadError

from .base import (
    DEFAULT_RAW_ROOT,
    ParsedRow,
    RawSeedLoadResult,
    clean,
    complete_load_run,
    create_load_run,
    discover_source_files,
    iter_delimited_rows,
    parse_int,
    run_in_transaction,
)


SUPPORTED_DATASETS = {"first_names_us", "first_names_ca"}
BATCH_FLUSH_SIZE = 10_000


@dataclass(frozen=True)
class _FirstNameConfig:
    dataset_type: str
    country_code: str
    source_dataset: str
    source_path: Path
    filename_tokens: tuple[str, ...]
    suffixes: tuple[str, ...]
    delimiter: str
    has_header: bool


DATASET_CONFIGS = {
    "first_names_us": _FirstNameConfig(
        dataset_type="first_names_us",
        country_code="US",
        source_dataset="usa_first_names",
        source_path=DEFAULT_RAW_ROOT / "first_names" / "us",
        filename_tokens=(),
        suffixes=(".txt",),
        delimiter=",",
        has_header=False,
    ),
    "first_names_ca": _FirstNameConfig(
        dataset_type="first_names_ca",
        country_code="CA",
        source_dataset="canada_first_names",
        source_path=DEFAULT_RAW_ROOT / "first_names" / "ca",
        filename_tokens=("canada_first_names",),
        suffixes=(".txt",),
        delimiter="|",
        has_header=True,
    ),
}


def load_raw_seed_dataset(
    dataset_type: str,
    *,
    input_path: Path | str | None = None,
    session: Session | None = None,
    job_status_id: int | None = None,
) -> RawSeedLoadResult:
    """Load a supported raw first-name dataset."""
    return FirstNameIngestor().load_dataset(
        dataset_type,
        input_path=input_path,
        session=session,
        job_status_id=job_status_id,
    )


class FirstNameIngestor:
    """Loads raw first-name frequency rows."""

    def load_dataset(
        self,
        dataset_type: str,
        *,
        input_path: Path | str | None = None,
        session: Session | None = None,
        job_status_id: int | None = None,
    ) -> RawSeedLoadResult:
        """Load a supported raw first-name dataset."""
        config = self._get_config(dataset_type)
        source_path = self._resolve_source_path(config, input_path)
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
        config: _FirstNameConfig,
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
            delete(RawFirstName).where(
                RawFirstName.source_dataset == config.source_dataset
            )
        )

        row_batch: list[RawFirstName] = []
        error_batch: list[RawSeedLoadError] = []
        for source_file in source_files:
            for source_row_number, raw_row in self._iter_source_rows(source_file, config):
                load_run.rows_read += 1
                parsed = self._parse_first_name_row(
                    config,
                    source_file,
                    source_row_number,
                    raw_row,
                    load_run.id,
                )
                if parsed.row is not None:
                    row_batch.append(parsed.row)
                    load_run.rows_loaded += 1
                if parsed.error is not None:
                    error_batch.append(parsed.error)
                    load_run.rows_rejected += 1
                if (load_run.rows_loaded + load_run.rows_rejected) % BATCH_FLUSH_SIZE == 0:
                    self._bulk_flush(session, row_batch, error_batch)
                    session.flush()

        self._bulk_flush(session, row_batch, error_batch)

        result = complete_load_run(load_run)
        session.flush()
        return result

    @staticmethod
    def _bulk_flush(
        session: Session,
        row_batch: list[RawFirstName],
        error_batch: list[RawSeedLoadError],
    ) -> None:
        if row_batch:
            session.bulk_save_objects(row_batch)
            row_batch.clear()
        if error_batch:
            session.bulk_save_objects(error_batch)
            error_batch.clear()

    def _parse_first_name_row(
        self,
        config: _FirstNameConfig,
        source_file: Path,
        source_row_number: int,
        raw_row: dict[str, str],
        load_run_id: int,
    ) -> ParsedRow:
        errors: list[str] = []
        raw_payload = dict(raw_row)

        state_province_code = clean(raw_row.get("state_province_code")).upper()
        if not state_province_code:
            errors.append("state/province code is required")

        gender = clean(raw_row.get("gender")).upper()
        if gender not in {"M", "F"}:
            errors.append("gender must be M or F")

        birth_year = parse_int(raw_row.get("birth_year"))
        if birth_year is None:
            errors.append("birth year must be an integer")

        first_name = clean(raw_row.get("first_name"))
        if not first_name:
            errors.append("first name is required")

        frequency_count = parse_int(raw_row.get("frequency_count"))
        if frequency_count is None or frequency_count <= 0:
            errors.append("frequency count must be a positive integer")

        if errors:
            return ParsedRow(
                row=None,
                error=RawSeedLoadError(
                    load_run_id=load_run_id,
                    source_file=str(source_file),
                    source_row_number=source_row_number,
                    error_code="INVALID_FIRST_NAME_ROW",
                    error_message="; ".join(errors),
                    raw_payload=raw_payload,
                ),
            )

        return ParsedRow(
            row=RawFirstName(
                load_run_id=load_run_id,
                source_file=str(source_file),
                source_row_number=source_row_number,
                raw_payload=raw_payload,
                country_code=config.country_code,
                state_province_code=state_province_code,
                gender=gender,
                birth_year=birth_year,
                first_name=first_name,
                frequency_count=frequency_count,
                source_dataset=config.source_dataset,
            ),
            error=None,
        )

    @staticmethod
    def _get_config(dataset_type: str) -> _FirstNameConfig:
        try:
            return DATASET_CONFIGS[dataset_type]
        except KeyError as exc:
            supported = ", ".join(sorted(SUPPORTED_DATASETS))
            raise ValueError(
                f"Unsupported dataset {dataset_type!r}; supported datasets: {supported}."
            ) from exc

    @staticmethod
    def _resolve_source_path(
        config: _FirstNameConfig,
        input_path: Path | str | None,
    ) -> Path:
        if input_path is None:
            return config.source_path
        return Path(input_path)

    @staticmethod
    def _discover_source_files(
        source_path: Path,
        config: _FirstNameConfig,
    ) -> list[Path]:
        if source_path.is_file():
            return [source_path]
        if not config.filename_tokens:
            if not source_path.exists():
                raise FileNotFoundError(f"Input path does not exist: {source_path}")
            if not source_path.is_dir():
                raise ValueError(f"Input path is not a file or directory: {source_path}")
            candidates = [
                path
                for path in source_path.iterdir()
                if path.is_file() and path.suffix.lower() in config.suffixes
            ]
            if not candidates:
                raise FileNotFoundError(
                    f"No source files for {config.dataset_type} found in {source_path}"
                )
            return sorted(candidates)

        return discover_source_files(
            source_path,
            dataset_type=config.dataset_type,
            filename_tokens=config.filename_tokens,
            suffixes=config.suffixes,
        )

    @staticmethod
    def _iter_source_rows(source_file: Path, config: _FirstNameConfig):
        if config.has_header:
            for source_row_number, row in iter_delimited_rows(
                source_file,
                delimiter=config.delimiter,
            ):
                yield source_row_number, {
                    "state_province_code": row.get("province"),
                    "gender": row.get("sex"),
                    "birth_year": row.get("birth_year"),
                    "first_name": row.get("name"),
                    "frequency_count": row.get("number_of_occurrences"),
                }
            return

        for source_row_number, row in iter_delimited_rows_without_header(
            source_file,
            delimiter=config.delimiter,
        ):
            yield source_row_number, {
                "state_province_code": row[0] if len(row) > 0 else "",
                "gender": row[1] if len(row) > 1 else "",
                "birth_year": row[2] if len(row) > 2 else "",
                "first_name": row[3] if len(row) > 3 else "",
                "frequency_count": row[4] if len(row) > 4 else "",
            }


def iter_delimited_rows_without_header(source_file: Path, *, delimiter: str):
    """Yield source row numbers and list rows for headerless files."""
    import csv

    for encoding in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            with source_file.open("r", encoding=encoding, newline="") as handle:
                reader = csv.reader(handle, delimiter=delimiter)
                rows = [
                    (source_row_number, row)
                    for source_row_number, row in enumerate(reader, start=1)
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
