"""Tests for the scoring-pipeline adapter and its worker wiring (SCRUM-166 / 167).

Covers: converting the scorer's dataclasses into what the worker stores, that the
converted data satisfies the database's rules, the PipelineAnalyzer hook, and the
opt-in app wiring. The model and CV stages are faked; one test at the end runs the
real pipeline when it is available.
"""

from __future__ import annotations

import io
import math
import uuid
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from brandlens.api import analysis as analysis_module
from brandlens.api import db as database
from brandlens.api.analysis import PipelineAnalyzer, to_image_analysis
from brandlens.api.app import create_app
from brandlens.api.config import Settings
from brandlens.api.results import build_job_results
from brandlens.api.worker import ImageAnalysis, run_job
from brandlens.scoring.engine import CriterionScore, ImageScore
from brandlens.scoring.explanations import explain_criterion

CRITERIA = ["exposure_brightness", "tone_approachability"]


def _criterion(cid, *, score=80.0, source="cv", availability="ok", weight=0.5,
               label=None, evidence=(), reasons=()):
    return CriterionScore(
        criterion_id=cid, score=score, weight=weight, configured_weight=weight,
        source=source, label=label, evidence=tuple(evidence),
        availability=availability, rule_id="test_rule", reasons=tuple(reasons),
    )


def _image_score(criteria, *, overall=80.0, flagged=False, status="scored"):
    return ImageScore(
        rubric_id="default-v1-draft", criteria=tuple(criteria),
        overall_score=overall, flagged=flagged, status=status,
    )


def _png(width=100, height=100) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (width, height), (128, 128, 128)).save(buf, format="PNG")
    return buf.getvalue()


# --------------------------------------------------------------------------- conversion


def test_available_criterion_becomes_a_storable_mapping():
    scored = _image_score([_criterion(
        "tone_approachability", score=87.4, source="vlm", label="warm",
        evidence=["smiling subject", "soft light"], weight=0.4,
    )])
    result = to_image_analysis(scored)

    assert result.status == "scored" and result.overall_score == 80.0
    (c,) = result.criteria
    assert c["criterion_id"] == "tone_approachability"
    assert c["score"] == 87.4 and c["weight"] == 0.4 and c["source"] == "vlm"
    assert c["label"] == "warm" and c["availability"] == "ok"
    assert c["evidence"] == ["smiling subject", "soft light"]
    assert c["explanation"] == explain_criterion(scored.criteria[0])
    assert "warm" in c["explanation"] and "smiling subject" in c["explanation"]


def test_unavailable_criterion_keeps_a_null_score_and_needs_review():
    scored = _image_score(
        [_criterion("exposure_brightness"),
         _criterion("tone_approachability", score=None, source="vlm", weight=0.0,
                    availability="unavailable_needs_review",
                    reasons=["Model did not answer in time."])],
        overall=80.0, status="partial",
    )
    result = to_image_analysis(scored)

    assert result.status == "partial"
    unavailable = result.criteria[1]
    assert unavailable["score"] is None
    assert unavailable["availability"] == "unavailable_needs_review"
    assert unavailable["explanation"] == explain_criterion(scored.criteria[1])
    assert "needs review" in unavailable["explanation"]
    assert "Model did not answer in time." in unavailable["explanation"]


def test_an_ok_criterion_without_a_score_is_treated_as_unavailable():
    """The database forbids availability 'ok' with a null score; never emit that."""
    scored = _image_score([_criterion("exposure_brightness", score=None)])
    (c,) = to_image_analysis(scored).criteria
    assert c["availability"] == "unavailable_needs_review" and c["score"] is None
    assert "needs review" in c["explanation"]  # explained, not an AssertionError


def test_scorer_failure_marks_the_image_failed_but_keeps_its_criteria():
    scored = _image_score(
        [_criterion("exposure_brightness", score=None, weight=0.0,
                    availability="unavailable_needs_review")],
        overall=None, status="failed",
    )
    result = to_image_analysis(scored)

    assert result.status == "failed" and result.overall_score is None
    assert result.error_code == "NO_CRITERIA_AVAILABLE"
    assert len(result.criteria) == 1


def test_an_unknown_scorer_status_is_stored_as_failed():
    result = to_image_analysis(_image_score([_criterion("exposure_brightness")], status="weird"))
    assert result.status == "failed" and result.overall_score is None


def test_flagged_is_carried_through():
    assert to_image_analysis(_image_score([_criterion("exposure_brightness")], flagged=True)).flagged


def test_measurements_are_made_json_safe():
    numpy = pytest.importorskip("numpy")

    @dataclass
    class Box:
        x: int

    cv = {"exposure_brightness": {
        "status": "available",
        "measurements": {"mean": numpy.float64(0.5), "hist": numpy.array([1, 2]),
                         "region": (1, 2), "bad": math.nan, "box": Box(3)},
        "reasons": ("ok",),
    }}
    vlm = {"tone_approachability": {"fit_score": 4, "tone_label": "warm"}}
    measurements = to_image_analysis(_image_score([_criterion("exposure_brightness")]), cv, vlm).measurements

    import json
    json.dumps(measurements, allow_nan=False)  # must not raise
    m = measurements["cv"]["exposure_brightness"]["measurements"]
    assert m["mean"] == 0.5 and m["hist"] == [1, 2] and m["region"] == [1, 2]
    assert m["bad"] is None and m["box"] == {"x": 3}
    assert measurements["vlm"]["tone_approachability"]["tone_label"] == "warm"


