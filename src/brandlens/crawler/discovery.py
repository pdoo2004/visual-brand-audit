"""Bounded public-webpage image discovery; no image downloads or analysis."""
from __future__ import annotations

import logging
import re
from collections import deque
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import parse_qs, urldefrag, urljoin, urlsplit

import httpx

from brandlens.crawler.downloader import (
    ResolveFn,
    _address_problem,
    _default_resolve,
    _read_capped,
    _resolution_problem,
)

log = logging.getLogger(__name__)
_REDIRECTS = {301, 302, 303, 307, 308}
_SKIP = (".svg", ".gif", ".ico", ".css", ".js", ".pdf", ".zip", ".mp4")
_IMAGES = (".jpg", ".jpeg", ".png", ".webp")


@dataclass(frozen=True)
class DiscoverySettings:
    max_pages: int = 1
    max_images: int = 30
    max_html_bytes: int = 2 * 1024 * 1024
    timeout_seconds: float = 15.0
    max_redirects: int = 5
    page_follow_mode: str = "all"  # "all" or "pagination"

    def __post_init__(self) -> None:
        for key in ("max_pages", "max_images", "max_html_bytes"):
            val = getattr(self, key)
            if type(val) is not int or val < 1:
                raise ValueError(f"{key} must be a positive integer")
        if self.max_pages > 50:
            raise ValueError("max_pages cannot exceed 50")
        if type(self.max_redirects) is not int or self.max_redirects < 0:
            raise ValueError("max_redirects must be a nonnegative integer")
        if type(self.timeout_seconds) not in (int, float) or self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if self.page_follow_mode not in {"all", "pagination"}:
            raise ValueError(
                "page_follow_mode must be 'all' or 'pagination'"
            )

@dataclass(frozen=True)
class PageFailure:
    url: str
    reason: str


@dataclass(frozen=True)
class DiscoveryResult:
    image_urls: list[str]
    pages_visited: list[str]
    failed_pages: list[PageFailure]


class _Parser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.images: list[str] = []
        self.links: list[str] = []
        self.pagination_links: list[str] = []
        self.base_href: str | None = None
        self._anchor_href: str | None = None
        self._anchor_text: list[str] = []

    @staticmethod
    def _srcset(value: str | None) -> str | None:
        if not value:
            return None
        candidates = [part.strip().split()[0] for part in value.split(",") if part.strip()]
        return candidates[-1] if candidates else None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = dict(attrs)
        if tag == "base" and self.base_href is None:
            self.base_href = a.get("href")
        elif tag == "img":
            src = (self._srcset(a.get("data-srcset"))
                   or self._srcset(a.get("srcset"))
                   or a.get("data-src") or a.get("data-original")
                   or a.get("data-lazy-src") or a.get("src"))
            if src:
                self.images.append(src)
        elif tag == "source":
            src = self._srcset(a.get("data-srcset") or a.get("srcset"))
            if src:
                self.images.append(src)
        elif tag == "meta":
            if (a.get("property") or a.get("name") or "").lower() in {
                "og:image", "twitter:image"
            } and a.get("content"):
                self.images.append(a["content"])
        elif tag == "a" and a.get("href"):
            href = a["href"]
            self.links.append(href)

            rel = (a.get("rel") or "").lower().split()
            if "next" in rel or _is_pagination_url(href):
                self.pagination_links.append(href)

            self._anchor_href = href
            self._anchor_text = []
        
    def handle_data(self, data: str) -> None:
        if self._anchor_href is not None:
            self._anchor_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._anchor_href is not None:
            label = "".join(self._anchor_text).strip().lower()

            if label in {"next", "next page", "older", "›", "»"}:
                self.pagination_links.append(self._anchor_href)

            self._anchor_href = None
            self._anchor_text = []

def _is_pagination_url(href: str) -> bool:
    """Recognize common static HTML pagination patterns."""
    parts = urlsplit(href)

    query = parse_qs(parts.query)
    if "page" in query:
        return any(
            value.isdigit()
            for value in query["page"]
        )

    return bool(
        re.search(r"/page/\d+/?$", parts.path, re.IGNORECASE)
        or re.search(r"/next/?$", parts.path, re.IGNORECASE)
    )
    
