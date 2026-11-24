"""Serve uploaded / crawled image bytes for UI previews.

GET /api/v1/images/{image_id}/file  →  200 image bytes
"""

from __future__ import annotations

import logging
import mimetypes
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from brandlens.api import db as database
from brandlens.api.routers.jobs import _error
from brandlens.api.schemas import ErrorCode

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["images"])


def _require_uuid(image_id: str) -> None:
    try:
        UUID(image_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=404,
            detail=_error(ErrorCode.NOT_FOUND, f"Image {image_id!r} not found."),
        ) from exc


@router.get(
    "/images/{image_id}/file",
    responses={404: {"description": "Image or file not found"}},
)
def get_image_file(image_id: str, request: Request) -> FileResponse:
    """Return the stored raw image for a results-page thumbnail."""
    _require_uuid(image_id)
    with database.get_conn(request.app.state.db_path) as conn:
        row = database.get_image(conn, image_id)
    if row is None:
        raise HTTPException(
            status_code=404,
            detail=_error(ErrorCode.NOT_FOUND, f"Image {image_id!r} not found."),
        )

    raw = row["raw_path"]
    if not raw:
        raise HTTPException(
            status_code=404,
            detail=_error(ErrorCode.NOT_FOUND, f"No file stored for image {image_id!r}."),
        )

    path = Path(raw).resolve()
    upload_root = Path(request.app.state.upload_dir).resolve()
    try:
        path.relative_to(upload_root)
    except ValueError as exc:
        log.warning("refusing image file outside upload_dir: %s", path)
        raise HTTPException(
            status_code=404,
            detail=_error(ErrorCode.NOT_FOUND, f"No file stored for image {image_id!r}."),
        ) from exc

    if not path.is_file():
        raise HTTPException(
            status_code=404,
            detail=_error(ErrorCode.NOT_FOUND, f"File missing for image {image_id!r}."),
        )

    media_type, _ = mimetypes.guess_type(path.name)
    return FileResponse(
        path,
        media_type=media_type or "application/octet-stream",
        filename=path.name,
        content_disposition_type="inline",
    )
