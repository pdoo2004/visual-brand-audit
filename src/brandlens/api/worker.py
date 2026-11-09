"""Background job worker: runs the analysis pipeline for one batch of images.

Executed in a background thread by FastAPI's BackgroundTasks (SCRUM-154). This is
the batch orchestrator (SCRUM-167): it takes every image in a job, runs each one
through the pipeline exactly once, stores each image's outcome as soon as it is
known, and finishes the job with a status that reflects the whole batch.

Rules the orchestrator keeps:

* Each image is independent. A failure on one image (including an unexpected
  exception) marks only that image ``failed``; the rest of the batch still runs.
* Each image is processed once. An image that already has a final status is
  skipped, so re-running a job never scores the same image twice.
* Each outcome is saved in its own transaction, so progress polling and partial
  results are accurate while the batch is still running.
* The job ends ``completed`` when every image scored or was filtered out,
  ``completed_with_errors`` when at least one image failed or only partly scored,
  and ``failed`` only when the batch itself could not run.

The analysis stage (CV measurements + VLM tone + scoring, SCRUM-166) plugs in
through the ``analyze`` argument. Until it is wired in, ``placeholder_analyze``
keeps the earlier behaviour: images that pass preprocessing are marked scored
with ``overall_score = 0``.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from PIL import Image

from brandlens.api import db as database
from brandlens.logger import image_logging_context, log_image_event, track_current_stage
from brandlens.preprocessing.image_io import load_image
from brandlens.preprocessing.photo_filter import FilterSettings, filter_reject_reason
from brandlens.preprocessing.preprocessor import preprocess_image
from brandlens.preprocessing.standardization import StandardizationSettings

log = logging.getLogger(__name__)

_FILTER = FilterSettings()
_STD = StandardizationSettings(max_size=(2048, 2048))


@dataclass(frozen=True)
class ImageAnalysis:
    """What the analysis stage returns for one preprocessed image.

    ``status`` is ``scored`` (every selected criterion scored), ``partial``
    (some criteria unavailable, e.g. the model timed out) or ``failed``.
    ``criteria`` holds one mapping per criterion in the shape accepted by
    ``db.save_image_result``.
    """

    status: str
    overall_score: float | None = None
    flagged: bool = False
    criteria: Sequence[Mapping[str, Any]] = field(default_factory=tuple)
    measurements: Mapping[str, Any] | None = None
    error_code: str | None = None
    error_message: str | None = None


# (standardized image, selected criterion ids) -> analysis. Raising is allowed:
# the orchestrator turns an exception into a failed image.
Analyzer = Callable[[Image.Image, Sequence[str]], ImageAnalysis]


def placeholder_analyze(image: Image.Image, criterion_ids: Sequence[str]) -> ImageAnalysis:
    """Stand-in until CV + VLM scoring is wired in (SCRUM-166)."""
    return ImageAnalysis(status="scored", overall_score=0.0, flagged=False)


def run_job(
    job_id: str,
    image_records: list[tuple[str, Path]],
    db_path: Path,
    processed_dir: Path,
    analyze: Analyzer | None = None,
) -> None:
    """Run every image in the job through the pipeline and finish the job.

    Args:
        job_id: UUID string for the job row.
        image_records: List of (image_id, raw_path) pairs in ordinal order.
        db_path: Path to the SQLite database file.
        processed_dir: Directory to write standardized images into.
        analyze: Analysis stage; defaults to ``placeholder_analyze``.
    """
    try:
        _run_batch(job_id, image_records, db_path, processed_dir, analyze or placeholder_analyze)
    except Exception as exc:  # noqa: BLE001 - prevent unexpected batch failures from escaping
        log.warning(
            "job %s: batch could not run; error_type=%s",
            job_id,
            type(exc).__name__,
        )
        with database.get_conn(db_path) as conn:
            database.set_job_status(
                conn, job_id, "failed", error_code="INTERNAL_ERROR",
                error_message=f"The analysis batch stopped unexpectedly: {type(exc).__name__}",
            )


def _run_batch(
    job_id: str,
    image_records: list[tuple[str, Path]],
    db_path: Path,
    processed_dir: Path,
    analyze: Analyzer,
) -> None:
    processed_dir.mkdir(parents=True, exist_ok=True)

    with database.get_conn(db_path) as conn:
        database.set_job_status(conn, job_id, "preprocessing")
        criterion_ids = database.get_job_criterion_ids(conn, job_id)
        already_done = database.get_finished_image_ids(conn, job_id)

    outcomes: dict[str, str] = {}
    stage = _Stage(job_id, db_path)
    for image_id, raw_path in image_records:
        if image_id in already_done:
            log.info("job %s image %s already has a result; skipping", job_id, image_id)
            continue
        with image_logging_context(job_id, image_id):
            try:
                status = _process_image(
                    job_id, image_id, raw_path, db_path, processed_dir, criterion_ids, analyze, stage
                )
            except Exception as exc:  # noqa: BLE001 - one bad image must not stop the batch
                log.warning("job %s image %s: unexpected error: %s", job_id, image_id, exc)
                _mark_failed(db_path, image_id, "INTERNAL_ERROR", f"{type(exc).__name__}: {exc}")
                status = "failed"

            log_image_event("image", status)
        outcomes[image_id] = status

    # Judge the whole job from every stored image status. Images finished in an earlier
    # run were skipped above, so this run's own outcomes alone would hide their failures.
    with database.get_conn(db_path) as conn:
        stored = database.get_job_image_statuses(conn, job_id)
        degraded = any(s in {"failed", "partial"} for s in stored.values())
        final = "completed_with_errors" if degraded else "completed"
        database.set_job_status(conn, job_id, final)

    log.info(
        "job %s → %s (%d processed now; all images: %s)",
        job_id, final, len(outcomes), _tally(stored),
    )


class _Stage:
    """Moves the job to 'analyzing' the first time an image reaches that stage."""

    def __init__(self, job_id: str, db_path: Path) -> None:
        self._job_id = job_id
        self._db_path = db_path
        self._analyzing = False

    def enter_analysis(self) -> None:
        if self._analyzing:
            return
        with database.get_conn(self._db_path) as conn:
            database.set_job_status(conn, self._job_id, "analyzing")
        self._analyzing = True


def _process_image(
    job_id: str,
    image_id: str,
    raw_path: Path,
    db_path: Path,
    processed_dir: Path,
    criterion_ids: Sequence[str],
    analyze: Analyzer,
    stage: _Stage,
) -> str:
    """Preprocess, analyze and store one image. Returns its final status."""
    try:
        with track_current_stage("image_loading"):
            image = load_image(raw_path)
    except ValueError as exc:
        reason = _load_reject_reason(str(exc))
        if reason:
            _mark_filtered(db_path, image_id, reason)
            log_image_event("image", "filtered_out", reason=reason)
            return "filtered_out"
        _mark_failed(db_path, image_id, "LOAD_ERROR", str(exc))
        return "failed"
    except Exception as exc:  # noqa: BLE001
        _mark_failed(db_path, image_id, "LOAD_ERROR", str(exc))
        log.warning(
            "job %s image %s: load failed; error_type=%s",
            job_id, image_id, type(exc).__name__,
        )
        return "failed"

    # Filtering and standardizing live in brandlens.preprocessing; the worker
    # only decides what to record. Analysis receives the standardized image and
    # must not preprocess it again.
    try:
        standardized = preprocess_image(image, _FILTER, _STD)
    except Exception as exc:  # noqa: BLE001
        _mark_failed(db_path, image_id, "PREPROCESS_ERROR", str(exc))
        log.warning(
            "job %s image %s: preprocessing failed; error_type=%s",
            job_id, image_id, type(exc).__name__,
        )
        return "failed"
    if standardized is None:
        reason = filter_reject_reason(image, _FILTER) or "unprocessable"
        _mark_filtered(db_path, image_id, reason)
        log_image_event("image", "filtered_out", reason=reason)
        return "filtered_out"

    out_path = processed_dir / f"{image_id}.png"
    standardized.save(out_path, format="PNG")

    stage.enter_analysis()
    try:
        with track_current_stage("analysis"):
            result = analyze(standardized, criterion_ids)
    except Exception as exc:  # noqa: BLE001 - analysis failures are per image
        log.warning(
            "job %s image %s: analysis failed; error_type=%s",
            job_id, image_id, type(exc).__name__,
        )
        with database.get_conn(db_path) as conn:
            database.save_image_result(
                conn, image_id, status="failed",
                width=standardized.width, height=standardized.height,
                processed_path=str(out_path),
                error_code="ANALYSIS_ERROR", error_message=str(exc) or type(exc).__name__,
            )
        return "failed"

    with database.get_conn(db_path) as conn:
        database.save_image_result(
            conn, image_id,
            status=result.status,
            overall_score=result.overall_score,
            flagged=result.flagged,
            criteria=result.criteria,
            measurements=result.measurements,
            width=standardized.width,
            height=standardized.height,
            processed_path=str(out_path),
            error_code=result.error_code,
            error_message=result.error_message,
        )
    return result.status


def _tally(outcomes: Mapping[str, str]) -> str:
    counts: dict[str, int] = {}
    for status in outcomes.values():
        counts[status] = counts.get(status, 0) + 1
    return ", ".join(f"{n} {s}" for s, n in sorted(counts.items())) or "none"


def _load_reject_reason(message: str) -> str | None:
    msg = message.lower()
    if "animated" in msg or "multi-frame" in msg:
        return "animated"
    if "pixels" in msg and "exceed" in msg:
        return "too_many_pixels"
    if "format" in msg or "cannot identify" in msg:
        return "unsupported_format"
    return None


def _mark_filtered(db_path: Path, image_id: str, reason: str) -> None:
    with database.get_conn(db_path) as conn:
        database.save_image_result(conn, image_id, status="filtered_out", reject_reason=reason)


def _mark_failed(db_path: Path, image_id: str, code: str, message: str) -> None:
    with database.get_conn(db_path) as conn:
        database.save_image_result(
            conn, image_id, status="failed", error_code=code, error_message=message
        )
