"""Reviewer feedback on the AI's reasoning (SCRUM-160 / task 7.8).

POST /api/v1/images/{image_id}/feedback  →  201 FeedbackRecord
GET  /api/v1/images/{image_id}/feedback  →  200 list[FeedbackRecord], newest first
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Body, HTTPException, Request
from pydantic import ValidationError

from brandlens.api import db as database
from brandlens.api.routers.jobs import _error
from brandlens.api.schemas import ErrorCode, FeedbackRecord, FeedbackSubmission

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["feedback"])


def _record(row) -> FeedbackRecord:
    return FeedbackRecord(
        feedback_id=UUID(row["feedback_id"]),
        image_id=UUID(row["image_id"]),
        criterion_id=row["criterion_id"],
        verdict=row["verdict"],
        comment=row["comment"],
        created_at=datetime.fromisoformat(row["created_at"]),
    )


def _require_image(conn, image_id: str) -> None:
    """404 for a malformed or unknown image id (no difference to the client)."""
    try:
        UUID(image_id)
    except ValueError:
        found = False
    else:
        found = database.image_exists(conn, image_id)
    if not found:
        raise HTTPException(
            status_code=404,
            detail=_error(ErrorCode.NOT_FOUND, f"Image {image_id!r} not found."),
        )


@router.post(
    "/images/{image_id}/feedback",
    status_code=201,
    response_model=FeedbackRecord,
    summary="Record Agree/Disagree on the AI's reasoning for an image or one criterion",
    responses={404: {"description": "Unknown image_id"}, 422: {"description": "Invalid payload"}},
)
async def submit_feedback(
    image_id: str,
    request: Request,
    payload: Annotated[dict[str, Any], Body(description="FeedbackSubmission JSON")],
) -> FeedbackRecord:
    db_path: Path = request.app.state.db_path

    # Validate by hand so errors use the same shape as the other endpoints.
    try:
        submission = FeedbackSubmission.model_validate(payload)
    except ValidationError as exc:
        first = exc.errors(include_url=False, include_context=False, include_input=False)[0]
        where = ".".join(str(p) for p in first["loc"]) or "body"
        raise HTTPException(
            status_code=422,
            detail=_error(ErrorCode.VALIDATION_ERROR, f"{where}: {first['msg']}"),
        ) from exc

    with database.get_conn(db_path) as conn:
        _require_image(conn, image_id)
        cid = submission.criterion_id
        if cid is not None and not database.image_has_criterion(conn, image_id, cid):
            raise HTTPException(
                status_code=422,
                detail=_error(
                    ErrorCode.VALIDATION_ERROR,
                    f"criterion_id {cid!r} has no result for this image.",
                ),
            )
        row = database.insert_feedback(
            conn,
            image_id=image_id,
            verdict=submission.verdict.value,
            criterion_id=cid,
            comment=submission.comment,
        )

    log.info("feedback %s on image %s (%s)", row["feedback_id"], image_id, submission.verdict)
    return _record(row)


@router.get(
    "/images/{image_id}/feedback",
    response_model=list[FeedbackRecord],
    summary="Feedback history for an image, newest first",
    responses={404: {"description": "Unknown image_id"}},
)
def list_image_feedback(image_id: str, request: Request) -> list[FeedbackRecord]:
    db_path: Path = request.app.state.db_path
    with database.get_conn(db_path) as conn:
        _require_image(conn, image_id)
        rows = database.list_feedback(conn, image_id)
    return [_record(r) for r in rows]
