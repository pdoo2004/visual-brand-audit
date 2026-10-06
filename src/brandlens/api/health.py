"""Liveness endpoint (contract: GET /health)."""

from importlib.metadata import PackageNotFoundError, version

from fastapi import APIRouter

router = APIRouter(tags=["health"])


def get_version() -> str:
    """Return the installed package version, or a placeholder when not installed."""
    try:
        return version("brandlens")
    except PackageNotFoundError:
        return "0.0.0+unknown"


@router.get("/health", summary="Liveness check")
def health() -> dict[str, str]:
    """Return 200 with the service version while the API process is running."""
    return {"status": "ok", "version": get_version()}
