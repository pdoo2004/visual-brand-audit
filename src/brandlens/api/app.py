"""FastAPI application factory."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from brandlens.api import health
from brandlens.api.config import Settings


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create the API app.

    A factory (instead of a module-level app alone) lets tests build an app
    with their own settings. Routers for uploads, jobs, rubrics and feedback
    are added here as they are implemented (SCRUM-125, 154, 155, ...).
    """
    settings = settings or Settings.from_env()
    app = FastAPI(
        title="BrandLens API",
        version=health.get_version(),
        description="Backend API for AI-enabled photography and visual brand standards analysis.",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health.router)
    return app
