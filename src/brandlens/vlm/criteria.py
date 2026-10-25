"""Rubric fields the vision-language model is allowed to score.

The locked MVP sends only B1. Q1-Q5 are computer-vision measurements.
"""

from __future__ import annotations

# Capital One recommendation, 11 October 2026. A photograph fits when it
# belongs in this set. It does not have to show every word.
RECOMMENDED_TONES = (
    "authentic",
    "aesthetic",
    "carefree",
    "bright",
    "boho",
    "natural",
    "genuine",
    "family",
    "premium",
    "minimalist",
    "lifestyle",
    "casual",
    "candid",
)

TARGET_TONE = ", ".join(RECOMMENDED_TONES)

CRITERIA = {
    "B1": {
        "id": "B1",
        "name": "Tone and approachability",
        "definition": (
            "The photograph fits the target tone stored in the rubric, "
            "and the judgment cites something visible."
        ),
        "fields": (
            "tone_label (words from the target tone list), "
            "fit_score (integer 1-5), evidence (one sentence)"
        ),
    }
}
