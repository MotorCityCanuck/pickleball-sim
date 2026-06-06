"""FastAPI routes for the operator control panel."""
from __future__ import annotations

from functools import lru_cache
import logging
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
from types import SimpleNamespace
from typing import Any
import zipfile
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Body, Depends, Form, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from starlette.background import BackgroundTask
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.background_jobs import (
    BackgroundJobRunner,
    get_default_background_job_runner,
)
from app.core import (
    ConfigurationLifecycleService,
    build_config_editor_sections,
    diff_config_payloads,
)
from app.db.session import get_session
from app.exports.student_dataset import StudentDatasetExportService
from app.generation import GenerationRunService, SeedRefreshService
from app.models import (
    JobStatus,
    TournamentEvent,
    TournamentSimulationRun,
    TournamentStudentGroup,
    TournamentSubmission,
)
from app.tournament_simulation import (
    PortfolioSlot,
    StudentGroup,
    TeamSubmission,
    TournamentService,
    latest_completed_source_batch,
    load_validated_tournament_input,
    validate_tournament_submission,
)

from .control_panel_queries import (
    ConfigEditorState,
    ControlPanelQueries,
    ControlPanelSnapshot,
    merge_payload_sections,
    split_payload_sections,
)
from .job_recovery import clear_stalled_job, dismiss_failed_job


TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates"
PROJECT_ROOT = Path(__file__).resolve().parents[3]
logger = logging.getLogger("uvicorn.error")
DEFAULT_CONFIG_SCOPE = "seed"
TOURNAMENT_PORTFOLIO_SLOTS: tuple[PortfolioSlot, ...] = (
    PortfolioSlot(country_code="CA", division="mens_doubles"),
    PortfolioSlot(country_code="CA", division="womens_doubles"),
    PortfolioSlot(country_code="CA", division="mixed_doubles"),
    PortfolioSlot(country_code="US", division="mens_doubles"),
    PortfolioSlot(country_code="US", division="womens_doubles"),
    PortfolioSlot(country_code="US", division="mixed_doubles"),
)
TOURNAMENT_GROUP_COUNT = 6


@lru_cache(maxsize=1)
def get_templates() -> Jinja2Templates:
    """Return the Jinja template loader."""
    return Jinja2Templates(directory=str(TEMPLATES_DIR))


def get_control_panel_queries() -> ControlPanelQueries:
    """Return the control panel query service."""
    return ControlPanelQueries()


def get_configuration_lifecycle() -> ConfigurationLifecycleService:
    """Return the configuration lifecycle service."""
    return ConfigurationLifecycleService()


def get_generation_run_service() -> GenerationRunService:
    """Return the generation run service."""
    return GenerationRunService()


def get_seed_refresh_service() -> SeedRefreshService:
    """Return the seed refresh service."""
    return SeedRefreshService()


def get_student_dataset_export_service() -> StudentDatasetExportService:
    """Return the student dataset export service."""
    return StudentDatasetExportService()


def get_tournament_service() -> TournamentService:
    """Return the tournament workflow service."""
    return TournamentService()


def get_background_job_runner() -> BackgroundJobRunner:
    """Return the local background job runner."""
    return get_default_background_job_runner()