def _absolute(value: str, base: str) -> str | None:
    try:
        value = urldefrag(urljoin(base, value.strip())).url
        return value if _address_problem(value) is None else None
    except ValueError:
        return None


async def _get_page(
    client: httpx.AsyncClient, url: str, settings: DiscoverySettings, resolve: ResolveFn
) -> tuple[str, str]:
    current = url
    for _ in range(settings.max_redirects + 1):
        problem = _address_problem(current) or _resolution_problem(current, resolve)
        if problem:
            raise ValueError(problem)
        async with client.stream("GET", current, follow_redirects=False,
                                 timeout=settings.timeout_seconds) as response:
            if response.status_code in _REDIRECTS:
                location = response.headers.get("location")
                if not location:
                    raise ValueError("Redirect missing Location")
                current = urljoin(current, location)
                continue
            if response.status_code != 200:
                raise ValueError(f"HTTP {response.status_code}")
            ctype = response.headers.get("content-type", "").lower()
            if ctype and not any(t in ctype for t in ("text/html", "application/xhtml+xml")):
                raise ValueError(f"Not HTML: {ctype}")
            data = await _read_capped(response, settings.max_html_bytes)
            if data is None:
                raise ValueError("HTML size limit exceeded")
            return data.decode("utf-8", errors="replace"), current
    raise ValueError("Too many page redirects")


async def discover_images(
    url: str, *, settings: DiscoverySettings | None = None,
    client: httpx.AsyncClient | None = None, resolve: ResolveFn | None = None,
) -> DiscoveryResult:
    """Return unique image URLs found on up to max_pages same-host HTML pages.

    HTTP clients and DNS resolver can be injected for deterministic tests.
    Static HTML only; image validation happens in the existing downloader.
    """
    settings = settings or DiscoverySettings()
    resolve = resolve or _default_resolve
    invalid = _address_problem(url)
    if invalid:
        raise ValueError(invalid)
    owned = client is None
    if client is None:
        client = httpx.AsyncClient(follow_redirects=False,
                                   headers={"User-Agent": "BrandLens/0.1"})
    queue = deque([url])
    seen_pages: set[str] = set()
    seen_images: set[str] = set()
    images: list[str] = []
    visited: list[str] = []
    failures: list[PageFailure] = []
    host = (urlsplit(url).hostname or "").lower()
    try:
        while queue and len(visited) + len(failures) < settings.max_pages:
            page_url = queue.popleft()
            if page_url in seen_pages:
                continue
            seen_pages.add(page_url)
            try:
                html, final_url = await _get_page(client, page_url, settings, resolve)
            except (ValueError, httpx.HTTPError) as exc:
                failures.append(PageFailure(page_url, str(exc)))
                log.warning("Skipped page %s: %s", page_url, exc)
                continue
            visited.append(final_url)
            parsed = _Parser()
            parsed.feed(html)
            base = urljoin(final_url, parsed.base_href or "")
            candidates = parsed.images + [
                a for a in parsed.links if urlsplit(a).path.lower().endswith(_IMAGES)
            ]
            for raw in candidates:
                absolute = _absolute(raw, base)
                if absolute and not urlsplit(absolute).path.lower().endswith(_SKIP) and absolute not in seen_images:
                    seen_images.add(absolute)
                    images.append(absolute)
                    if len(images) >= settings.max_images:
                        break
            if len(images) >= settings.max_images:
                break
            links_to_follow = (
                parsed.pagination_links
                if settings.page_follow_mode == "pagination"
                else parsed.links
            )

            for raw in links_to_follow if settings.max_pages > 1 else []:
                page = _absolute(raw, base)
                if not page or (urlsplit(page).hostname or "").lower() != host:
                    continue
                if urlsplit(page).path.lower().endswith(_SKIP + _IMAGES):
                    continue
                if page not in seen_pages and page not in queue:
                    queue.append(page)
    finally:
        if owned:
            await client.aclose()
    return DiscoveryResult(images, visited, failures)
