
"""Lightweight, privacy-safe pipeline stage logging."""

import logging
from contextlib import contextmanager
from time import perf_counter

logger = logging.getLogger("brandlens.pipeline")


@contextmanager
def track_stage(job_id: str, image_id: str, stage: str):
    """Log stage progress, duration, and failures."""

    start = perf_counter()

    logger.info(
        "job=%s image=%s stage=%s status=started",
        job_id,
        image_id,
        stage,
    )

    try:
        yield

    except Exception as exc:
        elapsed_ms = (perf_counter() - start) * 1000

        logger.warning(
            "job=%s image=%s stage=%s status=failed "
            "duration_ms=%.1f error_type=%s",
            job_id,
            image_id,
            stage,
            elapsed_ms,
            type(exc).__name__,
        )
        raise

    else:
        elapsed_ms = (perf_counter() - start) * 1000

        logger.info(
            "job=%s image=%s stage=%s status=completed "
            "duration_ms=%.1f",
            job_id,
            image_id,
            stage,
            elapsed_ms,
        )

"""
TODO:
Wait for [8.2] full pipeline integration to be merged into main
Update local branch with latest main
Inspect updated src/brandlens/api/worker.py
Import track_stage from brandlens.logger
Add logging around preprocessing stages (image loading, filtering, standardization)
Add logging around each CV criterion (brightness, contrast, color palette, framing, sharpness, etc.)
Ensure rejected images and processing failures have clear log entries without exposing sensitive information
Add integration tests verifying image-level progress and failure logging
Run pytest and ruff check .
Execute a representative job containing valid, rejected, and failed images
Capture console logs as Sprint demo evidence
Commit changes, push branch, and create PR
"""