"""Input validation and upload-security limits (SCRUM-161 / task 7.9).

Every request here must be refused *before* a job exists, so each test also checks that
no job or upload directory was created.
"""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from brandlens.api.app import create_app
from brandlens.api.config import Settings

RUBRIC = Path("config/brand_standards.json")
RUBRIC_ID = json.loads(RUBRIC.read_text())["rubric_id"]
REAL_CRITERION = json.loads(RUBRIC.read_text())["criteria"][0]["criterion_id"]


def _png(width: int = 100, height: int = 100) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (width, height), (128, 128, 128)).save(buf, format="PNG")
    return buf.getvalue()


def _make_client(tmp_path: Path, **limits) -> TestClient:
    settings = Settings(
        db_path=tmp_path / "test.db",
        upload_dir=tmp_path / "raw",
        processed_dir=tmp_path / "processed",
        rubric_path=RUBRIC,
        **limits,
    )
    return TestClient(create_app(settings))


@pytest.fixture
def client(tmp_path: Path):
    with _make_client(tmp_path) as c:
        yield c


def _post(client: TestClient, files, **data):
    data.setdefault("rubric_id", RUBRIC_ID)
    return client.post("/api/v1/analyses/uploads", files=files, data=data)


def _one_png(name: str = "a.png"):
    return [("files", (name, _png(), "image/png"))]


def _no_job_created(tmp_path: Path) -> bool:
    raw = tmp_path / "raw"
    return not raw.exists() or not any(raw.iterdir())


# --- rubric and criteria are validated for uploads (gap 1) -----------------------------

def test_unknown_rubric_with_criteria_subset_is_rejected(client, tmp_path):
    r = _post(client, _one_png(), rubric_id="does-not-exist", criterion_ids=[REAL_CRITERION])
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "VALIDATION_ERROR"
    assert _no_job_created(tmp_path)


def test_unknown_criterion_is_rejected(client, tmp_path):
    r = _post(client, _one_png(), criterion_ids=["bogus-criterion"])
    assert r.status_code == 422
    assert "bogus-criterion" in r.json()["detail"]["message"]
    assert _no_job_created(tmp_path)


def test_valid_criteria_subset_is_still_accepted(client):
    r = _post(client, _one_png(), criterion_ids=[REAL_CRITERION])
    assert r.status_code == 202


# --- file count and total size (gap 2) --------------------------------------------------

def test_too_many_files_is_rejected(tmp_path):
    with _make_client(tmp_path, max_files_per_request=3) as c:
        files = [("files", (f"{i}.png", _png(), "image/png")) for i in range(4)]
        r = _post(c, files)
        assert r.status_code == 422
        assert "Too many files" in r.json()["detail"]["message"]
        assert _no_job_created(tmp_path)


def test_exactly_the_file_limit_is_accepted(tmp_path):
    with _make_client(tmp_path, max_files_per_request=3) as c:
        files = [("files", (f"{i}.png", _png(), "image/png")) for i in range(3)]
        assert _post(c, files).status_code == 202


def test_total_size_over_limit_is_rejected_while_reading(tmp_path):
    png = _png()
    # Each file passes the per-file cap, but together they pass the total cap.
    with _make_client(
        tmp_path, max_file_bytes=len(png) * 2, max_total_bytes=len(png) * 2 + 10
    ) as c:
        files = [("files", (f"{i}.png", png, "image/png")) for i in range(3)]
        r = _post(c, files)
        assert r.status_code == 413
        assert r.json()["detail"]["code"] == "FILE_TOO_LARGE"
        assert _no_job_created(tmp_path)


def test_declared_content_length_over_limit_is_refused_before_parsing(tmp_path):
    with _make_client(tmp_path, max_file_bytes=1024, max_total_bytes=1024) as c:
        r = c.post(
            "/api/v1/analyses/uploads",
            content=b"x",
            headers={
                "content-type": "multipart/form-data; boundary=x",
                "content-length": str(10 * 1024 * 1024),
            },
        )
        assert r.status_code == 413
        assert r.json()["detail"]["code"] == "FILE_TOO_LARGE"


