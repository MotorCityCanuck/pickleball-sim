"""Shared destructive reset helpers for generated synthetic data."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy import delete, text
from sqlalchemy.engine import Dialect
from sqlalchemy.orm import Session

from .reset_plan import GENERATED_OPERATIONAL_REBUILDABLE_MODELS
from app.models import AuditBatchTeamRoster


DELETE_MODELS_IN_ORDER = GENERATED_OPERATIONAL_REBUILDABLE_MODELS
TRUNCATE_MODELS = tuple(
    model_to_truncate
    for model in GENERATED_OPERATIONAL_REBUILDABLE_MODELS
    for model_to_truncate in (
        (AuditBatchTeamRoster, model)
        if model.__name__ == "Team"
        else (model,)
    )
)
POSTGRES_TRUNCATE_DIALECTS = frozenset({"postgresql"})


@dataclass(frozen=True)
class ResetProgressEvent:
    """Structured progress event emitted while resetting generated data."""

    model_name: str
    model_label: str
    step_index: int
    total_steps: int
    status: str
    rows_affected: int | None = None
    reset_strategy: str = "delete"


ResetProgressListener = Callable[[ResetProgressEvent], None]


def reset_progress_message(event: ResetProgressEvent) -> str:
    """Return operator-facing progress text for a reset event."""
    if event.status == "running":
        if event.reset_strategy == "truncate":
            return (
                f"Truncating generated data tables "
                f"({event.step_index}/{event.total_steps})"
            )
        return f"Deleting {event.model_name} ({event.step_index}/{event.total_steps})"

    if event.reset_strategy == "truncate":
        return (
            f"Reset {event.model_name} via truncate "
            f"({event.step_index}/{event.total_steps})"
        )
    if event.rows_affected is None:
        return f"Deleted {event.model_name} ({event.step_index}/{event.total_steps})"
    return (
        f"Deleted {event.model_name} ({event.step_index}/{event.total_steps}); "
        f"{event.rows_affected} rows affected."
    )


def reset_progress_metadata(
    event: ResetProgressEvent,
    *,
    progress_current: int,
) -> dict[str, object]:
    """Return durable metadata for a reset progress event."""
    return {
        "current_model": event.model_name,
        "completed_models": progress_current,
        "total_models": event.total_steps,
        "rows_affected": event.rows_affected,
        "reset_strategy": event.reset_strategy,
    }


def delete_generated_data(
    *,
    session: Session,
    preserve_job_status_id: int | None = None,
    progress_listener: ResetProgressListener | None = None,
) -> None:
    """Compatibility wrapper for generated synthetic data reset."""
    reset_generated_data(
        session=session,
        preserve_job_status_id=preserve_job_status_id,
        progress_listener=progress_listener,
    )


def reset_generated_data(
    *,
    session: Session,
    preserve_job_status_id: int | None = None,
    progress_listener: ResetProgressListener | None = None,
) -> None:
    """Reset generated synthetic data using the best strategy for the active database."""
    del preserve_job_status_id
    dialect = _session_dialect(session)
    if dialect.name in POSTGRES_TRUNCATE_DIALECTS:
        _truncate_generated_data(
            session=session,
            dialect=dialect,
            progress_listener=progress_listener,
        )
        return

    _delete_generated_data(
        session=session,
        progress_listener=progress_listener,
    )


def _delete_generated_data(
    *,
    session: Session,
    progress_listener: ResetProgressListener | None,
) -> None:
    """Delete generated synthetic data in dependency order for non-Postgres dialects."""
    total_steps = len(DELETE_MODELS_IN_ORDER)
    for index, model in enumerate(DELETE_MODELS_IN_ORDER, start=1):
        _emit_progress(
            progress_listener,
            model=model,
            step_index=index,
            total_steps=total_steps,
            status="running",
            reset_strategy="delete",
        )
        statement = delete(model)
        result = session.execute(statement)
        _emit_progress(
            progress_listener,
            model=model,
            step_index=index,
            total_steps=total_steps,
            status="succeeded",
            rows_affected=(
                result.rowcount
                if result.rowcount is not None and result.rowcount >= 0
                else None
            ),
            reset_strategy="delete",
        )
    session.flush()


def _truncate_generated_data(
    *,
    session: Session,
    dialect: Dialect,
    progress_listener: ResetProgressListener | None,
) -> None:
    """Truncate the generated domain as one explicit Postgres FK-safe table group."""
    total_steps = len(TRUNCATE_MODELS)
    if total_steps == 0:
        return

    first_model = TRUNCATE_MODELS[0]
    _emit_progress(
        progress_listener,
        model=first_model,
        step_index=1,
        total_steps=total_steps,
        status="running",
        reset_strategy="truncate",
    )
    session.execute(text(_truncate_statement(TRUNCATE_MODELS, dialect)))
    for index, model in enumerate(TRUNCATE_MODELS, start=1):
        _emit_progress(
            progress_listener,
            model=model,
            step_index=index,
            total_steps=total_steps,
            status="succeeded",
            rows_affected=None,
            reset_strategy="truncate",
        )
    session.flush()


def _session_dialect(session: Session) -> Dialect:
    bind = session.get_bind()
    if bind is None:
        raise RuntimeError("Cannot reset generated data without a bound database session.")
    return bind.dialect


def _truncate_statement(models: tuple[type[object], ...], dialect: Dialect) -> str:
    preparer = dialect.identifier_preparer
    tables = ", ".join(
        preparer.format_table(model.__table__) for model in models
    )
    return f"TRUNCATE TABLE {tables} RESTART IDENTITY"


def _emit_progress(
    progress_listener: ResetProgressListener | None,
    *,
    model: type[object],
    step_index: int,
    total_steps: int,
    status: str,
    rows_affected: int | None = None,
    reset_strategy: str = "delete",
) -> None:
    if progress_listener is None:
        return
    progress_listener(
        ResetProgressEvent(
            model_name=model.__tablename__,
            model_label=model.__name__,
            step_index=step_index,
            total_steps=total_steps,
            status=status,
            rows_affected=rows_affected,
            reset_strategy=reset_strategy,
        )
    )
