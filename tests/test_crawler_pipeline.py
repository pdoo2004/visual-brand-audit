"""Standalone crawler retains previews even when fetched files are temporary."""

import asyncio
from types import SimpleNamespace

import pytest
from PIL import Image

from brandlens import crawler_pipeline
from brandlens.crawler.discovery import DiscoveryResult
from brandlens.crawler.downloader import DownloadedImage, DownloadResult


def test_temporary_images_preview_scores_and_measurements(tmp_path, monkeypatch):
    requested = []
    temporary_paths = []

    async def discover(url, *, settings=None):
        return DiscoveryResult(["https://cdn.example/photo.png"], [url], [])

    async def download(urls, dest):
        requested.extend(urls)
        dest.mkdir(parents=True, exist_ok=True)
        path = dest / "0000.png"
        temporary_paths.append(path)
        Image.new("RGB", (320, 240), "teal").save(path)
        item = DownloadedImage(urls[0], path, path.stat().st_size)
        return DownloadResult([item], [])

    def score_photo(image, configuration, *, vlm_client=None, criterion_ids=None,
                    subject_detector=None):
        assert image.size == (320, 240)
        assert configuration == ("rubric", "criteria")
        assert criterion_ids == ["contrast"]
        return (SimpleNamespace(overall_score=76.0, criteria=()),
                {"contrast": {"status": "available", "measurements": {"luminance_std": 15.0}}},
                {})

    monkeypatch.setattr(crawler_pipeline, "discover_images", discover)
    monkeypatch.setattr(crawler_pipeline, "download_images", download)
    monkeypatch.setattr(crawler_pipeline, "score_photo", score_photo)

    result = asyncio.run(crawler_pipeline.run_crawler_pipeline(
        "https://site.example/gallery", ("rubric", "criteria"),
        save_images=False, criterion_ids=["contrast"],
    ))

    assert requested == ["https://cdn.example/photo.png"]
    assert len(result.images) == 1
    photo = result.images[0]
    assert photo["path"] is None
    assert photo["preview"].size == (320, 240)
    assert photo["score"].overall_score == 76.0
    assert photo["cv_results"]["contrast"]["measurements"]["luminance_std"] == 15.0
    assert result.download_failures == []
    assert temporary_paths and not temporary_paths[0].exists()
    assert not list(tmp_path.iterdir())
    photo["preview"].close()


def test_save_images_retains_files_and_continues_after_scoring_failure(tmp_path, monkeypatch):
    async def discover(url, *, settings=None):
        return DiscoveryResult(["https://cdn.example/a.png", "https://cdn.example/b.png"], [url], [])

    async def download(urls, dest):
        dest.mkdir(parents=True, exist_ok=True)
        result = []
        for idx, url in enumerate(urls):
            path = dest / f"{idx:04d}.png"
            Image.new("RGB", (320, 240), "teal" if idx == 0 else "blue").save(path)
            result.append(DownloadedImage(url, path, path.stat().st_size))
        return DownloadResult(result, [])

    calls = 0

    def score_photo(image, configuration, *, vlm_client=None, criterion_ids=None,
                    subject_detector=None):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise ValueError("filtered out")
        return SimpleNamespace(overall_score=90.0, criteria=()), {}, {}

    monkeypatch.setattr(crawler_pipeline, "discover_images", discover)
    monkeypatch.setattr(crawler_pipeline, "download_images", download)
    monkeypatch.setattr(crawler_pipeline, "score_photo", score_photo)

    result = asyncio.run(crawler_pipeline.run_crawler_pipeline(
        "https://site.example/gallery", ("rubric", "criteria"),
        save_images=True, output_dir=tmp_path,
    ))

    assert calls == 2
    assert len(result.images) == 2
    assert all(row["path"].exists() for row in result.images)
    assert "filtered out" in result.images[0]["error"]
    assert result.images[0]["preview"] is not None
    assert result.images[1]["score"].overall_score == 90.0
    for row in result.images:
        row["preview"].close()


def test_saving_requires_destination():
    with pytest.raises(ValueError, match="output_dir is required"):
        asyncio.run(crawler_pipeline.run_crawler_pipeline(
            "https://site.example/gallery", ("rubric", "criteria"), save_images=True,
        ))
