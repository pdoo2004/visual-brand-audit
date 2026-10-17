"""FastAPI application factory."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from brandlens.api import db as database
from brandlens.api import health
from brandlens.api.config import Settings
from brandlens.api.routers import jobs as jobs_router


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create the API app.

    A factory (instead of a module-level app alone) lets tests build an app
    with their own settings. Routers for uploads, jobs, rubrics and feedback
    are added here as they are implemented (SCRUM-125, 154, 155, ...).
    """
    settings = settings or Settings.from_env()

    @asynccontextmanager
    async def _lifespan(app: FastAPI):
        database.init_db(settings.db_path)
        app.state.db_path = settings.db_path
        app.state.upload_dir = settings.upload_dir
        app.state.processed_dir = settings.processed_dir
        app.state.rubric_path = settings.rubric_path
        yield

    app = FastAPI(
        title="BrandLens API",
        version=health.get_version(),
        description="Backend API for AI-enabled photography and visual brand standards analysis.",
        lifespan=_lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health.router)
    app.include_router(jobs_router.router)
    return app
