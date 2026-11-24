"""Tests for GET /api/v1/images/{image_id}/file."""

from __future__ import annotations

import io
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from brandlens.api import db as database
from brandlens.api.app import create_app
from brandlens.api.config import Settings


def _png_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), (20, 40, 60)).save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture
def client(tmp_path: Path):
    settings = Settings(
        db_path=tmp_path / "test.db",
        upload_dir=tmp_path / "raw",
        processed_dir=tmp_path / "processed",
        rubric_path=Path("config/brand_standards.json"),
    )
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    with TestClient(create_app(settings)) as c:
        c.db_path = settings.db_path
        c.upload_dir = settings.upload_dir
        yield c


def test_image_file_is_served(client):
    job_id = str(uuid.uuid4())
    payload = _png_bytes()
    file_path = client.upload_dir / "shot.png"
    file_path.write_bytes(payload)
    with database.get_conn(client.db_path) as conn:
        database.create_job(conn, job_id=job_id, rubric_id="default-v1-draft")
        image_id = database.create_image(
            conn,
            job_id=job_id,
            ordinal=0,
            source="upload:shot.png",
            raw_path=str(file_path),
        )

    response = client.get(f"/api/v1/images/{image_id}/file")
    assert response.status_code == 200
    assert response.content == payload
    assert "image/png" in response.headers["content-type"]


def test_unknown_image_is_404(client):
    response = client.get(f"/api/v1/images/{uuid.uuid4()}/file")
    assert response.status_code == 404


def test_missing_raw_path_is_404(client):
    job_id = str(uuid.uuid4())
    with database.get_conn(client.db_path) as conn:
        database.create_job(conn, job_id=job_id, rubric_id="default-v1-draft")
        image_id = database.create_image(
            conn, job_id=job_id, ordinal=0, source="upload:x.jpg", raw_path=None
        )
    assert client.get(f"/api/v1/images/{image_id}/file").status_code == 404
