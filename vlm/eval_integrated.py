"""SCRUM-140: run CV + VLM + scoring + explanations on the review sample set.

Default mode is offline-safe: real CV analysis, mocked VLM success and failure
paths. Pass ``--live`` to call a running ModelClient (Ollama/vLLM).

Writes:
  vlm/results/SCRUM-140_integrated_eval.json
  vlm/results/SCRUM-140_integrated_eval.md

Usage (repo root):
  python vlm/eval_integrated.py
  python vlm/eval_integrated.py --live --base-url http://127.0.0.1:11434/v1 --model gemma4:e4b
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from brandlens.api.model_client import ModelClient, ModelFailure
from brandlens.config import load_cv_config
from brandlens.pipeline import score_photo
from brandlens.scoring import explained_results
from brandlens.vlm.validate import ParsedCriterion

SAMPLES = ROOT / "vlm" / "samples"
CONFIG = ROOT / "config" / "brand_standards.json"
OUT_JSON = ROOT / "vlm" / "results" / "SCRUM-140_integrated_eval.json"
OUT_MD = ROOT / "vlm" / "results" / "SCRUM-140_integrated_eval.md"

# Expected qualitative direction for the locked B1 review set (not hard scores).
EXPECTATIONS = {
    "01-coffee-shop.jpg": {
        "tone_fit": "high",
        "note": "Warm lifestyle / candid coffee scene; should fit Capital One tone list.",
    },
    "02-glass-office.jpg": {
        "tone_fit": "medium",
        "note": "Bright workplace; lifestyle/casual possible; less warm than coffee.",
    },
    "03-neon-city.jpg": {
        "tone_fit": "low",
        "note": "Technical night city, no people; should not read as approachable lifestyle.",
    },
}


class _FakeSuccessClient:
    """Deterministic VLM stand-in for offline integrated runs."""

    def __init__(self, by_file: dict[str, ParsedCriterion]):
        self._by_file = by_file
        self._current: str | None = None

    def set_image(self, name: str) -> None:
        self._current = name

    def judge(self, request, image_path: Path):
        assert self._current is not None
        criterion = self._by_file[self._current]

        class _Result:
            criteria = (criterion,)

        return _Result()


class _FakeFailClient:
    def judge(self, request, image_path: Path):
        raise ModelFailure("timeout", "request timed out", attempts=2)


def _mock_judgments() -> dict[str, ParsedCriterion]:
    return {
        "01-coffee-shop.jpg": ParsedCriterion(
            id="B1",
            name="Tone and approachability",
            tone_label="casual, lifestyle, candid",
            tone_words=("casual", "lifestyle", "candid"),
            fit_score=4,
            evidence="Hands and a latte under warm indoor light.",
        ),
        "02-glass-office.jpg": ParsedCriterion(
            id="B1",
            name="Tone and approachability",
            tone_label="lifestyle, casual, natural",
            tone_words=("lifestyle", "casual", "natural"),
            fit_score=3,
            evidence="A bright open office with one person at a desk.",
        ),
        "03-neon-city.jpg": ParsedCriterion(
            id="B1",
            name="Tone and approachability",
            tone_label="aesthetic, bright",
            tone_words=("aesthetic", "bright"),
            fit_score=2,
            evidence="A night city seen through blue neon mesh with no people.",
        ),
    }


def _run_one(image_path: Path, configuration, client) -> dict:
    image = Image.open(image_path)
    try:
        if hasattr(client, "set_image"):
            client.set_image(image_path.name)
        scored, cv_results, vlm_results = score_photo(image, configuration, client)
    finally:
        image.close()

    criteria, summary = explained_results(scored)
    mismatches: list[str] = []
    expectation = EXPECTATIONS.get(image_path.name, {})
    tone = next((c for c in scored.criteria if c.criterion_id == "tone_approachability"), None)
    if tone is None:
        mismatches.append("tone_approachability missing from scored criteria")
    elif tone.availability != "ok":
        if expectation.get("tone_fit") != "review":
            mismatches.append(
                f"tone unavailable ({tone.availability}): {', '.join(tone.reasons)}"
            )
    else:
        fit = tone.score
        wanted = expectation.get("tone_fit")
        if wanted == "high" and fit is not None and fit < 60:
            mismatches.append(f"expected high tone fit, got score {fit:.0f}")
        if wanted == "low" and fit is not None and fit > 50:
            mismatches.append(f"expected low tone fit, got score {fit:.0f}")
        explanation = next(
            (r["explanation"] for r in criteria if r["criterion_id"] == "tone_approachability"),
            "",
        )
        if tone.label and tone.label not in explanation:
            mismatches.append(
                f"explanation omits structured tone label {tone.label!r}: {explanation}"
            )

    return {
        "file": image_path.name,
        "expectation": expectation,
        "status": scored.status,
        "overall_score": scored.overall_score,
        "flagged": scored.flagged,
        "summary": summary,
        "criteria": criteria,
        "vlm_raw_keys": sorted(vlm_results.keys()),
        "cv_keys": sorted(cv_results.keys()),
        "mismatches": mismatches,
    }


def _write_markdown(payload: dict) -> None:
    lines = [
        "# SCRUM-140 — Integrated VLM/scoring evaluation",
        "",
        f"Generated: `{payload['generated_at']}`",
        f"Mode: `{payload['mode']}`",
        f"Config: `{payload['config']}`",
        "",
        "## Acceptance",
        "",
        "When the integrated pipeline runs on the review set, scoring/explanation",
        "mismatches are documented here. Blocking issues should be filed in Jira",
        "before midterm (SCRUM-140).",
        "",
        "## Review set",
        "",
        "Uses `vlm/samples/` (coffee, office, neon) — same SCRUM-119 benchmark trio.",
        "",
        "## Results",
        "",
    ]
    for row in payload["images"]:
        lines.append(f"### `{row['file']}`")
        lines.append("")
        lines.append(f"- Expectation: {row['expectation'].get('note', '')}")
        lines.append(f"- Status: `{row['status']}` | overall: `{row['overall_score']}` | flagged: `{row['flagged']}`")
        lines.append(f"- Summary: {row['summary']}")
        if row["mismatches"]:
            lines.append("- **Mismatches:**")
            for item in row["mismatches"]:
                lines.append(f"  - {item}")
        else:
            lines.append("- Mismatches: none recorded in this run")
        lines.append("- Criteria:")
        for crit in row["criteria"]:
            lines.append(
                f"  - `{crit['criterion_id']}` ({crit['availability']}, "
                f"score={crit['score']}): {crit['explanation']}"
            )
        lines.append("")

    lines.extend(
        [
            "## Fallback check",
            "",
            payload.get("fallback_note", "Not run."),
            "",
            "## Follow-ups",
            "",
        ]
    )
    for item in payload.get("follow_ups", []):
        lines.append(f"- {item}")
    lines.append("")
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="Call a real ModelClient")
    parser.add_argument("--base-url", default="http://127.0.0.1:11434/v1")
    parser.add_argument("--model", default="gemma4:e4b")
    args = parser.parse_args()

    configuration = load_cv_config(CONFIG)
    files = sorted(SAMPLES.glob("*.jpg"))
    if len(files) < 3:
        raise SystemExit(f"Expected sample jpgs under {SAMPLES}")

    mode = "live" if args.live else "offline-mock"
    client: object
    if args.live:
        client = ModelClient(args.base_url, args.model, timeout_s=90.0, max_retries=1)
    else:
        client = _FakeSuccessClient(_mock_judgments())

    images = []
    try:
        for path in files:
            images.append(_run_one(path, configuration, client))
    finally:
        if args.live:
            client.close()

    # Always exercise SCRUM-139 fallback on coffee once (offline or live).
    fail_client = _FakeFailClient()
    coffee = SAMPLES / "01-coffee-shop.jpg"
    fallback = _run_one(coffee, configuration, fail_client)
    fallback_ok = (
        fallback["status"] == "partial"
        and any(
            c["criterion_id"] == "tone_approachability"
            and c["availability"] == "unavailable_needs_review"
            for c in fallback["criteria"]
        )
        and fallback["overall_score"] is not None
    )

    follow_ups = []
    for row in images:
        for mismatch in row["mismatches"]:
            follow_ups.append(f"{row['file']}: {mismatch}")
    if not fallback_ok:
        follow_ups.append("SCRUM-139 fallback did not produce partial + needs-review on coffee.")
    if not follow_ups:
        follow_ups.append("No blocking mismatches in this run. Re-run with --live before midterm if Ollama/vLLM is up.")

    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "mode": mode,
        "config": str(CONFIG.relative_to(ROOT)),
        "images": images,
        "fallback_coffee": fallback,
        "fallback_note": (
            "Forced ModelFailure on 01-coffee-shop.jpg → "
            + ("PASS: partial CV-only score with tone needs-review." if fallback_ok else "FAIL.")
        ),
        "follow_ups": follow_ups,
    }

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    _write_markdown(payload)
    print(f"Wrote {OUT_JSON.relative_to(ROOT)}")
    print(f"Wrote {OUT_MD.relative_to(ROOT)}")
    for item in follow_ups:
        print(f"- {item}")
    return 0 if fallback_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
