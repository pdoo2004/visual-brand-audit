"""Tests for result persistence (SCRUM-158 / task 7.7).

Demonstrates: when a job completes, its image metadata, criterion results,
explanations, and summary can be stored and retrieved by job ID.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path

import pytest

from brandlens.api import db as database

CRITERIA = ["exposure_brightness", "contrast"]


@pytest.fixture
def conn(tmp_path: Path):
    db_path = tmp_path / "t.db"
    database.init_db(db_path)
    with database.get_conn(db_path) as c:
        yield c


def _job_with_images(conn: sqlite3.Connection, n: int = 2) -> tuple[str, list[str]]:
    job_id = str(uuid.uuid4())
    database.create_job(conn, job_id=job_id, rubric_id="default-v1-draft")
    database.insert_job_criteria(conn, job_id, CRITERIA)
    ids = [
        database.create_image(conn, job_id=job_id, ordinal=i, source=f"upload:{i}.png")
        for i in range(n)
    ]
    return job_id, ids


def _criterion(cid: str, score: float | None = 80.0, **kw) -> dict:
    base = {
        "criterion_id": cid,
        "score": score,
        "weight": 0.5,
        "source": "cv",
        "label": None,
        "explanation": f"{cid} looks fine",
        "evidence": ["mean luminance 120"],
        "availability": "ok" if score is not None else "unavailable_needs_review",
    }
    base.update(kw)
    return base


def test_store_then_retrieve_by_job_id(conn):
    job_id, (img, _) = _job_with_images(conn)
    database.save_image_result(
        conn, img,
        status="scored", overall_score=76.5, flagged=False,
        width=640, height=480, processed_path="p/x.png",
        measurements={"mean_luminance": 120.0},
        criteria=[_criterion("exposure_brightness", 80.0), _criterion("contrast", 73.0)],
    )
    database.set_job_status(conn, job_id, "completed")

    job = database.get_job(conn, job_id)
    assert job["status"] == "completed" and job["rubric_id"] == "default-v1-draft"

    images = database.get_job_images(conn, job_id)
    assert [i["ordinal"] for i in images] == [0, 1]
    stored = images[0]
    assert stored["status"] == "scored" and stored["overall_score"] == 76.5
    assert stored["flagged"] == 0 and (stored["width"], stored["height"]) == (640, 480)
    assert json.loads(stored["measurements_json"]) == {"mean_luminance": 120.0}

    rows = database.get_job_criterion_scores(conn, job_id)[img]
    assert [r["criterion_id"] for r in rows] == CRITERIA
    assert rows[0]["explanation"] == "exposure_brightness looks fine"
    assert json.loads(rows[0]["evidence_json"]) == ["mean luminance 120"]


def test_unavailable_criterion_is_stored_with_null_score(conn):
    job_id, (img, _) = _job_with_images(conn)
    database.save_image_result(
        conn, img, status="partial", overall_score=80.0, flagged=True,
        criteria=[_criterion("exposure_brightness"), _criterion("contrast", None, weight=0.0)],
    )
    rows = database.get_job_criterion_scores(conn, job_id)[img]
    assert rows[1]["score"] is None
    assert rows[1]["availability"] == "unavailable_needs_review"


def test_resaving_replaces_old_criterion_rows(conn):
    job_id, (img, _) = _job_with_images(conn)
    database.save_image_result(
        conn, img, status="scored", overall_score=50.0, flagged=False,
        criteria=[_criterion("exposure_brightness", 50.0), _criterion("contrast", 50.0)],
    )
    database.save_image_result(
        conn, img, status="scored", overall_score=90.0, flagged=False,
        criteria=[_criterion("exposure_brightness", 90.0), _criterion("contrast", 90.0)],
    )
    rows = database.get_job_criterion_scores(conn, job_id)[img]
    assert len(rows) == 2 and all(r["score"] == 90.0 for r in rows)


def test_filtered_and_failed_images_store_without_criteria(conn):
    job_id, (a, b) = _job_with_images(conn)
    database.save_image_result(conn, a, status="filtered_out", reject_reason="too_small")
    database.save_image_result(
        conn, b, status="failed", error_code="LOAD_ERROR", error_message="corrupt"
    )
    by_id = {r["image_id"]: r for r in database.get_job_images(conn, job_id)}
    assert by_id[a]["reject_reason"] == "too_small" and by_id[a]["overall_score"] is None
    assert by_id[b]["error_code"] == "LOAD_ERROR"
    assert database.get_job_criterion_scores(conn, job_id) == {}


def test_unknown_image_raises(conn):
    with pytest.raises(LookupError):
        database.save_image_result(conn, str(uuid.uuid4()), status="failed")


def test_unknown_job_returns_none_and_empty(conn):
    ghost = str(uuid.uuid4())
    assert database.get_job(conn, ghost) is None
    assert database.get_job_images(conn, ghost) == []
    assert database.get_job_criterion_scores(conn, ghost) == {}


def test_criterion_outside_job_selection_is_rejected_and_rolls_back(tmp_path):
    db_path = tmp_path / "t.db"
    database.init_db(db_path)
    with database.get_conn(db_path) as c:
        _, (img, _) = _job_with_images(c)
    with pytest.raises(sqlite3.IntegrityError):
        with database.get_conn(db_path) as c:
            database.save_image_result(
                c, img, status="scored", overall_score=10.0, flagged=False,
                criteria=[_criterion("not_selected")],
            )
    with database.get_conn(db_path) as c:  # image header must not have been half-written
        row = c.execute("SELECT status FROM images WHERE image_id = ?", (img,)).fetchone()
        assert row["status"] is None