def build_control_panel_router() -> APIRouter:
    """Build the control panel router."""
    router = APIRouter()
    templates = get_templates()

    @router.get("/control", response_class=HTMLResponse)
    def control_panel_shell(
        request: Request,
        session: Session = Depends(get_session),
        queries: ControlPanelQueries = Depends(get_control_panel_queries),
    ) -> HTMLResponse:
        snapshot, editor = _config_context(session, queries=queries)
        return templates.TemplateResponse(
            request,
            "control_panel.html",
            _build_config_template_context(snapshot, editor),
        )

    @router.get("/control/partials/config", response_class=HTMLResponse)
    def control_panel_config_partial(
        request: Request,
        session: Session = Depends(get_session),
        queries: ControlPanelQueries = Depends(get_control_panel_queries),
    ) -> HTMLResponse:
        return _render_config_tab_response(
            request,
            session=session,
            queries=queries,
            templates=templates,
            active_config_scope=DEFAULT_CONFIG_SCOPE,
        )

    @router.get("/control/partials/config/seed", response_class=HTMLResponse)
    def control_panel_seed_config_partial(
        request: Request,
        session: Session = Depends(get_session),
        queries: ControlPanelQueries = Depends(get_control_panel_queries),
    ) -> HTMLResponse:
        return _render_config_tab_response(
            request,
            session=session,
            queries=queries,
            templates=templates,
            active_config_scope="seed",
        )

    @router.get("/control/partials/config/player-match", response_class=HTMLResponse)
    def control_panel_player_match_config_partial(
        request: Request,
        session: Session = Depends(get_session),
        queries: ControlPanelQueries = Depends(get_control_panel_queries),
    ) -> HTMLResponse:
        return _render_config_tab_response(
            request,
            session=session,
            queries=queries,
            templates=templates,
            active_config_scope="synthetic",
        )

    @router.get("/control/partials/config/export", response_class=HTMLResponse)
    def control_panel_export_config_partial(
        request: Request,
        session: Session = Depends(get_session),
        queries: ControlPanelQueries = Depends(get_control_panel_queries),
    ) -> HTMLResponse:
        snapshot = queries.get_control_panel_snapshot(session)
        return templates.TemplateResponse(
            request,
            "partials/control_export_config_tab.html",
            {
                "snapshot": snapshot,
                "export_config": _default_export_config(snapshot),
                "export_launch_message": None,
                "export_launch_error": None,
            },
        )

    @router.get("/control/partials/config/tournament", response_class=HTMLResponse)
    def control_panel_tournament_config_partial(
        request: Request,
        session: Session = Depends(get_session),
        queries: ControlPanelQueries = Depends(get_control_panel_queries),
    ) -> HTMLResponse:
        return _render_config_tab_response(
            request,
            session=session,
            queries=queries,
            templates=templates,
            active_config_scope="tournament",
        )

    @router.post("/control/config/validate", response_class=HTMLResponse)
    def control_panel_config_validate(
        request: Request,
        config_title: str = Form(""),
        config_notes: str = Form(""),
        active_config_scope: str | None = Form(None),
        config_payload_json: str | None = Form(None),
        seed_config_json: str | None = Form(None),
        synthetic_config_json: str | None = Form(None),
        session: Session = Depends(get_session),
        queries: ControlPanelQueries = Depends(get_control_panel_queries),
        lifecycle: ConfigurationLifecycleService = Depends(get_configuration_lifecycle),
    ) -> HTMLResponse:
        snapshot, editor = _config_context(
            session,
            queries=queries,
            lifecycle=lifecycle,
            title=config_title,
            notes=config_notes,
            working_payload_json=config_payload_json,
            seed_payload_json=seed_config_json,
            synthetic_payload_json=synthetic_config_json,
            action="validate",
        )
        return templates.TemplateResponse(
            request,
            "partials/control_config_tab.html",
            _build_config_template_context(
                snapshot,
                editor,
                active_config_scope=_normalize_config_scope(active_config_scope),
            ),
        )

    @router.post("/control/config/save", response_class=HTMLResponse)
    def control_panel_config_save(
        request: Request,
        config_title: str = Form(""),
        config_notes: str = Form(""),
        active_config_scope: str | None = Form(None),
        config_payload_json: str | None = Form(None),
        seed_config_json: str | None = Form(None),
        synthetic_config_json: str | None = Form(None),
        session: Session = Depends(get_session),
        queries: ControlPanelQueries = Depends(get_control_panel_queries),
        lifecycle: ConfigurationLifecycleService = Depends(get_configuration_lifecycle),
    ) -> HTMLResponse:
        snapshot, editor = _config_context(
            session,
            queries=queries,
            lifecycle=lifecycle,
            title=config_title,
            notes=config_notes,
            working_payload_json=config_payload_json,
            seed_payload_json=seed_config_json,
            synthetic_payload_json=synthetic_config_json,
            action="save",
        )
        return templates.TemplateResponse(
            request,
            "partials/control_config_tab.html",
            _build_config_template_context(
                snapshot,
                editor,
                active_config_scope=_normalize_config_scope(active_config_scope),
            ),
        )

    @router.get("/control/partials/orchestration", response_class=HTMLResponse)
    def control_panel_orchestration_partial(
        request: Request,
        session: Session = Depends(get_session),
        queries: ControlPanelQueries = Depends(get_control_panel_queries),
    ) -> HTMLResponse:
        snapshot = queries.get_control_panel_snapshot(session)
        return templates.TemplateResponse(
            request,
            "partials/control_orchestration_tab.html",
            _build_orchestration_template_context(snapshot),
        )

    @router.get("/control/partials/tournament", response_class=HTMLResponse)
    def control_panel_tournament_partial(
        request: Request,
        session: Session = Depends(get_session),
        queries: ControlPanelQueries = Depends(get_control_panel_queries),
    ) -> HTMLResponse:
        snapshot = queries.get_control_panel_snapshot(session)
        return templates.TemplateResponse(
            request,
            "partials/control_tournament_tab.html",
            _build_tournament_template_context(session, snapshot=snapshot),
        )

    @router.get("/control/partials/tournament/simulation", response_class=HTMLResponse)
    def control_panel_tournament_simulation_partial(
        request: Request,
        session: Session = Depends(get_session),
        queries: ControlPanelQueries = Depends(get_control_panel_queries),
    ) -> HTMLResponse:
        snapshot = queries.get_control_panel_snapshot(session)
        return templates.TemplateResponse(
            request,
            "partials/tournament_simulation_panels.html",
            _build_tournament_template_context(session, snapshot=snapshot),
        )

    @router.post(
        "/control/tournaments/submissions/validate-field",
        response_class=HTMLResponse,
    )
    def control_panel_tournament_submission_validate_field(
        request: Request,
        team_id: str = Form(""),
        tournament_date: str = Form(""),
        group_index: int = Form(...),
        country_code: str = Form(""),
        division: str = Form(""),
        session: Session = Depends(get_session),
        queries: ControlPanelQueries = Depends(get_control_panel_queries),
    ) -> HTMLResponse:
        slot = PortfolioSlot(
            country_code=country_code,
            division=division,
        )
        field_value = str(team_id).strip()
        issues: tuple[object, ...] = ()

        snapshot = queries.get_control_panel_snapshot(session)
        generation_run_id = (
            snapshot.generation_run_summary.generation_run_id
            if snapshot.generation_run_summary is not None
            else None
        )
        source_batch = (
            latest_completed_source_batch(session, generation_run_id=generation_run_id)
            if generation_run_id is not None
            else None
        )

        if field_value:
            try:
                parsed_team_id = int(field_value)
            except ValueError:
                issues = (
                    SimpleNamespace(message="Team ID must be a whole number."),
                )
            else:
                try:
                    parsed_date = _parse_iso_date(tournament_date)
                except ValueError:
                    parsed_date = None
                if parsed_date is not None and source_batch is not None and generation_run_id is not None:
                    issues = validate_tournament_submission(
                        session,
                        submission=TeamSubmission(
                            group_id=group_index,
                            slot=slot,
                            team_id=parsed_team_id,
                        ),
                        tournament_date=parsed_date,
                        source_batch_id=source_batch.id,
                        generation_run_id=generation_run_id,
                    )

        return templates.TemplateResponse(
            request,
            "partials/tournament_team_input_field.html",
            _tournament_team_field_context(
                group_index=group_index,
                slot=slot,
                field_value=field_value,
                field_issues=issues,
            ),
        )

    @router.post("/control/tournaments/submissions/save", response_class=HTMLResponse)
    def control_panel_tournament_submissions_save(
        request: Request,
        event_name: str = Form(""),
        tournament_date: str = Form(""),
        tournament_payload_json: str = Form("{}"),
        session: Session = Depends(get_session),
        queries: ControlPanelQueries = Depends(get_control_panel_queries),
        tournament_service: TournamentService = Depends(get_tournament_service),
    ) -> HTMLResponse:
        snapshot = queries.get_control_panel_snapshot(session)
        context = _build_tournament_template_context(
            session,
            snapshot=snapshot,
            form_state=_tournament_form_state_from_json(
                tournament_payload_json,
                event_name=event_name,
                tournament_date=tournament_date,
            ),
        )
        source_batch = context["tournament_source_batch"]
        if source_batch is None or snapshot.generation_run_summary is None:
            context["tournament_save_error"] = (
                "A completed generation run is required before saving tournament submissions."
            )
            return templates.TemplateResponse(
                request,
                "partials/control_tournament_tab.html",
                context,
            )

        try:
            parsed_date = _parse_iso_date(tournament_date)
            student_groups, submissions = _tournament_form_payload_objects(
                context["tournament_form_state"],
            )
            validation = load_validated_tournament_input(
                session,
                submissions=submissions,
                tournament_date=parsed_date,
                source_batch_id=source_batch.id,
                generation_run_id=snapshot.generation_run_summary.generation_run_id,
            )
            if not validation.is_valid:
                context["tournament_validation_issues"] = validation.issues
                context["tournament_issue_map"] = _tournament_issue_map(validation.issues)
                context["tournament_save_error"] = (
                    "Fix the highlighted team submissions before saving this tournament event."
                )
                return templates.TemplateResponse(
                    request,
                    "partials/control_tournament_tab.html",
                    context,
                )

            creation = tournament_service.create_event(
                event_name=event_name.strip() or "Class Tournament",
                source_batch_id=source_batch.id,
                tournament_date=parsed_date,
                student_groups=student_groups,
                submissions=submissions,
                generation_run_id=snapshot.generation_run_summary.generation_run_id,
                session=session,
            )
            tournament_service.validate_event(
                event_id=creation.event.id,
                session=session,
            )
            session.commit()
            refreshed_snapshot = queries.get_control_panel_snapshot(session)
            refreshed_context = _build_tournament_template_context(
                session,
                snapshot=refreshed_snapshot,
                form_state=context["tournament_form_state"],
            )
            refreshed_context["tournament_save_message"] = (
                f"Tournament event {creation.event.id} saved and validated."
            )
            refreshed_context["saved_tournament_event_id"] = creation.event.id
            return templates.TemplateResponse(
                request,
                "partials/control_tournament_tab.html",
                refreshed_context,
            )
        except Exception as exc:
            session.rollback()
            context["tournament_save_error"] = str(exc)
            return templates.TemplateResponse(
                request,
                "partials/control_tournament_tab.html",
                context,
            )

    @router.post("/control/tournaments/monte-carlo/start", response_class=HTMLResponse)
    def control_panel_tournament_monte_carlo_start_partial(
        request: Request,
        event_id: int = Form(...),
        iterations: int = Form(1000),
        seed: int = Form(1),
        session: Session = Depends(get_session),
        queries: ControlPanelQueries = Depends(get_control_panel_queries),
        tournament_service: TournamentService = Depends(get_tournament_service),
        background_runner: BackgroundJobRunner = Depends(get_background_job_runner),
    ) -> HTMLResponse:
        snapshot = queries.get_control_panel_snapshot(session)
        context = _build_tournament_template_context(session, snapshot=snapshot)
        context["tournament_monte_carlo_state"] = {
            "event_id": event_id,
            "iterations": iterations,
            "seed": seed,
        }
        try:
            start = tournament_service.register_monte_carlo_run(
                event_id=event_id,
                iterations=iterations,
                seed=seed,
                session=session,
            )
            session.commit()
            background_runner.submit(
                tournament_service.execute_run_in_background,
                simulation_run_id=start.simulation_run.id,
            )
            refreshed_snapshot = queries.get_control_panel_snapshot(session)
            refreshed_context = _build_tournament_template_context(
                session,
                snapshot=refreshed_snapshot,
            )
            refreshed_context["tournament_monte_carlo_state"] = {
                "event_id": event_id,
                "iterations": iterations,
                "seed": seed,
            }
            refreshed_context["tournament_monte_carlo_message"] = (
                f"Monte Carlo run {start.simulation_run.id} queued."
            )
            return templates.TemplateResponse(
                request,
                "partials/tournament_simulation_panels.html",
                refreshed_context,
            )
        except Exception as exc:
            session.rollback()
            context["tournament_monte_carlo_error"] = str(exc)
            return templates.TemplateResponse(
                request,
                "partials/tournament_simulation_panels.html",
                context,
            )

    @router.post("/control/seed/load", response_class=HTMLResponse)
    def control_panel_seed_load_start(
        request: Request,
        destructive_confirm: str | None = Form(None),
        session: Session = Depends(get_session),
        queries: ControlPanelQueries = Depends(get_control_panel_queries),
        seed_service: SeedRefreshService = Depends(get_seed_refresh_service),
        background_runner: BackgroundJobRunner = Depends(get_background_job_runner),
    ) -> HTMLResponse:
        return _run_seed_action(
            request,
            session=session,
            queries=queries,
            seed_service=seed_service,
            background_runner=background_runner,
            action="load",
            destructive_confirm=destructive_confirm,
            templates=templates,
        )

    @router.post("/control/seed/normalize", response_class=HTMLResponse)
    def control_panel_seed_normalize_start(
        request: Request,
        destructive_confirm: str | None = Form(None),
        session: Session = Depends(get_session),
        queries: ControlPanelQueries = Depends(get_control_panel_queries),
        seed_service: SeedRefreshService = Depends(get_seed_refresh_service),
        background_runner: BackgroundJobRunner = Depends(get_background_job_runner),
    ) -> HTMLResponse:
        return _run_seed_action(
            request,
            session=session,
            queries=queries,
            seed_service=seed_service,
            background_runner=background_runner,
            action="normalize",
            destructive_confirm=destructive_confirm,
            templates=templates,
        )

    @router.post("/control/seed/refresh", response_class=HTMLResponse)
    def control_panel_seed_refresh_start(
        request: Request,
        destructive_confirm: str | None = Form(None),
        session: Session = Depends(get_session),
        queries: ControlPanelQueries = Depends(get_control_panel_queries),
        seed_service: SeedRefreshService = Depends(get_seed_refresh_service),
        background_runner: BackgroundJobRunner = Depends(get_background_job_runner),
    ) -> HTMLResponse:
        return _run_seed_action(
            request,
            session=session,
            queries=queries,
            seed_service=seed_service,
            background_runner=background_runner,
            action="refresh",
            destructive_confirm=destructive_confirm,
            templates=templates,
        )

    @router.post("/control/generation/start", response_class=HTMLResponse)
    def control_panel_generation_start(
        request: Request,
        generation_name: str = Form(""),
        destructive_confirm: str | None = Form(None),
        session: Session = Depends(get_session),
        queries: ControlPanelQueries = Depends(get_control_panel_queries),
        run_service: GenerationRunService = Depends(get_generation_run_service),
        background_runner: BackgroundJobRunner = Depends(get_background_job_runner),
    ) -> HTMLResponse:
        snapshot = queries.get_control_panel_snapshot(session)
        launch_message = None
        launch_error = None

        if destructive_confirm != "yes":
            launch_error = "Destructive reset confirmation is required before starting a generation run."
        elif not snapshot.allowed_actions.can_start_generation_run:
            launch_error = (
                snapshot.allowed_actions.start_generation_blockers[0]
                if snapshot.allowed_actions.start_generation_blockers
                else "Generation run cannot be started."
            )
        else:
            requested_name = generation_name.strip() or _default_generation_name(snapshot)
            try:
                registration = run_service.register_generation_run(
                    requested_name,
                    session=session,
                )
                session.commit()
                logger.warning(
                    "Queueing generation background job generation_run_id=%s job_status_id=%s",
                    registration.generation_run.id,
                    registration.job_status.id,
                )
                background_runner.submit(
                    run_service.execute_registered_generation_run_in_background,
                    config_version_id=registration.configuration_version.id,
                    generation_run_id=registration.generation_run.id,
                    job_status_id=registration.job_status.id,
                )
                snapshot = queries.get_control_panel_snapshot(session)
                launch_message = (
                    f"Generation run '{requested_name}' started in background."
                )
            except Exception as exc:
                session.rollback()
                snapshot = queries.get_control_panel_snapshot(session)
                launch_error = str(exc)

        return templates.TemplateResponse(
            request,
            "partials/control_orchestration_tab.html",
            _build_orchestration_template_context(
                snapshot,
                launch_message=launch_message,
                launch_error=launch_error,
            ),
        )

    @router.post("/control/export/student-dataset/start", response_class=HTMLResponse)
    def control_panel_student_dataset_export_start(
        request: Request,
        generation_run_id: int = Form(...),
        initial_history_month_count: int = Form(...),
        subsequent_month_count: int = Form(...),
        output_root: str = Form(...),
        release_name: str = Form(...),
        data_quality_level: str = Form("clean"),
        overwrite_existing: str | None = Form(None),
        return_target: str = Form("export_config"),
        session: Session = Depends(get_session),
        queries: ControlPanelQueries = Depends(get_control_panel_queries),
        export_service: StudentDatasetExportService = Depends(get_student_dataset_export_service),
        background_runner: BackgroundJobRunner = Depends(get_background_job_runner),
    ) -> HTMLResponse:
        snapshot = queries.get_control_panel_snapshot(session)
        export_launch_message = None
        export_launch_error = None
        export_config = {
            "generation_run_id": generation_run_id,
            "initial_history_month_count": initial_history_month_count,
            "subsequent_month_count": subsequent_month_count,
            "output_root": output_root,
            "release_name": release_name,
            "data_quality_level": data_quality_level,
            "overwrite_existing": overwrite_existing == "yes",
        }

        if not snapshot.allowed_actions.can_generate_student_dataset:
            export_launch_error = (
                snapshot.allowed_actions.student_dataset_blockers[0]
                if snapshot.allowed_actions.student_dataset_blockers
                else "Student dataset export cannot be started."
            )
        else:
            try:
                registration = export_service.register_export_job(
                    session=session,
                    generation_run_id=generation_run_id,
                    initial_history_month_count=initial_history_month_count,
                    subsequent_month_count=subsequent_month_count,
                    output_root=Path(output_root),
                    release_name=release_name.strip(),
                    data_quality_level=data_quality_level.strip() or "clean",
                    overwrite_existing=overwrite_existing == "yes",
                )
                session.commit()
                background_runner.submit(
                    export_service.execute_registered_export_in_background,
                    job_status_id=registration.job_status.id,
                    generation_run_id=generation_run_id,
                    initial_history_month_count=initial_history_month_count,
                    subsequent_month_count=subsequent_month_count,
                    output_root=output_root,
                    release_name=release_name.strip(),
                    data_quality_level=data_quality_level.strip() or "clean",
                    overwrite_existing=overwrite_existing == "yes",
                )
                snapshot = queries.get_control_panel_snapshot(session)
                export_launch_message = (
                    f"Student dataset export '{release_name.strip()}' started in background."
                )
            except Exception as exc:
                session.rollback()
                snapshot = queries.get_control_panel_snapshot(session)
                export_launch_error = str(exc)

        if return_target == "orchestration":
            return templates.TemplateResponse(
                request,
                "partials/control_orchestration_tab.html",
                _build_orchestration_template_context(
                    snapshot,
                    export_launch_message=export_launch_message,
                    export_launch_error=export_launch_error,
                    export_config=export_config,
                ),
            )
        return templates.TemplateResponse(
            request,
            "partials/control_export_config_tab.html",
            {
                "snapshot": snapshot,
                "export_config": export_config,
                "export_launch_message": export_launch_message,
                "export_launch_error": export_launch_error,
            },
            )

    @router.post("/control/tournaments/events", response_class=JSONResponse)
    def control_panel_tournament_event_create(
        payload: dict[str, Any] = Body(...),
        session: Session = Depends(get_session),
        tournament_service: TournamentService = Depends(get_tournament_service),
    ) -> JSONResponse:
        try:
            creation = tournament_service.create_event(
                event_name=str(payload.get("event_name") or "Tournament Event"),
                source_batch_id=int(payload["source_batch_id"]),
                tournament_date=_parse_iso_date(str(payload["tournament_date"])),
                student_groups=_student_groups_from_payload(payload),
                submissions=_team_submissions_from_payload(payload),
                generation_run_id=(
                    int(payload["generation_run_id"])
                    if payload.get("generation_run_id") is not None
                    else None
                ),
                config_snapshot=payload.get("config_snapshot"),
                session=session,
            )
            session.commit()
            return JSONResponse(
                {
                    "ok": True,
                    "event_id": creation.event.id,
                    "student_group_count": len(creation.student_groups),
                    "submission_count": len(creation.submissions),
                }
            )
        except Exception as exc:
            session.rollback()
            return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)

    @router.post("/control/tournaments/{event_id}/validate", response_class=JSONResponse)
    def control_panel_tournament_validate(
        event_id: int,
        session: Session = Depends(get_session),
        tournament_service: TournamentService = Depends(get_tournament_service),
    ) -> JSONResponse:
        try:
            result = tournament_service.validate_event(
                event_id=event_id,
                session=session,
            )
            session.commit()
            return JSONResponse(
                {
                    "ok": result.is_valid,
                    "source_batch_id": result.source_batch_id,
                    "division_count": len(result.divisions),
                    "issues": [_validation_issue_payload(issue) for issue in result.issues],
                },
                status_code=200 if result.is_valid else 422,
            )
        except Exception as exc:
            session.rollback()
            return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)

    @router.post("/control/tournaments/{event_id}/monte-carlo/start", response_class=JSONResponse)
    def control_panel_tournament_monte_carlo_start(
        event_id: int,
        payload: dict[str, Any] = Body(default={}),
        session: Session = Depends(get_session),
        tournament_service: TournamentService = Depends(get_tournament_service),
        background_runner: BackgroundJobRunner = Depends(get_background_job_runner),
    ) -> JSONResponse:
        try:
            seed = int(payload.get("seed", 1))
            iterations = int(payload.get("iterations", 1000))
            if bool(payload.get("background", False)):
                start = tournament_service.register_monte_carlo_run(
                    event_id=event_id,
                    iterations=iterations,
                    seed=seed,
                    session=session,
                )
                session.commit()
                background_runner.submit(
                    tournament_service.execute_run_in_background,
                    simulation_run_id=start.simulation_run.id,
                )
            else:
                start = tournament_service.run_monte_carlo(
                    event_id=event_id,
                    iterations=iterations,
                    seed=seed,
                    session=session,
                )
                session.commit()
            return JSONResponse(
                {
                    "ok": True,
                    "simulation_run_id": start.simulation_run.id,
                    "job_status_id": start.job_status.id,
                    "status": start.simulation_run.status,
                }
            )
        except Exception as exc:
            session.rollback()
            return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)

    @router.post("/control/tournaments/{event_id}/official/start", response_class=JSONResponse)
    def control_panel_tournament_official_start(
        event_id: int,
        payload: dict[str, Any] = Body(default={}),
        session: Session = Depends(get_session),
        tournament_service: TournamentService = Depends(get_tournament_service),
        background_runner: BackgroundJobRunner = Depends(get_background_job_runner),
    ) -> JSONResponse:
        try:
            seed = int(payload.get("seed", 1))
            if bool(payload.get("background", False)):
                start = tournament_service.register_official_run(
                    event_id=event_id,
                    seed=seed,
                    session=session,
                )
                session.commit()
                background_runner.submit(
                    tournament_service.execute_run_in_background,
                    simulation_run_id=start.simulation_run.id,
                )
            else:
                start = tournament_service.run_official(
                    event_id=event_id,
                    seed=seed,
                    session=session,
                )
                session.commit()
            return JSONResponse(
                {
                    "ok": True,
                    "simulation_run_id": start.simulation_run.id,
                    "job_status_id": start.job_status.id,
                    "status": start.simulation_run.status,
                }
            )
        except Exception as exc:
            session.rollback()
            return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)

    @router.get("/control/tournaments/{event_id}/summary", response_class=JSONResponse)
    def control_panel_tournament_summary(
        event_id: int,
        session: Session = Depends(get_session),
        tournament_service: TournamentService = Depends(get_tournament_service),
    ) -> JSONResponse:
        summary = tournament_service.latest_summary(event_id=event_id, session=session)
        if summary is None:
            return JSONResponse({"ok": False, "error": "No tournament results found."}, status_code=404)
        return JSONResponse({"ok": True, "summary": summary})

    @router.get("/control/tournaments/official-matches/{official_match_id}", response_class=JSONResponse)
    def control_panel_tournament_official_match_detail(
        official_match_id: int,
        session: Session = Depends(get_session),
        tournament_service: TournamentService = Depends(get_tournament_service),
    ) -> JSONResponse:
        detail = tournament_service.official_match_detail(
            official_match_id=official_match_id,
            session=session,
        )
        if detail is None:
            return JSONResponse({"ok": False, "error": "Official match not found."}, status_code=404)
        return JSONResponse({"ok": True, "match": detail})

    @router.post("/control/system/copy-path", response_class=JSONResponse)
    def control_panel_copy_path(path: str = Form(...)) -> JSONResponse:
        try:
            _copy_to_windows_clipboard(path)
        except Exception as exc:
            return JSONResponse(
                {"ok": False, "error": str(exc)},
                status_code=500,
            )
        return JSONResponse({"ok": True})

    @router.post("/control/system/open-folder", response_class=JSONResponse)
    def control_panel_open_folder(path: str = Form(...)) -> JSONResponse:
        try:
            resolved_path = _resolve_control_panel_path(path)
            _open_folder_in_host(resolved_path)
        except Exception as exc:
            return JSONResponse(
                {"ok": False, "error": str(exc)},
                status_code=500,
            )
        return JSONResponse(
            {
                "ok": True,
                "message": f"Opened folder: {resolved_path}",
            }
        )

    @router.post("/control/export/student-dataset/run-qc", response_class=JSONResponse)
    def control_panel_run_student_dataset_qc(path: str = Form(...)) -> JSONResponse:
        try:
            resolved_path = _resolve_control_panel_path(path)
            result = _run_student_dataset_qc(resolved_path)
        except Exception as exc:
            return JSONResponse(
                {"ok": False, "error": str(exc)},
                status_code=500,
            )
        status_code = 200 if result["ok"] else 422
        return JSONResponse(result, status_code=status_code)

    @router.post("/control/export/student-dataset/download-package", response_class=FileResponse)
    def control_panel_download_student_dataset_package(path: str = Form(...)) -> FileResponse:
        resolved_path = _resolve_control_panel_path(path)
        archive_path = _build_student_dataset_release_package(resolved_path)
        return FileResponse(
            archive_path,
            media_type="application/zip",
            filename=f"{resolved_path.name}.zip",
            background=BackgroundTask(_cleanup_temp_file, archive_path),
        )

    @router.post("/control/jobs/clear-stalled", response_class=HTMLResponse)
    def control_panel_clear_stalled_job(
        request: Request,
        job_status_id: int = Form(...),
        session: Session = Depends(get_session),
        queries: ControlPanelQueries = Depends(get_control_panel_queries),
    ) -> HTMLResponse:
        status_recovery_message = None
        status_recovery_error = None
        try:
            cleared = clear_stalled_job(session, job_status_id=job_status_id)
            session.commit()
            status_recovery_message = (
                f"Cleared stalled {cleared.job_type} job {cleared.job_id}."
            )
        except Exception as exc:
            session.rollback()
            status_recovery_error = str(exc)
        snapshot = queries.get_control_panel_snapshot(session)
        return templates.TemplateResponse(
            request,
            "partials/control_orchestration_tab.html",
            _build_orchestration_template_context(
                snapshot,
                status_recovery_message=status_recovery_message,
                status_recovery_error=status_recovery_error,
            ),
        )

    @router.post("/control/jobs/dismiss-failed", response_class=HTMLResponse)
    def control_panel_dismiss_failed_job(
        request: Request,
        job_status_id: int = Form(...),
        session: Session = Depends(get_session),
        queries: ControlPanelQueries = Depends(get_control_panel_queries),
    ) -> HTMLResponse:
        status_recovery_message = None
        status_recovery_error = None
        try:
            dismissed = dismiss_failed_job(session, job_status_id=job_status_id)
            session.commit()
            status_recovery_message = (
                f"Dismissed failed {dismissed.job_type} job {dismissed.job_id}."
            )
        except Exception as exc:
            session.rollback()
            status_recovery_error = str(exc)
        snapshot = queries.get_control_panel_snapshot(session)
        return templates.TemplateResponse(
            request,
            "partials/control_orchestration_tab.html",
            _build_orchestration_template_context(
                snapshot,
                status_recovery_message=status_recovery_message,
                status_recovery_error=status_recovery_error,
            ),
        )

    @router.get("/control/partials/run-status", response_class=HTMLResponse)
    def control_panel_run_status_partial(
        request: Request,
        session: Session = Depends(get_session),
        queries: ControlPanelQueries = Depends(get_control_panel_queries),
    ) -> HTMLResponse:
        snapshot = queries.get_control_panel_snapshot(session)
        return templates.TemplateResponse(
            request,
            "partials/control_run_status.html",
            {
                "snapshot": snapshot,
            },
        )

    @router.get("/control/partials/batch-table", response_class=HTMLResponse)
    def control_panel_batch_table_partial(
        request: Request,
        session: Session = Depends(get_session),
        queries: ControlPanelQueries = Depends(get_control_panel_queries),
    ) -> HTMLResponse:
        snapshot = queries.get_control_panel_snapshot(session)
        return templates.TemplateResponse(
            request,
            "partials/control_batch_table.html",
            {
                "snapshot": snapshot,
            },
        )

    @router.get("/control/partials/overall-progress", response_class=HTMLResponse)
    def control_panel_overall_progress_partial(
        request: Request,
        session: Session = Depends(get_session),
        queries: ControlPanelQueries = Depends(get_control_panel_queries),
    ) -> HTMLResponse:
        snapshot = queries.get_control_panel_snapshot(session)
        return templates.TemplateResponse(
            request,
            "partials/control_overall_progress.html",
            {
                "snapshot": snapshot,
            },
        )

    @router.get("/control/partials/progress-bars", response_class=HTMLResponse)
    def control_panel_progress_bars_partial(
        request: Request,
        session: Session = Depends(get_session),
        queries: ControlPanelQueries = Depends(get_control_panel_queries),
    ) -> HTMLResponse:
        snapshot = queries.get_control_panel_snapshot(session)
        return templates.TemplateResponse(
            request,
            "partials/control_progress_bars.html",
            {
                "snapshot": snapshot,
            },
        )

    return router


