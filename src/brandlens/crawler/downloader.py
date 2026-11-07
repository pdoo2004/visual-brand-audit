"""Download a list of public image URLs (SCRUM-179).

One bad URL is logged and skipped. The rest of the list still downloads. Concurrency,
response size, time, and redirects are capped. Page discovery is SCRUM-240.
"""

from __future__ import annotations

import asyncio
import ipaddress
import logging
import socket
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import httpx

from brandlens.crawler.public_url import non_public_reason
from brandlens.preprocessing.image_io import load_image

log = logging.getLogger(__name__)

_USER_AGENT = "BrandLens/0.1 (image-download)"

ResolveFn = Callable[[str, int], list[str]]


class DownloadCode(StrEnum):
    NON_PUBLIC = "non_public"
    UNAVAILABLE = "unavailable"
    HTTP_ERROR = "http_error"
    TOO_LARGE = "too_large"
    UNSUPPORTED_TYPE = "unsupported_type"
    EMPTY = "empty"
    TOO_MANY_REDIRECTS = "too_many_redirects"


@dataclass(frozen=True)
class DownloadSettings:
    """Caps for one batch. Failures inside these caps are logged, not raised."""

    max_concurrency: int = 4
    max_bytes: int = 20 * 1024 * 1024
    timeout_seconds: float = 20.0
    max_redirects: int = 5

    def __post_init__(self) -> None:
        if type(self.max_concurrency) is not int or self.max_concurrency < 1:
            raise ValueError("max_concurrency must be a positive integer.")
        if type(self.max_bytes) is not int or self.max_bytes < 1:
            raise ValueError("max_bytes must be a positive integer.")
        if type(self.timeout_seconds) not in (int, float) or not self.timeout_seconds > 0:
            raise ValueError("timeout_seconds must be positive.")
        if type(self.max_redirects) is not int or self.max_redirects < 0:
            raise ValueError("max_redirects must be a non-negative integer.")


@dataclass(frozen=True)
class DownloadedImage:
    url: str
    path: Path
    nbytes: int


@dataclass(frozen=True)
class DownloadFailure:
    url: str
    code: DownloadCode
    message: str


@dataclass(frozen=True)
class DownloadResult:
    downloaded: list[DownloadedImage]
    failed: list[DownloadFailure]


def _default_resolve(host: str, port: int) -> list[str]:
    infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    return [item[4][0] for item in infos]


def _sniff_extension(data: bytes) -> str | None:
    """File extension for JPEG, PNG, or WebP, judged from the bytes themselves."""
    if data.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return None


def _address_problem(url: str) -> str | None:
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https"):
        return "URL must use http or https."
    return non_public_reason(url)


def _resolution_problem(url: str, resolve: ResolveFn) -> str | None:
    """None when every resolved address is a public IP. Literals are already checked."""
    parts = urlsplit(url)
    host = (parts.hostname or "").rstrip(".").lower()
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        return None
    port = parts.port or (443 if parts.scheme == "https" else 80)
    try:
        addresses = resolve(host, port)
    except OSError as exc:
        return f"Could not resolve host: {exc}"
    if not addresses:
        return "Could not resolve host."
    for raw in addresses:
        try:
            ip = ipaddress.ip_address(raw)
        except ValueError:
            return "Could not resolve host."
        if not ip.is_global:
            return "Host resolved to a private or reserved IP address."
    return None


async def _read_capped(response: httpx.Response, max_bytes: int) -> bytes | None:
    """Body bytes, or None when the response is larger than max_bytes."""
    declared = response.headers.get("content-length")
    if declared is not None:
        try:
            if int(declared) > max_bytes:
                return None
        except ValueError:
            pass
    buf = bytearray()
    async for chunk in response.aiter_bytes():
        buf.extend(chunk)
        if len(buf) > max_bytes:
            return None
    return bytes(buf)


