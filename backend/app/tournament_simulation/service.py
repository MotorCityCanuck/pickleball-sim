"""Service layer for tournament event and simulation workflows."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
import random
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.default_configuration import DEFAULT_CONFIG_PAYLOAD
from app.db.session import SessionLocal, session_scope
from app.generators.matches import MatchGenerationConfig
from app.models import (
    JobStatus,
    TournamentEvent,
    TournamentOfficialGame,
    TournamentOfficialMatch,
    TournamentSimulationRun,
    TournamentStudentGroup,
    TournamentSubmission,
)

from .config import TournamentScoringConfig, TournamentSimulationConfig
from .dtos import StudentGroup
from .persistence import (
    latest_run_summary,
    replace_monte_carlo_results,
    replace_official_results,
)
from .monte_carlo import run_monte_carlo
from .round_robin_simulator import simulate_division_round_robin
from .student_scoring import score_student_groups
from .team_loader import (
    SubmissionValidationIssue,
    TeamSubmission,
    ValidatedTournamentInput,
    load_validated_tournament_input,
)


@dataclass(frozen=True)
class TournamentEventCreation:
    """Created tournament event workflow records."""

    event: TournamentEvent
    student_groups: tuple[TournamentStudentGroup, ...]
    submissions: tuple[TournamentSubmission, ...]


@dataclass(frozen=True)
class TournamentRunStart:
    """Started or registered tournament simulation run."""

    simulation_run: TournamentSimulationRun
    job_status: JobStatus


class TournamentService:
    """Application service for tournament validation and simulation runs."""

    def create_event(
        self,
        *,
        event_name: str,
        source_batch_id: int,
        tournament_date: date,
        student_groups: tuple[StudentGroup, ...],
        submissions: tuple[TeamSubmission, ...],
        generation_run_id: int | None = None,
        config_snapshot: dict[str, Any] | None = None,
        validation: ValidatedTournamentInput | None = None,
        session: Session | None = None,
    ) -> TournamentEventCreation:
        """Create event, groups, and normalized submissions."""
        if session is not None:
            return self._create_event(
                event_name=event_name,
                source_batch_id=source_batch_id,
                tournament_date=tournament_date,
                student_groups=student_groups,
                submissions=submissions,
                generation_run_id=generation_run_id,
                config_snapshot=config_snapshot,
                validation=validation,
                session=session,
            )
        with session_scope() as active_session:
            return self._create_event(
                event_name=event_name,
                source_batch_id=source_batch_id,
                tournament_date=tournament_date,
                student_groups=student_groups,
                submissions=submissions,
                generation_run_id=generation_run_id,
                config_snapshot=config_snapshot,
                validation=validation,
                session=active_session,
            )

    def validate_event(
        self,
        *,
        event_id: int,
        session: Session | None = None,
    ) -> ValidatedTournamentInput:
        """Validate persisted event submissions and update submission statuses."""
        if session is not None:
            return self._validate_event(event_id=event_id, session=session)
        with session_scope() as active_session:
            return self._validate_event(event_id=event_id, session=active_session)

    def run_monte_carlo(
        self,
        *,
        event_id: int,
        iterations: int,
        seed: int,
        session: Session | None = None,
    ) -> TournamentRunStart:
        """Synchronously run and persist Monte Carlo aggregate outputs."""
        if session is not None:
            start = self._register_run(
                event_id=event_id,
                run_type="monte_carlo",
                seed=seed,
                iterations=iterations,
                session=session,
            )
            self._execute_run(simulation_run_id=start.simulation_run.id, session=session)
            return start
        with session_scope() as active_session:
            start = self._register_run(
                event_id=event_id,
                run_type="monte_carlo",
                seed=seed,
                iterations=iterations,
                session=active_session,
            )
            self._execute_run(
                simulation_run_id=start.simulation_run.id,
                session=active_session,
            )
            return start

    def run_official(
        self,
        *,
        event_id: int,
        seed: int,
        session: Session | None = None,
    ) -> TournamentRunStart:
        """Synchronously run and persist official match/game outputs."""
        if session is not None:
            start = self._register_run(
                event_id=event_id,
                run_type="official",
                seed=seed,
                iterations=1,
                session=session,
            )
            self._execute_run(simulation_run_id=start.simulation_run.id, session=session)
            return start
        with session_scope() as active_session:
            start = self._register_run(
                event_id=event_id,
                run_type="official",
                seed=seed,
                iterations=1,
                session=active_session,
            )
            self._execute_run(
                simulation_run_id=start.simulation_run.id,
                session=active_session,
            )
            return start

    def register_monte_carlo_run(
        self,
        *,
        event_id: int,
        iterations: int,
        seed: int,
        session: Session,
    ) -> TournamentRunStart:
        """Register a pending Monte Carlo run for background execution."""
        return self._register_run(
            event_id=event_id,
            run_type="monte_carlo",
            seed=seed,
            iterations=iterations,
            session=session,
        )

    def register_official_run(
        self,
        *,
        event_id: int,
        seed: int,
        session: Session,
    ) -> TournamentRunStart:
        """Register a pending official run for background execution."""
        return self._register_run(
            event_id=event_id,
            run_type="official",
            seed=seed,
            iterations=1,
            session=session,
        )

    def execute_run_in_background(self, *, simulation_run_id: int) -> None:
        """Execute a registered run with durable background commits."""
        session = SessionLocal()
        try:
            self._execute_run(simulation_run_id=simulation_run_id, session=session)
            session.commit()
        except Exception as exc:
            session.rollback()
            _mark_run_failed_durable(simulation_run_id, str(exc))
            raise
        finally:
            session.close()

    def latest_summary(
        self,
        *,
        event_id: int,
        session: Session | None = None,
    ) -> dict[str, Any] | None:
        """Fetch compact latest summary for one event."""
        if session is not None:
            return latest_run_summary(session, event_id=event_id)
        with session_scope() as active_session:
            return latest_run_summary(active_session, event_id=event_id)

    def official_match_detail(
        self,
        *,
        official_match_id: int,
        session: Session | None = None,
    ) -> dict[str, Any] | None:
        """Fetch official match and game detail from tournament tables."""
        if session is not None:
            return self._official_match_detail(
                official_match_id=official_match_id,
                session=session,
            )
        with session_scope() as active_session:
            return self._official_match_detail(
                official_match_id=official_match_id,
                session=active_session,
            )

    def _create_event(
        self,
        *,
        event_name: str,
        source_batch_id: int,
        tournament_date: date,
        student_groups: tuple[StudentGroup, ...],
        submissions: tuple[TeamSubmission, ...],
        generation_run_id: int | None,
        config_snapshot: dict[str, Any] | None,
        validation: ValidatedTournamentInput | None,
        session: Session,
    ) -> TournamentEventCreation:
        from app.models import MonthlyBatch

        source_batch = session.get(MonthlyBatch, source_batch_id)
        if source_batch is None:
            raise ValueError(f"Monthly batch {source_batch_id} does not exist")
        if source_batch.processing_status != "succeeded":
            raise ValueError(f"Monthly batch {source_batch_id} is not succeeded")
        resolved_generation_run_id = generation_run_id or source_batch.generation_run_id
        if resolved_generation_run_id != source_batch.generation_run_id:
            raise ValueError("generation_run_id does not match source batch")

        event = TournamentEvent(
            event_name=event_name,
            generation_run_id=resolved_generation_run_id,
            source_batch_id=source_batch_id,
            tournament_date=tournament_date,
            config_snapshot=config_snapshot or DEFAULT_CONFIG_PAYLOAD,
            status="draft",
        )
        session.add(event)
        session.flush()

        groups_by_input_id: dict[int, TournamentStudentGroup] = {}
        persisted_groups: list[TournamentStudentGroup] = []
        for group in student_groups:
            row = TournamentStudentGroup(
                event_id=event.id,
                group_name=group.name,
                external_group_key=str(group.id),
            )
            session.add(row)
            session.flush()
            groups_by_input_id[group.id] = row
            persisted_groups.append(row)

        persisted_submissions: list[TournamentSubmission] = []
        for submission in submissions:
            group_row = groups_by_input_id.get(submission.group_id)
            if group_row is None:
                raise ValueError(f"Submission references unknown group {submission.group_id}")
            row = TournamentSubmission(
                event_id=event.id,
                student_group_id=group_row.id,
                slot_country_code=submission.slot.country_code,
                slot_division=submission.slot.division,
                team_id=submission.team_id,
                validation_status="pending",
            )
            session.add(row)
            persisted_submissions.append(row)
        session.flush()
        if validation is not None:
            _apply_submission_validation_statuses(
                submissions=tuple(persisted_submissions),
                validation=validation,
                group_db_id_by_input_id={
                    input_id: group.id
                    for input_id, group in groups_by_input_id.items()
                },
            )
            event.status = "ready" if validation.is_valid else "draft"
            session.flush()
        return TournamentEventCreation(
            event=event,
            student_groups=tuple(persisted_groups),
            submissions=tuple(persisted_submissions),
        )

    def _validate_event(
        self,
        *,
        event_id: int,
        session: Session,
    ) -> ValidatedTournamentInput:
        event = _event_or_raise(session, event_id)
        group_input_id_by_db_id = _group_input_id_by_db_id(session, event_id=event.id)
        submissions = tuple(
            TeamSubmission(
                group_id=group_input_id_by_db_id[row.student_group_id],
                slot=_slot(row.slot_country_code, row.slot_division),
                team_id=row.team_id,
            )
            for row in _event_submissions(session, event_id=event.id)
        )
        result = load_validated_tournament_input(
            session,
            submissions=submissions,
            tournament_date=event.tournament_date,
            source_batch_id=event.source_batch_id,
            generation_run_id=event.generation_run_id,
        )
        _update_submission_validation_statuses(
            session,
            event_id=event.id,
            validation=result,
            group_db_id_by_input_id={
                input_id: db_id for db_id, input_id in group_input_id_by_db_id.items()
            },
        )
        event.status = "ready" if result.is_valid else "draft"
        session.flush()
        return result

    def _register_run(
        self,
        *,
        event_id: int,
        run_type: str,
        seed: int,
        iterations: int,
        session: Session,
    ) -> TournamentRunStart:
        event = _event_or_raise(session, event_id)
        if iterations < 1:
            raise ValueError("iterations must be at least 1")
        job_status = JobStatus(
            job_type=f"tournament_{run_type}",
            job_id=str(uuid4()),
            status="pending",
            percent_complete=Decimal("0"),
            current_phase="registered",
            current_message="Tournament simulation run registered.",
        )
        session.add(job_status)
        session.flush()
        simulation_run = TournamentSimulationRun(
            event_id=event.id,
            run_type=run_type,
            status="pending",
            seed=seed,
            iteration_count=iterations if run_type == "monte_carlo" else 1,
            config_snapshot=event.config_snapshot,
            job_status_id=job_status.id,
        )
        session.add(simulation_run)
        session.flush()
        return TournamentRunStart(
            simulation_run=simulation_run,
            job_status=job_status,
        )

    def _execute_run(self, *, simulation_run_id: int, session: Session) -> None:
        simulation_run = session.get(TournamentSimulationRun, simulation_run_id)
        if simulation_run is None:
            raise ValueError(f"Tournament simulation run {simulation_run_id} does not exist")
        if simulation_run.status != "pending":
            raise ValueError(
                f"Tournament simulation run {simulation_run_id} is {simulation_run.status}"
            )
        job_status = session.get(JobStatus, simulation_run.job_status_id)
        event = _event_or_raise(session, simulation_run.event_id)

        try:
            _mark_run_running(simulation_run, job_status)
            event.status = "running"
            session.commit()
            validation = self._validate_event(event_id=event.id, session=session)
            if not validation.is_valid:
                raise ValueError("Tournament event has invalid submissions")

            simulation_config = _simulation_config(
                event=event,
                seed=int(simulation_run.seed or 1),
            )
            scoring_config = _scoring_config(event.config_snapshot)
            if simulation_run.run_type == "monte_carlo":
                group_db_id_by_input_id = _group_db_id_by_input_id(
                    session,
                    event_id=event.id,
                )
                result = run_monte_carlo(
                    validation.divisions,
                    simulation_config=simulation_config,
                    scoring_config=scoring_config,
                    iterations=int(simulation_run.iteration_count or 1),
                    progress_callback=lambda completed, total: _update_monte_carlo_progress(
                        session,
                        simulation_run=simulation_run,
                        job_status=job_status,
                        completed_iterations=completed,
                        total_iterations=total,
                    ),
                )
                _mark_persisting_results(job_status)
                session.commit()
                replace_monte_carlo_results(
                    session,
                    simulation_run=simulation_run,
                    result=result,
                    divisions=validation.divisions,
                    team_slots=_team_slots(validation),
                    group_db_id_by_input_id=group_db_id_by_input_id,
                )
            elif simulation_run.run_type == "official":
                group_db_id_by_input_id = _group_db_id_by_input_id(
                    session,
                    event_id=event.id,
                )
                rng = random.Random(int(simulation_run.seed or 1))
                division_results = tuple(
                    simulate_division_round_robin(
                        division,
                        config=simulation_config,
                        rng=rng,
                    )
                    for division in validation.divisions
                )
                group_scores = score_student_groups(
                    division_results,
                    config=scoring_config,
                )
                replace_official_results(
                    session,
                    simulation_run=simulation_run,
                    division_results=division_results,
                    group_scores=group_scores,
                    group_db_id_by_input_id=group_db_id_by_input_id,
                )
            else:
                raise ValueError(f"Unsupported tournament run type {simulation_run.run_type}")

            _mark_run_succeeded(simulation_run, job_status)
            event.status = "completed"
            session.flush()
        except Exception as exc:
            _mark_run_failed(simulation_run, job_status, str(exc))
            session.flush()
            raise

    def _official_match_detail(
        self,
        *,
        official_match_id: int,
        session: Session,
    ) -> dict[str, Any] | None:
        match = session.get(TournamentOfficialMatch, official_match_id)
        if match is None:
            return None
        games = session.execute(
            select(TournamentOfficialGame)
            .where(TournamentOfficialGame.official_match_id == match.id)
            .order_by(TournamentOfficialGame.game_number)
        ).scalars()
        return {
            "id": match.id,
            "simulation_run_id": match.simulation_run_id,
            "slot_country_code": match.slot_country_code,
            "slot_division": match.slot_division,
            "match_number": match.match_number,
            "team_one_id": match.team_one_id,
            "team_two_id": match.team_two_id,
            "winning_team_id": match.winning_team_id,
            "team_one_games_won": match.team_one_games_won,
            "team_two_games_won": match.team_two_games_won,
            "team_one_points": match.team_one_points,
            "team_two_points": match.team_two_points,
            "games": [
                {
                    "game_number": game.game_number,
                    "team_one_score": game.team_one_score,
                    "team_two_score": game.team_two_score,
                    "winning_team_number": game.winning_team_number,
                }
                for game in games
            ],
        }


def _event_or_raise(session: Session, event_id: int) -> TournamentEvent:
    event = session.get(TournamentEvent, event_id)
    if event is None:
        raise ValueError(f"Tournament event {event_id} does not exist")
    return event


def _event_submissions(session: Session, *, event_id: int) -> tuple[TournamentSubmission, ...]:
    return tuple(
        session.execute(
            select(TournamentSubmission)
            .where(TournamentSubmission.event_id == event_id)
            .order_by(TournamentSubmission.id)
        ).scalars()
    )


def _group_input_id_by_db_id(session: Session, *, event_id: int) -> dict[int, int]:
    groups = session.execute(
        select(TournamentStudentGroup).where(TournamentStudentGroup.event_id == event_id)
    ).scalars()
    return {
        group.id: int(group.external_group_key or group.id)
        for group in groups
    }


def _group_db_id_by_input_id(session: Session, *, event_id: int) -> dict[int, int]:
    return {
        input_id: db_id
        for db_id, input_id in _group_input_id_by_db_id(
            session,
            event_id=event_id,
        ).items()
    }


def _update_submission_validation_statuses(
    session: Session,
    *,
    event_id: int,
    validation: ValidatedTournamentInput,
    group_db_id_by_input_id: dict[int, int],
) -> None:
    _apply_submission_validation_statuses(
        submissions=_event_submissions(session, event_id=event_id),
        validation=validation,
        group_db_id_by_input_id=group_db_id_by_input_id,
    )


def _apply_submission_validation_statuses(
    *,
    submissions: tuple[TournamentSubmission, ...],
    validation: ValidatedTournamentInput,
    group_db_id_by_input_id: dict[int, int],
) -> None:
    issue_key: dict[tuple[int, str, str, int], list[SubmissionValidationIssue]] = {}
    for issue in validation.issues:
        key = (
            group_db_id_by_input_id[issue.group_id],
            issue.slot.country_code,
            issue.slot.division,
            issue.team_id,
        )
        issue_key.setdefault(key, []).append(issue)

    for row in submissions:
        issues = issue_key.get(
            (row.student_group_id, row.slot_country_code, row.slot_division, row.team_id),
            [],
        )
        if issues:
            row.validation_status = "invalid"
            row.validation_message = "; ".join(issue.message for issue in issues)
        else:
            row.validation_status = "valid"
            row.validation_message = None


def _simulation_config(
    *,
    event: TournamentEvent,
    seed: int,
) -> TournamentSimulationConfig:
    match_config = MatchGenerationConfig.from_payload(event.config_snapshot)
    return TournamentSimulationConfig(
        match_date=event.tournament_date,
        game_config=match_config,
        hidden_bias_config=match_config.hidden_performance_bias,
        seed=seed,
    )


def _scoring_config(config_snapshot: dict[str, Any] | None) -> TournamentScoringConfig:
    section = (config_snapshot or {}).get("tournament_scoring", {})
    return TournamentScoringConfig(
        champion_points=Decimal(str(section.get("champion_points", "10"))),
        runner_up_points=Decimal(str(section.get("runner_up_points", "6"))),
        top_four_points=Decimal(str(section.get("top_four_points", "3"))),
        match_win_points=Decimal(str(section.get("match_win_points", "1"))),
        top_four_points_enabled=bool(section.get("top_four_points_enabled", False)),
    )


def _team_slots(validation: ValidatedTournamentInput) -> dict[int, tuple[str, str]]:
    return {
        entry.id: (entry.country_code, entry.division)
        for division in validation.divisions
        for entry in division.entries
    }


def _slot(country_code: str, division: str):
    from .dtos import PortfolioSlot

    return PortfolioSlot(country_code=country_code, division=division)


def _mark_run_running(
    simulation_run: TournamentSimulationRun,
    job_status: JobStatus | None,
) -> None:
    now = datetime.now(UTC)
    simulation_run.status = "running"
    simulation_run.started_at = now
    if job_status is not None:
        job_status.status = "running"
        job_status.started_at = now
        job_status.current_phase = "running"
        job_status.percent_complete = Decimal("10")
        job_status.current_message = "Tournament simulation running."


def _mark_run_succeeded(
    simulation_run: TournamentSimulationRun,
    job_status: JobStatus | None,
) -> None:
    now = datetime.now(UTC)
    simulation_run.status = "succeeded"
    simulation_run.completed_at = now
    if job_status is not None:
        job_status.status = "succeeded"
        job_status.completed_at = now
        job_status.current_phase = "completed"
        job_status.percent_complete = Decimal("100")
        job_status.current_message = "Tournament simulation completed."


def _mark_run_failed(
    simulation_run: TournamentSimulationRun,
    job_status: JobStatus | None,
    error_message: str,
) -> None:
    now = datetime.now(UTC)
    simulation_run.status = "failed"
    simulation_run.completed_at = now
    simulation_run.error_message = error_message
    if job_status is not None:
        job_status.status = "failed"
        job_status.completed_at = now
        job_status.current_phase = "failed"
        job_status.error_message = error_message
        job_status.current_message = "Tournament simulation failed."


def _mark_run_failed_durable(simulation_run_id: int, error_message: str) -> None:
    with session_scope() as session:
        simulation_run = session.get(TournamentSimulationRun, simulation_run_id)
        if simulation_run is None:
            return
        job_status = session.get(JobStatus, simulation_run.job_status_id)
        _mark_run_failed(simulation_run, job_status, error_message)


def _update_monte_carlo_progress(
    session: Session,
    *,
    simulation_run: TournamentSimulationRun,
    job_status: JobStatus | None,
    completed_iterations: int,
    total_iterations: int,
) -> None:
    if job_status is None or total_iterations < 1:
        return
    percent = Decimal("10") + (
        Decimal("85") * Decimal(completed_iterations) / Decimal(total_iterations)
    )
    job_status.status = "running"
    job_status.current_phase = "simulating"
    job_status.percent_complete = percent.quantize(Decimal("0.01"))
    job_status.current_message = (
        f"Monte Carlo iteration {completed_iterations}/{total_iterations} completed."
    )
    simulation_run.status = "running"
    session.commit()


def _mark_persisting_results(job_status: JobStatus | None) -> None:
    if job_status is None:
        return
    job_status.status = "running"
    job_status.current_phase = "persisting_results"
    job_status.percent_complete = Decimal("95.00")
    job_status.current_message = "Persisting Monte Carlo results."
