"""URL intake adapter: crawl/download images, then use the shared batch worker.

SCRUM-240: this module deliberately does not preprocess, analyze, or score.
Those steps and result persistence belong to api.worker.run_job.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from brandlens.api import db as database
from brandlens.api.worker import Analyzer, run_job
from brandlens.crawler.deduplicate import unique_downloads
from brandlens.crawler.discovery import DiscoverySettings, discover_images
from brandlens.crawler.downloader import DownloadCode, download_images

log = logging.getLogger(__name__)


async def run_url_job(
    *,
    job_id: str,
    url: str,
    max_pages: int | None,
    db_path: Path,
    upload_dir: Path,
    processed_dir: Path,
    analyze: Analyzer | None = None,
) -> None:
    """Fetch public webpage images and hand each saved file to ``run_job``.

    Runs as a FastAPI background task; a failure in discovery or a webpage
    with no valid images makes the job terminal instead of leaving it queued.
    Files persist in the job's raw folder, as required by the existing worker.
    """
    try:
        with database.get_conn(db_path) as conn:
            database.set_job_status(conn, job_id, "crawling")

        discovery = await discover_images(
            url,
            settings=DiscoverySettings(
                max_pages=max_pages or 1,
                page_follow_mode="pagination",
            ),
        )
        raw_dir = upload_dir / job_id
        downloaded = await download_images(discovery.image_urls, raw_dir)

        unique_images, duplicates = unique_downloads(downloaded.downloaded)

        log.info(
            "URL job %s: %d unique images, %d duplicates skipped",
            job_id,
            len(unique_images),
            len(duplicates),
        )

        image_records: list[tuple[str, Path]] = []

        with database.get_conn(db_path) as conn:
            # Successfully downloaded images enter the analysis pipeline.
            for ordinal, image in enumerate(unique_images):
                image_id = database.create_image(
                    conn,
                    job_id=job_id,
                    ordinal=ordinal,
                    source=image.url,
                    raw_path=str(image.path),
                )
                image_records.append((image_id, image.path))

            # Failed downloads remain visible in the results,
            # but do not enter preprocessing or analysis.
            for ordinal, failure in enumerate(
                downloaded.failed, start=len(unique_images)
            ):
                image_id = database.create_image(
                    conn,
                    job_id=job_id,
                    ordinal=ordinal,
                    source=failure.url,
                )

                too_large = failure.code == DownloadCode.TOO_LARGE

                database.save_image_result(
                    conn,
                    image_id,
                    status="failed",
                    error_code=(
                        "FILE_TOO_LARGE"
                        if too_large
                        else f"DOWNLOAD_{failure.code.upper()}"
                    ),
                    error_message=(
                        "Image exceeds the 10 MB download limit."
                        if too_large
                        else failure.message
                    ),
                )

        # If nothing was downloaded successfully, end the job.
        # Failed image records remain available in the results API.
        if not unique_images:
            reason = (
                "Image exceeds the 10 MB download limit."
                if downloaded.failed and downloaded.failed[0].code == DownloadCode.TOO_LARGE
                else downloaded.failed[0].message
                if downloaded.failed
                else discovery.failed_pages[0].reason
                if discovery.failed_pages
                else "No supported images could be downloaded from the submitted webpage."
            )

            with database.get_conn(db_path) as conn:
                database.set_job_status(
                    conn,
                    job_id,
                    "failed",
                    error_code="CRAWL_FAILED",
                    error_message=f"URL analysis could not obtain images: {reason}",
                )
            return

        log.info(
            "URL job %s: %d pages, %d downloaded, %d rejected",
            job_id,
            len(discovery.pages_visited),
            len(downloaded.downloaded),
            len(downloaded.failed),
        )
        # The worker is synchronous. Run it off the event loop so polling and
        # other HTTP requests can proceed while the batch is being scored.
        await asyncio.to_thread(
            run_job,
            job_id=job_id,
            image_records=image_records,
            db_path=db_path,
            processed_dir=processed_dir / job_id,
            analyze=analyze,
        )
    except Exception as exc:
        log.exception("URL job %s failed before analysis", job_id)
        with database.get_conn(db_path) as conn:
            database.set_job_status(
                conn, job_id, "failed", error_code="INTERNAL_ERROR",
                error_message=f"URL job failed: {type(exc).__name__}",
            )