def test_per_file_limit_is_ten_mb_by_default(client):
    assert client.app.state.settings.max_file_bytes == 10 * 1024 * 1024


def test_file_over_per_file_limit_is_reported(tmp_path):
    png = _png()
    with _make_client(tmp_path, max_file_bytes=len(png) - 1, max_total_bytes=10 * len(png)) as c:
        r = _post(c, _one_png())
        assert r.status_code == 413
        assert "per-file limit" in r.json()["detail"]["message"]


# --- image dimensions (gap 3) -----------------------------------------------------------

def _huge_canvas_png() -> bytes:
    buf = io.BytesIO()
    Image.new("1", (20000, 20000)).save(buf, format="PNG")  # ~48 KB, 400 megapixels
    return buf.getvalue()


def test_huge_canvas_image_is_rejected_at_upload_not_in_worker(client, tmp_path):
    r = _post(client, [("files", ("bomb.png", _huge_canvas_png(), "image/png"))])
    assert r.status_code == 422
    assert "pixels" in r.json()["detail"]["message"]
    assert _no_job_created(tmp_path)


def test_pixel_limit_rejects_only_the_oversized_file_in_a_mixed_batch(tmp_path):
    with _make_client(tmp_path, max_image_pixels=200 * 200) as c:
        files = [
            ("files", ("ok.png", _png(100, 100), "image/png")),
            ("files", ("big.png", _png(300, 300), "image/png")),
        ]
        r = _post(c, files)
        assert r.status_code == 202
        rejected = r.json()["rejected"]
        assert [x["filename"] for x in rejected] == ["big.png"]


def test_corrupt_image_with_valid_header_is_left_to_the_worker(client):
    corrupt = b"\x89PNG\r\n\x1a\n" + b"not really a png"
    r = _post(client, [("files", ("bad.png", corrupt, "image/png"))])
    assert r.status_code == 202  # failed per image later, as before


# --- error messages do not leak server paths (gap 5) -----------------------------------

def test_unreadable_rubric_does_not_leak_the_path(tmp_path):
    missing = tmp_path / "secret-dir" / "rubric.json"
    settings = Settings(
        db_path=tmp_path / "t.db",
        upload_dir=tmp_path / "raw",
        processed_dir=tmp_path / "p",
        rubric_path=missing,
    )
    with TestClient(create_app(settings)) as c:
        r = _post(c, _one_png())
        assert r.status_code == 500
        assert "secret-dir" not in r.text


# --- settings from the environment ------------------------------------------------------

def test_defaults():
    s = Settings()
    assert (s.max_file_bytes, s.max_files_per_request) == (10 * 1024 * 1024, 20)
    assert (s.max_total_bytes, s.max_image_pixels) == (100 * 1024 * 1024, 25_000_000)


def test_limits_come_from_environment(monkeypatch):
    monkeypatch.setenv("BRANDLENS_MAX_FILE_BYTES", "2048")
    monkeypatch.setenv("BRANDLENS_MAX_FILES_PER_REQUEST", "5")
    monkeypatch.setenv("BRANDLENS_MAX_TOTAL_BYTES", "8192")
    monkeypatch.setenv("BRANDLENS_MAX_IMAGE_PIXELS", "1000000")
    s = Settings.from_env()
    assert (s.max_file_bytes, s.max_files_per_request) == (2048, 5)
    assert (s.max_total_bytes, s.max_image_pixels) == (8192, 1_000_000)


@pytest.mark.parametrize("name", [
    "max_file_bytes", "max_files_per_request", "max_total_bytes", "max_image_pixels",
])
def test_non_positive_limits_fail_at_startup(name):
    with pytest.raises(ValueError, match=name):
        Settings(**{name: 0})


def test_total_limit_below_file_limit_fails_at_startup():
    with pytest.raises(ValueError, match="max_total_bytes"):
        Settings(max_file_bytes=1000, max_total_bytes=999)
