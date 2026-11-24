"""Runtime settings for the API, read from environment variables.

Every setting has a safe local-development default, so the API starts with no
configuration. Override with BRANDLENS_* environment variables, for example:

    BRANDLENS_PORT=9000 BRANDLENS_LOG_LEVEL=debug python -m brandlens.api
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

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
    db_path: Path = field(default_factory=lambda: Path("data/brandlens.db"))
    upload_dir: Path = field(default_factory=lambda: Path("data/uploads/raw"))
    processed_dir: Path = field(default_factory=lambda: Path("data/uploads/processed"))
    rubric_path: Path = field(default_factory=lambda: Path("config/brand_standards.json"))
    # Model Serving (contract 4.4): any OpenAI-compatible /v1/chat/completions server.
    # Dev: local Ollama. Prod: vLLM. Set the model name to the tag you pulled / the served name.
    model_base_url: str = "http://localhost:11434/v1"
    model_name: str = "gemma4:e4b"
    model_api_key: str | None = None
    model_timeout_s: float = 60.0
    model_max_retries: int = 1  # contract: one retry, then the tone criterion is unavailable
    # Which analysis the worker runs on each image: "placeholder" (stub scores, no model
    # needed; the default so the API starts anywhere) or "pipeline" (real CV + VLM scoring).
    analyzer: str = "placeholder"
    # Upload limits (SCRUM-161). The per-file size matches the interface contract and the
    # frontend (10 MB); the pixel cap matches preprocessing.image_io.load_image (25 MP).
    max_file_bytes: int = 10 * 1024 * 1024
    max_files_per_request: int = 20
    max_total_bytes: int = 100 * 1024 * 1024
    max_image_pixels: int = 25_000_000

    def __post_init__(self) -> None:
        if self.analyzer not in ("placeholder", "pipeline"):
            raise ValueError(
                f"analyzer must be 'placeholder' or 'pipeline', got {self.analyzer!r}"
            )
        for name in (
            "max_file_bytes",
            "max_files_per_request",
            "max_total_bytes",
            "max_image_pixels",
        ):
            value = getattr(self, name)
            if type(value) is not int or value < 1:
                raise ValueError(f"{name} must be a positive integer, got {value!r}")
        if self.max_total_bytes < self.max_file_bytes:
            raise ValueError("max_total_bytes must be at least max_file_bytes")

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
            db_path=Path(os.getenv("BRANDLENS_DB_PATH", "data/brandlens.db")),
            upload_dir=Path(os.getenv("BRANDLENS_UPLOAD_DIR", "data/uploads/raw")),
            processed_dir=Path(os.getenv("BRANDLENS_PROCESSED_DIR", "data/uploads/processed")),
            rubric_path=Path(os.getenv("BRANDLENS_RUBRIC_PATH", "config/brand_standards.json")),
            model_base_url=os.getenv("BRANDLENS_MODEL_BASE_URL", cls.model_base_url),
            model_name=os.getenv("BRANDLENS_MODEL_NAME", cls.model_name),
            model_api_key=os.getenv("BRANDLENS_MODEL_API_KEY") or None,
            model_timeout_s=float(os.getenv("BRANDLENS_MODEL_TIMEOUT_S", str(cls.model_timeout_s))),
            model_max_retries=int(
                os.getenv("BRANDLENS_MODEL_MAX_RETRIES", str(cls.model_max_retries))
            ),
            analyzer=os.getenv("BRANDLENS_ANALYZER", cls.analyzer).strip().lower(),
            max_file_bytes=int(os.getenv("BRANDLENS_MAX_FILE_BYTES", str(cls.max_file_bytes))),
            max_files_per_request=int(
                os.getenv("BRANDLENS_MAX_FILES_PER_REQUEST", str(cls.max_files_per_request))
            ),
            max_total_bytes=int(
                os.getenv("BRANDLENS_MAX_TOTAL_BYTES", str(cls.max_total_bytes))
            ),
            max_image_pixels=int(
                os.getenv("BRANDLENS_MAX_IMAGE_PIXELS", str(cls.max_image_pixels))
            ),
        )
