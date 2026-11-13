"""FastAPI application factory."""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from brandlens.api import db as database
from brandlens.api import health
from brandlens.api.config import Settings
from brandlens.api.routers import feedback as feedback_router
from brandlens.api.routers import jobs as jobs_router
from brandlens.api.routers import urls as urls_router
from brandlens.api.schemas import ErrorBody, ErrorCode

# Multipart framing (boundaries, headers) adds a little on top of the file bytes.
_MULTIPART_OVERHEAD_BYTES = 1024 * 1024
_UPLOAD_PATH = "/api/v1/analyses/uploads"


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
        app.state.settings = settings
        # None -> the worker's placeholder analysis. "pipeline" builds the real analyzer
        # once (rubric + model client), so a bad configuration fails at startup.
        analyzer = None
        if settings.analyzer == "pipeline":
            from brandlens.api.analysis import PipelineAnalyzer

            analyzer = PipelineAnalyzer.from_settings(settings)
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

    @app.middleware("http")
    async def _reject_oversized_upload(request: Request, call_next):
        """Refuse an upload whose declared size is over the limit, before the body is read.

        Multipart bodies are parsed (and spooled to disk) before the endpoint runs, so the
        endpoint alone cannot stop a huge request. A client that omits Content-Length
        is still held to the per-file and total limits inside the endpoint.
        """
        if request.method == "POST" and request.url.path == _UPLOAD_PATH:
            declared = request.headers.get("content-length", "")
            limit = settings.max_total_bytes + _MULTIPART_OVERHEAD_BYTES
            if declared.isdigit() and int(declared) > limit:
                body = ErrorBody(
                    code=ErrorCode.FILE_TOO_LARGE,
                    message=f"Request exceeds the {settings.max_total_bytes // (1024 * 1024)} MB "
                    "total upload limit.",
                ).model_dump(mode="json")
                return JSONResponse(status_code=413, content={"detail": body})
        return await call_next(request)

    app.include_router(health.router)
    app.include_router(jobs_router.router)
    app.include_router(feedback_router.router)
    app.include_router(urls_router.router)
    return app
