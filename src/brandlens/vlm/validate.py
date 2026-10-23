"""Check a model reply before any score uses it.

A valid reply becomes criterion judgments. Anything malformed or incomplete
comes back as ``ok`` false and a list of reasons, instead of raising.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from brandlens.vlm.criteria import CRITERIA, RECOMMENDED_TONES

_MIN_EVIDENCE_CHARS = 12
_TONE_WORDS = set(RECOMMENDED_TONES)


class _CriterionScore(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    id: str
    name: str
    tone_label: str
    fit_score: int = Field(ge=1, le=5)
    evidence: str

    @field_validator("evidence")
    @classmethod
    def evidence_names_something_visible(cls, value: str) -> str:
        text = value.strip()
        if len(text) < _MIN_EVIDENCE_CHARS:
            raise ValueError("must be one sentence naming something visible")
        return text


class _ModelResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    criteria: list[_CriterionScore]


@dataclass(frozen=True)
class ParsedCriterion:
    """One criterion the model scored and the validator accepted."""

    id: str
    name: str
    tone_label: str
    tone_words: tuple[str, ...]
    fit_score: int
    evidence: str


@dataclass(frozen=True)
class ModelOutputValidation:
    """Parsed criterion scores, or the reasons the reply was rejected.

    ``ok`` is false for invalid JSON, the wrong criteria, a score outside
    1-5, an off-list tone word, or evidence that does not name anything.
    ``criteria`` is empty in that case. Callers keep going from ``errors``.
    """

    ok: bool
    criteria: tuple[ParsedCriterion, ...]
    errors: tuple[str, ...]


def validate_model_output(
    text: str,
    expected_ids: tuple[str, ...] = ("B1",),
) -> ModelOutputValidation:
    """Parse one model reply against the rubric criteria it was asked to score."""
    unknown = [item for item in expected_ids if item not in CRITERIA]
    if unknown:
        raise KeyError(f"No VLM criterion named {unknown}. MVP model criteria: {sorted(CRITERIA)}")

    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return _failure("response is not valid JSON")
    if not isinstance(payload, dict):
        return _failure("response is not a JSON object")

    try:
        parsed = _ModelResponse.model_validate(payload)
    except ValidationError as exc:
        return _failure(*_schema_errors(payload, exc))

    errors: list[str] = []
    ids = [row.id for row in parsed.criteria]
    if ids != list(expected_ids):
        errors.append(f"criteria ids are {ids}, expected {list(expected_ids)}")

    judgments: list[ParsedCriterion] = []
    for row, expected_id in zip(parsed.criteria, expected_ids, strict=False):
        if ids == list(expected_ids) and row.name != CRITERIA[expected_id]["name"]:
            errors.append(f'{expected_id} name must be "{CRITERIA[expected_id]["name"]}"')
        words, word_errors = _tone_words(row.tone_label, row.id or expected_id)
        errors.extend(word_errors)
        if not errors:
            judgments.append(
                ParsedCriterion(
                    id=row.id,
                    name=row.name,
                    tone_label=", ".join(words),
                    tone_words=words,
                    fit_score=row.fit_score,
                    evidence=row.evidence,
                )
            )

    if errors:
        return _failure(*errors)
    return ModelOutputValidation(ok=True, criteria=tuple(judgments), errors=())


def _failure(*errors: str) -> ModelOutputValidation:
    return ModelOutputValidation(ok=False, criteria=(), errors=errors)


def _schema_errors(payload: dict, exc: ValidationError) -> list[str]:
    messages: list[str] = []
    for err in exc.errors():
        loc = err["loc"]
        label = _label(payload, loc)
        field = loc[-1] if loc else ""
        kind = err["type"]
        if kind == "missing" and loc == ("criteria",):
            messages.append("criteria is missing")
        elif kind == "missing":
            messages.append(f"{label} is missing {field}")
        elif kind == "extra_forbidden" and len(loc) == 1:
            messages.append(f'response has unexpected field "{field}"')
        elif kind == "extra_forbidden":
            messages.append(f'{label} has unexpected field "{field}"')
        elif kind == "list_type":
            messages.append("criteria is not a list")
        elif field == "fit_score" and kind in {"int_type", "greater_than_equal", "less_than_equal"}:
            messages.append(f"{label} fit_score must be an integer from 1 to 5")
        elif kind == "string_type":
            messages.append(f"{label} {field} must be a string")
        elif kind == "value_error" and field == "evidence":
            messages.append(f"{label} evidence must be one sentence naming something visible")
        else:
            messages.append(f"{label} {err['msg']}")
    return messages or ["response does not match the criterion schema"]


def _label(payload: dict, loc: tuple) -> str:
    if len(loc) >= 2 and loc[0] == "criteria" and isinstance(loc[1], int):
        rows = payload.get("criteria")
        if isinstance(rows, list) and loc[1] < len(rows) and isinstance(rows[loc[1]], dict):
            row_id = rows[loc[1]].get("id")
            if isinstance(row_id, str) and row_id.strip():
                return row_id.strip()
        return f"criteria[{loc[1]}]"
    if loc and loc[0] == "criteria":
        return "criteria"
    return "response"


def _tone_words(label: str, criterion_id: str) -> tuple[tuple[str, ...], list[str]]:
    if not label.strip():
        return (), [f"{criterion_id} tone_label is empty"]
    words: list[str] = []
    errors: list[str] = []
    for piece in label.split(","):
        word = piece.strip().lower()
        if not word:
            errors.append(f"{criterion_id} tone_label has an empty word")
            continue
        if word not in _TONE_WORDS:
            errors.append(
                f'{criterion_id} tone_label contains "{word}", which is not a target tone word'
            )
            continue
        if word in words:
            errors.append(f'{criterion_id} tone_label repeats "{word}"')
            continue
        words.append(word)
    return tuple(words), errors
