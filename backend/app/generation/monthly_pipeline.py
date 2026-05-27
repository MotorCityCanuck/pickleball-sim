"""End-to-end monthly generation pipeline orchestration."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Callable

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.session import session_scope
from app.generators import (
    ClubMembershipGenerator,
    MatchGenerator,
    PlayerGenerator,
    RatingUpdateGenerator,
    TeamGenerator,
)
from app.models import (
    ClubMembership,
    GenerationRun,
    Match,
    MonthlyBatch,
    Player,
    PlayerRegistration,
    RatingsUpdateLog,
    Team,
)

from .control_plane import GenerationControlPlane


PIPELINE_STEPS = (
    "players",
    "club_memberships",
    "teams",
    "matches",
    "ratings",
)
MAX_PIPELINE_MONTHS = 12


@dataclass(frozen=True)
class PipelineStepResult:
    """Outcome for a single pipeline step."""

    step: str
    status: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MonthlyPipelineResult:
    """Outcome for one processed monthly batch."""

    generation_run_id: int
    batch_id: int
    batch_month: date
    step_results: tuple[PipelineStepResult, ...]


@dataclass(frozen=True)
class MultiMonthPipelineResult:
    """Outcome for one or more processed monthly batches."""

    generation_run_id: int
    months_requested: int
    batch_results: tuple[MonthlyPipelineResult, ...]


@dataclass(frozen=True)
class PipelineProgressEvent:
    """Progress signal emitted before and after each pipeline step."""

    generation_run_id: int
    batch_id: int
    batch_month: date
    step: str
    status: str
    details: dict[str, Any] = field(default_factory=dict)


class MonthlyGenerationPipeline:
    """Coordinate setup, match generation, and rating updates for monthly batches."""

    def __init__(
        self,
        *,
        control_plane: GenerationControlPlane | None = None,
        player_generator: PlayerGenerator | None = None,
        club_membership_generator: ClubMembershipGenerator | None = None,
        team_generator: TeamGenerator | None = None,
        match_generator: MatchGenerator | None = None,
        rating_update_generator: RatingUpdateGenerator | None = None,
    ) -> None:
        self.control_plane = control_plane or GenerationControlPlane()
        self.player_generator = player_generator or PlayerGenerator()
        self.club_membership_generator = (
            club_membership_generator or ClubMembershipGenerator()
        )
        self.team_generator = team_generator or TeamGenerator()
        self.match_generator = match_generator or MatchGenerator()
        self.rating_update_generator = rating_update_generator or RatingUpdateGenerator()

    def run_months(
        self,
        *,
        generation_run_id: int,
        months: int = 1,
        start_batch_id: int | None = None,
        player_count: int | None = None,
        skip_existing: bool = True,
        progress_listener: Callable[[PipelineProgressEvent], None] | None = None,
        session: Session | None = None,
    ) -> MultiMonthPipelineResult:
        """Run the pipeline for up to 12 successive monthly batches."""
        if months < 1 or months > MAX_PIPELINE_MONTHS:
            raise ValueError("months must be between 1 and 12")

        if session is not None:
            return self._run_months(
                generation_run_id=generation_run_id,
                months=months,
                start_batch_id=start_batch_id,
                player_count=player_count,
                skip_existing=skip_existing,
                progress_listener=progress_listener,
                session=session,
            )

        with session_scope() as active_session:
            return self._run_months(
                generation_run_id=generation_run_id,
                months=months,
                start_batch_id=start_batch_id,
                player_count=player_count,
                skip_existing=skip_existing,
                progress_listener=progress_listener,
                session=active_session,
            )

    def _run_months(
        self,
        *,
        generation_run_id: int,
        months: int,
        start_batch_id: int | None,
        player_count: int | None,
        skip_existing: bool,
        progress_listener: Callable[[PipelineProgressEvent], None] | None,
        session: Session,
    ) -> MultiMonthPipelineResult:
        generation_run = session.get(GenerationRun, generation_run_id)
        if generation_run is None:
            raise ValueError(f"Generation run {generation_run_id} does not exist")

        batches = _successive_batches(
            session,
            control_plane=self.control_plane,
            generation_run_id=generation_run_id,
            months=months,
            start_batch_id=start_batch_id,
        )
        results = [
            self._run_batch(
                generation_run_id=generation_run_id,
                batch=batch,
                player_count=player_count if index == 0 else None,
                skip_existing=skip_existing,
                progress_listener=progress_listener,
                session=session,
            )
            for index, batch in enumerate(batches)
        ]
        return MultiMonthPipelineResult(
            generation_run_id=generation_run_id,
            months_requested=months,
            batch_results=tuple(results),
        )

    def _run_batch(
        self,
        *,
        generation_run_id: int,
        batch: MonthlyBatch,
        player_count: int | None,
        skip_existing: bool,
        progress_listener: Callable[[PipelineProgressEvent], None] | None,
        session: Session,
    ) -> MonthlyPipelineResult:
        if batch.processing_status == "succeeded" and skip_existing:
            return MonthlyPipelineResult(
                generation_run_id=generation_run_id,
                batch_id=batch.id,
                batch_month=batch.batch_month,
                step_results=(
                    PipelineStepResult(
                        "batch",
                        "skipped",
                        {"processing_status": batch.processing_status},
                    ),
                ),
            )

        self.control_plane.start_monthly_batch(batch.id, session=session)
        step_results: list[PipelineStepResult] = []
        try:
            step_results.append(
                self._run_step(
                    generation_run_id=generation_run_id,
                    batch=batch,
                    step="players",
                    runner=lambda: self._run_players(
                        generation_run_id,
                        batch.id,
                        player_count,
                        skip_existing,
                        session,
                    ),
                    progress_listener=progress_listener,
                )
            )
            step_results.append(
                self._run_step(
                    generation_run_id=generation_run_id,
                    batch=batch,
                    step="club_memberships",
                    runner=lambda: self._run_club_memberships(
                        generation_run_id,
                        batch.id,
                        skip_existing,
                        session,
                    ),
                    progress_listener=progress_listener,
                )
            )
            step_results.append(
                self._run_step(
                    generation_run_id=generation_run_id,
                    batch=batch,
                    step="teams",
                    runner=lambda: self._run_teams(
                        generation_run_id,
                        batch,
                        skip_existing,
                        session,
                    ),
                    progress_listener=progress_listener,
                )
            )
            step_results.append(
                self._run_step(
                    generation_run_id=generation_run_id,
                    batch=batch,
                    step="matches",
                    runner=lambda: self._run_matches(batch.id, skip_existing, session),
                    progress_listener=progress_listener,
                )
            )
            step_results.append(
                self._run_step(
                    generation_run_id=generation_run_id,
                    batch=batch,
                    step="ratings",
                    runner=lambda: self._run_ratings(batch.id, skip_existing, session),
                    progress_listener=progress_listener,
                )
            )
        except Exception as exc:
            self.control_plane.fail_monthly_batch(
                batch.id,
                str(exc),
                session=session,
            )
            raise

        self.control_plane.complete_monthly_batch(batch.id, session=session)
        session.flush()
        return MonthlyPipelineResult(
            generation_run_id=generation_run_id,
            batch_id=batch.id,
            batch_month=batch.batch_month,
            step_results=tuple(step_results),
        )

    def _run_step(
        self,
        *,
        generation_run_id: int,
        batch: MonthlyBatch,
        step: str,
        runner: Callable[[], PipelineStepResult],
        progress_listener: Callable[[PipelineProgressEvent], None] | None,
    ) -> PipelineStepResult:
        _emit_progress(
            generation_run_id=generation_run_id,
            batch=batch,
            step=step,
            status="running",
            details={},
            progress_listener=progress_listener,
        )
        try:
            result = runner()
        except Exception as exc:
            _emit_progress(
                generation_run_id=generation_run_id,
                batch=batch,
                step=step,
                status="failed",
                details={"error_message": str(exc)},
                progress_listener=progress_listener,
            )
            raise
        _emit_progress(
            generation_run_id=generation_run_id,
            batch=batch,
            step=step,
            status="succeeded" if result.status in {"generated", "skipped"} else result.status,
            details=result.details,
            progress_listener=progress_listener,
        )
        return result

    def _run_players(
        self,
        generation_run_id: int,
        batch_id: int,
        player_count: int | None,
        skip_existing: bool,
        session: Session,
    ) -> PipelineStepResult:
        existing_players = _count(
            session,
            select(func.count()).select_from(Player).where(
                Player.generation_run_id == generation_run_id
            ),
        )
        existing_registrations = _count(
            session,
            select(func.count()).select_from(PlayerRegistration).where(
                PlayerRegistration.batch_id == batch_id
            ),
        )
        if existing_registrations:
            if skip_existing:
                return PipelineStepResult(
                    "players",
                    "skipped",
                    {
                        "existing_players": existing_players,
                        "existing_registrations": existing_registrations,
                    },
                )
            raise ValueError("Player registrations already exist for this batch")

        if existing_players:
            result = self.player_generator.generate_incremental_population(
                generation_run_id=generation_run_id,
                batch_id=batch_id,
                session=session,
            )
        else:
            result = self.player_generator.generate_initial_population(
                generation_run_id=generation_run_id,
                batch_id=batch_id,
                player_count=player_count,
                session=session,
            )
        return PipelineStepResult(
            "players",
            "generated",
            {
                "rows_loaded": result.rows_loaded,
                "active_player_count_end": result.active_player_count_end,
            },
        )

    def _run_club_memberships(
        self,
        generation_run_id: int,
        batch_id: int,
        skip_existing: bool,
        session: Session,
    ) -> PipelineStepResult:
        batch_registrations = _count(
            session,
            select(func.count()).select_from(PlayerRegistration).where(
                PlayerRegistration.batch_id == batch_id
            ),
        )
        if batch_registrations == 0:
            return PipelineStepResult(
                "club_memberships",
                "skipped",
                {"batch_registrations": 0},
            )

        existing = _count(
            session,
            select(func.count()).select_from(ClubMembership).where(
                ClubMembership.generation_run_id == generation_run_id
            ),
        )
        if existing == 0:
            result = self.club_membership_generator.generate_for_run(
                generation_run_id=generation_run_id,
                session=session,
            )
        else:
            result = self.club_membership_generator.generate_for_batch_registrations(
                generation_run_id=generation_run_id,
                batch_id=batch_id,
                session=session,
            )
        return PipelineStepResult(
            "club_memberships",
            "generated",
            {
                "players_evaluated": result.players_evaluated,
                "rows_loaded": result.rows_loaded,
                "batch_registrations": batch_registrations,
            },
        )

    def _run_teams(
        self,
        generation_run_id: int,
        batch: MonthlyBatch,
        skip_existing: bool,
        session: Session,
    ) -> PipelineStepResult:
        batch_team_events = _count(
            session,
            select(func.count()).select_from(Team).where(
                Team.generation_run_id == generation_run_id,
                (Team.formation_date == batch.batch_month)
                | (Team.dissolution_date == batch.batch_month),
            ),
        )
        if batch_team_events:
            if skip_existing:
                return PipelineStepResult(
                    "teams",
                    "skipped",
                    {"batch_team_events": batch_team_events},
                )
            raise ValueError("Team generation already ran for this batch")

        result = self.team_generator.generate_for_batch(
            generation_run_id=generation_run_id,
            batch_id=batch.id,
            session=session,
        )
        return PipelineStepResult(
            "teams",
            "generated",
            {
                "rows_loaded": result.rows_loaded,
                "membership_rows_loaded": result.membership_rows_loaded,
            },
        )

    def _run_matches(
        self,
        batch_id: int,
        skip_existing: bool,
        session: Session,
    ) -> PipelineStepResult:
        existing = _count(
            session,
            select(func.count()).select_from(Match).where(Match.batch_id == batch_id),
        )
        if existing:
            if skip_existing:
                return PipelineStepResult(
                    "matches",
                    "skipped",
                    {"existing_matches": existing},
                )
            raise ValueError(f"Monthly batch {batch_id} already has matches")

        result = self.match_generator.generate_for_batch(
            batch_id=batch_id,
            session=session,
        )
        return PipelineStepResult(
            "matches",
            "generated",
            {
                "match_count": result.match_count,
                "game_count": result.game_count,
            },
        )

    def _run_ratings(
        self,
        batch_id: int,
        skip_existing: bool,
        session: Session,
    ) -> PipelineStepResult:
        existing = _count(
            session,
            select(func.count()).select_from(RatingsUpdateLog).where(
                RatingsUpdateLog.batch_id == batch_id
            ),
        )
        if existing:
            if skip_existing:
                return PipelineStepResult(
                    "ratings",
                    "skipped",
                    {"existing_logs": existing},
                )
            raise ValueError(f"Monthly batch {batch_id} already has rating updates")

        result = self.rating_update_generator.generate_for_batch(
            batch_id=batch_id,
            session=session,
        )
        return PipelineStepResult(
            "ratings",
            "generated",
            {
                "match_count": result.match_count,
                "rating_history_count": result.rating_history_count,
                "log_count": result.log_count,
            },
        )


def _successive_batches(
    session: Session,
    *,
    control_plane: GenerationControlPlane,
    generation_run_id: int,
    months: int,
    start_batch_id: int | None,
) -> list[MonthlyBatch]:
    existing_batches = list(
        session.scalars(
            select(MonthlyBatch)
            .where(MonthlyBatch.generation_run_id == generation_run_id)
            .order_by(MonthlyBatch.batch_month, MonthlyBatch.id)
        )
    )
    if start_batch_id is not None:
        start_index = next(
            (
                index
                for index, batch in enumerate(existing_batches)
                if batch.id == start_batch_id
            ),
            None,
        )
        if start_index is None:
            raise ValueError(
                f"Monthly batch {start_batch_id} does not belong to generation run "
                f"{generation_run_id}"
            )
        selected = existing_batches[start_index : start_index + months]
    else:
        selected = existing_batches[:months]

    while len(selected) < months:
        if not selected and not existing_batches:
            raise ValueError(
                f"Generation run {generation_run_id} has no monthly batches"
            )
        anchor = selected[-1] if selected else existing_batches[-1]
        next_month = _add_months(anchor.batch_month, 1)
        next_sequence = anchor.batch_sequence + 1
        selected.append(
            control_plane.get_or_create_monthly_batch(
                generation_run_id,
                next_month,
                batch_sequence=next_sequence,
                batch_type="future_increment",
                session=session,
            )
        )
    return selected


def _add_months(value: date, months: int) -> date:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    return date(year, month, 1)


def _count(session: Session, statement) -> int:
    return int(session.scalar(statement) or 0)


def _emit_progress(
    generation_run_id: int,
    batch: MonthlyBatch,
    step: str,
    status: str,
    details: dict[str, Any],
    progress_listener: Callable[[PipelineProgressEvent], None] | None,
) -> None:
    if progress_listener is None:
        return
    progress_listener(
        PipelineProgressEvent(
            generation_run_id=generation_run_id,
            batch_id=batch.id,
            batch_month=batch.batch_month,
            step=step,
            status=status,
            details=details,
        )
    )
