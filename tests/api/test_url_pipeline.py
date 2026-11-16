"""SCRUM-240: URL submission reaches the normal worker and results endpoint.

Network discovery/download is replaced with deterministic local fixtures; the
real DB, API routes, job background task, and shared batch worker are exercised.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from brandlens.api import db as database
from brandlens.api import url_worker
from brandlens.api.app import create_app
from brandlens.api.config import Settings
from brandlens.api.worker import ImageAnalysis


@pytest.fixture
def client(tmp_path: Path, monkeypatch):
    settings = Settings(
        db_path=tmp_path / "jobs.db",
        upload_dir=tmp_path / "raw",
        processed_dir=tmp_path / "processed",
        rubric_path=Path("config/brand_standards.json"),
    )

    async def discover(url, *, settings):
        assert settings.max_pages == 1
        return SimpleNamespace(
            image_urls=["https://cdn.example/photo.png"],
            pages_visited=[url],
            failed_pages=[],
        )

    async def download(urls, dest_dir):
        assert urls == ["https://cdn.example/photo.png"]
        dest_dir.mkdir(parents=True, exist_ok=True)
        path = dest_dir / "0000.png"
        Image.new("RGB", (120, 120), "gray").save(path)
        return SimpleNamespace(
            downloaded=[SimpleNamespace(url=urls[0], path=path)], failed=[]
        )

    monkeypatch.setattr(url_worker, "discover_images", discover)
    monkeypatch.setattr(url_worker, "download_images", download)

    app = create_app(settings)
    with TestClient(app) as test_client:
        yield test_client, app, settings


def _submit(client, **extra):
    return client.post(
        "/api/v1/analyses/urls",
        json={
            "url": "https://example.com/gallery",
            "rubric_id": "default-v1-draft",
            "criterion_ids": ["exposure_brightness"],
            "max_pages": 1,
            **extra,
        },
    )


def test_url_job_creates_image_and_real_criterion_result(client):
    http, app, settings = client
    calls = []

    def analyze(image, criteria):
        calls.append((image.mode, list(criteria)))
        return ImageAnalysis(
            status="scored",
            overall_score=76.0,
            flagged=False,
            criteria=[{
                "criterion_id": "exposure_brightness",
                "score": 76.0,
                "weight": 1.0,
                "source": "cv",
                "availability": "ok",
                "explanation": "Exposure is within the test threshold.",
            }],
            measurements={"cv": {"exposure_brightness": {"mean_luminance": 128}}},
        )

    app.state.analyzer = analyze
    response = _submit(http)
    assert response.status_code == 202, response.text
    job_id = response.json()["job_id"]
    assert calls == [("RGB", ["exposure_brightness"])]

    progress = http.get(f"/api/v1/jobs/{job_id}")
    assert progress.status_code == 200
    assert progress.json()["status"] == "completed"
    assert progress.json()["progress"]["images_total"] == 1

    response = http.get(f"/api/v1/jobs/{job_id}/results")
    assert response.status_code == 200, response.text
    images = response.json()["images"]
    assert len(images) == 1
    assert images[0]["overall_score"] == 76.0
    assert images[0]["criteria"][0]["criterion_id"] == "exposure_brightness"
    assert images[0]["criteria"][0]["score"] == 76.0

    with database.get_conn(settings.db_path) as conn:
        raw_rows = database.get_job_images(conn, job_id)
        assert raw_rows[0]["source"] == "https://cdn.example/photo.png"
        assert Path(raw_rows[0]["raw_path"]).is_file()


def test_no_downloadable_image_ends_failed(client, monkeypatch):
    http, _, _ = client

    async def empty_download(urls, dest_dir):
        return SimpleNamespace(downloaded=[], failed=[])

    monkeypatch.setattr(url_worker, "download_images", empty_download)
    response = _submit(http)
    assert response.status_code == 202
    job_id = response.json()["job_id"]
    status = http.get(f"/api/v1/jobs/{job_id}").json()
    assert status["status"] == "failed"
    assert status["progress"]["images_total"] == 0


def test_invalid_criterion_rejected_before_creating_job(client):
    http, _, _ = client
    response = _submit(http, criterion_ids=["not_a_criterion"])
    assert response.status_code == 422


def test_private_url_rejected(client):
    http, _, _ = client
    response = _submit(http, url="http://127.0.0.1/private")
    assert response.status_code == 422


def test_url_job_uses_real_cv_pipeline(client):
    """The URL job can invoke the app's actual PipelineAnalyzer, not just a stub."""
    from brandlens.api.analysis import PipelineAnalyzer
    from brandlens.config import load_cv_config

    http, app, _ = client
    configuration = load_cv_config(
        Path("config/test_config/brand_standards_brightness_contrast_test.json"),
        schema_path=Path("config/brand_standards.schema.json"),
    )
    analyzer = PipelineAnalyzer(configuration)
    app.state.analyzer = analyzer
    response = _submit(http)
    assert response.status_code == 202, response.text
    job_id = response.json()["job_id"]
    results = http.get(f"/api/v1/jobs/{job_id}/results")
    assert results.status_code == 200, results.text
    image = results.json()["images"][0]
    assert image["status"] == "scored"
    assert len(image["criteria"]) == 1
    assert image["criteria"][0]["criterion_id"] == "exposure_brightness"
    assert image["overall_score"] is not None

