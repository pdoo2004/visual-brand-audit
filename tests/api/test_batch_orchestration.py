"""Tests for multiple-image batch orchestration (SCRUM-167 / task 8.3).

Demonstrates: when several images are submitted in one job, each is processed
once and the batch completes with per-image status/results.
"""

from __future__ import annotations

import io
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from brandlens.api import db as database
from brandlens.api import worker
from brandlens.api.app import create_app
from brandlens.api.config import Settings
from brandlens.api.results import build_job_results
from brandlens.api.worker import ImageAnalysis, run_job

CRITERIA = ["exposure_brightness", "contrast"]


def _png(width: int = 100, height: int = 100) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (width, height), (128, 128, 128)).save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture
def env(tmp_path: Path):
    db_path = tmp_path / "t.db"
    database.init_db(db_path)
    return {"db": db_path, "raw": tmp_path / "raw", "out": tmp_path / "out"}


def _make_job(env, files: list[bytes]) -> tuple[str, list[tuple[str, Path]]]:
    """Create a queued job with one image row + file on disk per entry in `files`."""
    job_id = str(uuid.uuid4())
    env["raw"].mkdir(exist_ok=True)
    records = []
    with database.get_conn(env["db"]) as conn:
        database.create_job(conn, job_id=job_id, rubric_id="default-v1-draft")
        database.insert_job_criteria(conn, job_id, CRITERIA)
        for i, data in enumerate(files):
            path = env["raw"] / f"{job_id}_{i}.png"
            path.write_bytes(data)
            image_id = database.create_image(
                conn, job_id=job_id, ordinal=i, source=f"upload:{i}.png", raw_path=str(path)
            )
            records.append((image_id, path))
    return job_id, records


def _run(env, job_id, records, analyze=None):
    run_job(job_id, records, env["db"], env["out"] / job_id, analyze=analyze)


def _results(env, job_id):
    with database.get_conn(env["db"]) as conn:
        return build_job_results(conn, job_id)


def _job_status(env, job_id) -> str:
    with database.get_conn(env["db"]) as conn:
        return database.get_job(conn, job_id)["status"]


def _scored(score: float):
    def analyze(image, criterion_ids):
        return ImageAnalysis(
            status="scored", overall_score=score, flagged=False,
            criteria=[
                {"criterion_id": c, "score": score, "weight": 1 / len(criterion_ids),
                 "source": "cv", "explanation": f"{c} ok", "availability": "ok"}
                for c in criterion_ids
            ],
        )
    return analyze


def test_every_image_is_processed_exactly_once(env):
    job_id, records = _make_job(env, [_png() for _ in range(5)])
    calls: list[int] = []

    def analyze(image, criterion_ids):
        calls.append(1)
        return _scored(80.0)(image, criterion_ids)

    _run(env, job_id, records, analyze)

    assert len(calls) == 5
    assert _job_status(env, job_id) == "completed"
    res = _results(env, job_id)
    assert [i.status for i in res.images] == ["scored"] * 5
    assert all(len(i.criteria) == 2 for i in res.images)
    assert res.summary.images_scored == 5 and res.summary.mean_overall == 80.0


def test_each_image_keeps_its_own_result(env):
    job_id, records = _make_job(env, [_png() for _ in range(3)])
    scores = iter([10.0, 50.0, 90.0])

    def analyze(image, criterion_ids):
        return _scored(next(scores))(image, criterion_ids)

    _run(env, job_id, records, analyze)
    assert [i.overall_score for i in _results(env, job_id).images] == [10.0, 50.0, 90.0]


def test_rerunning_a_job_does_not_process_images_again(env):
    job_id, records = _make_job(env, [_png(), _png()])
    calls: list[int] = []

    def analyze(image, criterion_ids):
        calls.append(1)
        return _scored(70.0)(image, criterion_ids)

    _run(env, job_id, records, analyze)
    _run(env, job_id, records, analyze)
    assert len(calls) == 2
    assert _job_status(env, job_id) == "completed"


def test_one_failing_image_does_not_stop_the_batch(env):
    job_id, records = _make_job(env, [_png() for _ in range(4)])
    seen = {"n": 0}

    def analyze(image, criterion_ids):
        seen["n"] += 1
        if seen["n"] == 2:
            raise RuntimeError("model exploded")
        return _scored(60.0)(image, criterion_ids)

    _run(env, job_id, records, analyze)

    res = _results(env, job_id)
    assert [i.status for i in res.images] == ["scored", "failed", "scored", "scored"]
    assert _job_status(env, job_id) == "completed_with_errors"
    with database.get_conn(env["db"]) as conn:
        failed = database.get_job_images(conn, job_id)[1]
    assert failed["error_code"] == "ANALYSIS_ERROR" and "model exploded" in failed["error_message"]


