"""Tests for the Model Serving client (SCRUM-137).

Replies are accepted or rejected by ``validate_model_output``. No real model is involved:
httpx.MockTransport plays the OpenAI-compatible server.
"""

from __future__ import annotations

import base64
import io
import json
import uuid
from pathlib import Path

import httpx
import pytest
from PIL import Image
from pydantic import ValidationError

from brandlens.api.config import Settings
from brandlens.api.model_client import ModelClient, ModelFailure
from brandlens.api.schemas.vlm import ModelCriterion, ModelRequest
from brandlens.serving.models import MAX_TOKENS, TEMPERATURE

RUBRIC = Path("config/brand_standards.json")


@pytest.fixture
def image_path(tmp_path: Path) -> Path:
    p = tmp_path / "img.png"
    buf = io.BytesIO()
    Image.new("RGB", (64, 48), (10, 120, 200)).save(buf, "PNG")
    p.write_bytes(buf.getvalue())
    return p


@pytest.fixture
def request_() -> ModelRequest:
    """Built from the real rubric so the test fails if the config and contract drift apart."""
    rubric = json.loads(RUBRIC.read_text())
    c = next(c for c in rubric["criteria"] if c["method"] == "vlm")
    return ModelRequest(
        image_id=uuid.uuid4(),
        criteria=[ModelCriterion(
            criterion_id=c["criterion_id"], name=c["name"], definition=c["definition"],
            evaluation_evidence=c["evaluation_evidence"],
            allowed_labels=c["params"]["allowed_labels"],
        )],
    )


def _reply(payload: dict, *, fenced: bool = False) -> httpx.Response:
    text = json.dumps(payload)
    if fenced:
        text = f"```json\n{text}\n```"
    return httpx.Response(200, json={"choices": [{"message": {"content": text}}]})


def _good(**over) -> dict:
    row = {
        "id": "B1",
        "name": "Tone and approachability",
        "tone_label": "casual, lifestyle",
        "fit_score": 4,
        "evidence": "The subject is smiling and facing the camera.",
    }
    row.update(over)
    return {"criteria": [row]}


def _client(handler, **kw) -> ModelClient:
    return ModelClient(
        "http://model.test/v1",
        "test-model",
        transport=httpx.MockTransport(handler),
        **kw,
    )


def test_valid_reply_returns_criteria(request_, image_path):
    with _client(lambda r: _reply(_good())) as c:
        result = c.judge(request_, image_path)
    assert result.criteria[0].id == "B1"
    assert result.criteria[0].fit_score == 4
    assert result.criteria[0].tone_words == ("casual", "lifestyle")


def test_code_fenced_json_is_rejected(request_, image_path):
    with _client(lambda r: _reply(_good(), fenced=True)) as c, pytest.raises(ModelFailure) as err:
        c.judge(request_, image_path)
    assert err.value.reason == "invalid_json"


def test_request_is_openai_chat_shape(request_, image_path):
    seen = {}

    def handler(r: httpx.Request):
        seen["url"] = str(r.url)
        seen["auth"] = r.headers.get("authorization")
        seen["body"] = json.loads(r.content)
        return _reply(_good())

    with _client(handler, api_key="secret") as c:
        c.judge(request_, image_path)
    body = seen["body"]
    assert seen["url"] == "http://model.test/v1/chat/completions"
    assert seen["auth"] == "Bearer secret"
    assert body["model"] == "test-model"
    assert body["temperature"] == TEMPERATURE
    assert body["max_tokens"] == MAX_TOKENS
    assert body["reasoning_effort"] == "none"
    assert body["response_format"] == {"type": "json_object"}
    parts = body["messages"][0]["content"]
    assert "B1" in parts[0]["text"]
    assert "Tone and approachability" in parts[0]["text"]
    url = parts[1]["image_url"]["url"]
    assert url.startswith("data:image/png;base64,")
    assert base64.b64decode(url.split(",", 1)[1]) == image_path.read_bytes()


def test_prompt_uses_the_target_tone_list(request_, image_path):
    seen = {}

    def handler(r: httpx.Request):
        seen["text"] = json.loads(r.content)["messages"][0]["content"][0]["text"]
        return _reply(_good())

    with _client(handler) as c:
        c.judge(request_, image_path)
    assert "casual" in seen["text"]
    assert "Do not add a tone word that is not on that list." in seen["text"]