def test_duplicate_downloads_are_analyzed_once(
    client, monkeypatch
):
    http, app, settings = client
    calls = []

    async def duplicate_download(urls, dest_dir):
        dest_dir.mkdir(parents=True, exist_ok=True)

        items = []
        for index in range(2):
            path = dest_dir / f"{index}.png"

            Image.new(
                "RGB", (120, 120), "gray"
            ).save(path)

            items.append(
                SimpleNamespace(
                    url=f"https://cdn.example/photo{index}.png",
                    path=path,
                )
            )

        return SimpleNamespace(downloaded=items, failed=[])

    monkeypatch.setattr(
        url_worker,
        "download_images",
        duplicate_download,
    )

    def analyze(image, criteria):
        calls.append(1)
        return ImageAnalysis(
            status="scored",
            overall_score=80.0,
            criteria=[],
        )

    app.state.analyzer = analyze

    response = _submit(http)
    assert response.status_code == 202

    job_id = response.json()["job_id"]

    with database.get_conn(settings.db_path) as conn:
        images = database.get_job_images(conn, job_id)

    assert len(images) == 1
    assert len(calls) == 1

def test_oversized_url_image_visible_in_results(client, monkeypatch):
    from brandlens.crawler.downloader import DownloadCode, DownloadFailure

    http, app, _ = client
    analyzed = []

    async def download_with_oversized_image(urls, dest_dir):
        dest_dir.mkdir(parents=True, exist_ok=True)

        path = dest_dir / "small.png"
        Image.new("RGB", (120, 120), "green").save(path)

        return SimpleNamespace(
            downloaded=[
                SimpleNamespace(
                    url="https://cdn.example/small.png",
                    path=path,
                )
            ],
            failed=[
                DownloadFailure(
                    url="https://cdn.example/large.png",
                    code=DownloadCode.TOO_LARGE,
                    message="Image exceeds the 10485760 byte limit.",
                )
            ],
        )

    monkeypatch.setattr(
        url_worker, "download_images", download_with_oversized_image
    )

    def analyze(image, criteria):
        analyzed.append(1)
        return ImageAnalysis(
            status="scored",
            overall_score=85.0,
            criteria=[],
        )

    app.state.analyzer = analyze

    response = _submit(http)
    assert response.status_code == 202
    job_id = response.json()["job_id"]

    progress = http.get(f"/api/v1/jobs/{job_id}").json()
    assert progress["status"] == "completed_with_errors"
    assert progress["progress"]["images_total"] == 2
    assert progress["progress"]["images_failed"] == 1

    results = http.get(f"/api/v1/jobs/{job_id}/results")
    assert results.status_code == 200

    images = results.json()["images"]
    assert len(images) == 2
    assert len(analyzed) == 1

    assert images[0]["status"] == "scored"
    assert images[0]["overall_score"] == 85.0

    assert images[1]["status"] == "failed"
    assert images[1]["source"] == "https://cdn.example/large.png"
    assert images[1]["error_code"] == "FILE_TOO_LARGE"
    assert "10 MB" in images[1]["error_message"]
    assert images[1]["overall_score"] is None

def test_all_oversized_url_images_remain_visible(client, monkeypatch):
    from brandlens.crawler.downloader import DownloadCode, DownloadFailure

    http, _, _ = client

    async def download_only_oversized(urls, dest_dir):
        return SimpleNamespace(
            downloaded=[],
            failed=[
                DownloadFailure(
                    url="https://cdn.example/large.png",
                    code=DownloadCode.TOO_LARGE,
                    message="Image exceeds the 10485760 byte limit.",
                )
            ],
        )

    monkeypatch.setattr(
        url_worker, "download_images", download_only_oversized
    )

    response = _submit(http)
    assert response.status_code == 202
    job_id = response.json()["job_id"]

    progress = http.get(f"/api/v1/jobs/{job_id}").json()
    assert progress["status"] == "failed"
    assert progress["progress"]["images_total"] == 1
    assert progress["progress"]["images_failed"] == 1

    results = http.get(f"/api/v1/jobs/{job_id}/results")
    assert results.status_code == 200

    images = results.json()["images"]
    assert len(images) == 1
    assert images[0]["status"] == "failed"
    assert images[0]["error_code"] == "FILE_TOO_LARGE"
    assert "10 MB" in images[0]["error_message"]