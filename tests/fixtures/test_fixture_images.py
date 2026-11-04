"""Verifies that every manifest entry loads as a valid RGB image."""

import json
from pathlib import Path

import pytest
from PIL import Image

from brandlens.preprocessing.photo_filter import FilterSettings, filter_photo

FIXTURES_DIR = Path(__file__).parent / "images"
MANIFEST = json.loads((FIXTURES_DIR / "manifest.json").read_text())

_scoreable = [e for e in MANIFEST["images"] if e.get("filter_result") != "rejected"]
_rejected  = [e for e in MANIFEST["images"] if e.get("filter_result") == "rejected"]


@pytest.mark.parametrize("entry", MANIFEST["images"], ids=lambda e: e["file"])
def test_image_loads_as_rgb(entry):
    path = FIXTURES_DIR / entry["file"]
    assert path.exists(), f"{entry['file']} missing from fixtures directory"
    with Image.open(path) as img:
        img.verify()
    with Image.open(path) as img:
        rgb = img.convert("RGB")
        assert rgb.size[0] > 0 and rgb.size[1] > 0


def test_ten_scoreable_images():
    assert len(_scoreable) == 10, f"Expected 10 scoreable images, got {len(_scoreable)}"


def test_manifest_covers_all_criteria():
    required = {"brightness", "contrast", "color_palette", "subject_framing", "subject_sharpness", "tone"}
    for entry in _scoreable:
        missing = required - entry["expected"].keys()
        assert not missing, f"{entry['file']} manifest entry missing criteria: {missing}"


def test_dataset_has_pass_and_fail_for_each_criterion():
    """Every criterion must have at least one expected pass and one expected fail."""
    for criterion in MANIFEST["criteria"]:
        verdicts = [e["expected"][criterion] for e in _scoreable]
        assert "pass" in verdicts, f"No passing image for criterion '{criterion}'"
        assert "fail" in verdicts, f"No failing image for criterion '{criterion}'"


@pytest.mark.parametrize("entry", _rejected, ids=lambda e: e["file"])
def test_filter_rejects_unsupported_images(entry):
    """Unsupported images (too small, wrong aspect ratio) must be rejected by filter_photo."""
    path = FIXTURES_DIR / entry["file"]
    with Image.open(path) as img:
        result = filter_photo(img, FilterSettings())
    assert result is None, f"{entry['file']} should be rejected but filter_photo returned an image"
