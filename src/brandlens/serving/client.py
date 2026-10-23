"""Send one photograph to the model server."""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from brandlens.serving.contract import (
    build_chat_request,
    chat_completions_url,
    parse_chat_response,
)


def post_chat(base_url: str, body: dict, timeout: int) -> dict:
    """POST a chat-completions body and return the JSON payload."""
    request = urllib.request.Request(
        chat_completions_url(base_url),
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"model server HTTP {exc.code}: {detail}") from exc


def infer(
    prompt: str,
    image: bytes,
    *,
    base_url: str,
    model: str,
    timeout: int = 180,
) -> str:
    """Score one image. The caller chooses the server and the model name."""
    body = build_chat_request(prompt, image, model)
    return parse_chat_response(post_chat(base_url, body, timeout))
