"""Tests for the API schemas (SCRUM-153).

Acceptance: valid payloads parse; representative malformed payloads are rejected
with explicit validation errors.
"""

import json
from datetime import UTC, datetime, timedelta, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from brandlens.api.schemas import (
    MAX_CRAWL_PAGES,
    CriterionResult,
    ErrorResponse,
    FeedbackRecord,
    FeedbackSubmission,
    HealthResponse,
    ImageResult,
    InputType,
    JobAccepted,
    JobProgress,
    JobResults,
    JobState,
    JobStatus,
    ResultsSummary,
    RubricInfo,
    UploadRequest,
    UrlSubmission,
)

NOW = datetime(2026, 10, 5, 14, 3, 22, 123456, tzinfo=UTC)


def reject(model, payload: dict, expected_text: str):
    """Assert the payload is rejected and the error message names the problem."""
    with pytest.raises(ValidationError) as excinfo:
        model.model_validate(payload)
    assert expected_text in str(excinfo.value), str(excinfo.value)


# ---- builders for valid payloads -------------------------------------------------
def criterion(**overrides) -> dict:
    base = {
        "criterion_id": "exposure_brightness",
        "score": 80.0,
        "weight": 0.2,
        "source": "cv",
        "label": None,
        "explanation": "Well exposed.",
        "evidence": ["mean luminance 128"],
        "availability": "ok",
    }
    return base | overrides


def image(**overrides) -> dict:
    base = {
        "image_id": str(uuid4()),
        "source": "upload:hero.jpg",
        "status": "scored",
        "overall_score": 71.0,
        "flagged": False,
        "measurements": {"mean_luminance": 128.4},
        "criteria": [criterion()],
        "feedback": None,
    }
    return base | overrides


def job_status(**overrides) -> dict:
    base = {
        "job_id": str(uuid4()),
        "status": "analyzing",
        "progress": {"images_total": 12, "images_done": 5, "images_failed": 1},
        "created_at": NOW.isoformat(),
        "updated_at": (NOW + timedelta(seconds=5)).isoformat(),
        "error": None,
    }
    return base | overrides


# ---- requests --------------------------------------------------------------------
def test_upload_request_valid_and_optional_criteria():
    assert UploadRequest.model_validate({"rubric_id": "default-v1"}).criterion_ids is None
    ok = UploadRequest.model_validate(
        {"rubric_id": "default-v1", "criterion_ids": ["contrast", "tone_approachability"]}
    )
    assert ok.criterion_ids == ["contrast", "tone_approachability"]


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({}, "rubric_id"),
        ({"rubric_id": ""}, "rubric_id"),
        ({"rubric_id": "Default V1"}, "rubric_id"),
        ({"rubric_id": "default-v1", "criterion_ids": []}, "criterion_ids"),
        ({"rubric_id": "default-v1", "criterion_ids": ["a", "a"]}, "duplicates"),
        ({"rubric_id": "default-v1", "criterion_ids": ["Bad ID"]}, "criterion_ids"),
        ({"rubric_id": "default-v1", "unknown_field": 1}, "unknown_field"),
    ],
)
def test_upload_request_rejects_malformed(payload, expected):
    reject(UploadRequest, payload, expected)


def test_url_submission_valid():
    ok = UrlSubmission.model_validate(
        {"url": "https://www.capitalone.com/", "rubric_id": "default-v1", "max_pages": 10}
    )
    assert str(ok.url) == "https://www.capitalone.com/"
    assert ok.max_pages == 10


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({"url": "not a url", "rubric_id": "default-v1"}, "url"),
        ({"url": "ftp://example.com/a.jpg", "rubric_id": "default-v1"}, "url"),
        ({"url": "javascript:alert(1)", "rubric_id": "default-v1"}, "url"),
        ({"url": "https://example.com", "rubric_id": "default-v1", "max_pages": 0}, "max_pages"),
        (
            {"url": "https://example.com", "rubric_id": "default-v1", "max_pages": MAX_CRAWL_PAGES + 1},
            "max_pages",
        ),
        ({"rubric_id": "default-v1"}, "url"),
    ],
)
def test_url_submission_rejects_malformed(payload, expected):
    reject(UrlSubmission, payload, expected)


