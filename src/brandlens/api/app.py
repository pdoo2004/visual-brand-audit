"""FastAPI application factory."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from brandlens.api import db as database
from brandlens.api import health
from brandlens.api.config import Settings
from brandlens.api.routers import feedback as feedback_router
from brandlens.api.routers import images as images_router
from brandlens.api.routers import jobs as jobs_router
from brandlens.api.routers import urls as urls_router

log = logging.getLogger(__name__)


def _build_subject_detector(settings: Settings):
    """Optional RT-DETR for framing/sharpness. Failures leave detector unset."""
    if not settings.subject_detector_enabled:
        return None
    try:
        from brandlens.cv.subject.rtdetr_detector import RTDetrSubjectDetector

        return RTDetrSubjectDetector({"device": settings.subject_detector_device})
    except Exception:
        log.exception(
            "subject detector unavailable; framing/sharpness will need review "
            "(set BRANDLENS_SUBJECT_DETECTOR=0 to silence)"
        )
        return None


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create the API app.

    A factory (instead of a module-level app alone) lets tests build an app
    with their own settings. Routers for uploads, jobs, rubrics and feedback
    are added here as they are implemented.
    """
    settings = settings or Settings.from_env()

    @asynccontextmanager
    async def _lifespan(app: FastAPI):
        database.init_db(settings.db_path)
        app.state.db_path = settings.db_path
        app.state.upload_dir = settings.upload_dir
        app.state.processed_dir = settings.processed_dir
        app.state.rubric_path = settings.rubric_path
        # None -> the worker's placeholder analysis. "pipeline" builds the real analyzer
        # once (rubric + model client), so a bad configuration fails at startup.
        analyzer = None
        if settings.analyzer == "pipeline":
            from brandlens.api.analysis import PipelineAnalyzer
            from brandlens.cv.subject.selector import SingleSubjectSelector

            analyzer = PipelineAnalyzer.from_settings(
                settings,
                subject_detector=_build_subject_detector(settings),
                subject_selector=SingleSubjectSelector(
                    {"multi_policy": settings.subject_multi_policy}
                ),
            )
        app.state.analyzer = analyzer
        try:
            yield
        finally:
            if analyzer is not None:
                analyzer.close()

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
    app.include_router(feedback_router.router)
    app.include_router(images_router.router)
    app.include_router(urls_router.router)
    return app
