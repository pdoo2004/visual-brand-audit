"""Tests for the Model Serving client (SCRUM-137) and its output rules (SCRUM-138).

No real model is involved: httpx.MockTransport plays the OpenAI-compatible server.
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
from brandlens.api.schemas.vlm import (
    Judgment,
    ModelCriterion,
    ModelRequest,
    ModelResponse,
    sentence_count,
)

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


def _reply(judgments, *, fenced=False) -> httpx.Response:
    text = json.dumps({"judgments": judgments})
    if fenced:
        text = f"```json\n{text}\n```"
    return httpx.Response(200, json={"choices": [{"message": {"content": text}}]})


def _good(**over):
    j = {"criterion_id": "tone_approachability", "label": "approachable",
         "fit_score": 4, "evidence": "The subject is smiling and facing the camera."}
    return {**j, **over}


def _client(handler, **kw) -> ModelClient:
    return ModelClient("http://model.test/v1", "test-model",
                       transport=httpx.MockTransport(handler), **kw)


# ---------------------------------------------------------------- happy path

def test_valid_reply_returns_judgments(request_, image_path):
    with _client(lambda r: _reply([_good()])) as c:
        result = c.judge(request_, image_path)
    assert [j.label for j in result.judgments] == ["approachable"]
    assert result.judgments[0].fit_score == 4 and result.warnings == []


def test_code_fenced_json_is_accepted(request_, image_path):
    with _client(lambda r: _reply([_good()], fenced=True)) as c:
        assert c.judge(request_, image_path).judgments[0].fit_score == 4


def test_request_is_openai_chat_shape(request_, image_path):
    seen = {}

    def handler(r: httpx.Request):
        seen["url"], seen["auth"], seen["body"] = str(r.url), r.headers.get("authorization"), json.loads(r.content)
        return _reply([_good()])

    with _client(handler, api_key="secret") as c:
        c.judge(request_, image_path)
    body = seen["body"]
    assert seen["url"] == "http://model.test/v1/chat/completions"
    assert seen["auth"] == "Bearer secret"
    assert body["model"] == "test-model" and body["response_format"] == {"type": "json_object"}
    parts = body["messages"][1]["content"]
    assert json.loads(parts[0]["text"])["criteria"][0]["criterion_id"] == "tone_approachability"
    url = parts[1]["image_url"]["url"]
    assert url.startswith("data:image/png;base64,")
    assert base64.b64decode(url.split(",", 1)[1]) == image_path.read_bytes()


def test_prompt_tells_model_not_to_invent_labels_and_to_score_low(request_, image_path):
    """Found in live testing: on a dark photo the model invented 'inapproachable'."""
    seen = {}

    def handler(r: httpx.Request):
        seen["system"] = json.loads(r.content)["messages"][0]["content"]
        return _reply([_good()])

    with _client(handler) as c:
        c.judge(request_, image_path)
    assert "Never invent a label" in seen["system"]
    assert "closest allowed label" in seen["system"] and "LOW fit_score" in seen["system"]


def test_from_settings(request_, image_path):
    s = Settings(model_base_url="http://x.test/v1", model_name="m", model_max_retries=0)
    with ModelClient.from_settings(s, transport=httpx.MockTransport(lambda r: _reply([_good()]))) as c:
        assert c.judge(request_, image_path).judgments


# ------------------------------------------------------------ retry behaviour

def test_one_retry_then_success(request_, image_path):
    calls = []

    def handler(r):
        calls.append(1)
        if len(calls) == 1:
            raise httpx.ReadTimeout("slow")
        return _reply([_good()])

    with _client(handler) as c:
        assert c.judge(request_, image_path).judgments
    assert len(calls) == 2


@pytest.mark.parametrize(("handler", "reason"), [
    (lambda r: (_ for _ in ()).throw(httpx.ReadTimeout("slow")), "timeout"),
    (lambda r: (_ for _ in ()).throw(httpx.ConnectError("refused")), "connection"),
    (lambda r: httpx.Response(500, text="boom"), "http_error"),
    (lambda r: httpx.Response(200, json={"choices": [{"message": {"content": "not json"}}]}), "invalid_json"),
    (lambda r: httpx.Response(200, json={"unexpected": True}), "invalid_json"),
    (lambda r: _reply([_good(fit_score=9)]), "invalid_output"),
])
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


# ---------------------------------- output rules from SCRUM-138 (contract 4.4)

@pytest.mark.parametrize("bad", [
    _good(label="grumpy"),                 # label not in allowed_labels
    _good(fit_score=0), _good(fit_score=6),  # outside 1-5
    _good(fit_score=3.5), _good(fit_score="4"), _good(fit_score=True),  # not an integer
    _good(evidence=""), _good(evidence="   "),  # empty evidence
    _good(criterion_id="authenticity"),    # not requested
])
def test_invalid_judgment_is_rejected(request_, image_path, bad):
    with _client(lambda r: _reply([bad])) as c, pytest.raises(ModelFailure) as err:
        c.judge(request_, image_path)
    assert err.value.reason == "invalid_output"


def test_missing_and_repeated_criteria_are_rejected(request_, image_path):
    for judgments in ([], [_good(), _good()]):
        with _client(lambda r, j=judgments: _reply(j)) as c, pytest.raises(ModelFailure):
            c.judge(request_, image_path)


def test_extra_fields_in_reply_are_rejected(request_, image_path):
    with _client(lambda r: _reply([{**_good(), "confidence": 0.9}])) as c, pytest.raises(ModelFailure):
        c.judge(request_, image_path)


def test_multi_sentence_evidence_is_only_a_warning(request_, image_path):
    long = "The subject is smiling. The lighting is warm."
    with _client(lambda r: _reply([_good(evidence=long)])) as c:
        result = c.judge(request_, image_path)
    assert result.judgments[0].evidence == long
    assert result.warnings and "more than one sentence" in result.warnings[0]


def test_sentence_count():
    assert sentence_count("One sentence.") == 1
    assert sentence_count("Dr. smith waves. He smiles.") >= 2
    assert sentence_count("") == 0


# ---------------------------------------------------------------- schemas

def test_schemas_reject_bad_shapes():
    with pytest.raises(ValidationError):
        ModelRequest(image_id=uuid.uuid4(), criteria=[])
    with pytest.raises(ValidationError):
        ModelCriterion(criterion_id="t", name="n", definition="d", evaluation_evidence="e",
                       allowed_labels=["a", "a"])
    with pytest.raises(ValidationError):
        ModelResponse(judgments=[])
    assert Judgment(criterion_id="t", label="a", fit_score=5, evidence="ok").fit_score == 5
