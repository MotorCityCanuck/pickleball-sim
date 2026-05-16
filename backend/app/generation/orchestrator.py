"""High-level generation orchestration entry points."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from app.core import SimulationSettings, load_settings
from app.db.session import session_scope
from app.models import GenerationRun, MonthlyBatch

from .control_plane import GenerationControlPlane


@dataclass(frozen=True)
class InitialGenerationPlan:
    """Control-plane records created for a new simulation run."""

    generation_run: GenerationRun
    monthly_batches: list[MonthlyBatch]


class GenerationOrchestrator:
    """Coordinates run setup without creating synthetic domain data."""

    def __init__(
        self,
        settings: SimulationSettings | None = None,
        control_plane: GenerationControlPlane | None = None,
    ) -> None:
        self.settings = settings or load_settings()
        self.control_plane = control_plane or GenerationControlPlane(self.settings)

    def create_initial_generation_plan(
        self,
        generation_name: str,
        first_batch_month: date,
        *,
        seed_value: int | None = None,
        parameter_snapshot: dict[str, Any] | None = None,
        historical_months: int | None = None,
        session: Session | None = None,
    ) -> InitialGenerationPlan:
        """Create a generation run and its initial historical batch records."""
        if historical_months is None:
            historical_months = self.settings.initial_historical_months
        if historical_months < 1:
            raise ValueError("historical_months must be at least 1.")

        if session is not None:
            return self._create_initial_generation_plan(
                generation_name,
                first_batch_month,
                seed_value=seed_value,
                parameter_snapshot=parameter_snapshot,
                historical_months=historical_months,
                session=session,
            )

        with session_scope() as active_session:
            return self._create_initial_generation_plan(
                generation_name,
                first_batch_month,
                seed_value=seed_value,
                parameter_snapshot=parameter_snapshot,
                historical_months=historical_months,
                session=active_session,
            )

    def _create_initial_generation_plan(
        self,
        generation_name: str,
        first_batch_month: date,
        *,
        seed_value: int | None,
        parameter_snapshot: dict[str, Any] | None,
        historical_months: int,
        session: Session,
    ) -> InitialGenerationPlan:
        generation_run = self.control_plane.create_generation_run(
            generation_name,
            seed_value=seed_value,
            parameter_snapshot=parameter_snapshot,
            session=session,
        )

        first_month = _month_start(first_batch_month)
        monthly_batches = [
            self.control_plane.get_or_create_monthly_batch(
                generation_run.id,
                _add_months(first_month, month_offset),
                batch_sequence=month_offset + 1,
                batch_type="historical_initial",
                session=session,
            )
            for month_offset in range(historical_months)
        ]

        return InitialGenerationPlan(
            generation_run=generation_run,
            monthly_batches=monthly_batches,
        )


def _month_start(value: date) -> date:
    return date(value.year, value.month, 1)


def _add_months(value: date, months: int) -> date:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    return date(year, month, 1)
