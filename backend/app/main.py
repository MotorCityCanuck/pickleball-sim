"""FastAPI application entrypoint for operator web surfaces."""
from __future__ import annotations

from fastapi import FastAPI

from app.web.routes import build_control_panel_router


def create_app() -> FastAPI:
    """Create the FastAPI application."""
    app = FastAPI(title="Pickleball Simulation Control Panel")
    app.include_router(build_control_panel_router())
    return app


app = create_app()
