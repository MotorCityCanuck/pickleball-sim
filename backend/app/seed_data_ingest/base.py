"""Shared raw seed-data ingestion primitives."""
from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from pathlib import Path
from typing import Any, Iterable

from sqlalchemy.orm import Session

from app.db.session import session_scope
from app.models import RawSeedLoadError, RawSeedLoadRun


DEFAULT_RAW_ROOT = Path(__file__).resolve().parents[3] / "data" / "raw"


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
class ParsedRow:
    """Parsed staging row or row-level ingestion error."""

    row: Any | None
    error: RawSeedLoadError | None


def run_in_transaction(callback, session: Session | None = None) -> RawSeedLoadResult:
    """Run a load callback in a transaction or nested transaction."""
    if session is not None:
        with session.begin_nested():
            return callback(session)

    with session_scope() as active_session:
        with active_session.begin_nested():
            return callback(active_session)


def create_load_run(
    session: Session,
    *,
    dataset_type: str,
    source_path: Path,
    source_files: list[Path],
) -> RawSeedLoadRun:
    """Create and flush a running raw seed load-run record."""
    load_run = RawSeedLoadRun(
        dataset_type=dataset_type,
        source_path=str(source_path),
        source_file_count=len(source_files),
        source_checksum=source_checksum(source_files),
        started_at=utc_now(),
        status="running",
        rows_read=0,
        rows_loaded=0,
        rows_rejected=0,
    )
    session.add(load_run)
    session.flush()
    return load_run


def complete_load_run(load_run: RawSeedLoadRun) -> RawSeedLoadResult:
    """Mark a raw seed load run completed and return its summary."""
    load_run.status = "completed"
    load_run.completed_at = utc_now()
    return RawSeedLoadResult(
        load_run_id=load_run.id,
        dataset_type=load_run.dataset_type,
        source_file_count=load_run.source_file_count,
        rows_read=load_run.rows_read,
        rows_loaded=load_run.rows_loaded,
        rows_rejected=load_run.rows_rejected,
        status=load_run.status,
    )


def discover_source_files(
    source_path: Path,
    *,
    dataset_type: str,
    filename_tokens: tuple[str, ...],
    suffixes: tuple[str, ...] = (".csv",),
) -> list[Path]:
    """Discover source files for a dataset from a file or directory path."""
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
        and path.suffix.lower() in suffixes
        and any(token in path.name.lower() for token in filename_tokens)
    ]
    if not candidates:
        raise FileNotFoundError(f"No source files for {dataset_type} found in {source_path}")
    return sorted(candidates)


def iter_delimited_rows(
    source_file: Path,
    *,
    delimiter: str = ",",
) -> Iterable[tuple[int, dict[str, str]]]:
    """Yield source row numbers and dict rows with encoding fallback."""
    for encoding in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            with source_file.open("r", encoding=encoding, newline="") as handle:
                reader = csv.DictReader(handle, delimiter=delimiter)
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


def add_parsed_row(
    session: Session,
    load_run: RawSeedLoadRun,
    parsed: ParsedRow,
) -> None:
    """Add a parsed staging row or error and update load counters."""
    if parsed.row is not None:
        session.add(parsed.row)
        load_run.rows_loaded += 1
    if parsed.error is not None:
        session.add(parsed.error)
        load_run.rows_rejected += 1


def source_checksum(source_files: list[Path]) -> str:
    """Return a stable checksum for source names and bytes."""
    digest = sha256()
    for source_file in source_files:
        digest.update(source_file.name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(source_file.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def utc_now() -> datetime:
    """Return a timezone-naive UTC timestamp for database storage."""
    return datetime.now(UTC).replace(tzinfo=None)


def clean(value: Any) -> str:
    """Normalize raw scalar values to stripped strings."""
    if value is None:
        return ""
    return str(value).strip()


def normalize_country(value: str) -> str:
    """Normalize source country values to production country codes."""
    normalized = value.strip().upper()
    if normalized in {"USA", "US", "UNITED STATES"}:
        return "US"
    if normalized in {"CAN", "CA", "CANADA"}:
        return "CA"
    return normalized


def parse_int(value: Any) -> int | None:
    """Parse integer-like source values, allowing commas and decimals."""
    cleaned = clean(value).replace(",", "")
    if cleaned == "":
        return None
    try:
        return int(Decimal(cleaned))
    except (InvalidOperation, ValueError):
        return None


def parse_decimal(value: Any) -> Decimal | None:
    """Parse decimal source values, allowing commas."""
    cleaned = clean(value).replace(",", "")
    if cleaned == "":
        return None
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None
