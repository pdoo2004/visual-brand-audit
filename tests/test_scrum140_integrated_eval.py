"""SCRUM-140: integrated CV + VLM scoring on the representative sample set."""

from pathlib import Path

import pytest
from PIL import Image

from brandlens.api.model_client import ModelFailure
from brandlens.config import load_cv_config
from brandlens.pipeline import score_photo
from brandlens.scoring import explained_results
from brandlens.vlm.validate import ParsedCriterion

ROOT = Path(__file__).resolve().parents[1]
SAMPLES = ROOT / "vlm" / "samples"
CONFIG = ROOT / "config" / "brand_standards.json"


class _OkClient:
    def judge(self, request, image_path: Path):
        class _Result:
            criteria = (
                ParsedCriterion(
                    id="B1",
                    name="Tone and approachability",
                    tone_label="casual, lifestyle",
                    tone_words=("casual", "lifestyle"),
                    fit_score=4,
                    evidence="Visible people and warm indoor light.",
                ),
            )

        return _Result()


class _FailClient:
    def judge(self, request, image_path: Path):
        raise ModelFailure("invalid_output", "malformed model JSON", attempts=2)


@pytest.fixture(scope="module")
def configuration():
    return load_cv_config(CONFIG)


def test_integrated_pipeline_scores_sample_with_explanations(configuration):
    path = SAMPLES / "01-coffee-shop.jpg"
    assert path.is_file()
    image = Image.open(path)
    try:
        scored, cv_results, vlm_results = score_photo(image, configuration, _OkClient())
    finally:
        image.close()

    assert cv_results
    assert "tone_approachability" in vlm_results
    assert scored.status in {"scored", "partial"}
    assert scored.overall_score is not None

    criteria, summary = explained_results(scored)
    tone = next(c for c in criteria if c["criterion_id"] == "tone_approachability")
    assert tone["availability"] == "ok"
    assert "casual, lifestyle" in tone["explanation"]
    assert "Overall score" in summary


def test_integrated_pipeline_survives_vlm_failure(configuration):
    path = SAMPLES / "03-neon-city.jpg"
    image = Image.open(path)
    try:
        scored, _, vlm_results = score_photo(image, configuration, _FailClient())
    finally:
        image.close()

    assert vlm_results["tone_approachability"]["ok"] is False
    assert scored.status == "partial"
    tone = next(c for c in scored.criteria if c.criterion_id == "tone_approachability")
    assert tone.availability == "unavailable_needs_review"
    assert scored.overall_score is not None
    _, summary = explained_results(scored)
    assert "Needs review:" in summary
    assert "tone_approachability" in summary
