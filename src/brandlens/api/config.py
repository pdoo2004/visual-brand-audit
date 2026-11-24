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
    # Framing/sharpness need a subject box. RT-DETR is optional; disable with
    # BRANDLENS_SUBJECT_DETECTOR=0 if torch/transformers weights are unavailable.
    subject_detector_enabled: bool = True
    subject_detector_device: int = -1  # -1 = CPU
    # When multiple detections pass the confidence filter: review | highest_confidence | largest_area
    subject_multi_policy: str = "highest_confidence"

    def __post_init__(self) -> None:
        if self.analyzer not in ("placeholder", "pipeline"):
            raise ValueError(
                f"analyzer must be 'placeholder' or 'pipeline', got {self.analyzer!r}"
            )
        if self.subject_multi_policy not in {
            "review",
            "highest_confidence",
            "largest_area",
        }:
            raise ValueError(
                "subject_multi_policy must be one of: "
                "review, highest_confidence, largest_area, "
                f"got {self.subject_multi_policy!r}"
            )

    @classmethod
    def from_env(cls) -> Settings:
        """Build settings from BRANDLENS_* environment variables."""
        origins = os.getenv("BRANDLENS_CORS_ORIGINS", _DEFAULT_CORS_ORIGINS)
        subject_raw = os.getenv("BRANDLENS_SUBJECT_DETECTOR", "1").lower()
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
            subject_detector_enabled=subject_raw not in {"0", "false", "no", "off"},
            subject_detector_device=int(
                os.getenv("BRANDLENS_SUBJECT_DEVICE", str(cls.subject_detector_device))
            ),
            subject_multi_policy=os.getenv(
                "BRANDLENS_SUBJECT_MULTI_POLICY", cls.subject_multi_policy
            ).strip().lower(),
        )
