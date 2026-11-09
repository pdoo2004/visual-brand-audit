"""POST /api/v1/analyses/urls: submit public webpage for background analysis."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, Body, HTTPException, Request
from pydantic import ValidationError

from brandlens.api import db as database
from brandlens.api.routers.jobs import _error, _load_rubric_criteria
from brandlens.api.schemas import ErrorCode, InputType, JobAccepted, UrlSubmission
from brandlens.api.url_worker import run_url_job
from brandlens.crawler.public_url import non_public_reason

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["analyses"])

# Keep the original helper available for existing URL-validation tests.
_non_public_reason = non_public_reason


@router.post(
    "/analyses/urls",
    status_code=202,
    response_model=JobAccepted,
    summary="Submit a public webpage for analysis",
    response_description="Job accepted; poll status_url for progress.",
)
async def submit_url(
    request: Request,
    background_tasks: BackgroundTasks,
    payload: Annotated[dict[str, Any], Body(description="UrlSubmission JSON")],
) -> JobAccepted:
    db_path: Path = request.app.state.db_path
    rubric_path: Path = request.app.state.rubric_path

    try:
        submission = UrlSubmission.model_validate(payload)
    except ValidationError as exc:
        first = exc.errors(include_url=False, include_context=False, include_input=False)[0]
        where = ".".join(str(p) for p in first["loc"]) or "body"
        raise HTTPException(
            status_code=422,
            detail=_error(ErrorCode.VALIDATION_ERROR, f"{where}: {first['msg']}"),
        ) from exc

    url = str(submission.url)
    reason = _non_public_reason(url)
    if reason:
        raise HTTPException(status_code=422, detail=_error(ErrorCode.VALIDATION_ERROR, reason))

    # Validate the rubric even when the user supplied a custom criterion subset.
    valid_criteria = _load_rubric_criteria(rubric_path, submission.rubric_id)
    criteria = submission.criterion_ids or valid_criteria
    unknown = set(criteria) - set(valid_criteria)
    if unknown:
        raise HTTPException(
            status_code=422,
            detail=_error(
                ErrorCode.VALIDATION_ERROR,
                "Unknown criterion IDs: " + ", ".join(sorted(unknown)),
            ),
        )

    job_id = str(uuid.uuid4())
    created_at = datetime.now(UTC)
    with database.get_conn(db_path) as conn:
        database.create_job(
            conn,
            job_id=job_id,
            rubric_id=submission.rubric_id,
            input_type=InputType.URL.value,
            submission_url=url,
            max_pages=submission.max_pages,
        )
        database.insert_job_criteria(conn, job_id, criteria)

    background_tasks.add_task(
        run_url_job,
        job_id=job_id,
        url=url,
        max_pages=submission.max_pages,
        db_path=db_path,
        upload_dir=request.app.state.upload_dir,
        processed_dir=request.app.state.processed_dir,
        analyze=getattr(request.app.state, "analyzer", None),
    )
    log.info("URL job %s accepted: %s (max_pages=%s)", job_id, url, submission.max_pages)
    return JobAccepted.for_job(uuid.UUID(job_id), InputType.URL, created_at)
