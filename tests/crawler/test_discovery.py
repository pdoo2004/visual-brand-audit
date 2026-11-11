"""Offline deterministic discovery tests using httpx.MockTransport."""
import asyncio

import httpx
import pytest

from brandlens.crawler.discovery import DiscoverySettings, discover_images


def fetch(url, handler, **options):
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await discover_images(
                url, client=client, resolve=lambda host, port: ["93.184.216.34"],
                **options,
            )
    return asyncio.run(run())


def test_extracts_srcset_lazy_preview_and_next_page():
    requested = []
    def handler(request):
        requested.append(str(request.url))
        if request.url.path == "/next":
            text = '<img src="/second.jpg"><img src="/large.jpg#same">'
        else:
            text = '''<meta property="og:image" content="//cdn.example/preview.png">
<img src="/small.jpg" srcset="/medium.jpg 1x, /large.jpg 2x">
<img data-src="/lazy.jpg" src="/placeholder.svg">
<img src="data:image/png;base64,AA">
<a href="/next">next</a><a href="https://other.example/other">offsite</a>'''
        return httpx.Response(200, text=text, headers={"content-type": "text/html"})
    result = fetch("https://site.example/", handler,
                   settings=DiscoverySettings(max_pages=2))
    assert result.image_urls == [
        "https://cdn.example/preview.png", "https://site.example/large.jpg",
        "https://site.example/lazy.jpg", "https://site.example/second.jpg",
    ]
    assert requested == ["https://site.example/", "https://site.example/next"]
    assert len(result.pages_visited) == 2


def test_respects_limits():
    def handler(request):
        assert request.url.path == "/"
        return httpx.Response(200, text='<img src="/a.jpg"><img src="/b.jpg"><a href="/next">next</a>',
                              headers={"content-type": "text/html"})
    result = fetch("https://site.example/", handler,
                   settings=DiscoverySettings(max_pages=5, max_images=1))
    assert result.image_urls == ["https://site.example/a.jpg"]
    assert len(result.pages_visited) == 1


def test_blocks_private_redirect():
    seen = []
    def handler(request):
        seen.append(str(request.url))
        return httpx.Response(302, headers={"location": "http://127.0.0.1/private"})
    result = fetch("https://site.example/", handler)
    assert seen == ["https://site.example/"]
    assert not result.image_urls
    assert len(result.failed_pages) == 1


def test_non_html_is_skipped():
    result = fetch("https://site.example/", lambda req: httpx.Response(
        200, content=b"x", headers={"content-type": "image/png"}))
    assert not result.pages_visited
    assert len(result.failed_pages) == 1


def test_settings_and_input_validation():
    with pytest.raises(ValueError):
        DiscoverySettings(max_pages=0)
    with pytest.raises(ValueError):
        DiscoverySettings(max_pages=51)
    with pytest.raises(ValueError):
        asyncio.run(discover_images("http://127.0.0.1/"))


def test_rejected_page_is_reported():
    result = fetch(
        "https://site.example/",
        lambda request: httpx.Response(403, text="Forbidden"),
    )
    assert result.pages_visited == []
    assert result.image_urls == []
    assert len(result.failed_pages) == 1
    assert result.failed_pages[0].reason == "HTTP 403"
    
def test_pagination_mode_skips_unrelated_pages():
    requested = []

    def handler(request):
        requested.append(str(request.url))

        page = request.url.params.get("page")

        if page == "2":
            html = '''
                <img src="/b.jpg">
                <a href="?page=3" rel="next">Next</a>
            '''
        elif page == "3":
            html = '<img src="/c.jpg">'
        else:
            html = '''
                <img src="/a.jpg">
                <a href="/about">About</a>
                <a href="?page=2" rel="next">Next</a>
            '''

        return httpx.Response(
            200,
            text=html,
            headers={"content-type": "text/html"},
        )

    result = fetch(
        "https://site.example/gallery",
        handler,
        settings=DiscoverySettings(
            max_pages=3,
            page_follow_mode="pagination",
        ),
    )

    assert len(result.pages_visited) == 3
    assert len(result.image_urls) == 3
    assert all("/about" not in url for url in requested)
