"""Release-window planning for student-facing dataset exports."""

from __future__ import annotations

from calendar import monthrange
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import GenerationRun, MonthlyBatch


HISTORICAL_BASELINE_RELEASE_TYPE = "historical_baseline"
MONTHLY_INCREMENTAL_RELEASE_TYPE = "monthly_incremental"


class ReleaseWindowValidationError(ValueError):
    """Raised when a requested student dataset release window is invalid."""


@dataclass(frozen=True)
class StudentDatasetReleaseRequest:
    """Validated build parameters required for release-window planning."""

    generation_run_id: int
    initial_history_month_count: int
    subsequent_month_count: int

    @property
    def maximum_batch_sequence(self) -> int:
        """Return the last monthly batch sequence required by this request."""

        return self.initial_history_month_count + self.subsequent_month_count


@dataclass(frozen=True)
class ReleaseBatch:
    """Monthly batch metadata needed by a planned release."""

    id: int
    batch_sequence: int
    batch_month: date


@dataclass(frozen=True)
class StudentDatasetReleaseWindow:
    """One concrete release folder's monthly-batch window."""

    release_index: int
    release_type: str
    folder_suffix: str
    batch_sequence_start: int
    batch_sequence_end: int
    batches: tuple[ReleaseBatch, ...]

    @property
    def batch_ids(self) -> tuple[int, ...]:
        """Return included monthly batch ids in sequence order."""

        return tuple(batch.id for batch in self.batches)

    @property
    def batch_sequences(self) -> tuple[int, ...]:
        """Return included monthly batch sequences in sequence order."""

        return tuple(batch.batch_sequence for batch in self.batches)

    @property
    def batch_months(self) -> tuple[date, ...]:
        """Return included monthly batch months in sequence order."""

        return tuple(batch.batch_month for batch in self.batches)

    @property
    def snapshot_month(self) -> date:
        """Return the newest monthly batch month included in this release."""

        return self.batches[-1].batch_month

    @property
    def snapshot_end_exclusive(self) -> date:
        """Return the first day after the release snapshot month."""

        return first_day_of_next_month(self.snapshot_month)


def resolve_release_request(
    *,
    generation_run_id: int,
    initial_history_month_count: int,
    subsequent_month_count: int,
) -> StudentDatasetReleaseRequest:
    """Validate and normalize raw release-window parameters."""

    request = StudentDatasetReleaseRequest(
        generation_run_id=_positive_int("generation_run_id", generation_run_id),
        initial_history_month_count=_positive_int(
            "initial_history_month_count",
            initial_history_month_count,
        ),
        subsequent_month_count=_nonnegative_int(
            "subsequent_month_count",
            subsequent_month_count,
        ),
    )
    return request


def plan_release_windows(
    *,
    session: Session,
    generation_run_id: int,
    initial_history_month_count: int,
    subsequent_month_count: int,
) -> tuple[StudentDatasetReleaseWindow, ...]:
    """Validate a generation run and return all requested release windows."""

    request = resolve_release_request(
        generation_run_id=generation_run_id,
        initial_history_month_count=initial_history_month_count,
        subsequent_month_count=subsequent_month_count,
    )
    generation_run = session.get(GenerationRun, request.generation_run_id)
    if generation_run is None:
        raise ReleaseWindowValidationError(
            f"Generation run {request.generation_run_id} does not exist."
        )
    if generation_run.status != "succeeded":
        raise ReleaseWindowValidationError(
            "Generation run must have status 'succeeded' before export; "
            f"found {generation_run.status!r}."
        )

    batches = _load_requested_batches(session, request)
    return build_release_windows(request, batches)


def build_release_windows(
    request: StudentDatasetReleaseRequest,
    requested_batches: Sequence[MonthlyBatch | ReleaseBatch],
) -> tuple[StudentDatasetReleaseWindow, ...]:
    """Build deterministic initial-history and snapshot windows."""

    batch_by_sequence = _validate_requested_batches(request, requested_batches)
    release_windows: list[StudentDatasetReleaseWindow] = []

    initial_batches = tuple(
        batch_by_sequence[sequence]
        for sequence in range(1, request.initial_history_month_count + 1)
    )
    release_windows.append(
        StudentDatasetReleaseWindow(
            release_index=0,
            release_type=HISTORICAL_BASELINE_RELEASE_TYPE,
            folder_suffix="_initial_history",
            batch_sequence_start=1,
            batch_sequence_end=request.initial_history_month_count,
            batches=initial_batches,
        )
    )

    for offset in range(1, request.subsequent_month_count + 1):
        batch_sequence_end = request.initial_history_month_count + offset
        snapshot_batches = tuple(
            batch_by_sequence[sequence]
            for sequence in range(1, batch_sequence_end + 1)
        )
        snapshot_month = snapshot_batches[-1].batch_month
        release_windows.append(
            StudentDatasetReleaseWindow(
                release_index=offset,
                release_type=MONTHLY_INCREMENTAL_RELEASE_TYPE,
                folder_suffix=f"_snapshot_{snapshot_month:%Y_%m}",
                batch_sequence_start=1,
                batch_sequence_end=batch_sequence_end,
                batches=snapshot_batches,
            )
        )

    return tuple(release_windows)


