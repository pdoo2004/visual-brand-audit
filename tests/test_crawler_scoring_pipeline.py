"""Verify the adapter uses the real BrandLens score_photo without reimplementing it."""

import asyncio
from pathlib import Path

from PIL import Image, ImageDraw

import brandlens.crawler_pipeline as crawler_pipeline
from brandlens.config import load_cv_config
from brandlens.crawler.discovery import DiscoveryResult
from brandlens.crawler.downloader import DownloadResult, DownloadedImage

ROOT = Path(__file__).resolve().parents[1]
RUBRIC = ROOT / "config" / "test_config" / "brand_standards_brightness_contrast_test.json"


def test_actual_cv_scores_include_all_measurements(tmp_path, monkeypatch):
    async def discover(url, *, settings=None):
        return DiscoveryResult(["https://cdn.example/photo.png"], [url], [])

    async def download(urls, dest):
        dest.mkdir(parents=True, exist_ok=True)
        image = Image.new("RGB", (320, 240), "#446680")
        draw = ImageDraw.Draw(image)
        draw.rectangle((0, 130, 319, 239), fill="#ddcc88")
        draw.ellipse((80, 40, 210, 190), fill="#c93431")
        path = dest / "0000.png"
        image.save(path)
        return DownloadResult([DownloadedImage(urls[0], path, path.stat().st_size)], [])

    monkeypatch.setattr(crawler_pipeline, "discover_images", discover)
    monkeypatch.setattr(crawler_pipeline, "download_images", download)

    result = asyncio.run(crawler_pipeline.run_crawler_pipeline(
        "https://site.example/gallery", load_cv_config(RUBRIC), save_images=False,
    ))

    assert len(result.images) == 1
    photo = result.images[0]
    assert photo["error"] is None
    assert photo["path"] is None
    assert photo["preview"] is not None
    assert photo["score"].overall_score is not None
    assert {c.criterion_id for c in photo["score"].criteria} == {
        "exposure_brightness", "contrast",
    }
    assert "mean_luminance" in photo["cv_results"]["exposure_brightness"]["measurements"]
    assert "luminance_std" in photo["cv_results"]["contrast"]["measurements"]
    photo["preview"].close()
