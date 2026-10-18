"""Backend client for the Model Serving component (SCRUM-137; contract section 4.4).

Talks to any OpenAI-compatible `/v1/chat/completions` server (Ollama in development, vLLM in
production), so the model can be swapped by changing settings only.

Failure handling follows the contract: a timeout, connection or HTTP error, invalid JSON, or a
reply that breaks the schema triggers one retry. If the retry also fails, `judge` raises
`ModelFailure`; the worker (SCRUM-139) turns that into an `unavailable_needs_review` tone
criterion while the CV criteria still score.

The client is synchronous because the job worker runs in a background thread.
"""

from __future__ import annotations

import base64
import json
import logging
import mimetypes
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Self

import httpx
from pydantic import ValidationError

from brandlens.api.config import Settings
from brandlens.api.schemas.vlm import (
    Judgment,
    ModelRequest,
    ModelResponse,
    sentence_count,
)

log = logging.getLogger(__name__)

FailureReason = Literal["timeout", "connection", "http_error", "invalid_json", "invalid_output"]

_SYSTEM_PROMPT = (
    "You are a critical photography reviewer for a brand-standards tool. For each criterion in "
    "the request, judge the attached photograph against the target tone named by that "
    "criterion's allowed_labels. Reply with ONLY a JSON object, no prose and no code fences, in "
    'exactly this shape: {"judgments": [{"criterion_id": "<id from the request>", '
    '"label": "<one allowed label>", "fit_score": <integer 1-5>, '
    '"evidence": "<ONE sentence naming something visible in the photo>"}]}. '
    "Rules: (1) label must be copied exactly from that criterion's allowed_labels. Never invent "
    "a label and never use an opposite such as 'inapproachable'. (2) If no allowed label really "
    "fits the photo, still choose the closest allowed label and give a LOW fit_score. "
    "(3) fit_score is how clearly the photo conveys the target tone: 5 = clearly and strongly, "
    "4 = mostly, 3 = partly or neutral, 2 = weakly, 1 = not at all or the opposite (for example a "
    "cold, dark or threatening mood). Do not give 5 unless the evidence is obvious in the photo; "
    "if there is little visible evidence of the tone, give 3 or lower. "
    "(4) Include exactly one judgment per requested criterion."
)

_FENCE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL | re.IGNORECASE)


class ModelFailure(Exception):
    """The model could not produce a usable judgment, even after retrying."""

    def __init__(self, reason: FailureReason, message: str, attempts: int):
        super().__init__(f"{reason}: {message} (after {attempts} attempt(s))")
        self.reason = reason
        self.message = message
        self.attempts = attempts


@dataclass(frozen=True)
class ModelResult:
    """Validated judgments, in the order the criteria were requested."""

    judgments: list[Judgment]
    warnings: list[str] = field(default_factory=list)  # soft-rule notes, never failures


class _Retryable(Exception):
    def __init__(self, reason: FailureReason, message: str):
        super().__init__(message)
        self.reason = reason
        self.message = message


def check_judgments(request: ModelRequest, response: ModelResponse) -> ModelResult:
    """Check a parsed reply against the request it answers (SCRUM-138 rules).

    Hard failures: an unrequested or repeated criterion, a missing criterion, or a label that is
    not in that criterion's `allowed_labels`. Evidence longer than one sentence is only a warning
    (the contract calls it a soft rule). Range and empty-text checks are done by the schema.
    """
    allowed = {c.criterion_id: set(c.allowed_labels) for c in request.criteria}
    seen: dict[str, Judgment] = {}
    for j in response.judgments:
        if j.criterion_id not in allowed:
            raise _Retryable("invalid_output", f"unrequested criterion_id {j.criterion_id!r}")
        if j.criterion_id in seen:
            raise _Retryable("invalid_output", f"repeated criterion_id {j.criterion_id!r}")
        if j.label not in allowed[j.criterion_id]:
            raise _Retryable(
                "invalid_output",
                f"label {j.label!r} is not allowed for {j.criterion_id!r} "
                f"(allowed: {sorted(allowed[j.criterion_id])})",
            )
        seen[j.criterion_id] = j

    missing = [c.criterion_id for c in request.criteria if c.criterion_id not in seen]
    if missing:
        raise _Retryable("invalid_output", f"no judgment for criteria: {missing}")

    ordered = [seen[c.criterion_id] for c in request.criteria]
    warnings = [
        f"{j.criterion_id}: evidence is more than one sentence"
        for j in ordered
        if sentence_count(j.evidence) > 1
    ]
    return ModelResult(judgments=ordered, warnings=warnings)