def test_partial_result_makes_the_job_completed_with_errors(env):
    job_id, records = _make_job(env, [_png(), _png()])
    n = {"i": 0}

    def analyze(image, criterion_ids):
        n["i"] += 1
        if n["i"] == 1:
            return ImageAnalysis(
                status="partial", overall_score=55.0, flagged=True,
                criteria=[
                    {"criterion_id": "exposure_brightness", "score": 55.0, "weight": 1.0,
                     "source": "cv", "availability": "ok"},
                    {"criterion_id": "contrast", "score": None, "weight": 0.0, "source": "vlm",
                     "availability": "unavailable_needs_review"},
                ],
            )
        return _scored(80.0)(image, criterion_ids)

    _run(env, job_id, records, analyze)
    res = _results(env, job_id)
    assert [i.status for i in res.images] == ["partial", "scored"]
    assert res.images[0].flagged and res.summary.flagged_count == 1
    assert _job_status(env, job_id) == "completed_with_errors"


def test_mixed_batch_reports_per_image_status(env):
    files = [_png(), b"this is not an image", _png(10, 10), _png()]
    job_id, records = _make_job(env, files)
    _run(env, job_id, records, _scored(75.0))

    res = _results(env, job_id)
    statuses = [i.status for i in res.images]
    assert statuses[0] == "scored" and statuses[3] == "scored"
    assert statuses[1] in {"filtered_out", "failed"}
    assert statuses[2] == "filtered_out" and res.images[2].reject_reason == "too_small"
    assert res.summary.images_scored == 2


def test_filtered_images_alone_do_not_make_the_job_an_error(env):
    job_id, records = _make_job(env, [_png(10, 10), _png(10, 10)])
    _run(env, job_id, records, _scored(75.0))
    assert _job_status(env, job_id) == "completed"


def test_progress_is_visible_while_the_batch_runs(env):
    job_id, records = _make_job(env, [_png() for _ in range(3)])
    snapshots: list[tuple[str, int]] = []

    def analyze(image, criterion_ids):
        with database.get_conn(env["db"]) as conn:
            row = database.query_job_progress(conn, job_id)
        snapshots.append((row["status"], row["images_done"]))
        return _scored(70.0)(image, criterion_ids)

    _run(env, job_id, records, analyze)
    # Each result is saved before the next image starts, so progress climbs 0, 1, 2.
    assert snapshots == [("analyzing", 0), ("analyzing", 1), ("analyzing", 2)]


def test_default_analyzer_keeps_the_previous_placeholder_behaviour(env):
    job_id, records = _make_job(env, [_png()])
    _run(env, job_id, records)
    res = _results(env, job_id)
    assert res.images[0].status == "scored" and res.images[0].overall_score == 0.0


def test_batch_level_crash_marks_the_job_failed(env, monkeypatch):
    job_id, records = _make_job(env, [_png()])

    def boom(conn, job_id):
        raise RuntimeError("database vanished")

    monkeypatch.setattr(worker.database, "get_job_criterion_ids", boom)
    _run(env, job_id, records, _scored(70.0))

    with database.get_conn(env["db"]) as conn:
        job = database.get_job(conn, job_id)
    assert job["status"] == "failed" and job["error_code"] == "INTERNAL_ERROR"
    assert "database vanished" not in (job["error_message"] or "")  # no internals to the client


def test_upload_of_several_images_end_to_end(tmp_path: Path):
    settings = Settings(
        db_path=tmp_path / "e2e.db",
        upload_dir=tmp_path / "raw",
        processed_dir=tmp_path / "processed",
        rubric_path=Path("config/brand_standards.json"),
    )
    with TestClient(create_app(settings)) as client:
        files = [("files", (f"img{i}.png", _png(), "image/png")) for i in range(4)]
        r = client.post(
            "/api/v1/analyses/uploads", data={"rubric_id": "default-v1-draft"}, files=files
        )
        job_id = r.json()["job_id"]

        status = client.get(f"/api/v1/jobs/{job_id}").json()
        assert status["status"] == "completed"
        assert status["progress"] == {"images_total": 4, "images_done": 4, "images_failed": 0}

        results = client.get(f"/api/v1/jobs/{job_id}/results").json()
        assert len(results["images"]) == 4
        assert {i["status"] for i in results["images"]} == {"scored"}


def test_worker_preprocesses_through_the_shared_preprocessor(env, monkeypatch):
    """Filtering/standardizing is done once per image, by preprocess_image."""
    calls = []
    real = worker.preprocess_image

    def counting(image, *args, **kwargs):
        calls.append(image.size)
        return real(image, *args, **kwargs)

    monkeypatch.setattr(worker, "preprocess_image", counting)
    job_id, records = _make_job(env, [_png(), _png(120, 90)])
    _run(env, job_id, records, analyze=_scored(80.0))

    assert len(calls) == 2
    assert [i.status for i in _results(env, job_id).images] == ["scored", "scored"]


