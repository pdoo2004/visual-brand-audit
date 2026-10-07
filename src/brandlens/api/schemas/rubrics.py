"""Selectable rubrics for Screen 1 (endpoint #2). Internal-only fields are left out."""

from typing import Self

from pydantic import Field, model_validator

from brandlens.api.schemas.base import BaseSchema, Slug, Weight
from brandlens.api.schemas.enums import CriterionSource


class CriterionInfo(BaseSchema):
    criterion_id: Slug
    name: str = Field(min_length=1)
    definition: str = Field(min_length=1)
    evaluation_evidence: str = Field(min_length=1)
    method: CriterionSource
    weight: Weight


class RubricInfo(BaseSchema):
    rubric_id: Slug
    name: str = Field(min_length=1)
    criteria: list[CriterionInfo] = Field(min_length=1)

    @model_validator(mode="after")
    def _unique_criteria(self) -> Self:
        ids = [c.criterion_id for c in self.criteria]
        if len(set(ids)) != len(ids):
            raise ValueError("a rubric must not repeat a criterion_id")
        return self


class RubricList(BaseSchema):
    rubrics: list[RubricInfo]
