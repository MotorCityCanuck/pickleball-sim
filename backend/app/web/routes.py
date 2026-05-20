"""FastAPI routes for the operator control panel."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.db.session import get_session

from .control_panel_queries import ControlPanelQueries


TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates"


@lru_cache(maxsize=1)
def get_templates() -> Jinja2Templates:
    """Return the Jinja template loader."""
    return Jinja2Templates(directory=str(TEMPLATES_DIR))


def get_control_panel_queries() -> ControlPanelQueries:
    """Return the control panel query service."""
    return ControlPanelQueries()


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
        snapshot = queries.get_control_panel_snapshot(session)
        return templates.TemplateResponse(
            request,
            "control_panel.html",
            {
                "snapshot": snapshot,
            },
        )

    @router.get("/control/partials/config", response_class=HTMLResponse)
    def control_panel_config_partial(
        request: Request,
        session: Session = Depends(get_session),
        queries: ControlPanelQueries = Depends(get_control_panel_queries),
    ) -> HTMLResponse:
        snapshot = queries.get_control_panel_snapshot(session)
        return templates.TemplateResponse(
            request,
            "partials/control_config_tab.html",
            {
                "snapshot": snapshot,
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
