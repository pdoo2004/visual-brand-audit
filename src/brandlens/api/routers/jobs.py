"""Upload submission and job-status polling endpoints.

POST /api/v1/analyses/uploads  →  202 JobAccepted
GET  /api/v1/jobs/{job_id}     →  200 JobStatus
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from fastapi import (
    APIRouter,
    BackgroundTasks,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
)
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
    RejectedUpload,
    UploadRequest,
)
from brandlens.api.worker import run_job

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["jobs"])

_MAX_FILE_BYTES = 20 * 1024 * 1024  # 20 MB


def _sniff_is_image(head: bytes) -> bool:
    """True for JPEG/PNG/WebP, judged by the file's own bytes (client Content-Type is not trusted)."""
    if head.startswith((b"\xff\xd8\xff", b"\x89PNG\r\n\x1a\n")):
        return True
    return head[:4] == b"RIFF" and head[8:12] == b"WEBP"


def _display_name(name: str | None) -> str:
    """Filename safe to show and to use on disk: no directories, no odd characters."""
    base = re.split(r"[\\/]", name or "")[-1]
    return re.sub(r"[^\w.\- ]", "_", base).strip()[:150] or "unnamed"


_REJECT_STATUS = {
    ErrorCode.FILE_TOO_LARGE: 413,
    ErrorCode.UNSUPPORTED_FILE_TYPE: 415,
}


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
    files: list[UploadFile] = File(..., description="JPEG, PNG, or WEBP images"),  # noqa: B008
    rubric_id: str = Form(..., description="Rubric identifier, e.g. 'default-v1-draft'"),
    criterion_ids: list[str] | None = Form(  # noqa: B008
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

    # Validate each file on its own: keep the good ones, report the bad ones.
    pending: list[tuple[str, bytes]] = []  # (display filename, data)
    rejected: list[RejectedUpload] = []
    for f in files:
        name = _display_name(f.filename)
        data = await f.read(_MAX_FILE_BYTES + 1)
        if len(data) > _MAX_FILE_BYTES:
            rejected.append(RejectedUpload(
                filename=name,
                code=ErrorCode.FILE_TOO_LARGE,
                message="File exceeds the 20 MB per-file limit.",
            ))
        elif not data:
            rejected.append(RejectedUpload(
                filename=name, code=ErrorCode.VALIDATION_ERROR, message="File is empty."
            ))
        elif not _sniff_is_image(data[:16]):
            rejected.append(RejectedUpload(
                filename=name,
                code=ErrorCode.UNSUPPORTED_FILE_TYPE,
                message="Not a supported image. Use JPEG, PNG, or WebP.",
            ))
        else:
            pending.append((name, data))

    if not pending:
        first = rejected[0]
        body = ErrorBody(
            code=first.code,
            message=f"No valid images in the upload. {first.filename!r}: {first.message}",
            details=[r.model_dump(mode="json") for r in rejected],
        ).model_dump(mode="json")
        raise HTTPException(status_code=_REJECT_STATUS.get(first.code, 422), detail=body)

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

    log.info(
        "job %s accepted: %d image(s), %d rejected, rubric %s",
        job_id, len(image_records), len(rejected), opts.rubric_id,
    )
    return JobAccepted.for_job(UUID(job_id), InputType.UPLOAD, created_at, rejected=rejected)


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
