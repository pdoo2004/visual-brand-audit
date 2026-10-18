"""Model Serving request/response schemas (interface contract section 4.4, SCRUM-137/138).

The model makes one judgment in the MVP (tone and approachability), but the lists are generic so
a second VLM criterion can be added without a contract change.

These models check *shape* (types, ranges, non-empty text). Checks that need the request, such as
"label is one of this criterion's allowed_labels", live in `brandlens.api.model_client`.
"""

import re
from typing import Annotated, Self
from uuid import UUID

from pydantic import AfterValidator, Field, StringConstraints, model_validator

from brandlens.api.schemas.base import BaseSchema, Slug

# An integer from 1 to 5. Strict: 4.5, "4" and True are all invalid.
FitScore = Annotated[int, Field(ge=1, le=5, strict=True)]

NonEmptyText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


def _unique(values: list[str], what: str) -> list[str]:
    if len(set(values)) != len(values):
        raise ValueError(f"{what} must not repeat")
    return values


class ModelCriterion(BaseSchema):
    """One criterion the model is asked to judge (copied from the rubric)."""

    criterion_id: Slug
    name: NonEmptyText
    definition: NonEmptyText
    evaluation_evidence: NonEmptyText
    allowed_labels: Annotated[list[NonEmptyText], Field(min_length=1), AfterValidator(
        lambda v: _unique(v, "allowed_labels"))]


class ModelRequest(BaseSchema):
    """What the backend's model client builds for one image."""

    image_id: UUID
    criteria: Annotated[list[ModelCriterion], Field(min_length=1)]

    @model_validator(mode="after")
    def _unique_criteria(self) -> Self:
        _unique([c.criterion_id for c in self.criteria], "criterion_id")
        return self


class Judgment(BaseSchema):
    """One criterion's verdict, as returned by the model."""

    criterion_id: Slug
    label: NonEmptyText
    fit_score: FitScore
    evidence: NonEmptyText


class ModelResponse(BaseSchema):
    """The model's reply. Anything that does not parse into this is a model failure."""

    judgments: Annotated[list[Judgment], Field(min_length=1)]


_SENTENCE_BREAK = re.compile(r"(?<=[.!?])\s+(?=[A-Z\"'])")


def sentence_count(text: str) -> int:
    """Rough sentence count, used for the contract's soft one-sentence evidence rule."""
    return len(_SENTENCE_BREAK.split(text.strip())) if text.strip() else 0