def test_analysis_receives_the_standardized_image_once(env):
    """The image handed to analysis is already standardized (RGB, size-capped)."""
    seen = []

    def analyze(image, criterion_ids):
        seen.append((image.mode, image.size))
        return ImageAnalysis(status="scored", overall_score=50.0, flagged=False, criteria=[])

    job_id, records = _make_job(env, [_png(4000, 3000)])
    _run(env, job_id, records, analyze=analyze)

    assert len(seen) == 1
    mode, (w, h) = seen[0]
    assert mode == "RGB" and max(w, h) <= 2048


def test_filter_reasons_come_from_the_shared_filter(env):
    job_id, records = _make_job(env, [_png(40, 40), _png(600, 100), _png(100, 100)])
    _run(env, job_id, records, analyze=_scored(70.0))
    images = _results(env, job_id).images
    assert [i.status for i in images] == ["filtered_out", "filtered_out", "scored"]
    assert images[0].reject_reason == "too_small"
    assert images[1].reject_reason == "extreme_aspect_ratio"


def test_preprocessing_error_fails_only_that_image(env, monkeypatch):
    real = worker.preprocess_image
    state = {"n": 0}

    def flaky(image, *args, **kwargs):
        state["n"] += 1
        if state["n"] == 1:
            raise ValueError("boom")
        return real(image, *args, **kwargs)

    monkeypatch.setattr(worker, "preprocess_image", flaky)
    job_id, records = _make_job(env, [_png(), _png()])
    _run(env, job_id, records, analyze=_scored(60.0))

    with database.get_conn(env["db"]) as conn:
        rows = database.get_job_images(conn, job_id)
    assert rows[0]["status"] == "failed" and rows[0]["error_code"] == "PREPROCESS_ERROR"
    assert rows[1]["status"] == "scored"
    assert _job_status(env, job_id) == "completed_with_errors"


# --- the job status reflects every stored image, not only the ones processed this run ----


def _partial(image, criterion_ids):
    return ImageAnalysis(
        status="partial", overall_score=55.0, flagged=False,
        criteria=[
            {"criterion_id": "exposure_brightness", "score": 55.0, "weight": 1.0,
             "source": "cv", "availability": "ok"},
            {"criterion_id": "contrast", "score": None, "weight": 0.0, "source": "vlm",
             "availability": "unavailable_needs_review"},
        ],
    )


def _boom(image, criterion_ids):
    raise RuntimeError("model exploded")


def test_rerun_keeps_completed_with_errors_when_an_image_failed(env):
    job_id, records = _make_job(env, [_png(), _png()])
    n = {"i": 0}

    def analyze(image, criterion_ids):
        n["i"] += 1
        return _boom(image, criterion_ids) if n["i"] == 1 else _scored(70.0)(image, criterion_ids)

    _run(env, job_id, records, analyze)
    assert _job_status(env, job_id) == "completed_with_errors"

    _run(env, job_id, records, analyze)  # every image already has a result: nothing reruns
    assert n["i"] == 2
    assert _job_status(env, job_id) == "completed_with_errors"


def test_rerun_keeps_completed_with_errors_when_an_image_is_partial(env):
    job_id, records = _make_job(env, [_png(), _png()])
    n = {"i": 0}

    def analyze(image, criterion_ids):
        n["i"] += 1
        return _partial(image, criterion_ids) if n["i"] == 1 else _scored(80.0)(image, criterion_ids)

    _run(env, job_id, records, analyze)
    _run(env, job_id, records, analyze)
    assert [i.status for i in _results(env, job_id).images] == ["partial", "scored"]
    assert _job_status(env, job_id) == "completed_with_errors"


def test_earlier_failures_count_when_a_later_run_finishes_the_rest(env):
    """A resumed job: image 0 failed in run 1; run 2 only processes image 1, which scores."""
    job_id, records = _make_job(env, [_png(), _png()])

    _run(env, job_id, records[:1], _boom)
    assert _job_status(env, job_id) == "completed_with_errors"

    _run(env, job_id, records, _scored(90.0))
    assert [i.status for i in _results(env, job_id).images] == ["failed", "scored"]
    assert _job_status(env, job_id) == "completed_with_errors"


def test_rerun_of_a_clean_job_with_a_filtered_image_stays_completed(env):
    job_id, records = _make_job(env, [_png(), _png(30, 30)])  # second is too small
    _run(env, job_id, records, _scored(75.0))
    _run(env, job_id, records, _scored(75.0))
    assert [i.status for i in _results(env, job_id).images] == ["scored", "filtered_out"]
    assert _job_status(env, job_id) == "completed"
