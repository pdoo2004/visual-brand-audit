"""Run the API with Uvicorn: `python -m brandlens.api`."""

import uvicorn

from brandlens.api.config import Settings


def main() -> None:
    """Start Uvicorn using settings from the environment."""
    settings = Settings.from_env()
    uvicorn.run(
        "brandlens.api.main:app",
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level,
        reload=settings.reload,
    )


if __name__ == "__main__":
    main()
