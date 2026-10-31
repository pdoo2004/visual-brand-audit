"""Tests for POST/GET /api/v1/images/{image_id}/feedback (SCRUM-160 / task 7.8).

Demonstrates: when Agree/Disagree feedback is submitted for a result, it is
validated, stored, and retrievable with the correct image/criterion association.
"""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from brandlens.api import db as database
from brandlens.api.app import create_app
from brandlens.api.config import Settings

CRITERIA = ["exposure_brightness", "contrast"]


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


@pytest.fixture
def seeded(client):
    """A completed job with two scored images; returns (job_id, image_a, image_b)."""
    job_id = str(uuid.uuid4())
    with database.get_conn(client.db_path) as c:
        database.create_job(c, job_id=job_id, rubric_id="default-v1-draft")
        database.insert_job_criteria(c, job_id, CRITERIA)
        ids = []
        for i in range(2):
            img = database.create_image(c, job_id=job_id, ordinal=i, source=f"upload:{i}.png")
            database.save_image_result(
                c, img, status="scored", overall_score=70.0, flagged=False,
                criteria=[
                    {"criterion_id": cid, "score": 70.0, "weight": 0.5, "source": "cv",
                     "explanation": "ok", "availability": "ok"}
                    for cid in CRITERIA
                ],
            )
            ids.append(img)
        database.set_job_status(c, job_id, "completed")
    return job_id, ids[0], ids[1]


def _post(client, image_id, body):
    return client.post(f"/api/v1/images/{image_id}/feedback", json=body)


def test_whole_image_feedback_is_stored_and_returned(client, seeded):
    _, img, _ = seeded
    r = _post(client, img, {"verdict": "agree", "comment": "  looks right  "})
    assert r.status_code == 201
    body = r.json()
    assert body["image_id"] == img and body["criterion_id"] is None
    assert body["verdict"] == "agree" and body["comment"] == "looks right"
    uuid.UUID(body["feedback_id"])
    assert body["created_at"].endswith("Z")

    listed = client.get(f"/api/v1/images/{img}/feedback").json()
    assert [f["feedback_id"] for f in listed] == [body["feedback_id"]]


def test_criterion_feedback_keeps_its_criterion_association(client, seeded):
    _, img, other = seeded
    r = _post(client, img, {"verdict": "disagree", "criterion_id": "contrast"})
    assert r.status_code == 201 and r.json()["criterion_id"] == "contrast"
    assert client.get(f"/api/v1/images/{img}/feedback").json()[0]["criterion_id"] == "contrast"
    assert client.get(f"/api/v1/images/{other}/feedback").json() == []  # not leaked to other image


def test_history_is_kept_newest_first(client, seeded):
    _, img, _ = seeded
    first = _post(client, img, {"verdict": "agree"}).json()
    second = _post(client, img, {"verdict": "disagree"}).json()
    listed = client.get(f"/api/v1/images/{img}/feedback").json()
    assert {f["feedback_id"] for f in listed} == {first["feedback_id"], second["feedback_id"]}
    assert listed[0]["feedback_id"] == second["feedback_id"] or (
        listed[0]["created_at"] == listed[1]["created_at"]  # same-millisecond tie is accepted
    )


def test_feedback_shows_up_in_job_results(client, seeded):
    job_id, img, _ = seeded
    _post(client, img, {"verdict": "disagree", "comment": "too dark"})
    images = client.get(f"/api/v1/jobs/{job_id}/results").json()["images"]
    assert images[0]["feedback"]["verdict"] == "disagree"
    assert images[0]["feedback"]["comment"] == "too dark"
    assert images[1]["feedback"] is None


@pytest.mark.parametrize(
    "body",
    [
        {"verdict": "maybe"},
        {},
        {"verdict": "agree", "comment": "x" * 1001},
        {"verdict": "agree", "unknown_field": 1},
        {"verdict": "agree", "criterion_id": "Not A Slug"},
    ],
)
def test_invalid_payloads_return_422_and_store_nothing(client, seeded, body):
    _, img, _ = seeded
    r = _post(client, img, body)
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "VALIDATION_ERROR"
    assert client.get(f"/api/v1/images/{img}/feedback").json() == []


def test_criterion_the_image_has_no_result_for_is_rejected(client, seeded):
    _, img, _ = seeded
    r = _post(client, img, {"verdict": "agree", "criterion_id": "composition"})
    assert r.status_code == 422 and r.json()["detail"]["code"] == "VALIDATION_ERROR"
    assert client.get(f"/api/v1/images/{img}/feedback").json() == []


@pytest.mark.parametrize("image_id", [str(uuid.uuid4()), "not-a-uuid"])
def test_unknown_or_malformed_image_id_returns_404(client, image_id):
    assert _post(client, image_id, {"verdict": "agree"}).status_code == 404
    assert client.get(f"/api/v1/images/{image_id}/feedback").status_code == 404


def test_blank_comment_is_stored_as_null(client, seeded):
    _, img, _ = seeded
    assert _post(client, img, {"verdict": "agree", "comment": "   "}).json()["comment"] is None