def _default_export_config(snapshot: ControlPanelSnapshot) -> dict[str, object]:
    run = snapshot.generation_run_summary
    config = snapshot.config_summary
    generation_run_id = run.generation_run_id if run else ""
    batch_count = run.succeeded_batch_count if run else 0
    initial_history_month_count = (
        config.historical_batch_count
        if config and config.historical_batch_count
        else batch_count
    )
    if batch_count and initial_history_month_count > batch_count:
        initial_history_month_count = batch_count
    subsequent_month_count = max(batch_count - (initial_history_month_count or 0), 0)
    release_base = "student_dataset_release"
    if run and run.generation_name:
        release_base = _safe_release_name(run.generation_name)
    return {
        "generation_run_id": generation_run_id,
        "initial_history_month_count": initial_history_month_count or "",
        "subsequent_month_count": subsequent_month_count,
        "output_root": "data/student_dataset_exports",
        "release_name": release_base,
        "data_quality_level": "clean",
        "overwrite_existing": False,
    }


def _build_orchestration_template_context(
    snapshot: ControlPanelSnapshot,
    *,
    seed_launch_message: str | None = None,
    seed_launch_error: str | None = None,
    launch_message: str | None = None,
    launch_error: str | None = None,
    status_recovery_message: str | None = None,
    status_recovery_error: str | None = None,
    export_launch_message: str | None = None,
    export_launch_error: str | None = None,
    export_config: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "snapshot": snapshot,
        "seed_launch_message": seed_launch_message,
        "seed_launch_error": seed_launch_error,
        "launch_message": launch_message,
        "launch_error": launch_error,
        "status_recovery_message": status_recovery_message,
        "status_recovery_error": status_recovery_error,
        "export_launch_message": export_launch_message,
        "export_launch_error": export_launch_error,
        "export_config": export_config or _default_export_config(snapshot),
    }