# ---- feedback --------------------------------------------------------------------
def test_feedback_submission_valid_and_normalizes_blank_comment():
    whole_image = FeedbackSubmission.model_validate({"verdict": "agree", "comment": "   "})
    assert whole_image.comment is None and whole_image.criterion_id is None
    one_criterion = FeedbackSubmission.model_validate(
        {"verdict": "disagree", "comment": " too dark ", "criterion_id": "exposure_brightness"}
    )
    assert one_criterion.comment == "too dark"


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({"verdict": "maybe"}, "verdict"),
        ({}, "verdict"),
        ({"verdict": "agree", "comment": "x" * 1001}, "comment"),
        ({"verdict": "agree", "criterion_id": "Not A Slug"}, "criterion_id"),
    ],
)
def test_feedback_submission_rejects_malformed(payload, expected):
    reject(FeedbackSubmission, payload, expected)


def test_feedback_record_round_trip():
    record = FeedbackRecord(
        feedback_id=uuid4(), image_id=uuid4(), criterion_id=None,
        verdict="agree", comment=None, created_at=NOW,
    )
    assert FeedbackRecord.model_validate_json(record.model_dump_json()) == record


# ---- jobs ------------------------------------------------------------------------
def test_job_accepted_for_job_builds_status_url():
    job_id = uuid4()
    accepted = JobAccepted.for_job(job_id, InputType.UPLOAD, NOW)
    assert accepted.status is JobState.QUEUED
    assert accepted.status_url == f"/api/v1/jobs/{job_id}"


def test_job_accepted_must_be_queued():
    reject(
        JobAccepted,
        {"job_id": str(uuid4()), "status": "completed", "input_type": "upload",
         "created_at": NOW.isoformat(), "status_url": "/x"},
        "status",
    )


def test_job_status_valid_states():
    for state in JobState:
        if state is JobState.FAILED:
            continue
        assert JobStatus.model_validate(job_status(status=state.value)).status is state


def test_job_status_failed_requires_error_and_only_failed_allows_it():
    error = {"code": "CRAWL_FAILED", "message": "Site unreachable"}
    assert JobStatus.model_validate(job_status(status="failed", error=error)).error is not None
    reject(JobStatus, job_status(status="failed"), "failed job must include an error")
    reject(JobStatus, job_status(status="analyzing", error=error), "only allowed when status is 'failed'")


@pytest.mark.parametrize(
    "progress",
    [
        {"images_total": 3, "images_done": 4, "images_failed": 0},
        {"images_total": 3, "images_done": 1, "images_failed": 2},
        {"images_total": -1, "images_done": 0, "images_failed": 0},
    ],
)
def test_job_progress_rejects_inconsistent_counts(progress):
    with pytest.raises(ValidationError):
        JobProgress.model_validate(progress)


def test_job_status_rejects_updated_before_created_and_naive_timestamps():
    reject(JobStatus, job_status(updated_at=(NOW - timedelta(seconds=1)).isoformat()), "updated_at")
    reject(JobStatus, job_status(created_at="2026-10-05T14:03:22"), "timezone")
    reject(JobStatus, job_status(status="not_a_state"), "status")


def test_timestamps_serialize_with_milliseconds_and_z():
    est = timezone(timedelta(hours=-5))
    status = JobStatus.model_validate(job_status(created_at=NOW.astimezone(est).isoformat()))
    dumped = json.loads(status.model_dump_json())
    assert dumped["created_at"] == "2026-10-05T14:03:22.123Z"


# ---- results ---------------------------------------------------------------------
def test_criterion_result_availability_rules():
    CriterionResult.model_validate(criterion())
    CriterionResult.model_validate(
        criterion(score=None, availability="unavailable_needs_review", source="vlm")
    )
    reject(CriterionResult, criterion(score=None), "score is required")
    reject(CriterionResult, criterion(availability="unavailable_needs_review"), "must be null")
    reject(CriterionResult, criterion(score=101), "score")
    reject(CriterionResult, criterion(score=-1), "score")
    reject(CriterionResult, criterion(weight=1.5), "weight")
    reject(CriterionResult, criterion(source="magic"), "source")