async def _download_one(
    client: httpx.AsyncClient,
    url: str,
    dest_dir: Path,
    index: int,
    settings: DownloadSettings,
    resolve: ResolveFn,
) -> DownloadedImage | DownloadFailure:
    current = url
    for _hop in range(settings.max_redirects + 1):
        problem = _address_problem(current)
        if problem:
            return DownloadFailure(url, DownloadCode.NON_PUBLIC, problem)
        problem = _resolution_problem(current, resolve)
        if problem:
            code = (
                DownloadCode.UNAVAILABLE
                if problem.startswith("Could not resolve")
                else DownloadCode.NON_PUBLIC
            )
            return DownloadFailure(url, code, problem)
        try:
            async with client.stream(
                "GET",
                current,
                timeout=settings.timeout_seconds,
                follow_redirects=False,
            ) as response:
                if response.status_code in {301, 302, 303, 307, 308}:
                    location = response.headers.get("location")
                    if not location:
                        return DownloadFailure(
                            url, DownloadCode.HTTP_ERROR, "Redirect had no Location header."
                        )
                    current = urljoin(current, location)
                    continue
                if response.status_code != 200:
                    return DownloadFailure(
                        url, DownloadCode.HTTP_ERROR, f"HTTP {response.status_code}"
                    )
                data = await _read_capped(response, settings.max_bytes)
        except httpx.HTTPError as exc:
            return DownloadFailure(url, DownloadCode.UNAVAILABLE, f"Download failed: {exc}")
        if data is None:
            return DownloadFailure(
                url,
                DownloadCode.TOO_LARGE,
                f"Image exceeds the {settings.max_bytes} byte limit.",
            )
        if not data:
            return DownloadFailure(url, DownloadCode.EMPTY, "Response body was empty.")
        ext = _sniff_extension(data)
        if ext is None:
            return DownloadFailure(
                url, DownloadCode.UNSUPPORTED_TYPE, "Not a JPEG, PNG, or WebP image."
            )
        path = dest_dir / f"{index:04d}.{ext}"
        path.write_bytes(data)
        try:
            load_image(path)
        except (OSError, ValueError) as exc:
            path.unlink(missing_ok=True)
            return DownloadFailure(url, DownloadCode.UNSUPPORTED_TYPE, str(exc))
        return DownloadedImage(url, path, len(data))
    return DownloadFailure(url, DownloadCode.TOO_MANY_REDIRECTS, "Too many redirects.")


async def download_images(
    urls: list[str],
    dest_dir: Path,
    *,
    settings: DownloadSettings | None = None,
    client: httpx.AsyncClient | None = None,
    resolve: ResolveFn | None = None,
) -> DownloadResult:
    """Download each public image URL into dest_dir.

    Valid JPEG, PNG, and WebP files are saved as ``0000.jpg`` and so on, in input
    order. Invalid, private, and unreachable URLs are logged and returned in
    ``failed``. They do not cancel the other downloads.
    """
    settings = settings or DownloadSettings()
    resolve = resolve or _default_resolve
    dest_dir.mkdir(parents=True, exist_ok=True)
    semaphore = asyncio.Semaphore(settings.max_concurrency)
    owns_client = client is None
    if client is None:
        client = httpx.AsyncClient(
            follow_redirects=False,
            headers={"User-Agent": _USER_AGENT},
            timeout=settings.timeout_seconds,
        )

    async def bounded(index: int, url: str) -> DownloadedImage | DownloadFailure:
        async with semaphore:
            try:
                outcome = await _download_one(client, url, dest_dir, index, settings, resolve)
            except Exception as exc:  # noqa: BLE001
                log.warning("image download failed for %s: %s", url, exc)
                return DownloadFailure(url, DownloadCode.UNAVAILABLE, "Download failed.")
            if isinstance(outcome, DownloadFailure):
                log.warning(
                    "image download skipped %s (%s): %s", url, outcome.code, outcome.message
                )
            return outcome

    try:
        results = await asyncio.gather(*(bounded(i, url) for i, url in enumerate(urls)))
    finally:
        if owns_client:
            await client.aclose()

    downloaded = [item for item in results if isinstance(item, DownloadedImage)]
    failed = [item for item in results if isinstance(item, DownloadFailure)]
    log.info("image download finished: %d saved, %d failed", len(downloaded), len(failed))
    return DownloadResult(downloaded, failed)
