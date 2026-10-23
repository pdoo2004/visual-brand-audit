"""OpenAI chat-completions body shared by vLLM and Ollama.

Both servers accept POST /v1/chat/completions. The model field is the
only part that changes when the weights change.
"""

from __future__ import annotations

import base64

from brandlens.serving.models import MAX_TOKENS, TEMPERATURE


def image_data_url(image: bytes) -> str:
    """Encode a JPEG, PNG, or WEBP file as a data URL."""
    if image.startswith(b"\xff\xd8\xff"):
        mime = "image/jpeg"
    elif image.startswith(b"\x89PNG\r\n\x1a\n"):
        mime = "image/png"
    elif len(image) >= 12 and image.startswith(b"RIFF") and image[8:12] == b"WEBP":
        mime = "image/webp"
    else:
        raise ValueError("image must be JPEG, PNG, or WEBP")
    encoded = base64.b64encode(image).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def build_chat_request(
    prompt: str,
    image: bytes,
    model: str,
    *,
    temperature: float = TEMPERATURE,
    max_tokens: int = MAX_TOKENS,
    reasoning_effort: str | None = "none",
) -> dict:
    """Build one vision request. `model` is passed through unchanged.

    Gemma 4 thinks by default. On the OpenAI-compatible endpoint that
    spends the token budget before the JSON answer, so content comes
    back empty. ``reasoning_effort`` ``none`` keeps the answer in
    ``content``. ``response_format`` asks for a JSON object so the
    reply is not wrapped in a markdown fence. vLLM is started without
    its reasoning parser, which leaves thinking off on that server too.
    """
    if not prompt.strip():
        raise ValueError("prompt is empty")
    if not model.strip():
        raise ValueError("model is empty")
    body = {
        "model": model,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
        "response_format": {"type": "json_object"},
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": image_data_url(image)},
                    },
                ],
            }
        ],
    }
    if reasoning_effort is not None:
        body["reasoning_effort"] = reasoning_effort
    return body


def chat_completions_url(base_url: str) -> str:
    """Accept either the server root or a URL that already ends in /v1."""
    root = base_url.rstrip("/")
    if not root:
        raise ValueError("base_url is empty")
    if root.endswith("/v1"):
        return f"{root}/chat/completions"
    return f"{root}/v1/chat/completions"


def message_text(content: str | list | None) -> str:
    """Read assistant text from a string or a list of content parts."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict) and part.get("type") == "text":
                text = part.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "".join(parts)
    return ""


def parse_chat_response(payload: dict) -> str:
    """Return the assistant text from one chat-completions payload."""
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ValueError("response has no choices")
    choice = choices[0]
    message = choice.get("message") if isinstance(choice, dict) else None
    content = message.get("content") if isinstance(message, dict) else None
    text = message_text(content).strip()
    if not text:
        raise ValueError("response content is empty")
    return text
