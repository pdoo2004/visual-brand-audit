"""Standalone webpage -> image discovery/download -> existing score_photo demo.

Images are fetched for analysis, but saving them permanently is optional.
There are no API, database, worker, or additional scoring implementations here.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

from brandlens.crawler.deduplicate import unique_downloads
from brandlens.crawler.discovery import (
    DiscoveryResult,
    DiscoverySettings,
    discover_images,
)
from brandlens.crawler.downloader import DownloadFailure, download_images
from brandlens.pipeline import score_photo
from brandlens.preprocessing.image_io import load_image


@dataclass
class CrawlerPipelineResult:
    """Images, scores, measurements, and crawl diagnostics."""

    images: list[dict]
    discovery: DiscoveryResult
    download_failures: list[DownloadFailure]
    duplicate_count: int = 0

async def run_crawler_pipeline(
    url: str,
    configuration: tuple,
    *,
    save_images: bool = False,
    output_dir: Path | None = None,
    discovery_settings: DiscoverySettings | None = None,
    criterion_ids: list[str] | None = None,
    vlm_client=None,
    subject_detector=None,
) -> CrawlerPipelineResult:
    """Discover, fetch, and score photos; optionally retain the original files.

    When save_images is False, download_images uses a temporary directory that
    is removed before return. Small Pillow previews and the complete scoring
    output remain available in the returned object for notebook inspection.
    """
    if save_images and output_dir is None:
        raise ValueError("output_dir is required when save_images=True")

    discovery = await discover_images(url, settings=discovery_settings)
    photos: list[dict] = []

    with TemporaryDirectory(prefix="brandlens-crawler-") as temp_dir:
        destination = Path(output_dir) if save_images else Path(temp_dir)
        downloads = await download_images(discovery.image_urls, destination)
        unique_images, duplicates = unique_downloads(downloads.downloaded)

        for item in unique_images:
            row = {
                "url": item.url,
                "path": item.path if save_images else None,
                "preview": None,
                "score": None,
                "cv_results": {},
                "vlm_results": {},
                "error": None,
            }
            image = None
            try:
                image = load_image(item.path)
                preview = image.copy()
                preview.thumbnail((640, 480))
                row["preview"] = preview

                score, cv_results, vlm_results = score_photo(
                    image,
                    configuration,
                    vlm_client=vlm_client,
                    criterion_ids=criterion_ids,
                    subject_detector=subject_detector,
                )
                row["score"] = score
                row["cv_results"] = cv_results
                row["vlm_results"] = vlm_results
            except Exception as exc:  # noqa: BLE001 - failures are isolated by image
                row["error"] = f"{type(exc).__name__}: {exc}"
            finally:
                if image is not None:
                    image.close()
            photos.append(row)

    return CrawlerPipelineResult(
        images=photos,
        discovery=discovery,
        download_failures=downloads.failed,
        duplicate_count=len(duplicates),
    )
