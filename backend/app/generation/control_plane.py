"""Run and batch orchestration for the simulation control plane."""
from __future__ import annotations

from contextlib import nullcontext
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import SimulationSettings, load_settings
from app.db.session import session_scope
from app.models import GenerationRun, MonthlyBatch


GENERATION_TERMINAL_STATUSES = {"succeeded", "failed"}
BATCH_TERMINAL_STATUSES = {"succeeded", "failed"}


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class GenerationControlPlane:
    """Coordinates generation run and monthly batch lifecycle records."""

    def __init__(self, settings: SimulationSettings | None = None) -> None:
        self.settings = settings or load_settings()

    def create_generation_run(
        self,
        generation_name: str,
        *,
        seed_value: int | None = None,
        parameter_snapshot: dict[str, Any] | None = None,
        settings: SimulationSettings | None = None,
        session: Session | None = None,
    ) -> GenerationRun:
        with self._session_context(session) as active_session:
            effective_settings = settings or self.settings
            generation_run = GenerationRun(
                generation_name=generation_name,
                seed_value=seed_value
                if seed_value is not None
                else effective_settings.default_seed_value,
                simulation_version=effective_settings.simulation_version,
                parameter_snapshot=parameter_snapshot,
                status="not_started",
            )
            active_session.add(generation_run)
            active_session.flush()
            return generation_run

    def start_generation_run(
        self,
        generation_run_id: int,
        *,
        session: Session | None = None,
    ) -> GenerationRun:
        with self._session_context(session) as active_session:
            generation_run = self._get_generation_run(
                active_session,
                generation_run_id,
            )
            self._ensure_generation_can_transition(generation_run, "running")
            generation_run.status = "running"
            generation_run.started_at = _utc_now()
            active_session.flush()
            return generation_run

    def complete_generation_run(
        self,
        generation_run_id: int,
        *,
        session: Session | None = None,
    ) -> GenerationRun:
        with self._session_context(session) as active_session:
            generation_run = self._get_generation_run(
                active_session,
                generation_run_id,
            )
            self._ensure_generation_can_transition(generation_run, "succeeded")
            generation_run.status = "succeeded"
            generation_run.completed_at = _utc_now()
            active_session.flush()
            return generation_run

    def fail_generation_run(
        self,
        generation_run_id: int,
        *,
        session: Session | None = None,
    ) -> GenerationRun:
        with self._session_context(session) as active_session:
            generation_run = self._get_generation_run(
                active_session,
                generation_run_id,
            )
            self._ensure_generation_can_transition(generation_run, "failed")
            generation_run.status = "failed"
            generation_run.completed_at = _utc_now()
            active_session.flush()
            return generation_run

    def get_or_create_monthly_batch(
        self,
        generation_run_id: int,
        batch_month: date,
        *,
        batch_sequence: int,
        batch_type: str = "future_increment",
        session: Session | None = None,
    ) -> MonthlyBatch:
        with self._session_context(session) as active_session:
            existing_batch = active_session.execute(
                select(MonthlyBatch).where(
                    MonthlyBatch.generation_run_id == generation_run_id,
                    MonthlyBatch.batch_month == batch_month,
                )
            ).scalar_one_or_none()
            if existing_batch is not None:
                return existing_batch

            self._get_generation_run(active_session, generation_run_id)
            monthly_batch = MonthlyBatch(
                generation_run_id=generation_run_id,
                batch_month=batch_month,
                batch_sequence=batch_sequence,
                batch_type=batch_type,
                processing_status="pending",
            )
            active_session.add(monthly_batch)
            active_session.flush()
            return monthly_batch

    def start_monthly_batch(
        self,
        monthly_batch_id: int,
        *,
        session: Session | None = None,
    ) -> MonthlyBatch:
        with self._session_context(session) as active_session:
            monthly_batch = self._get_monthly_batch(
                active_session,
                monthly_batch_id,
            )
            self._ensure_batch_can_transition(monthly_batch, "running")
            monthly_batch.processing_status = "running"
            monthly_batch.started_at = _utc_now()
            monthly_batch.error_message = None
            active_session.flush()
            return monthly_batch

    def complete_monthly_batch(
        self,
        monthly_batch_id: int,
        *,
        session: Session | None = None,
    ) -> MonthlyBatch:
        with self._session_context(session) as active_session:
            monthly_batch = self._get_monthly_batch(
                active_session,
                monthly_batch_id,
            )
            self._ensure_batch_can_transition(monthly_batch, "succeeded")
            monthly_batch.processing_status = "succeeded"
            monthly_batch.completed_at = _utc_now()
            active_session.flush()
            return monthly_batch

    def fail_monthly_batch(
        self,
        monthly_batch_id: int,
        error_message: str,
        *,
        session: Session | None = None,
    ) -> MonthlyBatch:
        with self._session_context(session) as active_session:
            monthly_batch = self._get_monthly_batch(
                active_session,
                monthly_batch_id,
            )
            self._ensure_batch_can_transition(monthly_batch, "failed")
            monthly_batch.processing_status = "failed"
            monthly_batch.completed_at = _utc_now()
            monthly_batch.error_message = error_message
            active_session.flush()
            return monthly_batch

    def _session_context(self, session: Session | None):
        if session is not None:
            return nullcontext(session)
        return session_scope()

    @staticmethod
    def _get_generation_run(session: Session, generation_run_id: int) -> GenerationRun:
        generation_run = session.get(GenerationRun, generation_run_id)
        if generation_run is None:
            raise ValueError(f"Generation run {generation_run_id} does not exist.")
        return generation_run

    @staticmethod
    def _get_monthly_batch(session: Session, monthly_batch_id: int) -> MonthlyBatch:
        monthly_batch = session.get(MonthlyBatch, monthly_batch_id)
        if monthly_batch is None:
            raise ValueError(f"Monthly batch {monthly_batch_id} does not exist.")
        return monthly_batch

    @staticmethod
    def _ensure_generation_can_transition(
        generation_run: GenerationRun,
        next_status: str,
    ) -> None:
        if generation_run.status in GENERATION_TERMINAL_STATUSES:
            raise ValueError(
                "Generation run "
                f"{generation_run.id} is already {generation_run.status}; "
                f"cannot transition to {next_status}."
            )

    @staticmethod
    def _ensure_batch_can_transition(
        monthly_batch: MonthlyBatch,
        next_status: str,
    ) -> None:
        if monthly_batch.processing_status in BATCH_TERMINAL_STATUSES:
            raise ValueError(
                "Monthly batch "
                f"{monthly_batch.id} is already "
                f"{monthly_batch.processing_status}; "
                f"cannot transition to {next_status}."
            )
