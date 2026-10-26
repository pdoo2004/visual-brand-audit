"""POST /api/v1/analyses/urls: submit a public webpage for analysis (SCRUM-178, [STRETCH]).

This endpoint only accepts the submission: it validates the URL, records the job and its
input (`input_type='url'`, `submission_url`, `max_pages`), and returns 202. Image bytes are
downloaded by `brandlens.crawler.downloader.download_images` once a list of image URLs exists
(SCRUM-179). Finding those URLs and starting that download is SCRUM-240, so the job stays
`queued`.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Body, HTTPException, Request
from pydantic import ValidationError

from brandlens.api import db as database
from brandlens.api.routers.jobs import _error, _load_rubric_criteria
from brandlens.api.schemas import ErrorCode, InputType, JobAccepted, UrlSubmission
from brandlens.crawler.public_url import non_public_reason as _non_public_reason

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["analyses"])


@router.post(
    "/analyses/urls",
    status_code=202,
    response_model=JobAccepted,
    summary="Submit a public webpage for analysis [stretch]",
    response_description="Job accepted; poll status_url for progress.",
)
async def submit_url(
    request: Request,
    payload: Annotated[dict[str, Any], Body(description="UrlSubmission JSON")],
) -> JobAccepted:
    db_path: Path = request.app.state.db_path
    rubric_path: Path = request.app.state.rubric_path

    # Validate by hand so errors use the same shape as the upload endpoint.
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

    criteria = submission.criterion_ids or _load_rubric_criteria(rubric_path, submission.rubric_id)

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

    # SCRUM-240: discover image URLs, then brandlens.crawler.downloader.download_images.
    # This request does not fetch anything; the job stays queued.
    log.info("url job %s accepted: %s (max_pages=%s)", job_id, url, submission.max_pages)
    return JobAccepted.for_job(uuid.UUID(job_id), InputType.URL, created_at)