def _safe_release_name(value: str) -> str:
    cleaned = "".join(
        character.lower() if character.isalnum() else "_"
        for character in value.strip()
    )
    parts = [part for part in cleaned.split("_") if part]
    return "_".join(parts) or "student_dataset_release"


def _copy_to_windows_clipboard(value: str) -> None:
    clip_exe = shutil.which("clip.exe")
    if clip_exe is None:
        raise RuntimeError("clip.exe is not available in this environment.")
    subprocess.run(
        [clip_exe],
        input=value,
        text=True,
        check=True,
    )


def _resolve_control_panel_path(value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


def _open_folder_in_host(path: Path) -> None:
    if not path.is_dir():
        raise RuntimeError(f"Folder does not exist: {path}")
    wslpath_exe = shutil.which("wslpath")
    explorer_exe = shutil.which("explorer.exe")
    if wslpath_exe is None or explorer_exe is None:
        raise RuntimeError("wslpath or explorer.exe is not available in this environment.")
    windows_path = subprocess.run(
        [wslpath_exe, "-w", str(path)],
        text=True,
        capture_output=True,
        check=True,
    ).stdout.strip()
    if not windows_path:
        raise RuntimeError(f"Could not resolve Windows path for {path}")
    subprocess.run(
        [explorer_exe, windows_path],
        check=True,
    )


def _run_student_dataset_qc(path: Path) -> dict[str, Any]:
    if not path.is_dir():
        raise RuntimeError(f"Release folder does not exist: {path}")
    manifest_path = path / "manifest.json"
    if not manifest_path.is_file():
        raise RuntimeError(f"manifest.json not found in release folder: {path}")

    import duckdb

    sql_script = (
        PROJECT_ROOT / "scripts" / "student_dataset_duckdb_quality_check.sql"
    ).read_text(encoding="utf-8")
    connection = duckdb.connect()
    escaped_path = str(path).replace("'", "''")
    connection.execute(f"SET VARIABLE release_dir = '{escaped_path}'")
    statements = [statement.strip() for statement in sql_script.split(";") if statement.strip()]
    execution_error: Exception | None = None
    try:
        for statement in statements:
            connection.execute(statement)
    except Exception as exc:
        execution_error = exc

    summary_rows = connection.execute(
        """
        SELECT status, COUNT(*) AS check_count
        FROM qc_results
        GROUP BY status
        ORDER BY status
        """
    ).fetchall()
    failed_rows = connection.execute(
        """
        SELECT check_name, details
        FROM qc_results
        WHERE status = 'failed'
        ORDER BY category, check_name
        LIMIT 5
        """
    ).fetchall()
    total_checks = sum(int(row[1]) for row in summary_rows)
    failed_checks = next((int(row[1]) for row in summary_rows if row[0] == "failed"), 0)
    if execution_error is None and failed_checks == 0:
        return {
            "ok": True,
            "message": (
                f"QC passed for {path.name}. "
                f"Executed {total_checks} checks with 0 failures."
            ),
            "check_count": total_checks,
            "failed_check_count": 0,
        }

    failed_details = [
        {"check_name": str(row[0]), "details": str(row[1])}
        for row in failed_rows
    ]
    error_message = str(execution_error) if execution_error is not None else "QC failed."
    return {
        "ok": False,
        "error": error_message,
        "message": (
            f"QC failed for {path.name}. "
            f"{failed_checks} of {total_checks} checks failed."
        ),
        "check_count": total_checks,
        "failed_check_count": failed_checks,
        "failed_checks": failed_details,
    }


def _build_student_dataset_release_package(path: Path) -> Path:
    if not path.is_dir():
        raise RuntimeError(f"Release folder does not exist: {path}")
    manifest_path = path / "manifest.json"
    if not manifest_path.is_file():
        raise RuntimeError(f"manifest.json not found in release folder: {path}")
    parquet_files = sorted(path.glob("*.parquet"))
    if not parquet_files:
        raise RuntimeError(f"No Parquet files found in release folder: {path}")

    with tempfile.NamedTemporaryFile(
        prefix=f"{path.name}_",
        suffix=".zip",
        delete=False,
    ) as handle:
        archive_path = Path(handle.name)

    with zipfile.ZipFile(archive_path, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.write(manifest_path, arcname=f"{path.name}/manifest.json")
        for parquet_path in parquet_files:
            archive.write(
                parquet_path,
                arcname=f"{path.name}/{parquet_path.name}",
            )
    return archive_path


def _cleanup_temp_file(path: Path | str) -> None:
    try:
        Path(path).unlink(missing_ok=True)
    except OSError:
        pass


def _config_context(
    session: Session,
    *,
    queries: ControlPanelQueries,
    lifecycle: ConfigurationLifecycleService | None = None,
    title: str | None = None,
    notes: str | None = None,
    working_payload_json: str | None = None,
    seed_payload_json: str | None = None,
    synthetic_payload_json: str | None = None,
    action: str | None = None,
) -> tuple[ControlPanelSnapshot, ConfigEditorState]:
    snapshot = queries.get_control_panel_snapshot(session)
    default_editor = queries.get_config_editor_state(session)
    lifecycle = lifecycle or ConfigurationLifecycleService()
    working_payload_json = working_payload_json if isinstance(working_payload_json, str) else None
    seed_payload_json = seed_payload_json if isinstance(seed_payload_json, str) else None
    synthetic_payload_json = (
        synthetic_payload_json if isinstance(synthetic_payload_json, str) else None
    )

    if action is None:
        return snapshot, default_editor

    editor_title = (title or "").strip()
    editor_notes = notes or ""
    payload: dict[str, object] = {}

    if working_payload_json is not None:
        editor_working_payload_json = working_payload_json or "{}"
        payload, json_errors = _parse_payload_json(
            editor_working_payload_json,
            label="Configuration payload",
        )
        editor_seed_payload_json, editor_synthetic_payload_json = _split_editor_payloads(payload)
    else:
        editor_seed_payload_json = seed_payload_json or "{}"
        editor_synthetic_payload_json = synthetic_payload_json or "{}"
        seed_payload, seed_errors = _parse_payload_json(
            editor_seed_payload_json,
            label="Seed configuration",
        )
        synthetic_payload, synthetic_errors = _parse_payload_json(
            editor_synthetic_payload_json,
            label="Player and match configuration",
        )
        payload, merge_errors = merge_payload_sections(seed_payload, synthetic_payload)
        json_errors = seed_errors + synthetic_errors + merge_errors
        editor_working_payload_json = json.dumps(payload, indent=2, sort_keys=True)

    if json_errors:
        return snapshot, ConfigEditorState(
            title=editor_title,
            notes=editor_notes,
            working_payload_json=editor_working_payload_json,
            seed_payload_json=editor_seed_payload_json,
            synthetic_payload_json=editor_synthetic_payload_json,
            validation_passed=False,
            validation_issues=(),
            validation_errors=json_errors,
            validation_hash=None,
            status_message=None,
            change_count=None,
        )

    validation = lifecycle.validate_working_copy(payload)
    change_count = _change_count(session, lifecycle=lifecycle, payload=payload)
    if action == "validate":
        seed_editor_json, synthetic_editor_json = _split_editor_payloads(validation.normalized_payload)
        return snapshot, ConfigEditorState(
            title=editor_title,
            notes=editor_notes,
            working_payload_json=json.dumps(validation.normalized_payload, indent=2, sort_keys=True),
            seed_payload_json=seed_editor_json,
            synthetic_payload_json=synthetic_editor_json,
            validation_passed=validation.is_valid,
            validation_issues=validation.issues,
            validation_errors=validation.errors,
            validation_hash=validation.config_hash,
            status_message=(
                "Configuration is valid and ready to save."
                if validation.is_valid
                else None
            ),
            change_count=change_count,
        )

    if not snapshot.allowed_actions.can_edit_config:
        seed_editor_json, synthetic_editor_json = _split_editor_payloads(validation.normalized_payload)
        return snapshot, ConfigEditorState(
            title=editor_title,
            notes=editor_notes,
            working_payload_json=json.dumps(validation.normalized_payload, indent=2, sort_keys=True),
            seed_payload_json=seed_editor_json,
            synthetic_payload_json=synthetic_editor_json,
            validation_passed=False,
            validation_issues=(),
            validation_errors=("Configuration editing is blocked while a generation run is active.",),
            validation_hash=validation.config_hash,
            status_message=None,
            change_count=change_count,
        )

    if not validation.is_valid:
        seed_editor_json, synthetic_editor_json = _split_editor_payloads(validation.normalized_payload)
        return snapshot, ConfigEditorState(
            title=editor_title,
            notes=editor_notes,
            working_payload_json=json.dumps(validation.normalized_payload, indent=2, sort_keys=True),
            seed_payload_json=seed_editor_json,
            synthetic_payload_json=synthetic_editor_json,
            validation_passed=False,
            validation_issues=validation.issues,
            validation_errors=validation.errors,
            validation_hash=validation.config_hash,
            status_message=None,
            change_count=change_count,
        )

    if not editor_title:
        seed_editor_json, synthetic_editor_json = _split_editor_payloads(validation.normalized_payload)
        return snapshot, ConfigEditorState(
            title=editor_title,
            notes=editor_notes,
            working_payload_json=json.dumps(validation.normalized_payload, indent=2, sort_keys=True),
            seed_payload_json=seed_editor_json,
            synthetic_payload_json=synthetic_editor_json,
            validation_passed=True,
            validation_issues=(),
            validation_errors=("Configuration version title is required.",),
            validation_hash=validation.config_hash,
            status_message=None,
            change_count=change_count,
        )

    lifecycle.save_new_version(
        session,
        title=editor_title,
        notes=editor_notes or None,
        payload=validation.normalized_payload,
    )
    session.commit()
    refreshed_snapshot = queries.get_control_panel_snapshot(session)
    refreshed_editor = queries.get_config_editor_state(session)
    refreshed_editor = ConfigEditorState(
        title=refreshed_editor.title,
        notes=refreshed_editor.notes,
        working_payload_json=refreshed_editor.working_payload_json,
        seed_payload_json=refreshed_editor.seed_payload_json,
        synthetic_payload_json=refreshed_editor.synthetic_payload_json,
        validation_passed=False,
        validation_issues=(),
        validation_errors=(),
        validation_hash=refreshed_snapshot.config_summary.config_hash if refreshed_snapshot.config_summary else None,
        status_message="Configuration validated and saved as the current valid version.",
        change_count=0,
    )
    return refreshed_snapshot, refreshed_editor


def _run_seed_action(
    request: Request,
    *,
    session: Session,
    queries: ControlPanelQueries,
    seed_service: SeedRefreshService,
    background_runner: BackgroundJobRunner,
    action: str,
    destructive_confirm: str | None,
    templates: Jinja2Templates,
) -> HTMLResponse:
    snapshot = queries.get_control_panel_snapshot(session)
    seed_launch_message = None
    seed_launch_error = None

    if destructive_confirm != "yes":
        seed_launch_error = (
            "Destructive reset confirmation is required before starting a seed data load."
        )
    elif not snapshot.allowed_actions.can_start_seed_refresh:
        seed_launch_error = (
            snapshot.allowed_actions.seed_refresh_blockers[0]
            if snapshot.allowed_actions.seed_refresh_blockers
            else "Seed preparation cannot be started."
        )
    else:
        try:
            if action == "load":
                registration = seed_service.register_raw_seed_ingest(session=session)
                session.commit()
                logger.warning(
                    "Queueing seed background job mode=%s job_status_id=%s",
                    registration.mode,
                    registration.job_status.id,
                )
                background_runner.submit(
                    seed_service.execute_registered_seed_job_in_background,
                    config_version_id=registration.configuration_version.id,
                    job_status_id=registration.job_status.id,
                    mode=registration.mode,
                )
                seed_launch_message = "Raw seed ingest started in background."
            elif action == "normalize":
                registration = seed_service.register_seed_normalization(session=session)
                session.commit()
                logger.warning(
                    "Queueing seed background job mode=%s job_status_id=%s",
                    registration.mode,
                    registration.job_status.id,
                )
                background_runner.submit(
                    seed_service.execute_registered_seed_job_in_background,
                    config_version_id=registration.configuration_version.id,
                    job_status_id=registration.job_status.id,
                    mode=registration.mode,
                )
                seed_launch_message = "Seed normalization started in background."
            else:
                registration = seed_service.register_seed_refresh(session=session)
                session.commit()
                logger.warning(
                    "Queueing seed background job mode=%s job_status_id=%s",
                    registration.mode,
                    registration.job_status.id,
                )
                background_runner.submit(
                    seed_service.execute_registered_seed_job_in_background,
                    config_version_id=registration.configuration_version.id,
                    job_status_id=registration.job_status.id,
                    mode=registration.mode,
                )
                seed_launch_message = "Full seed refresh started in background."
            snapshot = queries.get_control_panel_snapshot(session)
        except Exception as exc:
            session.rollback()
            snapshot = queries.get_control_panel_snapshot(session)
            seed_launch_error = str(exc)

    return templates.TemplateResponse(
        request,
        "partials/control_orchestration_tab.html",
        _build_orchestration_template_context(
            snapshot,
            seed_launch_message=seed_launch_message,
            seed_launch_error=seed_launch_error,
        ),
    )


def _parse_payload_json(
    payload_json: str,
    *,
    label: str,
) -> tuple[dict[str, object], tuple[str, ...]]:
    try:
        parsed = json.loads(payload_json)
    except json.JSONDecodeError as exc:
        return {}, (f"{label} is not valid JSON: {exc.msg}.",)
    if not isinstance(parsed, dict):
        return {}, (f"{label} must be a JSON object.",)
    return parsed, ()


def _change_count(
    session: Session,
    *,
    lifecycle: ConfigurationLifecycleService,
    payload: dict[str, object],
) -> int | None:
    try:
        current_version = lifecycle.load_current_valid_version(session)
    except ValueError:
        return None
    return len(diff_config_payloads(current_version.config_payload, payload))


def _default_generation_name(snapshot: ControlPanelSnapshot) -> str:
    if snapshot.config_summary is not None and snapshot.config_summary.simulation_name:
        return f"{snapshot.config_summary.simulation_name} run"
    return "Generation run"


def _split_editor_payloads(payload: dict[str, object]) -> tuple[str, str]:
    seed_payload, synthetic_payload = split_payload_sections(payload)
    return (
        json.dumps(seed_payload, indent=2, sort_keys=True),
        json.dumps(synthetic_payload, indent=2, sort_keys=True),
    )


def _normalize_config_scope(scope: str | None) -> str:
    if scope == "tournament":
        return "tournament"
    if scope == "synthetic":
        return "synthetic"
    return "seed"


def _render_config_tab_response(
    request: Request,
    *,
    session: Session,
    queries: ControlPanelQueries,
    templates: Jinja2Templates,
    active_config_scope: str,
) -> HTMLResponse:
    snapshot, editor = _config_context(session, queries=queries)
    return templates.TemplateResponse(
        request,
        "partials/control_config_tab.html",
        _build_config_template_context(
            snapshot,
            editor,
            active_config_scope=_normalize_config_scope(active_config_scope),
        ),
    )


def _build_config_template_context(
    snapshot: ControlPanelSnapshot,
    editor: ConfigEditorState,
    *,
    active_config_scope: str = DEFAULT_CONFIG_SCOPE,
) -> dict[str, object]:
    payload, errors = _parse_payload_json(
        editor.working_payload_json or "{}",
        label="Configuration payload",
    )
    if errors:
        payload = {}
    sections = build_config_editor_sections(payload)
    normalized_scope = _normalize_config_scope(active_config_scope)
    scope_sections = tuple(
        section for section in sections if section.definition.scope == normalized_scope
    )
    validation_messages_by_path = _validation_messages_by_path(
        scope_sections,
        editor.validation_issues,
    )
    section_issue_counts = _section_issue_counts(
        scope_sections,
        editor.validation_issues,
    )
    if normalized_scope == "seed":
        tab_kicker = "Seed Data Configuration"
        tab_title = "Seed Data Ingest and Preparation"
        tab_description = (
            "Raw datasets, naming, regional distribution, and club baseline configuration."
        )
    elif normalized_scope == "tournament":
        tab_kicker = "Tournament Configuration"
        tab_title = "Tournament Simulation Rules"
        tab_description = (
            "Scoring, tournament match structure, and hidden-bias settings used by tournament workflows."
        )
    else:
        tab_kicker = "Synthetic Workload Configuration"
        tab_title = "Player and Match Generation"
        tab_description = (
            "Simulation identity, player generation, team formation, match logic, and export settings."
        )
    return {
        "snapshot": snapshot,
        "editor": editor,
        "active_config_scope": normalized_scope,
        "config_tab_kicker": tab_kicker,
        "config_tab_title": tab_title,
        "config_tab_description": tab_description,
        "config_sections": scope_sections,
        "field_tooltip": _build_field_tooltip,
        "validation_messages_by_path": validation_messages_by_path,
        "section_issue_counts": section_issue_counts,
        "seed_sections": tuple(
            section for section in sections if section.definition.scope == "seed"
        ),
        "synthetic_sections": tuple(
            section for section in sections if section.definition.scope == "synthetic"
        ),
        "tournament_sections": tuple(
            section for section in sections if section.definition.scope == "tournament"
        ),
    }


def _build_field_tooltip(definition: object) -> str:
    if not hasattr(definition, "description"):
        return ""

    parts = [str(getattr(definition, "description", ""))]
    options = getattr(definition, "options", ()) or ()
    min_value = getattr(definition, "min_value", None)
    max_value = getattr(definition, "max_value", None)
    step = getattr(definition, "step", None)
    required = bool(getattr(definition, "required", False))
    control_type = getattr(definition, "control_type", None)

    if options:
        option_values = ", ".join(str(option.value) for option in options)
        parts.append(f"Options: {option_values}.")
    guidance = _control_type_guidance(control_type)
    if guidance:
        parts.append(guidance)
    if min_value is not None and max_value is not None:
        parts.append(f"Range: {min_value} to {max_value}.")
    elif min_value is not None:
        parts.append(f"Minimum: {min_value}.")
    elif max_value is not None:
        parts.append(f"Maximum: {max_value}.")
    if step is not None and control_type in {"integer", "decimal", "slider"}:
        parts.append(f"Step: {step}.")
    if required:
        parts.append("Required.")

    return " ".join(part for part in parts if part).strip()


def _control_type_guidance(control_type: object) -> str | None:
    guidance_by_type = {
        "text": "Valid input: short text value.",
        "date": "Valid input: ISO date in YYYY-MM-DD format.",
        "integer": "Valid input: whole number.",
        "decimal": "Valid input: numeric value; decimals allowed.",
        "checkbox": "Valid input: enabled or disabled.",
        "select": "Valid input: choose one listed option.",
        "slider": "Valid input: numeric value within the shown range.",
        "string_list": "Valid input: one item per line or comma-separated.",
        "multi_select": "Valid input: select one or more listed options.",
        "weight_table": "Valid input: numeric weights for each row.",
        "range_table": "Valid input: numeric min/max pair for each row.",
        "weighted_range_table": "Valid input: numeric distribution weights plus min/max pairs for each row.",
        "json": "Valid input: valid JSON object.",
    }
    return guidance_by_type.get(control_type if isinstance(control_type, str) else "")


def _validation_messages_by_path(
    sections: tuple[object, ...],
    issues: tuple[object, ...],
) -> dict[str, tuple[str, ...]]:
    messages: dict[str, list[str]] = {}
    for issue in issues:
        issue_path = getattr(issue, "path", None)
        issue_message = getattr(issue, "message", None)
        if not isinstance(issue_path, str) or not issue_message:
            continue
        for section in sections:
            for field in section.fields:
                field_key = getattr(field.definition, "path", None)
                if not isinstance(field_key, str) or not field_key:
                    continue
                if any(
                    _issue_matches_field(issue_path, field_path)
                    for field_path in _field_validation_paths(field)
                ):
                    messages.setdefault(field_key, []).append(str(issue_message))
    return {
        path: tuple(dict.fromkeys(path_messages))
        for path, path_messages in messages.items()
    }


def _section_issue_counts(
    sections: tuple[object, ...],
    issues: tuple[object, ...],
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for section in sections:
        field_paths = [
            field_path
            for field in section.fields
            for field_path in _field_validation_paths(field)
        ]
        count = sum(
            1
            for issue in issues
            if isinstance(getattr(issue, "path", None), str)
            and any(_issue_matches_field(issue.path, field_path) for field_path in field_paths)
        )
        counts[section.definition.id] = count
    return counts


def _issue_matches_field(issue_path: str, field_path: str) -> bool:
    return (
        issue_path == field_path
        or issue_path.startswith(f"{field_path}.")
        or field_path.startswith(f"{issue_path}.")
    )


def _field_validation_paths(field: object) -> tuple[str, ...]:
    definition = getattr(field, "definition", None)
    primary_path = getattr(definition, "path", None)
    validation_paths = getattr(definition, "validation_paths", ()) or ()
    resolved_paths = tuple(
        path
        for path in validation_paths
        if isinstance(path, str) and path
    )
    if resolved_paths:
        return resolved_paths
    if isinstance(primary_path, str) and primary_path:
        return (primary_path,)
    return ()


def _parse_iso_date(value: str):
    from datetime import date

    return date.fromisoformat(value)


def _student_groups_from_payload(payload: dict[str, Any]) -> tuple[StudentGroup, ...]:
    return tuple(
        StudentGroup(
            id=int(group["id"]),
            name=str(group.get("name") or f"Group {group['id']}"),
        )
        for group in payload.get("student_groups", ())
    )


def _team_submissions_from_payload(payload: dict[str, Any]) -> tuple[TeamSubmission, ...]:
    return tuple(
        TeamSubmission(
            group_id=int(row["group_id"]),
            slot=PortfolioSlot(
                country_code=str(row["country_code"]),
                division=str(row["division"]),
            ),
            team_id=int(row["team_id"]),
        )
        for row in payload.get("submissions", ())
    )


def _build_tournament_template_context(
    session: Session,
    *,
    snapshot: ControlPanelSnapshot,
    form_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    generation_run_id = (
        snapshot.generation_run_summary.generation_run_id
        if snapshot.generation_run_summary is not None
        else None
    )
    source_batch = (
        latest_completed_source_batch(session, generation_run_id=generation_run_id)
        if generation_run_id is not None
        else None
    )
    event_summary = _latest_tournament_event_summary(
        session,
        generation_run_id=generation_run_id,
        source_batch_id=getattr(source_batch, "id", None),
    )
    resolved_form_state = form_state or _latest_tournament_form_state(
        session,
        snapshot=snapshot,
        source_batch=source_batch,
        event_id=event_summary["event_id"] if event_summary else None,
    )
    results_summary = (
        _tournament_results_summary(session, event_id=event_summary["event_id"])
        if event_summary
        else None
    )
    return {
        "snapshot": snapshot,
        "tournament_slots": TOURNAMENT_PORTFOLIO_SLOTS,
        "tournament_group_indexes": tuple(range(1, TOURNAMENT_GROUP_COUNT + 1)),
        "tournament_source_batch": source_batch,
        "tournament_event_summary": event_summary,
        "tournament_results_summary": results_summary,
        "tournament_form_state": resolved_form_state,
        "tournament_monte_carlo_state": {
            "event_id": event_summary["event_id"] if event_summary else None,
            "iterations": 1000,
            "seed": 1,
        },
        "tournament_issue_map": {},
        "tournament_validation_issues": (),
        "tournament_save_message": None,
        "tournament_save_error": None,
        "tournament_monte_carlo_message": None,
        "tournament_monte_carlo_error": None,
        "saved_tournament_event_id": None,
    }


def _default_tournament_form_state(
    snapshot: ControlPanelSnapshot,
    *,
    source_batch: object | None,
) -> dict[str, Any]:
    event_name = "Class Tournament"
    if snapshot.generation_run_summary is not None:
        event_name = f"{snapshot.generation_run_summary.generation_name} Tournament"
    source_month = getattr(source_batch, "batch_month", None)
    tournament_date = source_month.isoformat() if source_month is not None else ""
    return {
        "event_name": event_name,
        "tournament_date": tournament_date,
        "group_names": {
            str(group_index): f"Group {group_index}"
            for group_index in range(1, TOURNAMENT_GROUP_COUNT + 1)
        },
        "team_ids": {},
    }


def _latest_tournament_form_state(
    session: Session,
    *,
    snapshot: ControlPanelSnapshot,
    source_batch: object | None,
    event_id: int | None,
) -> dict[str, Any]:
    default_state = _default_tournament_form_state(
        snapshot,
        source_batch=source_batch,
    )
    if event_id is None:
        return default_state

    event = session.get(TournamentEvent, event_id)
    if event is None:
        return default_state

    group_rows = session.execute(
        select(TournamentStudentGroup)
        .where(TournamentStudentGroup.event_id == event_id)
        .order_by(TournamentStudentGroup.id)
    ).scalars().all()
    group_names = {
        str(int(group.external_group_key or group.id)): group.group_name
        for group in group_rows
    }
    group_input_ids_by_student_group_id = {
        int(group.id): int(group.external_group_key or group.id)
        for group in group_rows
    }
    submission_rows = session.execute(
        select(TournamentSubmission)
        .where(TournamentSubmission.event_id == event_id)
        .order_by(TournamentSubmission.id)
    ).scalars()
    team_ids = {
        _tournament_team_field_key(
            group_input_id,
            PortfolioSlot(
                country_code=submission.slot_country_code,
                division=submission.slot_division,
            ),
        ): str(submission.team_id)
        for submission in submission_rows
        if (
            group_input_id := group_input_ids_by_student_group_id.get(
                int(submission.student_group_id)
            )
        )
        is not None
    }

    return {
        "event_name": event.event_name,
        "tournament_date": event.tournament_date.isoformat(),
        "group_names": {
            **default_state["group_names"],
            **group_names,
        },
        "team_ids": team_ids,
    }


def _tournament_form_state_from_json(
    payload_json: str,
    *,
    event_name: str,
    tournament_date: str,
) -> dict[str, Any]:
    try:
        payload = json.loads(payload_json or "{}")
    except json.JSONDecodeError:
        payload = {}
    return {
        "event_name": event_name,
        "tournament_date": tournament_date,
        "group_names": {
            str(key): str(value)
            for key, value in (payload.get("group_names") or {}).items()
        },
        "team_ids": {
            str(key): str(value)
            for key, value in (payload.get("team_ids") or {}).items()
        },
    }


def _tournament_form_payload_objects(
    form_state: dict[str, Any],
) -> tuple[tuple[StudentGroup, ...], tuple[TeamSubmission, ...]]:
    group_names = form_state.get("group_names") or {}
    team_ids = form_state.get("team_ids") or {}
    groups = tuple(
        StudentGroup(
            id=group_index,
            name=str(group_names.get(str(group_index)) or f"Group {group_index}"),
        )
        for group_index in range(1, TOURNAMENT_GROUP_COUNT + 1)
    )
    submissions: list[TeamSubmission] = []
    for group_index in range(1, TOURNAMENT_GROUP_COUNT + 1):
        for slot in TOURNAMENT_PORTFOLIO_SLOTS:
            key = _tournament_team_field_key(group_index, slot)
            raw_team_id = str(team_ids.get(key) or "").strip()
            if not raw_team_id:
                raise ValueError(
                    f"Team ID is required for group {group_index} "
                    f"{slot.country_code} {slot.division}."
                )
            try:
                team_id = int(raw_team_id)
            except ValueError as exc:
                raise ValueError(
                    f"Team ID must be a whole number for group {group_index} "
                    f"{slot.country_code} {slot.division}."
                ) from exc
            submissions.append(
                TeamSubmission(
                    group_id=group_index,
                    slot=slot,
                    team_id=team_id,
                )
            )
    return groups, tuple(submissions)


def _tournament_issue_map(issues: tuple[object, ...]) -> dict[str, tuple[object, ...]]:
    mapped: dict[str, list[object]] = {}
    for issue in issues:
        slot = getattr(issue, "slot")
        key = _tournament_team_field_key(
            int(getattr(issue, "group_id")),
            PortfolioSlot(
                country_code=slot.country_code,
                division=slot.division,
            ),
        )
        mapped.setdefault(key, []).append(issue)
    return {key: tuple(value) for key, value in mapped.items()}


def _tournament_team_field_context(
    *,
    group_index: int,
    slot: PortfolioSlot,
    field_value: str,
    field_issues: tuple[object, ...],
) -> dict[str, Any]:
    return {
        "group_index": group_index,
        "slot": slot,
        "field_key": _tournament_team_field_key(group_index, slot),
        "field_value": field_value,
        "field_issues": field_issues,
    }


def _tournament_team_field_key(group_index: int, slot: PortfolioSlot) -> str:
    return f"group_{group_index}_{slot.country_code}_{slot.division}"


def _latest_tournament_event_summary(
    session: Session,
    *,
    generation_run_id: int | None,
    source_batch_id: int | None,
) -> dict[str, Any] | None:
    if generation_run_id is None or source_batch_id is None:
        return None
    event = session.execute(
        select(TournamentEvent)
        .where(
            TournamentEvent.generation_run_id == generation_run_id,
            TournamentEvent.source_batch_id == source_batch_id,
        )
        .order_by(TournamentEvent.id.desc())
        .limit(1)
    ).scalar_one_or_none()
    if event is None:
        return None

    latest_run = session.execute(
        select(TournamentSimulationRun, JobStatus)
        .outerjoin(JobStatus, TournamentSimulationRun.job_status_id == JobStatus.id)
        .where(
            TournamentSimulationRun.event_id == event.id,
            TournamentSimulationRun.run_type == "monte_carlo",
        )
        .order_by(TournamentSimulationRun.id.desc())
        .limit(1)
    ).one_or_none()
    run_summary = None
    if latest_run is not None:
        simulation_run, job_status = latest_run
        run_summary = {
            "simulation_run_id": simulation_run.id,
            "status": simulation_run.status,
            "job_status_id": simulation_run.job_status_id,
            "job_status": job_status.status if job_status is not None else None,
            "current_phase": job_status.current_phase if job_status is not None else None,
            "percent_complete": job_status.percent_complete if job_status is not None else None,
            "current_message": (
                job_status.current_message if job_status is not None else None
            ),
            "iteration_count": simulation_run.iteration_count,
            "seed": simulation_run.seed,
            "error_message": simulation_run.error_message,
        }

    return {
        "event_id": event.id,
        "event_name": event.event_name,
        "event_status": event.status,
        "tournament_date": event.tournament_date,
        "source_batch_id": event.source_batch_id,
        "latest_monte_carlo_run": run_summary,
    }


def _tournament_results_summary(
    session: Session,
    *,
    event_id: int,
) -> dict[str, Any] | None:
    summary = TournamentService().latest_summary(event_id=event_id, session=session)
    if summary is None or summary["status"] != "succeeded":
        return None

    group_names = {
        int(group_id): str(group_name)
        for group_id, group_name in session.execute(
            select(TournamentStudentGroup.id, TournamentStudentGroup.group_name).where(
                TournamentStudentGroup.event_id == event_id,
            )
        ).all()
    }
    submissions = session.execute(
        select(
            TournamentSubmission.team_id,
            TournamentSubmission.slot_country_code,
            TournamentSubmission.slot_division,
            TournamentStudentGroup.group_name,
        )
        .join(
            TournamentStudentGroup,
            TournamentSubmission.student_group_id == TournamentStudentGroup.id,
        )
        .where(TournamentSubmission.event_id == event_id)
    ).all()

    submitted_groups_by_team_slot: dict[tuple[int, str, str], set[str]] = {}
    for team_id, country_code, division, group_name in submissions:
        key = (int(team_id), str(country_code), str(division))
        submitted_groups_by_team_slot.setdefault(key, set()).add(str(group_name))

    team_results = sorted(
        summary["team_results"],
        key=lambda row: (
            str(row["slot_division"]),
            -_decimal_value(row["championship_probability"]),
            str(row["slot_country_code"]),
            row["team_id"],
        ),
    )
    for row in team_results:
        key = (
            int(row["team_id"]),
            str(row["slot_country_code"]),
            str(row["slot_division"]),
        )
        credited_groups = tuple(sorted(submitted_groups_by_team_slot.get(key, ())))
        row["credited_groups"] = credited_groups
        row["credit_count"] = len(credited_groups)
        row["championship_probability_display"] = _percentage_display(
            row["championship_probability"]
        )
        row["top_three_probability_display"] = _percentage_display(
            row["top_three_probability"]
        )
        row["probability_rank"] = None

    for division in sorted({str(row["slot_division"]) for row in team_results}):
        division_rows = [
            row for row in team_results if str(row["slot_division"]) == division
        ]
        division_rows.sort(
            key=lambda row: (
                -_decimal_value(row["championship_probability"]),
                -_decimal_value(row["top_three_probability"]),
                _decimal_value(row["average_finish"] or 999),
                str(row["slot_country_code"]),
                int(row["team_id"]),
            )
        )
        for rank, row in enumerate(division_rows, start=1):
            row["probability_rank"] = rank

    division_results = sorted(
        summary["division_results"],
        key=lambda row: str(row["slot_division"]),
    )
    group_results = sorted(
        summary["group_results"],
        key=lambda row: (
            -_decimal_value(row["expected_score"] or row["official_score"]),
            _decimal_value(row["average_rank"] or row["final_rank"] or 999),
            row["student_group_id"],
        ),
    )
    for row in group_results:
        row["group_name"] = group_names.get(row["student_group_id"], "Group")

    duplicate_credits = [
        {
            "team_id": team_id,
            "slot_country_code": country_code,
            "slot_division": division,
            "credited_groups": tuple(sorted(group_names_for_team)),
            "credit_count": len(group_names_for_team),
        }
        for (
            team_id,
            country_code,
            division,
        ), group_names_for_team in submitted_groups_by_team_slot.items()
        if len(group_names_for_team) > 1
    ]
    duplicate_credits.sort(
        key=lambda row: (
            str(row["slot_country_code"]),
            str(row["slot_division"]),
            int(row["team_id"]),
        )
    )

    return {
        **summary,
        "team_results": team_results,
        "division_results": division_results,
        "group_results": group_results,
        "duplicate_credits": duplicate_credits,
    }


def _decimal_value(value: object) -> Decimal:
    if value is None:
        return Decimal("0")
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return Decimal("0")


def _percentage_display(value: object) -> str:
    percent = (_decimal_value(value) * Decimal("100")).quantize(Decimal("0.1"))
    return f"{percent}%"


def _validation_issue_payload(issue: object) -> dict[str, Any]:
    return {
        "group_id": getattr(issue, "group_id"),
        "team_id": getattr(issue, "team_id"),
        "country_code": getattr(issue, "slot").country_code,
        "division": getattr(issue, "slot").division,
        "field": getattr(issue, "field"),
        "code": getattr(issue, "code"),
        "message": getattr(issue, "message"),
    }
