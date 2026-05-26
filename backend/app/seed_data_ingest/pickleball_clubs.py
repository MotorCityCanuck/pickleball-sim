"""Raw pickleball club seed ingestion."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.models import (
    RawPickleballClubDistribution,
    RawPickleballClubName,
    RawSeedLoadError,
)

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
    parse_int,
    run_in_transaction,
)


SUPPORTED_DATASETS = {"pickleball_club_distributions", "pickleball_club_names"}


@dataclass(frozen=True)
class _DistributionConfig:
    dataset_type: str
    source_dataset: str
    filename_tokens: tuple[str, ...]


@dataclass(frozen=True)
class _ClubNameConfig:
    dataset_type: str
    source_dataset: str
    filename_tokens: tuple[str, ...]


DISTRIBUTION_CONFIG = _DistributionConfig(
    dataset_type="pickleball_club_distributions",
    source_dataset="pickleball_club_distribution_summary",
    filename_tokens=("distribution", "summary"),
)

CLUB_NAME_CONFIG = _ClubNameConfig(
    dataset_type="pickleball_club_names",
    source_dataset="pickleball_club_names_by_state_province",
    filename_tokens=("club_names", "state_province"),
)


def load_raw_seed_dataset(
    dataset_type: str,
    *,
    input_path: Path | str | None = None,
    session: Session | None = None,
    job_status_id: int | None = None,
) -> RawSeedLoadResult:
    """Load a supported pickleball club seed dataset."""
    if dataset_type == CLUB_NAME_CONFIG.dataset_type:
        return PickleballClubNameIngestor().load_dataset(
            dataset_type,
            input_path=input_path,
            session=session,
            job_status_id=job_status_id,
        )

    return PickleballClubDistributionIngestor().load_dataset(
        dataset_type,
        input_path=input_path,
        session=session,
        job_status_id=job_status_id,
    )


class PickleballClubDistributionIngestor:
    """Loads raw club-count distribution seed data."""

    def load_dataset(
        self,
        dataset_type: str,
        *,
        input_path: Path | str | None = None,
        session: Session | None = None,
        job_status_id: int | None = None,
    ) -> RawSeedLoadResult:
        """Load raw pickleball club distribution rows."""
        if dataset_type != DISTRIBUTION_CONFIG.dataset_type:
            supported = ", ".join(sorted(SUPPORTED_DATASETS))
            raise ValueError(
                f"Unsupported dataset {dataset_type!r}; supported datasets: {supported}."
            )

        source_path = self._resolve_source_path(input_path)
        source_files = discover_source_files(
            source_path,
            dataset_type=DISTRIBUTION_CONFIG.dataset_type,
            filename_tokens=DISTRIBUTION_CONFIG.filename_tokens,
        )

        return run_in_transaction(
            lambda active_session: self._load(
                source_path,
                source_files,
                active_session,
                job_status_id=job_status_id,
            ),
            session=session,
        )

    def _load(
        self,
        source_path: Path,
        source_files: list[Path],
        session: Session,
        *,
        job_status_id: int | None = None,
    ) -> RawSeedLoadResult:
        load_run = create_load_run(
            session,
            job_status_id=job_status_id,
            dataset_type=DISTRIBUTION_CONFIG.dataset_type,
            source_path=source_path,
            source_files=source_files,
        )

        session.execute(
            delete(RawPickleballClubDistribution).where(
                RawPickleballClubDistribution.source_dataset
                == DISTRIBUTION_CONFIG.source_dataset,
            )
        )

        for source_file in source_files:
            for source_row_number, raw_row in iter_delimited_rows(source_file):
                load_run.rows_read += 1
                parsed = self._parse_distribution_row(
                    source_file,
                    source_row_number,
                    raw_row,
                    load_run.id,
                )
                add_parsed_row(session, load_run, parsed)

        result = complete_load_run(load_run)
        session.flush()
        return result

    def _parse_distribution_row(
        self,
        source_file: Path,
        source_row_number: int,
        raw_row: dict[str, str],
        load_run_id: int,
    ) -> ParsedRow:
        errors: list[str] = []
        raw_payload = dict(raw_row)

        country_code = normalize_country(clean(raw_row.get("country")))
        if country_code not in {"US", "CA"}:
            errors.append("country must map to US or CA")

        state_province_code = clean(raw_row.get("state_province_code")).upper()
        if not state_province_code:
            errors.append("state/province code is required")

        state_province_name = clean(raw_row.get("state_province_name"))
        if not state_province_name:
            errors.append("state/province name is required")

        target_club_count = parse_int(raw_row.get("club_count"))
        if target_club_count is None or target_club_count < 0:
            errors.append("club count must be a non-negative integer")

        if errors:
            return ParsedRow(
                row=None,
                error=RawSeedLoadError(
                    load_run_id=load_run_id,
                    source_file=str(source_file),
                    source_row_number=source_row_number,
                    error_code="INVALID_CLUB_DISTRIBUTION_ROW",
                    error_message="; ".join(errors),
                    raw_payload=raw_payload,
                ),
            )

        return ParsedRow(
            row=RawPickleballClubDistribution(
                load_run_id=load_run_id,
                source_file=str(source_file),
                source_row_number=source_row_number,
                raw_payload=raw_payload,
                country_code=country_code,
                state_province_code=state_province_code,
                state_province_name=state_province_name,
                target_club_count=target_club_count,
                source_dataset=DISTRIBUTION_CONFIG.source_dataset,
            ),
            error=None,
        )

    @staticmethod
    def _resolve_source_path(input_path: Path | str | None) -> Path:
        if input_path is None:
            return DEFAULT_RAW_ROOT / "pickleball_clubs" / "distributions"
        return Path(input_path)


class PickleballClubNameIngestor:
    """Loads raw pickleball club name seed data."""

    def load_dataset(
        self,
        dataset_type: str,
        *,
        input_path: Path | str | None = None,
        session: Session | None = None,
        job_status_id: int | None = None,
    ) -> RawSeedLoadResult:
        """Load raw candidate club-name rows."""
        if dataset_type != CLUB_NAME_CONFIG.dataset_type:
            supported = ", ".join(sorted(SUPPORTED_DATASETS))
            raise ValueError(
                f"Unsupported dataset {dataset_type!r}; supported datasets: {supported}."
            )

        source_path = self._resolve_source_path(input_path)
        source_files = discover_source_files(
            source_path,
            dataset_type=CLUB_NAME_CONFIG.dataset_type,
            filename_tokens=CLUB_NAME_CONFIG.filename_tokens,
        )

        return run_in_transaction(
            lambda active_session: self._load(
                source_path,
                source_files,
                active_session,
                job_status_id=job_status_id,
            ),
            session=session,
        )

    def _load(
        self,
        source_path: Path,
        source_files: list[Path],
        session: Session,
        *,
        job_status_id: int | None = None,
    ) -> RawSeedLoadResult:
        load_run = create_load_run(
            session,
            job_status_id=job_status_id,
            dataset_type=CLUB_NAME_CONFIG.dataset_type,
            source_path=source_path,
            source_files=source_files,
        )

        session.execute(
            delete(RawPickleballClubName).where(
                RawPickleballClubName.source_dataset == CLUB_NAME_CONFIG.source_dataset,
            )
        )

        for source_file in source_files:
            for source_row_number, raw_row in iter_delimited_rows(source_file):
                load_run.rows_read += 1
                parsed = self._parse_club_name_row(
                    source_file,
                    source_row_number,
                    raw_row,
                    load_run.id,
                )
                add_parsed_row(session, load_run, parsed)

        result = complete_load_run(load_run)
        session.flush()
        return result

    def _parse_club_name_row(
        self,
        source_file: Path,
        source_row_number: int,
        raw_row: dict[str, str],
        load_run_id: int,
    ) -> ParsedRow:
        errors: list[str] = []
        raw_payload = dict(raw_row)

        club_seed = parse_int(raw_row.get("club_seed_id"))
        if club_seed is None or club_seed <= 0:
            errors.append("club seed id must be a positive integer")

        country_code = normalize_country(clean(raw_row.get("country")))
        if country_code not in {"US", "CA"}:
            errors.append("country must map to US or CA")

        state_province_code = clean(raw_row.get("state_province_code")).upper()
        if not state_province_code:
            errors.append("state/province code is required")

        club_name = clean(raw_row.get("club_name"))
        if not club_name:
            errors.append("club name is required")

        club_type = clean(raw_row.get("club_type")) or None
        size_tier = clean(raw_row.get("size_tier")) or None
        generation_method = clean(raw_row.get("generation_method")) or None

        if errors:
            return ParsedRow(
                row=None,
                error=RawSeedLoadError(
                    load_run_id=load_run_id,
                    source_file=str(source_file),
                    source_row_number=source_row_number,
                    error_code="INVALID_CLUB_NAME_ROW",
                    error_message="; ".join(errors),
                    raw_payload=raw_payload,
                ),
            )

        return ParsedRow(
            row=RawPickleballClubName(
                load_run_id=load_run_id,
                source_file=str(source_file),
                source_row_number=source_row_number,
                raw_payload=raw_payload,
                club_seed=club_seed,
                country_code=country_code,
                state_province_code=state_province_code,
                club_name=club_name,
                club_type=club_type,
                size_tier=size_tier,
                generation_method=generation_method,
                source_dataset=CLUB_NAME_CONFIG.source_dataset,
            ),
            error=None,
        )

    @staticmethod
    def _resolve_source_path(input_path: Path | str | None) -> Path:
        if input_path is None:
            return DEFAULT_RAW_ROOT / "pickleball_clubs" / "names"
        return Path(input_path)
