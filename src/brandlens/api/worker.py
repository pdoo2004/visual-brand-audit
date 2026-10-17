"""Background job worker: runs the analysis pipeline for one job.

Executed in a background thread by FastAPI's BackgroundTasks. Each image is
processed independently so one failure does not abort the rest of the batch.

Scoring (CV measurements + VLM tone) is implemented in later tasks. Images
that pass preprocessing are marked scored with overall_score=0 as a stub;
those values will be replaced once the scoring engines are wired in.
"""

from __future__ import annotations

import logging
from pathlib import Path

from brandlens.api import db as database
from brandlens.preprocessing.image_io import load_image
from brandlens.preprocessing.photo_filter import FilterSettings, filter_photo
from brandlens.preprocessing.standardization import (
    StandardizationSettings,
    standardize_image,
)

log = logging.getLogger(__name__)

_FILTER = FilterSettings()
_STD = StandardizationSettings(max_size=(2048, 2048))


def run_job(
    job_id: str,
    image_records: list[tuple[str, Path]],
    db_path: Path,
    processed_dir: Path,
) -> None:
    """Preprocess every image in the job and update DB status throughout.

    Args:
        job_id: UUID string for the job row.
        image_records: List of (image_id, raw_path) pairs in ordinal order.
        db_path: Path to the SQLite database file.
        processed_dir: Directory to write standardized images into.
    """
    processed_dir.mkdir(parents=True, exist_ok=True)
    had_error = False

    with database.get_conn(db_path) as conn:
        database.set_job_status(conn, job_id, "preprocessing")

    for image_id, raw_path in image_records:
        try:
            image = load_image(raw_path)
        except ValueError as exc:
            reason = _load_reject_reason(str(exc))
            if reason:
                _mark_filtered(db_path, image_id, reason)
            else:
                _mark_failed(db_path, image_id, "LOAD_ERROR", str(exc))
                had_error = True
            continue
        except Exception as exc:  # noqa: BLE001
            _mark_failed(db_path, image_id, "LOAD_ERROR", str(exc))
            had_error = True
            log.warning("job %s image %s: load failed: %s", job_id, image_id, exc)
            continue

        filtered = filter_photo(image, _FILTER)
        if filtered is None:
            reason = _filter_reject_reason(image)
            _mark_filtered(db_path, image_id, reason)
            continue

        try:
            standardized = standardize_image(filtered, _STD)
        except Exception as exc:  # noqa: BLE001
            _mark_failed(db_path, image_id, "STANDARDIZE_ERROR", str(exc))
            had_error = True
            log.warning("job %s image %s: standardization failed: %s", job_id, image_id, exc)
            continue

        out_path = processed_dir / f"{image_id}.png"
        standardized.save(out_path, format="PNG")

        with database.get_conn(db_path) as conn:
            # overall_score=0 is a placeholder; CV + VLM scoring replaces this.
            database.set_image_done(
                conn,
                image_id,
                status="scored",
                width=standardized.width,
                height=standardized.height,
                processed_path=str(out_path),
                overall_score=0.0,
                flagged=0,
            )

    final = "completed_with_errors" if had_error else "completed"
    with database.get_conn(db_path) as conn:
        database.set_job_status(conn, job_id, final)

    log.info("job %s → %s (%d images)", job_id, final, len(image_records))


def _load_reject_reason(message: str) -> str | None:
    msg = message.lower()
    if "animated" in msg or "multi-frame" in msg:
        return "animated"
    if "pixels" in msg and "exceed" in msg:
        return "too_many_pixels"
    if "format" in msg or "cannot identify" in msg:
        return "unsupported_format"
    return None


def _filter_reject_reason(image) -> str:
    w, h = image.size
    short, long = min(w, h), max(w, h)
    if short < _FILTER.min_short_side:
        return "too_small"
    if long / short > _FILTER.max_aspect_ratio:
        return "extreme_aspect_ratio"
    return "unprocessable"


def _mark_filtered(db_path: Path, image_id: str, reason: str) -> None:
    with database.get_conn(db_path) as conn:
        database.set_image_done(conn, image_id, status="filtered_out", reject_reason=reason)


def _mark_failed(db_path: Path, image_id: str, code: str, message: str) -> None:
    with database.get_conn(db_path) as conn:
        database.set_image_done(conn, image_id, status="failed",
                                error_code=code, error_message=message)