def first_day_of_next_month(value: date) -> date:
    """Return the first day of the month after ``value``."""

    return value.replace(day=monthrange(value.year, value.month)[1]) + timedelta(days=1)


def _load_requested_batches(
    session: Session,
    request: StudentDatasetReleaseRequest,
) -> tuple[MonthlyBatch, ...]:
    return tuple(
        session.scalars(
            select(MonthlyBatch)
            .where(
                MonthlyBatch.generation_run_id == request.generation_run_id,
                MonthlyBatch.batch_sequence <= request.maximum_batch_sequence,
            )
            .order_by(MonthlyBatch.batch_sequence, MonthlyBatch.id)
        )
    )


def _validate_requested_batches(
    request: StudentDatasetReleaseRequest,
    requested_batches: Sequence[MonthlyBatch | ReleaseBatch],
) -> dict[int, ReleaseBatch]:
    batch_by_sequence: dict[int, ReleaseBatch] = {}
    duplicate_sequences: set[int] = set()
    incomplete_sequences: list[int] = []

    for source_batch in requested_batches:
        batch = _to_release_batch(source_batch)
        if batch.batch_sequence in batch_by_sequence:
            duplicate_sequences.add(batch.batch_sequence)
            continue
        batch_by_sequence[batch.batch_sequence] = batch

        processing_status = getattr(source_batch, "processing_status", "succeeded")
        if processing_status != "succeeded":
            incomplete_sequences.append(batch.batch_sequence)

    if duplicate_sequences:
        raise ReleaseWindowValidationError(
            "Duplicate monthly batch_sequence values found for requested export "
            f"window: {sorted(duplicate_sequences)}."
        )

    expected_sequences = set(range(1, request.maximum_batch_sequence + 1))
    actual_sequences = set(batch_by_sequence)
    missing_sequences = sorted(expected_sequences - actual_sequences)
    if missing_sequences:
        raise ReleaseWindowValidationError(
            "Missing completed monthly batches for requested export window: "
            f"{missing_sequences}."
        )

    unexpected_sequences = sorted(actual_sequences - expected_sequences)
    if unexpected_sequences:
        raise ReleaseWindowValidationError(
            "Unexpected monthly batch sequences supplied for requested export "
            f"window: {unexpected_sequences}."
        )

    if incomplete_sequences:
        raise ReleaseWindowValidationError(
            "Monthly batches must have processing_status 'succeeded' before "
            f"export; incomplete sequences: {sorted(incomplete_sequences)}."
        )

    return batch_by_sequence


def _to_release_batch(source_batch: MonthlyBatch | ReleaseBatch) -> ReleaseBatch:
    batch_id = getattr(source_batch, "id")
    batch_sequence = getattr(source_batch, "batch_sequence")
    batch_month = getattr(source_batch, "batch_month")
    if batch_id is None:
        raise ReleaseWindowValidationError("Monthly batch id is required for export.")
    if batch_month is None:
        raise ReleaseWindowValidationError(
            f"Monthly batch {batch_id} is missing batch_month."
        )
    return ReleaseBatch(
        id=int(batch_id),
        batch_sequence=int(batch_sequence),
        batch_month=batch_month,
    )


def _positive_int(name: str, value: int) -> int:
    value = _coerce_int(name, value)
    if value <= 0:
        raise ReleaseWindowValidationError(f"{name} must be greater than zero.")
    return value


def _nonnegative_int(name: str, value: int) -> int:
    value = _coerce_int(name, value)
    if value < 0:
        raise ReleaseWindowValidationError(f"{name} must be zero or greater.")
    return value


def _coerce_int(name: str, value: int) -> int:
    if isinstance(value, bool):
        raise ReleaseWindowValidationError(f"{name} must be an integer.")
    if isinstance(value, float):
        raise ReleaseWindowValidationError(f"{name} must be an integer.")
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ReleaseWindowValidationError(f"{name} must be an integer.") from exc
