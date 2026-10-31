"""Shared pytest fixtures for the BrandLens test suite."""

import json
from pathlib import Path

import pytest
from PIL import Image

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "images"
MANIFEST = json.loads((FIXTURES_DIR / "manifest.json").read_text())


def _load(filename: str) -> Image.Image:
    return Image.open(FIXTURES_DIR / filename).convert("RGB")


@pytest.fixture(scope="session")
def fixture_images() -> dict[str, Image.Image]:
    """All 9 representative images, keyed by filename stem (e.g. '01-coffee-shop')."""
    images = {
        Path(entry["file"]).stem: _load(entry["file"])
        for entry in MANIFEST["images"]
    }
    yield images
    for img in images.values():
        img.close()


@pytest.fixture(scope="session")
def fixture_manifest() -> list[dict]:
    """The parsed manifest entries, useful for parametrized expectation tests."""
    return MANIFEST["images"]


# ── Convenience fixtures for individual images ────────────────────────────────

@pytest.fixture(scope="session")
def img_coffee_shop():
    img = _load("01-coffee-shop.jpg")
    yield img
    img.close()


@pytest.fixture(scope="session")
def img_glass_office():
    img = _load("02-glass-office.jpg")
    yield img
    img.close()


@pytest.fixture(scope="session")
def img_neon_city():
    img = _load("03-neon-city.jpg")
    yield img
    img.close()


@pytest.fixture(scope="session")
def img_dim_portrait():
    img = _load("04-dim-portrait.jpg")
    yield img
    img.close()


@pytest.fixture(scope="session")
def img_overexposed():
    img = _load("05-overexposed-sunlight.jpg")
    yield img
    img.close()


@pytest.fixture(scope="session")
def img_foggy():
    img = _load("06-foggy-low-contrast.jpg")
    yield img
    img.close()


@pytest.fixture(scope="session")
def img_cold_blue_office():
    img = _load("07-cold-blue-office.jpg")
    yield img
    img.close()


@pytest.fixture(scope="session")
def img_motion_blur():
    img = _load("08-motion-blur.jpg")
    yield img
    img.close()


@pytest.fixture(scope="session")
def img_tight_crop():
    img = _load("09-tight-crop.jpg")
    yield img
    img.close()


@pytest.fixture(scope="session")
def img_too_small():
    img = _load("10-too-small.jpg")
    yield img
    img.close()


@pytest.fixture(scope="session")
def img_banner_strip():
    img = _load("11-banner-strip.jpg")
    yield img
    img.close()
