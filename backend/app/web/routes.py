"""FastAPI routes for the operator control panel."""
from __future__ import annotations

from functools import lru_cache
import logging
import json
from pathlib import Path
import shutil
import subprocess

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
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

from .control_panel_queries import (
    ConfigEditorState,
    ControlPanelQueries,
    ControlPanelSnapshot,
    merge_payload_sections,
    split_payload_sections,
)
from .job_recovery import clear_stalled_job, dismiss_failed_job


TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates"
logger = logging.getLogger("uvicorn.error")
DEFAULT_CONFIG_SCOPE = "seed"


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
