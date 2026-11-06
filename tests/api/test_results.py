"""Tests for GET /api/v1/jobs/{job_id}/results (SCRUM-159 / task 7.7a).

Demonstrates: when a completed job ID is requested, the backend returns the
stored image-level and criterion-level result structure the results UI needs.
"""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from brandlens.api import db as database
from brandlens.api.app import create_app
from brandlens.api.config import Settings
from brandlens.api.schemas import JobResults

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


def _crit(cid: str, score: float | None, weight: float = 0.5) -> dict:
    return {
        "criterion_id": cid,
        "score": score,
        "weight": weight,
        "source": "cv",
        "label": None,
        "explanation": f"{cid} explanation" if score is not None else None,
        "evidence": ["obs"] if score is not None else [],
        "availability": "ok" if score is not None else "unavailable_needs_review",
    }


def _seed(client, *, status: str = "completed") -> tuple[str, dict[str, str]]:
    """A finished job with one scored, one partial/flagged, one filtered, one failed image."""
    job_id = str(uuid.uuid4())
    with database.get_conn(client.db_path) as c:
        database.create_job(c, job_id=job_id, rubric_id="default-v1-draft")
        database.insert_job_criteria(c, job_id, CRITERIA)
        ids = {
            name: database.create_image(c, job_id=job_id, ordinal=i, source=f"upload:{name}.png")
            for i, name in enumerate(["good", "partial", "small", "broken"])
        }
        database.save_image_result(
            c, ids["good"], status="scored", overall_score=90.0, flagged=False,
            measurements={"mean_luminance": 120.0},
            criteria=[_crit("exposure_brightness", 95.0), _crit("contrast", 85.0)],
        )
        database.save_image_result(
            c, ids["partial"], status="partial", overall_score=40.0, flagged=True,
            criteria=[_crit("exposure_brightness", 40.0, 1.0), _crit("contrast", None, 0.0)],
        )
        database.save_image_result(c, ids["small"], status="filtered_out", reject_reason="too_small")
        database.save_image_result(c, ids["broken"], status="failed", error_code="LOAD_ERROR")
        database.set_job_status(c, job_id, status)
    return job_id, ids


def test_completed_job_returns_images_criteria_and_summary(client):
    job_id, ids = _seed(client, status="completed_with_errors")
    r = client.get(f"/api/v1/jobs/{job_id}/results")
    assert r.status_code == 200
    body = JobResults.model_validate(r.json())  # response honours the contract schema

    assert body.rubric_id == "default-v1-draft"
    assert [i.source for i in body.images] == [
        "upload:good.png", "upload:partial.png", "upload:small.png", "upload:broken.png",
    ]
    good = body.images[0]
    assert str(good.image_id) == ids["good"] and good.overall_score == 90.0
    assert good.measurements == {"mean_luminance": 120.0}
    assert [c.criterion_id for c in good.criteria] == CRITERIA
    assert good.criteria[0].explanation == "exposure_brightness explanation"
    assert good.criteria[0].evidence == ["obs"]

    partial = body.images[1]
    assert partial.flagged and partial.criteria[1].availability == "unavailable_needs_review"
    assert partial.criteria[1].score is None

    assert body.images[2].status == "filtered_out" and body.images[2].reject_reason == "too_small"
    assert body.images[3].status == "failed" and body.images[3].criteria == []


def test_summary_is_derived_from_the_stored_rows(client):
    job_id, _ = _seed(client)
    s = client.get(f"/api/v1/jobs/{job_id}/results").json()["summary"]
    assert s["images_scored"] == 2
    assert s["mean_overall"] == 65.0
    assert s["flagged_count"] == 1
    assert {b["bucket"]: b["count"] for b in s["score_distribution"]} == {
        "0-20": 0, "20-40": 0, "40-60": 1, "60-80": 0, "80-100": 1,
    }


def test_score_of_exactly_100_lands_in_the_top_bucket(client):
    job_id = str(uuid.uuid4())
    with database.get_conn(client.db_path) as c:
        database.create_job(c, job_id=job_id, rubric_id="default-v1-draft")
        database.insert_job_criteria(c, job_id, CRITERIA)
        img = database.create_image(c, job_id=job_id, ordinal=0, source="upload:a.png")
        database.save_image_result(c, img, status="scored", overall_score=100.0, flagged=False)
        database.set_job_status(c, job_id, "completed")
    dist = client.get(f"/api/v1/jobs/{job_id}/results").json()["summary"]["score_distribution"]
    assert dist[-1] == {"bucket": "80-100", "count": 1}


def test_job_with_no_scored_images_has_null_mean(client):
    job_id = str(uuid.uuid4())
    with database.get_conn(client.db_path) as c:
        database.create_job(c, job_id=job_id, rubric_id="default-v1-draft")
        database.insert_job_criteria(c, job_id, CRITERIA)
        database.set_job_status(c, job_id, "failed", error_code="INTERNAL_ERROR", error_message="x")
    r = client.get(f"/api/v1/jobs/{job_id}/results")
    assert r.status_code == 200
    assert r.json()["summary"]["mean_overall"] is None and r.json()["images"] == []


def test_unfinished_image_in_a_failed_job_is_reported_as_failed(client):
    job_id = str(uuid.uuid4())
    with database.get_conn(client.db_path) as c:
        database.create_job(c, job_id=job_id, rubric_id="default-v1-draft")
        database.insert_job_criteria(c, job_id, CRITERIA)
        database.create_image(c, job_id=job_id, ordinal=0, source="upload:a.png")
        database.set_job_status(c, job_id, "failed", error_code="INTERNAL_ERROR", error_message="x")
    img = client.get(f"/api/v1/jobs/{job_id}/results").json()["images"][0]
    assert img["status"] == "failed"


@pytest.mark.parametrize("state", ["queued", "preprocessing", "analyzing", "scoring"])
def test_results_while_job_is_running_return_409(client, state):
    job_id, _ = _seed(client, status=state)
    r = client.get(f"/api/v1/jobs/{job_id}/results")
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "JOB_NOT_FINISHED"


@pytest.mark.parametrize("job_id", [str(uuid.uuid4()), "not-a-uuid"])
def test_unknown_or_malformed_job_id_returns_404(client, job_id):
    r = client.get(f"/api/v1/jobs/{job_id}/results")
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "NOT_FOUND"


def test_latest_whole_image_feedback_is_included(client):
    job_id, ids = _seed(client)
    with database.get_conn(client.db_path) as c:
        for fid, verdict, crit, ts in [
            ("11111111-1111-4111-8111-111111111111", "agree", None, "2026-10-30T10:00:00.000Z"),
            ("22222222-2222-4222-8222-222222222222", "disagree", None, "2026-10-30T11:00:00.000Z"),
            # Criterion-level feedback must not appear as the whole-image verdict.
            ("33333333-3333-4333-8333-333333333333", "agree", "contrast", "2026-10-30T12:00:00.000Z"),
        ]:
            c.execute(
                "INSERT INTO feedback (feedback_id, image_id, criterion_id, verdict, comment,"
                " created_at) VALUES (?, ?, ?, ?, NULL, ?)",
                (fid, ids["good"], crit, verdict, ts),
            )
    images = client.get(f"/api/v1/jobs/{job_id}/results").json()["images"]
    assert images[0]["feedback"]["verdict"] == "disagree"
    assert images[0]["feedback"]["criterion_id"] is None
    assert images[1]["feedback"] is None
