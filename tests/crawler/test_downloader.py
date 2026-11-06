"""SCRUM-179: a bad image URL is logged and the rest of the batch still downloads."""

from __future__ import annotations

import asyncio
import io
import socket
from pathlib import Path

import httpx
import pytest
from PIL import Image

from brandlens.crawler.downloader import (
    DownloadCode,
    DownloadSettings,
    download_images,
)

PUBLIC = "93.184.216.34"


def _png_bytes() -> bytes:
    image = Image.new("RGB", (8, 8), (20, 40, 60))
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()


def _jpeg_bytes() -> bytes:
    image = Image.new("RGB", (8, 8), (200, 10, 10))
    buf = io.BytesIO()
    image.save(buf, format="JPEG")
    return buf.getvalue()


def _public_resolve(host: str, port: int) -> list[str]:
    return [PUBLIC]


def _run(urls, dest: Path, handler, **kwargs):
    transport = httpx.MockTransport(handler)

    async def go():
        async with httpx.AsyncClient(transport=transport, follow_redirects=False) as client:
            return await download_images(
                urls,
                dest,
                client=client,
                resolve=kwargs.pop("resolve", _public_resolve),
                settings=kwargs.pop("settings", DownloadSettings(max_concurrency=2)),
                **kwargs,
            )

    return asyncio.run(go())


def test_valid_images_save_and_failures_do_not_stop_the_batch(tmp_path, caplog):
    png = _png_bytes()
    jpeg = _jpeg_bytes()
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        if request.url.path == "/a.png":
            return httpx.Response(200, content=png)
        if request.url.path == "/b.jpg":
            return httpx.Response(200, content=jpeg)
        if request.url.path == "/missing.png":
            return httpx.Response(404, content=b"nope")
        if request.url.path == "/notes.txt":
            return httpx.Response(200, content=b"hello")
        raise AssertionError(request.url.path)

    urls = [
        "https://cdn.example/a.png",
        "https://cdn.example/missing.png",
        "http://127.0.0.1/secret.png",
        "https://cdn.example/notes.txt",
        "https://cdn.example/b.jpg",
    ]
    with caplog.at_level("WARNING"):
        result = _run(urls, tmp_path, handler)

    saved = {item.url: item.path.name for item in result.downloaded}
    assert saved == {
        "https://cdn.example/a.png": "0000.png",
        "https://cdn.example/b.jpg": "0004.jpg",
    }
    assert saved["https://cdn.example/a.png"] and (tmp_path / "0000.png").read_bytes() == png
    assert {item.url: item.code for item in result.failed} == {
        "https://cdn.example/missing.png": DownloadCode.HTTP_ERROR,
        "http://127.0.0.1/secret.png": DownloadCode.NON_PUBLIC,
        "https://cdn.example/notes.txt": DownloadCode.UNSUPPORTED_TYPE,
    }
    assert all("127.0.0.1" not in url for url in seen)
    assert "https://cdn.example/missing.png" in caplog.text
    assert not list(tmp_path.glob("*notes*"))
    assert not list(tmp_path.glob("*secret*"))


def test_oversized_response_is_not_saved(tmp_path):
    png = _png_bytes()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=png)

    result = _run(
        ["https://cdn.example/big.png"],
        tmp_path,
        handler,
        settings=DownloadSettings(max_bytes=32),
    )
    assert result.downloaded == []
    assert result.failed[0].code == DownloadCode.TOO_LARGE
    assert list(tmp_path.iterdir()) == []


def test_unreachable_host_is_logged_and_the_next_url_still_saves(tmp_path):
    png = _png_bytes()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "down.example":
            raise httpx.ConnectError("connection refused")
        return httpx.Response(200, content=png)

    result = _run(
        ["https://down.example/a.png", "https://cdn.example/ok.png"],
        tmp_path,
        handler,
    )
    assert [item.url for item in result.downloaded] == ["https://cdn.example/ok.png"]
    assert result.failed[0].code == DownloadCode.UNAVAILABLE
    assert (tmp_path / "0001.png").read_bytes() == png


def test_private_dns_answer_is_not_requested(tmp_path):
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.host)
        return httpx.Response(200, content=_png_bytes())

    def resolve(host: str, port: int) -> list[str]:
        if host == "rebind.example":
            return ["10.1.2.3", PUBLIC]
        return [PUBLIC]

    result = _run(
        ["https://rebind.example/a.png", "https://cdn.example/ok.png"],
        tmp_path,
        handler,
        resolve=resolve,
    )
    assert seen == ["cdn.example"]
    assert result.failed[0].code == DownloadCode.NON_PUBLIC
    assert len(result.downloaded) == 1


def test_redirect_to_a_private_address_stops_before_the_second_request(tmp_path):
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(302, headers={"location": "http://127.0.0.1/secret"})

    result = _run(["https://cdn.example/go"], tmp_path, handler)
    assert seen == ["https://cdn.example/go"]
    assert result.failed[0].code == DownloadCode.NON_PUBLIC
    assert result.downloaded == []


def test_relative_redirect_to_a_public_image_is_saved(tmp_path):
    png = _png_bytes()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/go":
            return httpx.Response(302, headers={"location": "/ok.png"})
        return httpx.Response(200, content=png)

    result = _run(["https://cdn.example/go"], tmp_path, handler)
    assert result.failed == []
    assert result.downloaded[0].path.name == "0000.png"
    assert result.downloaded[0].path.read_bytes() == png


def test_redirect_limit_is_bounded(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "/again"})

    result = _run(
        ["https://cdn.example/start"],
        tmp_path,
        handler,
        settings=DownloadSettings(max_redirects=2),
    )
    assert result.failed[0].code == DownloadCode.TOO_MANY_REDIRECTS
    assert list(tmp_path.iterdir()) == []


def test_unresolved_name_is_a_failure(tmp_path):
    def resolve(host: str, port: int) -> list[str]:
        raise socket.gaierror("no address")

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("must not fetch an unresolved host")

    result = _run(["https://missing.example/a.png"], tmp_path, handler, resolve=resolve)
    assert result.downloaded == []
    assert result.failed[0].code == DownloadCode.UNAVAILABLE


def test_empty_list_writes_nothing(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("no urls")

    result = _run([], tmp_path, handler)
    assert result.downloaded == [] and result.failed == []


def test_literal_public_ip_does_not_use_dns(tmp_path):
    png = _png_bytes()

    def resolve(host: str, port: int) -> list[str]:
        raise AssertionError("literal IP must not be resolved")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=png)

    result = _run([f"http://{PUBLIC}/a.png"], tmp_path, handler, resolve=resolve)
    assert len(result.downloaded) == 1


def test_settings_reject_a_non_positive_cap():
    with pytest.raises(ValueError):
        DownloadSettings(max_concurrency=0)
