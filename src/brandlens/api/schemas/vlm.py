"""What the backend passes the model client for one image (SCRUM-137).

The model's reply is not parsed here. ``validate_model_output`` accepts or rejects that JSON.
"""

from typing import Annotated, Self
from uuid import UUID

from pydantic import AfterValidator, Field, StringConstraints, model_validator

from brandlens.api.schemas.base import BaseSchema, Slug

NonEmptyText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


def _unique(values: list[str], what: str) -> list[str]:
    if len(set(values)) != len(values):
        raise ValueError(f"{what} must not repeat")
    return values


class ModelCriterion(BaseSchema):
    """One criterion named on the image request."""

    criterion_id: Slug
    name: NonEmptyText
    definition: NonEmptyText
    evaluation_evidence: NonEmptyText
    allowed_labels: Annotated[list[NonEmptyText], Field(min_length=1), AfterValidator(
        lambda v: _unique(v, "allowed_labels"))]


class ModelRequest(BaseSchema):
    """Identity of the image the model client is scoring."""

    image_id: UUID
    criteria: Annotated[list[ModelCriterion], Field(min_length=1)]

    @model_validator(mode="after")
    def _unique_criteria(self) -> Self:
        _unique([c.criterion_id for c in self.criteria], "criterion_id")
        return self
