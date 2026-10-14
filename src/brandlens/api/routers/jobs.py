"""Upload submission and job-status polling endpoints.

POST /api/v1/analyses/uploads  →  202 JobAccepted
GET  /api/v1/jobs/{job_id}     →  200 JobStatus
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, Request, UploadFile
from pydantic import ValidationError

from brandlens.api import db as database
from brandlens.api.schemas import (
    ErrorBody,
    ErrorCode,
    InputType,
    JobAccepted,
    JobProgress,
    JobState,
    JobStatus,
    UploadRequest,
)
from brandlens.api.worker import run_job

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["jobs"])

_MAX_FILE_BYTES = 20 * 1024 * 1024  # 20 MB
_ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}


def _load_rubric_criteria(rubric_path: Path, rubric_id: str) -> list[str]:
    """Return criterion_ids from the rubric JSON, or raise 422 if rubric not found."""
    try:
        rubric = json.loads(rubric_path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=500,
            detail=_error(ErrorCode.INTERNAL_ERROR, f"Could not read rubric file: {exc}"),
        )
    if rubric.get("rubric_id") != rubric_id:
        raise HTTPException(
            status_code=422,
            detail=_error(
                ErrorCode.VALIDATION_ERROR,
                f"rubric_id {rubric_id!r} not found. Available: {rubric['rubric_id']!r}",
            ),
        )
    return [c["criterion_id"] for c in rubric.get("criteria", [])]


def _error(code: ErrorCode, message: str) -> dict:
    return ErrorBody(code=code, message=message).model_dump()


@router.post(
    "/analyses/uploads",
    status_code=202,
    response_model=JobAccepted,
    summary="Submit images for brand analysis",
    response_description="Job accepted; poll status_url for progress.",
)
async def submit_upload(
    request: Request,
    background_tasks: BackgroundTasks,
    files: list[UploadFile] = File(..., description="JPEG, PNG, or WEBP images"),
    rubric_id: str = Form(..., description="Rubric identifier, e.g. 'default-v1-draft'"),
    criterion_ids: list[str] | None = Form(
        default=None,
        description="Criterion subset to evaluate (omit to use all rubric criteria)",
    ),
) -> JobAccepted:
    db_path: Path = request.app.state.db_path
    upload_dir: Path = request.app.state.upload_dir
    processed_dir: Path = request.app.state.processed_dir
    rubric_path: Path = request.app.state.rubric_path

    # Validate non-file form fields with the existing Pydantic schema.
    try:
        opts = UploadRequest(
            rubric_id=rubric_id,
            criterion_ids=criterion_ids or None,
        )
    except ValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail=_error(ErrorCode.VALIDATION_ERROR, str(exc)),
        )

    if not files:
        raise HTTPException(
            status_code=422,
            detail=_error(ErrorCode.VALIDATION_ERROR, "At least one file is required."),
        )

    # Validate and buffer each upload before touching the database.
    pending: list[tuple[str, bytes]] = []  # (filename, data)
    for f in files:
        if f.content_type not in _ALLOWED_CONTENT_TYPES:
            raise HTTPException(
                status_code=422,
                detail=_error(
                    ErrorCode.UNSUPPORTED_FILE_TYPE,
                    f"{f.filename!r}: unsupported content type {f.content_type!r}.",
                ),
            )
        data = await f.read()
        if len(data) > _MAX_FILE_BYTES:
            raise HTTPException(
                status_code=413,
                detail=_error(
                    ErrorCode.FILE_TOO_LARGE,
                    f"{f.filename!r} exceeds the 20 MB per-file limit.",
                ),
            )
        pending.append((f.filename or f"file_{len(pending)}", data))

    # Resolve criteria — rubric default when caller omits criterion_ids.
    criteria = opts.criterion_ids or _load_rubric_criteria(rubric_path, opts.rubric_id)

    # Generate job UUID upfront so we can use it as the upload subdirectory.
    job_id = str(uuid.uuid4())
    job_raw_dir = upload_dir / job_id
    job_raw_dir.mkdir(parents=True, exist_ok=True)

    # Save files to disk under the job directory.
    saved: list[tuple[str, Path]] = []  # (source string, raw_path)
    for ordinal, (filename, data) in enumerate(pending):
        raw_path = job_raw_dir / f"{ordinal:04d}_{filename}"
        raw_path.write_bytes(data)
        saved.append((f"upload:{filename}", raw_path))

    # Insert job, criteria, and image rows inside a single transaction.
    created_at = datetime.now(UTC)
    with database.get_conn(db_path) as conn:
        database.create_job(conn, job_id=job_id, rubric_id=opts.rubric_id)
        database.insert_job_criteria(conn, job_id, criteria)
        image_records: list[tuple[str, Path]] = []
        for ordinal, (source, raw_path) in enumerate(saved):
            image_id = database.create_image(
                conn,
                job_id=job_id,
                ordinal=ordinal,
                source=source,
                raw_path=str(raw_path),
            )
            image_records.append((image_id, raw_path))

    background_tasks.add_task(
        run_job,
        job_id=job_id,
        image_records=image_records,
        db_path=db_path,
        processed_dir=processed_dir / job_id,
    )

    log.info("job %s accepted: %d image(s), rubric %s", job_id, len(image_records), opts.rubric_id)
    return JobAccepted.for_job(UUID(job_id), InputType.UPLOAD, created_at)


@router.get(
    "/jobs/{job_id}",
    response_model=JobStatus,
    summary="Poll job status and progress",
)
def get_job_status(job_id: str, request: Request) -> JobStatus:
    db_path: Path = request.app.state.db_path

    try:
        UUID(job_id)
    except ValueError:
        raise HTTPException(
            status_code=404,
            detail=_error(ErrorCode.NOT_FOUND, f"Job {job_id!r} not found."),
        )

    with database.get_conn(db_path) as conn:
        row = database.query_job_progress(conn, job_id)

    if row is None:
        raise HTTPException(
            status_code=404,
            detail=_error(ErrorCode.NOT_FOUND, f"Job {job_id!r} not found."),
        )

    error: ErrorBody | None = None
    if row["status"] == JobState.FAILED:
        code_str = row["error_code"]
        try:
            code = ErrorCode(code_str)
        except ValueError:
            code = ErrorCode.INTERNAL_ERROR
        error = ErrorBody(
            code=code,
            message=row["error_message"] or "Job failed.",
        )

    return JobStatus(
        job_id=UUID(job_id),
        status=JobState(row["status"]),
        progress=JobProgress(
            images_total=row["images_total"] or 0,
            images_done=row["images_done"] or 0,
            images_failed=row["images_failed"] or 0,
        ),
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
        error=error,
    )