def test_image_result_status_rules():
    ImageResult.model_validate(image())
    ImageResult.model_validate(image(status="partial"))
    ImageResult.model_validate(
        image(status="filtered_out", reject_reason="too_small", overall_score=None, criteria=[])
    )
    ImageResult.model_validate(image(status="failed", overall_score=None, criteria=[]))
    reject(ImageResult, image(overall_score=None), "overall_score is required")
    reject(ImageResult, image(status="failed"), "overall_score must be null")
    reject(ImageResult, image(status="filtered_out", overall_score=None), "reject_reason is required")
    reject(ImageResult, image(reject_reason="too_small"), "only allowed when status is 'filtered_out'")
    reject(ImageResult, image(criteria=[criterion(), criterion()]), "repeat a criterion_id")


def test_results_summary_mean_rule():
    ResultsSummary(images_scored=0, mean_overall=None, flagged_count=0)
    ResultsSummary(images_scored=2, mean_overall=70.5, flagged_count=1)
    with pytest.raises(ValidationError):
        ResultsSummary(images_scored=2, mean_overall=None, flagged_count=0)
    with pytest.raises(ValidationError):
        ResultsSummary(images_scored=0, mean_overall=50.0, flagged_count=0)


def results_payload(**overrides) -> dict:
    images = [image(flagged=True), image(status="failed", overall_score=None, criteria=[])]
    base = {
        "job_id": str(uuid4()),
        "rubric_id": "default-v1",
        "summary": {
            "images_scored": 1, "mean_overall": 71.0, "flagged_count": 1,
            "score_distribution": [{"bucket": "60-80", "count": 1}],
        },
        "images": images,
    }
    return base | overrides


def test_job_results_valid_json_round_trip():
    results = JobResults.model_validate(results_payload())
    again = JobResults.model_validate_json(results.model_dump_json())
    assert again == results


def test_job_results_summary_must_match_images():
    bad_scored = results_payload()
    bad_scored["summary"]["images_scored"] = 5
    reject(JobResults, bad_scored, "images_scored does not match")
    bad_flagged = results_payload()
    bad_flagged["summary"]["flagged_count"] = 0
    reject(JobResults, bad_flagged, "flagged_count does not match")


# ---- rubrics, errors, health -----------------------------------------------------
def rubric_info(**overrides) -> dict:
    criterion_info = {
        "criterion_id": "contrast", "name": "Contrast", "definition": "d",
        "evaluation_evidence": "e", "method": "cv", "weight": 0.2,
    }
    return {"rubric_id": "default-v1", "name": "MVP rubric", "criteria": [criterion_info]} | overrides


def test_rubric_info_rules():
    RubricInfo.model_validate(rubric_info())
    reject(RubricInfo, rubric_info(criteria=[]), "criteria")
    dup = rubric_info()["criteria"] * 2
    reject(RubricInfo, rubric_info(criteria=dup), "repeat a criterion_id")


def test_error_envelope():
    ok = ErrorResponse.model_validate(
        {"error": {"code": "VALIDATION_ERROR", "message": "Bad payload", "details": [{"loc": "url"}]}}
    )
    assert ok.error.details == [{"loc": "url"}]
    reject(ErrorResponse, {"error": {"code": "SOMETHING_ELSE", "message": "x"}}, "code")
    reject(ErrorResponse, {"error": {"code": "NOT_FOUND", "message": ""}}, "message")


def test_health_response():
    assert HealthResponse(status="ok", version="0.1.0").status == "ok"
    reject(HealthResponse, {"status": "down", "version": "0.1.0"}, "status")


def test_timestamps_are_truncated_to_milliseconds_on_input():
    status = JobStatus.model_validate(job_status())
    assert status.created_at.microsecond == 123000
