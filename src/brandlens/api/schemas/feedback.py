"""Reviewer feedback (endpoint #7) and the stored record returned from it."""

from typing import Annotated
from uuid import UUID

from pydantic import StringConstraints, field_validator

from brandlens.api.schemas.base import BaseSchema, Slug, UtcTimestamp
from brandlens.api.schemas.enums import Verdict

Comment = Annotated[str, StringConstraints(strip_whitespace=True, max_length=1000)]


class FeedbackSubmission(BaseSchema):
    verdict: Verdict
    comment: Comment | None = None
    criterion_id: Slug | None = None  # None = feedback on the whole image

    @field_validator("comment")
    @classmethod
    def _blank_comment_is_none(cls, value: str | None) -> str | None:
        return value or None


class FeedbackRecord(BaseSchema):
    feedback_id: UUID
    image_id: UUID
    criterion_id: Slug | None
    verdict: Verdict
    comment: str | None
    created_at: UtcTimestamp