def test_no_results_means_no_measurements():
    assert to_image_analysis(_image_score([_criterion("exposure_brightness")])).measurements is None


# --------------------------------------------------------------------------- database rules


def test_converted_results_satisfy_the_database_rules(tmp_path: Path):
    """Adapter output must pass the schema's checks (score/availability, weight 0..1)."""
    db_path = tmp_path / "t.db"
    database.init_db(db_path)
    job_id = str(uuid.uuid4())
    scored = _image_score(
        [_criterion("exposure_brightness", score=92.0, evidence=["well exposed"]),
         _criterion("tone_approachability", score=None, source="vlm", weight=0.0,
                    availability="unavailable_needs_review", reasons=["timeout"])],
        overall=92.0, status="partial",
    )
    analysis = to_image_analysis(scored, {"exposure_brightness": {"measurements": {"mean": 0.4}}})

    with database.get_conn(db_path) as conn:
        database.create_job(conn, job_id=job_id, rubric_id="default-v1-draft")
        database.insert_job_criteria(conn, job_id, CRITERIA)
        image_id = database.create_image(conn, job_id=job_id, ordinal=0, source="upload:a.png")
        database.save_image_result(
            conn, image_id, status=analysis.status, overall_score=analysis.overall_score,
            flagged=analysis.flagged, criteria=analysis.criteria,
            measurements=analysis.measurements,
        )
        database.set_job_status(conn, job_id, "completed_with_errors")
        res = build_job_results(conn, job_id)

    (image,) = res.images
    assert image.status == "partial" and image.overall_score == 92.0
    by_id = {c.criterion_id: c for c in image.criteria}
    assert by_id["exposure_brightness"].score == 92.0
    assert by_id["tone_approachability"].score is None
    assert by_id["tone_approachability"].availability == "unavailable_needs_review"


# --------------------------------------------------------------------------- PipelineAnalyzer


def _fake_score_fn(calls=None, *, raises=None):
    def score(image, configuration, vlm_client, **kwargs):
        if calls is not None:
            calls.append((image, configuration, vlm_client, kwargs))
        if raises:
            raise raises
        return (
            _image_score([_criterion(cid) for cid in kwargs["criterion_ids"]]),
            {cid: {"measurements": {"n": 1}} for cid in kwargs["criterion_ids"]},
            {},
        )
    return score


def test_analyzer_passes_the_image_selection_and_components_to_the_pipeline():
    calls = []
    detector, selector, client = Mock(), Mock(), Mock()
    analyzer = PipelineAnalyzer(
        "CONFIG", client, subject_detector=detector, subject_selector=selector,
        score_fn=_fake_score_fn(calls),
    )
    image = Image.new("RGB", (50, 50))

    result = analyzer(image, ("exposure_brightness", "contrast"))

    (img, config, vlm, kwargs), = calls
    assert img is image and config == "CONFIG" and vlm is client
    assert kwargs == {
        "criterion_ids": ["exposure_brightness", "contrast"],
        "subject_detector": detector, "subject_selector": selector,
    }
    assert isinstance(result, ImageAnalysis)
    assert [c["criterion_id"] for c in result.criteria] == ["exposure_brightness", "contrast"]


def test_pipeline_errors_propagate_so_the_worker_can_fail_that_image():
    analyzer = PipelineAnalyzer("CONFIG", score_fn=_fake_score_fn(raises=RuntimeError("model down")))
    with pytest.raises(RuntimeError, match="model down"):
        analyzer(Image.new("RGB", (50, 50)), ["exposure_brightness"])


def test_close_releases_the_model_client():
    client = Mock()
    PipelineAnalyzer("CONFIG", client, score_fn=_fake_score_fn()).close()
    client.close.assert_called_once()
    PipelineAnalyzer("CONFIG", None, score_fn=_fake_score_fn()).close()  # no client: no error


def test_worker_runs_the_analyzer_and_isolates_a_failing_image(tmp_path: Path):
    db_path = tmp_path / "t.db"
    database.init_db(db_path)
    job_id = str(uuid.uuid4())
    raw = tmp_path / "raw"
    raw.mkdir()
    records = []
    with database.get_conn(db_path) as conn:
        database.create_job(conn, job_id=job_id, rubric_id="default-v1-draft")
        database.insert_job_criteria(conn, job_id, CRITERIA)
        for i in range(3):
            path = raw / f"{i}.png"
            path.write_bytes(_png())
            records.append((database.create_image(
                conn, job_id=job_id, ordinal=i, source=f"upload:{i}.png", raw_path=str(path)), path))

    state = {"n": 0}
    inner = _fake_score_fn()

    def sometimes_fails(image, configuration, vlm_client, **kwargs):
        state["n"] += 1
        if state["n"] == 2:
            raise RuntimeError("model down")
        return inner(image, configuration, vlm_client, **kwargs)

    analyzer = PipelineAnalyzer("CONFIG", score_fn=sometimes_fails)
    run_job(job_id, records, db_path, tmp_path / "out", analyze=analyzer)

    with database.get_conn(db_path) as conn:
        res = build_job_results(conn, job_id)
        job = database.get_job(conn, job_id)
    assert [i.status for i in res.images] == ["scored", "failed", "scored"]
    assert {c.criterion_id for c in res.images[0].criteria} == set(CRITERIA)
    assert job["status"] == "completed_with_errors"