class ModelClient:
    """Sends one image plus its VLM criteria to the model server and validates the reply."""

    def __init__(
        self,
        base_url: str,
        model: str,
        *,
        api_key: str | None = None,
        timeout_s: float = 60.0,
        max_retries: int = 1,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self._model = model
        self._max_retries = max(0, max_retries)
        self._http = httpx.Client(
            base_url=base_url.rstrip("/"),
            headers=headers,
            timeout=timeout_s,
            transport=transport,
        )

    @classmethod
    def from_settings(
        cls, settings: Settings, transport: httpx.BaseTransport | None = None
    ) -> ModelClient:
        return cls(
            settings.model_base_url,
            settings.model_name,
            api_key=settings.model_api_key,
            timeout_s=settings.model_timeout_s,
            max_retries=settings.model_max_retries,
            transport=transport,
        )

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    # ------------------------------------------------------------------ public

    def judge(self, request: ModelRequest, image_path: Path) -> ModelResult:
        """Return validated judgments for `image_path`, or raise `ModelFailure`."""
        payload = self._build_payload(request, image_path)
        attempts = self._max_retries + 1
        last: _Retryable | None = None
        for attempt in range(1, attempts + 1):
            try:
                return self._attempt(request, payload)
            except _Retryable as exc:
                last = exc
                log.warning(
                    "model call for image %s failed (%s, attempt %d/%d): %s",
                    request.image_id, exc.reason, attempt, attempts, exc.message,
                )
        assert last is not None
        raise ModelFailure(last.reason, last.message, attempts)

    # ----------------------------------------------------------------- private

    def _build_payload(self, request: ModelRequest, image_path: Path) -> dict:
        mime = mimetypes.guess_type(image_path.name)[0] or "image/png"
        data_url = f"data:{mime};base64,{base64.b64encode(image_path.read_bytes()).decode()}"
        return {
            "model": self._model,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": request.model_dump_json()},
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                },
            ],
        }

    def _attempt(self, request: ModelRequest, payload: dict) -> ModelResult:
        try:
            resp = self._http.post("/chat/completions", json=payload)
        except httpx.TimeoutException as exc:
            raise _Retryable("timeout", str(exc) or "request timed out") from exc
        except httpx.TransportError as exc:
            raise _Retryable("connection", str(exc) or "could not reach model server") from exc

        if resp.status_code >= 400:
            raise _Retryable("http_error", f"HTTP {resp.status_code}: {resp.text[:200]}")

        text = self._extract_text(resp)
        try:
            data = json.loads(_FENCE.sub(r"\1", text.strip()))
        except json.JSONDecodeError as exc:
            raise _Retryable("invalid_json", f"reply is not valid JSON: {exc.msg}") from exc

        try:
            parsed = ModelResponse.model_validate(data)
        except ValidationError as exc:
            first = exc.errors()[0]
            where = ".".join(str(p) for p in first["loc"])
            raise _Retryable("invalid_output", f"{where}: {first['msg']}") from exc
        return check_judgments(request, parsed)

    @staticmethod
    def _extract_text(resp: httpx.Response) -> str:
        try:
            content = resp.json()["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise _Retryable("invalid_json", "response is not an OpenAI chat completion") from exc
        if not isinstance(content, str) or not content.strip():
            raise _Retryable("invalid_json", "model returned no content")
        return content
