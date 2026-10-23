"""POST /api/v1/analyses/urls: submit a public webpage for analysis (SCRUM-178, [STRETCH]).

This endpoint only *accepts* the submission: it validates the URL, records the job and its
input (`input_type='url'`, `submission_url`, `max_pages`), and returns 202. The crawler and image
downloader (SCRUM-179 and the crawler work) are not built yet, so the job stays `queued` until
they are wired in at the marked hook below.
"""

from __future__ import annotations

import ipaddress
import logging
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any
from urllib.parse import urlsplit

from fastapi import APIRouter, Body, HTTPException, Request
from pydantic import ValidationError

from brandlens.api import db as database
from brandlens.api.routers.jobs import _error, _load_rubric_criteria
from brandlens.api.schemas import ErrorCode, InputType, JobAccepted, UrlSubmission

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["analyses"])

# Hostnames that can never be a public website.
_BLOCKED_SUFFIXES = (".local", ".localhost", ".internal", ".lan", ".home", ".corp")


def _non_public_reason(url: str) -> str | None:
    """Why `url` cannot be a public website, or None if it looks public.

    A server-side crawler will fetch this URL, so addresses that point back at our own machine
    or private network (SSRF) are refused up front. This is a syntax-level check only: the
    crawler must also re-check the resolved IP address when it actually fetches.
    """
    parts = urlsplit(url)
    if parts.username or parts.password:
        return "URLs with embedded credentials are not allowed."
    host = (parts.hostname or "").rstrip(".").lower()
    if not host:
        return "URL has no host."
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        if host == "localhost" or host.endswith(_BLOCKED_SUFFIXES) or "." not in host:
            return "URL must point to a public website, not a local or internal host."
        return None
    if not ip.is_global:
        return "URL must point to a public website, not a private or reserved IP address."
    return None


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

    # Hook: start the crawl -> download -> preprocess pipeline for `job_id` here once the crawler
    # exists. Until then the job stays `queued`.
    log.info("url job %s accepted: %s (max_pages=%s)", job_id, url, submission.max_pages)
    return JobAccepted.for_job(uuid.UUID(job_id), InputType.URL, created_at)
