"""FastAPI application entrypoint for operator web surfaces."""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.background_jobs import get_default_background_job_runner
from app.web.routes import build_control_panel_router


@asynccontextmanager
async def _lifespan(app: FastAPI):
    """Own long-lived app resources."""
    get_default_background_job_runner()
    try:
        yield
    finally:
        get_default_background_job_runner().shutdown(wait=False)


def create_app() -> FastAPI:
    """Create the FastAPI application."""
    app = FastAPI(
        title="Pickleball Simulation Control Panel",
        lifespan=_lifespan,
    )
    app.include_router(build_control_panel_router())
    return app


app = create_app()
