"""Tests for POST /api/v1/analyses/urls (SCRUM-178)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from brandlens.api.app import create_app
from brandlens.api.config import Settings

URLS = "/api/v1/analyses/urls"
RUBRIC = "default-v1-draft"


@pytest.fixture
def client(tmp_path: Path):
    settings = Settings(
        db_path=tmp_path / "test.db",
        upload_dir=tmp_path / "raw",
        processed_dir=tmp_path / "processed",
        rubric_path=Path("config/brand_standards.json"),
    )
    with TestClient(create_app(settings)) as c:
        c.db_path = settings.db_path
        yield c


def _post(client, **body):
    body.setdefault("rubric_id", RUBRIC)
    return client.post(URLS, json=body)


def test_valid_url_creates_queued_job(client):
    r = _post(client, url="https://www.capitalone.com/", max_pages=10)
    assert r.status_code == 202
    body = r.json()
    assert body["status"] == "queued" and body["input_type"] == "url"
    assert body["status_url"] == f"/api/v1/jobs/{body['job_id']}"

    row = sqlite3.connect(client.db_path).execute(
        "SELECT input_type, submission_url, max_pages, status FROM jobs WHERE job_id = ?",
        (body["job_id"],),
    ).fetchone()
    assert row == ("url", "https://www.capitalone.com/", 10, "queued")


def test_job_is_pollable(client):
    job = _post(client, url="https://example.com/page").json()
    status = client.get(job["status_url"])
    assert status.status_code == 200 and status.json()["status"] == "queued"


def test_max_pages_is_optional(client):
    assert _post(client, url="https://example.com").status_code == 202


def test_all_rubric_criteria_stored_by_default(client):
    job_id = _post(client, url="https://example.com").json()["job_id"]
    n = sqlite3.connect(client.db_path).execute(
        "SELECT COUNT(*) FROM job_criteria WHERE job_id = ?", (job_id,)
    ).fetchone()[0]
    assert n >= 1


def test_criterion_subset_is_stored(client):
    import json

    first = json.loads(Path("config/brand_standards.json").read_text())["criteria"][0]["criterion_id"]
    job_id = _post(client, url="https://example.com", criterion_ids=[first]).json()["job_id"]
    rows = sqlite3.connect(client.db_path).execute(
        "SELECT criterion_id FROM job_criteria WHERE job_id = ?", (job_id,)
    ).fetchall()
    assert rows == [(first,)]


@pytest.mark.parametrize("bad_url", [
    "not a url", "example.com", "ftp://example.com/file", "javascript:alert(1)", "", "https://",
])
def test_invalid_urls_are_rejected(client, bad_url):
    r = _post(client, url=bad_url)
    assert r.status_code == 422 and r.json()["detail"]["code"] == "VALIDATION_ERROR"


@pytest.mark.parametrize("private_url", [
    "http://localhost:8000/", "http://127.0.0.1/", "http://10.0.0.5/", "http://192.168.1.1/",
    "http://169.254.169.254/latest/meta-data/", "http://[::1]/", "http://intranet/",
    "http://printer.local/", "http://user:pass@example.com/",
])
def test_non_public_urls_are_rejected(client, private_url):
    r = _post(client, url=private_url)
    assert r.status_code == 422 and r.json()["detail"]["code"] == "VALIDATION_ERROR"


@pytest.mark.parametrize("pages", [0, -1, 51, 1000])
def test_max_pages_out_of_range_is_rejected(client, pages):
    assert _post(client, url="https://example.com", max_pages=pages).status_code == 422


def test_rejected_submissions_create_no_job(client):
    _post(client, url="http://localhost/")
    count = sqlite3.connect(client.db_path).execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
    assert count == 0


def test_unknown_rubric_is_rejected(client):
    assert _post(client, url="https://example.com", rubric_id="nope-v9").status_code == 422


def test_missing_url_and_extra_fields_are_rejected(client):
    assert client.post(URLS, json={"rubric_id": RUBRIC}).status_code == 422
    assert _post(client, url="https://example.com", crawl_depth=3).status_code == 422
