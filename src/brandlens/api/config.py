"""Runtime settings for the API, read from environment variables.

Every setting has a safe local-development default, so the API starts with no
configuration. Override with BRANDLENS_* environment variables, for example:

    BRANDLENS_PORT=9000 BRANDLENS_LOG_LEVEL=debug python -m brandlens.api
"""

from __future__ import annotations

import os
from dataclasses import dataclass

# Vite's default dev-server addresses (the React UI runs here during development).
_DEFAULT_CORS_ORIGINS = "http://localhost:5173,http://127.0.0.1:5173"


@dataclass(frozen=True)
class Settings:
    """Immutable API settings."""

    host: str = "127.0.0.1"
    port: int = 8000
    log_level: str = "info"
    reload: bool = False
    cors_origins: tuple[str, ...] = tuple(_DEFAULT_CORS_ORIGINS.split(","))

    @classmethod
    def from_env(cls) -> Settings:
        """Build settings from BRANDLENS_* environment variables."""
        origins = os.getenv("BRANDLENS_CORS_ORIGINS", _DEFAULT_CORS_ORIGINS)
        return cls(
            host=os.getenv("BRANDLENS_HOST", cls.host),
            port=int(os.getenv("BRANDLENS_PORT", str(cls.port))),
            log_level=os.getenv("BRANDLENS_LOG_LEVEL", cls.log_level).lower(),
            reload=os.getenv("BRANDLENS_RELOAD", "").lower() in {"1", "true", "yes"},
            cors_origins=tuple(o.strip() for o in origins.split(",") if o.strip()),
        )
