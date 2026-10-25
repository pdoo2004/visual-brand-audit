"""Backend client for the Model Serving component (SCRUM-137).

Talks to any OpenAI-compatible `/v1/chat/completions` server (Ollama in development, vLLM in
production), so the model can be swapped by changing settings only.

The reply is checked with ``validate_model_output`` (SCRUM-138). A timeout, connection or HTTP
error, or a reply that checker rejects triggers one retry. If the retry also fails, ``judge``
raises ``ModelFailure``; the worker (SCRUM-139) turns that into an ``unavailable_needs_review``
tone criterion while the CV criteria still score.

The client is synchronous because the job worker runs in a background thread.
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Self

import httpx

from brandlens.api.config import Settings
from brandlens.api.schemas.vlm import ModelRequest
from brandlens.serving.contract import build_chat_request, parse_chat_response
from brandlens.vlm.validate import ParsedCriterion, validate_model_output

log = logging.getLogger(__name__)

FailureReason = Literal["timeout", "connection", "http_error", "invalid_json", "invalid_output"]

_JSON_ERRORS = frozenset(
    {
        "response is not valid JSON",
        "response is not a JSON object",
    }
)


def _render_b1_prompt() -> str:
    """Load the locked B1 prompt from the repo's vlm script."""
    vlm_dir = Path(__file__).resolve().parents[3] / "vlm"
    if str(vlm_dir) not in sys.path:
        sys.path.insert(0, str(vlm_dir))
    from prompt_template import render_prompt

    return render_prompt(["B1"])


class ModelFailure(Exception):
    """The model could not produce a usable judgment, even after retrying."""

    def __init__(self, reason: FailureReason, message: str, attempts: int):
        super().__init__(f"{reason}: {message} (after {attempts} attempt(s))")
        self.reason = reason
        self.message = message
        self.attempts = attempts


@dataclass(frozen=True)
class ModelResult:
    """Criterion scores ``validate_model_output`` accepted, in reply order."""

    criteria: tuple[ParsedCriterion, ...]


class _Retryable(Exception):
    def __init__(self, reason: FailureReason, message: str):
        super().__init__(message)
        self.reason = reason
        self.message = message


class ModelClient:
    """Sends one image to the model server and validates the reply."""

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

    def judge(self, request: ModelRequest, image_path: Path) -> ModelResult:
        """Return validated B1 scores for ``image_path``, or raise ``ModelFailure``.

        ``request`` supplies the image id used in logs. The prompt is always the locked B1
        prompt; the reply is accepted only when ``validate_model_output`` says so.
        """
        payload = build_chat_request(_render_b1_prompt(), image_path.read_bytes(), self._model)
        attempts = self._max_retries + 1
        last: _Retryable | None = None
        for attempt in range(1, attempts + 1):
            try:
                return self._attempt(payload)
            except _Retryable as exc:
                last = exc
                log.warning(
                    "model call for image %s failed (%s, attempt %d/%d): %s",
                    request.image_id,
                    exc.reason,
                    attempt,
                    attempts,
                    exc.message,
                )
        assert last is not None
        raise ModelFailure(last.reason, last.message, attempts)

    def _attempt(self, payload: dict) -> ModelResult:
        try:
            resp = self._http.post("/chat/completions", json=payload)
        except httpx.TimeoutException as exc:
            raise _Retryable("timeout", str(exc) or "request timed out") from exc
        except httpx.TransportError as exc:
            raise _Retryable("connection", str(exc) or "could not reach model server") from exc

        if resp.status_code >= 400:
            raise _Retryable("http_error", f"HTTP {resp.status_code}: {resp.text[:200]}")

        text = self._extract_text(resp)
        result = validate_model_output(text)
        if not result.ok:
            json_reply = all(error in _JSON_ERRORS for error in result.errors)
            reason: FailureReason = "invalid_json" if json_reply else "invalid_output"
            raise _Retryable(reason, "; ".join(result.errors))
        return ModelResult(criteria=result.criteria)

    @staticmethod
    def _extract_text(resp: httpx.Response) -> str:
        try:
            payload = resp.json()
        except ValueError as exc:
            raise _Retryable("invalid_json", "response is not an OpenAI chat completion") from exc
        try:
            return parse_chat_response(payload)
        except ValueError as exc:
            raise _Retryable("invalid_json", str(exc)) from exc
