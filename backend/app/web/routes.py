"""FastAPI routes for the operator control panel."""
from __future__ import annotations

from functools import lru_cache
import json
from pathlib import Path

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.core import ConfigurationLifecycleService, diff_config_payloads
from app.db.session import get_session
from app.generation import GenerationRunService

from .control_panel_queries import (
    ConfigEditorState,
    ControlPanelQueries,
    ControlPanelSnapshot,
    merge_payload_sections,
)


TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates"


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
            {
                "snapshot": snapshot,
                "editor": editor,
            },
        )

    @router.get("/control/partials/config", response_class=HTMLResponse)
    def control_panel_config_partial(
        request: Request,
        session: Session = Depends(get_session),
        queries: ControlPanelQueries = Depends(get_control_panel_queries),
    ) -> HTMLResponse:
        snapshot, editor = _config_context(session, queries=queries)
        return templates.TemplateResponse(
            request,
            "partials/control_config_tab.html",
            {
                "snapshot": snapshot,
                "editor": editor,
            },
        )

    @router.post("/control/config/validate", response_class=HTMLResponse)
    def control_panel_config_validate(
        request: Request,
        config_title: str = Form(""),
        config_notes: str = Form(""),
        seed_config_json: str = Form("{}"),
        synthetic_config_json: str = Form("{}"),
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
            seed_payload_json=seed_config_json,
            synthetic_payload_json=synthetic_config_json,
            action="validate",
        )
        return templates.TemplateResponse(
            request,
            "partials/control_config_tab.html",
            {
                "snapshot": snapshot,
                "editor": editor,
            },
        )

    @router.post("/control/config/save", response_class=HTMLResponse)
    def control_panel_config_save(
        request: Request,
        config_title: str = Form(""),
        config_notes: str = Form(""),
        seed_config_json: str = Form("{}"),
        synthetic_config_json: str = Form("{}"),
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
            seed_payload_json=seed_config_json,
            synthetic_payload_json=synthetic_config_json,
            action="save",
        )
        return templates.TemplateResponse(
            request,
            "partials/control_config_tab.html",
            {
                "snapshot": snapshot,
                "editor": editor,
            },
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
            {
                "snapshot": snapshot,
                "launch_message": None,
                "launch_error": None,
            },
        )

    @router.post("/control/generation/start", response_class=HTMLResponse)
    def control_panel_generation_start(
        request: Request,
        generation_name: str = Form(""),
        destructive_confirm: str | None = Form(None),
        session: Session = Depends(get_session),
        queries: ControlPanelQueries = Depends(get_control_panel_queries),
        run_service: GenerationRunService = Depends(get_generation_run_service),
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
                run_service.launch_generation_run(requested_name, session=session)
                session.commit()
                snapshot = queries.get_control_panel_snapshot(session)
                launch_message = f"Generation run '{requested_name}' completed successfully."
            except Exception as exc:
                session.rollback()
                snapshot = queries.get_control_panel_snapshot(session)
                launch_error = str(exc)

        return templates.TemplateResponse(
            request,
            "partials/control_orchestration_tab.html",
            {
                "snapshot": snapshot,
                "launch_message": launch_message,
                "launch_error": launch_error,
            },
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


def _config_context(
    session: Session,
    *,
    queries: ControlPanelQueries,
    lifecycle: ConfigurationLifecycleService | None = None,
    title: str | None = None,
    notes: str | None = None,
    seed_payload_json: str | None = None,
    synthetic_payload_json: str | None = None,
    action: str | None = None,
) -> tuple[ControlPanelSnapshot, ConfigEditorState]:
    snapshot = queries.get_control_panel_snapshot(session)
    default_editor = queries.get_config_editor_state(session)
    lifecycle = lifecycle or ConfigurationLifecycleService()

    if action is None:
        return snapshot, default_editor

    editor_title = (title or "").strip()
    editor_notes = notes or ""
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
    if json_errors:
        return snapshot, ConfigEditorState(
            title=editor_title,
            notes=editor_notes,
            seed_payload_json=editor_seed_payload_json,
            synthetic_payload_json=editor_synthetic_payload_json,
            validation_passed=False,
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
            seed_payload_json=seed_editor_json,
            synthetic_payload_json=synthetic_editor_json,
            validation_passed=validation.is_valid,
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
            seed_payload_json=seed_editor_json,
            synthetic_payload_json=synthetic_editor_json,
            validation_passed=False,
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
            seed_payload_json=seed_editor_json,
            synthetic_payload_json=synthetic_editor_json,
            validation_passed=False,
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
            seed_payload_json=seed_editor_json,
            synthetic_payload_json=synthetic_editor_json,
            validation_passed=True,
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
        title="",
        notes=refreshed_editor.notes,
        seed_payload_json=refreshed_editor.seed_payload_json,
        synthetic_payload_json=refreshed_editor.synthetic_payload_json,
        validation_passed=False,
        validation_errors=(),
        validation_hash=refreshed_snapshot.config_summary.config_hash if refreshed_snapshot.config_summary else None,
        status_message="Configuration saved as the current valid version.",
        change_count=0,
    )
    return refreshed_snapshot, refreshed_editor


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
    seed_payload: dict[str, object] = {}
    synthetic_payload: dict[str, object] = {}
    for key, value in payload.items():
        if key in {"raw_seed_data", "name_assignment", "regional", "club_generation"}:
            seed_payload[key] = value
        else:
            synthetic_payload[key] = value
    return (
        json.dumps(seed_payload, indent=2, sort_keys=True),
        json.dumps(synthetic_payload, indent=2, sort_keys=True),
    )