def test_from_settings(request_, image_path):
    s = Settings(model_base_url="http://x.test/v1", model_name="m", model_max_retries=0)
    with ModelClient.from_settings(
        s, transport=httpx.MockTransport(lambda r: _reply(_good()))
    ) as c:
        assert c.judge(request_, image_path).criteria


def test_one_retry_then_success(request_, image_path):
    calls = []

    def handler(r):
        calls.append(1)
        if len(calls) == 1:
            raise httpx.ReadTimeout("slow")
        return _reply(_good())

    with _client(handler) as c:
        assert c.judge(request_, image_path).criteria
    assert len(calls) == 2


@pytest.mark.parametrize(
    ("handler", "reason"),
    [
        (lambda r: (_ for _ in ()).throw(httpx.ReadTimeout("slow")), "timeout"),
        (lambda r: (_ for _ in ()).throw(httpx.ConnectError("refused")), "connection"),
        (lambda r: httpx.Response(500, text="boom"), "http_error"),
        (
            lambda r: httpx.Response(
                200, json={"choices": [{"message": {"content": "not json"}}]}
            ),
            "invalid_json",
        ),
        (lambda r: httpx.Response(200, json={"unexpected": True}), "invalid_json"),
        (lambda r: _reply(_good(fit_score=9)), "invalid_output"),
    ],
)
def test_two_failures_raise_model_failure(request_, image_path, handler, reason):
    with _client(handler) as c, pytest.raises(ModelFailure) as err:
        c.judge(request_, image_path)
    assert err.value.reason == reason and err.value.attempts == 2


def test_zero_retries_means_one_attempt(request_, image_path):
    calls = []

    def handler(r):
        calls.append(1)
        return httpx.Response(503)

    with _client(handler, max_retries=0) as c, pytest.raises(ModelFailure) as err:
        c.judge(request_, image_path)
    assert len(calls) == 1 and err.value.attempts == 1


@pytest.mark.parametrize(
    "bad",
    [
        _good(tone_label="authentic, industrial"),
        _good(fit_score=0),
        _good(fit_score=6),
        _good(fit_score=3.5),
        _good(fit_score="4"),
        _good(fit_score=True),
        _good(evidence=""),
        _good(evidence="   "),
        _good(evidence="Smiling."),
        _good(id="Q1"),
    ],
)
def test_invalid_reply_is_rejected(request_, image_path, bad):
    with _client(lambda r: _reply(bad)) as c, pytest.raises(ModelFailure) as err:
        c.judge(request_, image_path)
    assert err.value.reason == "invalid_output"


def test_missing_and_repeated_criteria_are_rejected(request_, image_path):
    repeated = _good()
    repeated["criteria"] = repeated["criteria"] + repeated["criteria"]
    for payload in ({"criteria": []}, repeated):
        with _client(lambda r, body=payload: _reply(body)) as c, pytest.raises(ModelFailure) as err:
            c.judge(request_, image_path)
        assert err.value.reason == "invalid_output"


def test_extra_fields_in_reply_are_rejected(request_, image_path):
    payload = _good()
    payload["criteria"][0]["notes"] = "extra"
    with _client(lambda r: _reply(payload)) as c, pytest.raises(ModelFailure) as err:
        c.judge(request_, image_path)
    assert err.value.reason == "invalid_output"


def test_old_judgments_shape_is_rejected(request_, image_path):
    old = {
        "judgments": [
            {
                "criterion_id": "tone_approachability",
                "label": "approachable",
                "fit_score": 4,
                "evidence": "The subject is smiling and facing the camera.",
            }
        ]
    }
    with _client(lambda r: _reply(old)) as c, pytest.raises(ModelFailure) as err:
        c.judge(request_, image_path)
    assert err.value.reason == "invalid_output"


def test_two_sentences_of_visible_evidence_are_accepted(request_, image_path):
    long = "The subject is smiling at the camera. The room behind them is brightly lit."
    with _client(lambda r: _reply(_good(evidence=long))) as c:
        result = c.judge(request_, image_path)
    assert result.criteria[0].evidence == long


def test_schemas_reject_bad_shapes():
    with pytest.raises(ValidationError):
        ModelRequest(image_id=uuid.uuid4(), criteria=[])
    with pytest.raises(ValidationError):
        ModelCriterion(
            criterion_id="t",
            name="n",
            definition="d",
            evaluation_evidence="e",
            allowed_labels=["a", "a"],
        )
