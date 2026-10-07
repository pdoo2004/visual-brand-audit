"""Dashboard results (endpoint #6): per-criterion scores, per-image results, summary."""

from typing import Any, Self
from uuid import UUID

from pydantic import Field, model_validator

from brandlens.api.schemas.base import BaseSchema, Score, Slug, Weight
from brandlens.api.schemas.enums import (
    Availability,
    CriterionSource,
    ImageStatus,
    RejectReason,
)
from brandlens.api.schemas.feedback import FeedbackRecord


class CriterionResult(BaseSchema):
    criterion_id: Slug
    score: Score | None  # None when the criterion could not be evaluated
    weight: Weight
    source: CriterionSource
    label: str | None = None  # tone label for the VLM criterion, else None
    explanation: str | None = None
    evidence: list[str] = Field(default_factory=list)
    availability: Availability

    @model_validator(mode="after")
    def _score_matches_availability(self) -> Self:
        # Same rule the database enforces on criterion_scores.
        if self.availability is Availability.OK and self.score is None:
            raise ValueError("score is required when availability is 'ok'")
        if self.availability is not Availability.OK and self.score is not None:
            raise ValueError("score must be null when the criterion is unavailable")
        return self


class ImageResult(BaseSchema):
    image_id: UUID
    source: str = Field(min_length=1)  # "upload:name.jpg" or an image URL
    status: ImageStatus
    reject_reason: RejectReason | None = None  # only for filtered_out images
    overall_score: Score | None = None
    flagged: bool = False
    # CV measurement keys are provisional until SCRUM-116/129/130/131 settle them.
    measurements: dict[str, Any] | None = None
    criteria: list[CriterionResult] = Field(default_factory=list)
    feedback: FeedbackRecord | None = None  # latest reviewer feedback, if any

    @model_validator(mode="after")
    def _fields_match_status(self) -> Self:
        has_score = self.status in {ImageStatus.SCORED, ImageStatus.PARTIAL}
        if has_score and self.overall_score is None:
            raise ValueError(f"overall_score is required when status is '{self.status}'")
        if not has_score and self.overall_score is not None:
            raise ValueError(f"overall_score must be null when status is '{self.status}'")
        if self.status is ImageStatus.FILTERED_OUT and self.reject_reason is None:
            raise ValueError("reject_reason is required when status is 'filtered_out'")
        if self.status is not ImageStatus.FILTERED_OUT and self.reject_reason is not None:
            raise ValueError("reject_reason is only allowed when status is 'filtered_out'")
        ids = [c.criterion_id for c in self.criteria]
        if len(set(ids)) != len(ids):
            raise ValueError("criteria must not repeat a criterion_id")
        return self


class ScoreBucket(BaseSchema):
    bucket: str = Field(min_length=1)  # e.g. "0-20"
    count: int = Field(ge=0)


class ResultsSummary(BaseSchema):
    images_scored: int = Field(ge=0)
    mean_overall: Score | None  # None when no image was scored
    score_distribution: list[ScoreBucket] = Field(default_factory=list)
    flagged_count: int = Field(ge=0)

    @model_validator(mode="after")
    def _mean_matches_count(self) -> Self:
        if (self.mean_overall is None) != (self.images_scored == 0):
            raise ValueError("mean_overall must be null exactly when images_scored is 0")
        return self


class JobResults(BaseSchema):
    job_id: UUID
    rubric_id: Slug
    summary: ResultsSummary
    images: list[ImageResult]

    @model_validator(mode="after")
    def _summary_matches_images(self) -> Self:
        # Catches aggregation bugs: the headline numbers must agree with the rows.
        scored = sum(1 for i in self.images if i.overall_score is not None)
        flagged = sum(1 for i in self.images if i.flagged)
        if self.summary.images_scored != scored:
            raise ValueError("summary.images_scored does not match the images with a score")
        if self.summary.flagged_count != flagged:
            raise ValueError("summary.flagged_count does not match the flagged images")
        return self