# --------------------------------------------------------------------------- settings & app


def test_analyzer_setting_defaults_to_the_placeholder(monkeypatch):
    monkeypatch.delenv("BRANDLENS_ANALYZER", raising=False)
    assert Settings().analyzer == "placeholder"
    assert Settings.from_env().analyzer == "placeholder"


def test_analyzer_setting_can_be_set_from_the_environment(monkeypatch):
    monkeypatch.setenv("BRANDLENS_ANALYZER", " Pipeline ")
    assert Settings.from_env().analyzer == "pipeline"


def test_unknown_analyzer_setting_is_rejected():
    with pytest.raises(ValueError, match="analyzer"):
        Settings(analyzer="magic")


def _settings(tmp_path: Path, **kw) -> Settings:
    return Settings(
        db_path=tmp_path / "a.db", upload_dir=tmp_path / "raw",
        processed_dir=tmp_path / "processed",
        rubric_path=Path("config/brand_standards.json"), **kw,
    )


def test_app_uses_the_placeholder_unless_the_pipeline_is_selected(tmp_path: Path):
    with TestClient(create_app(_settings(tmp_path))) as client:
        assert client.app.state.analyzer is None


def test_app_builds_closes_and_uses_the_pipeline_analyzer(tmp_path: Path, monkeypatch):
    seen = []

    class FakeAnalyzer:
        closed = False

        def __call__(self, image, criterion_ids):
            seen.append((image.mode, list(criterion_ids)))
            return to_image_analysis(_image_score(
                [_criterion(cid, score=70.0) for cid in criterion_ids], overall=70.0))

        def close(self):
            FakeAnalyzer.closed = True

    monkeypatch.setattr(
        analysis_module.PipelineAnalyzer, "from_settings",
        classmethod(lambda cls, settings, **kw: FakeAnalyzer()),
    )
    with TestClient(create_app(_settings(tmp_path, analyzer="pipeline"))) as client:
        r = client.post(
            "/api/v1/analyses/uploads", data={"rubric_id": "default-v1-draft"},
            files=[("files", ("a.png", _png(), "image/png"))],
        )
        job_id = r.json()["job_id"]
        results = client.get(f"/api/v1/jobs/{job_id}/results").json()

    (image,) = results["images"]
    assert image["status"] == "scored" and image["overall_score"] == 70.0
    assert image["criteria"] and all(c["score"] == 70.0 for c in image["criteria"])
    assert seen and seen[0][0] == "RGB"  # analysis got the standardized RGB image
    assert FakeAnalyzer.closed  # closed when the app shut down


# --------------------------------------------------------------------------- real pipeline


def test_real_pipeline_scores_an_image_through_the_worker(tmp_path: Path):
    """Runs only where brandlens.pipeline.score_standardized_image and a CV-only rubric exist."""
    pipeline = pytest.importorskip("brandlens.pipeline")
    if not hasattr(pipeline, "score_standardized_image"):
        pytest.skip("pipeline.score_standardized_image is not available on this branch yet")
    rubric_path = Path("config/brand_standards_brightness_contrast_test.json")
    if not rubric_path.exists():
        pytest.skip("brightness/contrast test rubric not present")

    settings = Settings(
        db_path=tmp_path / "r.db", upload_dir=tmp_path / "raw",
        processed_dir=tmp_path / "processed", rubric_path=rubric_path, analyzer="pipeline",
    )
    analyzer = PipelineAnalyzer.from_settings(settings)
    rubric = analyzer._configuration[0]
    selected = [c["criterion_id"] for c in rubric["criteria"]]

    db_path = tmp_path / "r.db"
    database.init_db(db_path)
    job_id = str(uuid.uuid4())
    (tmp_path / "raw").mkdir()
    path = tmp_path / "raw" / "a.png"
    path.write_bytes(_png(300, 200))
    with database.get_conn(db_path) as conn:
        database.create_job(conn, job_id=job_id, rubric_id=rubric["rubric_id"])
        database.insert_job_criteria(conn, job_id, selected)
        image_id = database.create_image(
            conn, job_id=job_id, ordinal=0, source="upload:a.png", raw_path=str(path))

    run_job(job_id, [(image_id, path)], db_path, tmp_path / "out", analyze=analyzer)
    analyzer.close()

    with database.get_conn(db_path) as conn:
        (image,) = build_job_results(conn, job_id).images
    assert image.status in {"scored", "partial"}
    assert {c.criterion_id for c in image.criteria} == set(selected)
    assert image.overall_score is not None and 0 <= image.overall_score <= 100
