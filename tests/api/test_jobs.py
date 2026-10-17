"""Integration tests for the upload and job-status endpoints (task 7.3).

Demonstrates: when an analysis request is accepted, processing continues
asynchronously (BackgroundTasks run inline in TestClient) and a job_id can be
used to query progress.
"""

from __future__ import annotations

import io
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from brandlens.api.app import create_app
from brandlens.api.config import Settings

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def client(tmp_path: Path):
    """TestClient with a fresh isolated database and upload directories."""
    settings = Settings(
        db_path=tmp_path / "test.db",
        upload_dir=tmp_path / "raw",
        processed_dir=tmp_path / "processed",
        rubric_path=Path("config/brand_standards.json"),
    )
    with TestClient(create_app(settings)) as c:
        yield c


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _png_bytes(width: int = 100, height: int = 100) -> bytes:
    """Return bytes of a plain PNG that passes the photo filter."""
    img = Image.new("RGB", (width, height), (128, 128, 128))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _upload(client: TestClient, *, n: int = 1, rubric_id: str = "default-v1-draft"):
    files = [("files", (f"img{i}.png", _png_bytes(), "image/png")) for i in range(n)]
    return client.post(
        "/api/v1/analyses/uploads",
        data={"rubric_id": rubric_id},
        files=files,
    )


# ---------------------------------------------------------------------------
# Submission
# ---------------------------------------------------------------------------

def test_submit_returns_202_with_job_id(client):
    r = _upload(client)
    assert r.status_code == 202
    body = r.json()
    assert body["status"] == "queued"
    assert "job_id" in body
    assert body["status_url"] == f"/api/v1/jobs/{body['job_id']}"
    assert body["input_type"] == "upload"


def test_submit_multiple_files(client):
    r = _upload(client, n=3)
    assert r.status_code == 202


def test_submit_with_criterion_subset(client):
    files = [("files", ("img.png", _png_bytes(), "image/png"))]
    r = client.post(
        "/api/v1/analyses/uploads",
        data={
            "rubric_id": "default-v1-draft",
            "criterion_ids": ["exposure_brightness", "contrast"],
        },
        files=files,
    )
    assert r.status_code == 202


def test_submit_rejects_missing_files(client):
    r = client.post(
        "/api/v1/analyses/uploads",
        data={"rubric_id": "default-v1-draft"},
    )
    assert r.status_code == 422


def test_submit_rejects_unsupported_content_type(client):
    r = client.post(
        "/api/v1/analyses/uploads",
        data={"rubric_id": "default-v1-draft"},
        files=[("files", ("logo.gif", b"GIF89a", "image/gif"))],
    )
    assert r.status_code == 422


def test_submit_rejects_bad_rubric_slug(client):
    r = client.post(
        "/api/v1/analyses/uploads",
        data={"rubric_id": "NOT A VALID SLUG"},
        files=[("files", ("img.png", _png_bytes(), "image/png"))],
    )
    assert r.status_code == 422


def test_submit_rejects_unknown_rubric(client):
    r = client.post(
        "/api/v1/analyses/uploads",
        data={"rubric_id": "unknown-rubric"},
        files=[("files", ("img.png", _png_bytes(), "image/png"))],
    )
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# Status polling
# ---------------------------------------------------------------------------

def test_poll_returns_job_status_with_progress(client):
    submit = _upload(client, n=2)
    job_id = submit.json()["job_id"]

    r = client.get(f"/api/v1/jobs/{job_id}")
    assert r.status_code == 200
    body = r.json()
    assert body["job_id"] == job_id
    assert "status" in body
    assert body["progress"]["images_total"] == 2


def test_poll_unknown_job_returns_404(client):
    r = client.get(f"/api/v1/jobs/{uuid.uuid4()}")
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "NOT_FOUND"


def test_poll_invalid_uuid_returns_404(client):
    r = client.get("/api/v1/jobs/not-a-uuid")
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Async execution (BackgroundTasks run synchronously inside TestClient)
# ---------------------------------------------------------------------------

def test_background_worker_completes_job(client):
    """Submit → background task processes images → job reaches a terminal state."""
    submit = _upload(client, n=1)
    job_id = submit.json()["job_id"]

    poll = client.get(f"/api/v1/jobs/{job_id}")
    body = poll.json()
    assert body["status"] in ("completed", "completed_with_errors")
    assert body["progress"]["images_done"] == 1
    assert body["progress"]["images_failed"] == 0


def test_background_worker_counts_filtered_images(client):
    """An image too small to pass the filter is marked filtered_out (counts as done)."""
    tiny = _png_bytes(width=10, height=10)  # below FilterSettings.min_short_side=64
    r = client.post(
        "/api/v1/analyses/uploads",
        data={"rubric_id": "default-v1-draft"},
        files=[("files", ("tiny.png", tiny, "image/png"))],
    )
    job_id = r.json()["job_id"]

    poll = client.get(f"/api/v1/jobs/{job_id}")
    body = poll.json()
    assert body["status"] in ("completed", "completed_with_errors")
    assert body["progress"]["images_done"] == 1
    assert body["progress"]["images_failed"] == 0


def test_processed_file_is_written_to_disk(client, tmp_path):
    """The worker saves a standardized PNG for each image that passes the filter."""
    _upload(client, n=1)
    processed = list((tmp_path / "processed").rglob("*.png"))
    assert len(processed) == 1


def test_two_jobs_are_independent(client):
    """Each job gets its own job_id and separate progress counter."""
    id_a = _upload(client, n=1).json()["job_id"]
    id_b = _upload(client, n=2).json()["job_id"]
    assert id_a != id_b

    body_a = client.get(f"/api/v1/jobs/{id_a}").json()
    body_b = client.get(f"/api/v1/jobs/{id_b}").json()
    assert body_a["progress"]["images_total"] == 1
    assert body_b["progress"]["images_total"] == 2
