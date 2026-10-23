"""VLM prompt for SCRUM-135.

The locked MVP rubric (SCRUM-180) sends only B1 to the model.
Q1-Q5 are computer-vision measurements and must not be scored here.
"""

from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from brandlens.vlm.criteria import CRITERIA, RECOMMENDED_TONES, TARGET_TONE

__all__ = ["CRITERIA", "RECOMMENDED_TONES", "RESPONSE_SCHEMA", "TARGET_TONE", "render_prompt"]

# Injected into the prompt and also sent as Ollama's structured-output schema.
RESPONSE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["criteria"],
    "properties": {
        "criteria": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["id", "name", "tone_label", "fit_score", "evidence"],
                "properties": {
                    "id": {"type": "string"},
                    "name": {"type": "string"},
                    "tone_label": {
                        "type": "string",
                        "description": (
                            "Comma-separated words from the target tone list "
                            "that are actually visible."
                        ),
                    },
                    "fit_score": {"type": "integer", "minimum": 1, "maximum": 5},
                    "evidence": {"type": "string"},
                },
            },
        }
    },
}

TEMPLATE = """You evaluate one marketing photograph. Score only the criteria listed below.
Do not score exposure, contrast, color palette, framing, or sharpness. Another system measures those.
Do not add criteria that were not listed.
Return one JSON object and no other text.

Target tone. A fitting photograph belongs in this set. It does not have to show every word:
{target_tone}

Criteria:
{criteria_block}

Use this JSON shape:
{{
  "criteria": [
    {{
      "id": "<criterion id>",
      "name": "<criterion name>",
      "tone_label": "<comma-separated words from the target tone that you actually see>",
      "fit_score": <integer 1 to 5, where 5 is a strong fit to the target tone>,
      "evidence": "<one sentence that names something visible in this photograph>"
    }}
  ]
}}

Rules:
- The criteria array contains only the ids listed above, in that order.
- name must be copied exactly from that criterion's name line.
- fit_score is an integer from 1 to 5.
- tone_label uses only words from the target tone list, lowercase and comma-separated. Name the words you actually see. Do not add a tone word that is not on that list.
- evidence must name a visible subject, object, place, or light. Do not invent words, logos, or people that are not in the photograph.
- If the photograph does not fit the target tone, say so with a low score. Do not force a passing judgment.
"""


def criteria_block(criterion_ids: list[str]) -> str:
    lines = []
    for criterion_id in criterion_ids:
        item = CRITERIA[criterion_id]
        lines.append(
            f"- id: {item['id']}\n"
            f"  name: {item['name']}\n"
            f"  definition: {item['definition']}\n"
            f"  required fields: {item['fields']}"
        )
    return "\n".join(lines)


def render_prompt(
    criterion_ids: list[str] | None = None,
    target_tone: str = TARGET_TONE,
) -> str:
    ids = criterion_ids or ["B1"]
    unknown = [item for item in ids if item not in CRITERIA]
    if unknown:
        raise KeyError(f"No VLM criterion named {unknown}. MVP model criteria: {sorted(CRITERIA)}")
    return TEMPLATE.format(
        target_tone=target_tone,
        criteria_block=criteria_block(ids),
    )
