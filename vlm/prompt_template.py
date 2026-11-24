"""VLM prompt for local scripts — re-exports the BrandLens serving template."""

from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from brandlens.serving.prompt_template import (
    CRITERIA,
    RECOMMENDED_TONES,
    RESPONSE_SCHEMA,
    TARGET_TONE,
    criteria_block,
    render_prompt,
)

__all__ = [
    "CRITERIA",
    "RECOMMENDED_TONES",
    "RESPONSE_SCHEMA",
    "TARGET_TONE",
    "criteria_block",
    "render_prompt",
]
