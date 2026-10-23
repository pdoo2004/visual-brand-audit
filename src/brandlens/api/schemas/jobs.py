"""Job submission acknowledgement and status polling (endpoints #3, #4, #5)."""

from typing import Literal, Self
from uuid import UUID

from pydantic import Field, model_validator

from brandlens.api.schemas.base import BaseSchema, UtcTimestamp
from brandlens.api.schemas.enums import InputType, JobState
from brandlens.api.schemas.errors import ErrorBody


class JobAccepted(BaseSchema):
    """202 response: the job exists and is queued; poll `status_url` for progress."""

    job_id: UUID
    status: Literal[JobState.QUEUED] = JobState.QUEUED
    input_type: InputType
    created_at: UtcTimestamp
    status_url: str

    @classmethod
    def for_job(cls, job_id: UUID, input_type: InputType, created_at: UtcTimestamp) -> Self:
        """Build the response so every endpoint formats `status_url` the same way."""
        return cls(
            job_id=job_id,
            input_type=input_type,
            created_at=created_at,
            status_url=f"/api/v1/jobs/{job_id}",
        )


class JobProgress(BaseSchema):
    """Counts for the progress screen. `images_failed` is part of `images_done`."""

    images_total: int = Field(ge=0)
    images_done: int = Field(ge=0)
    images_failed: int = Field(ge=0)

    @model_validator(mode="after")
    def _counts_are_consistent(self) -> Self:
        if self.images_done > self.images_total:
            raise ValueError("images_done cannot exceed images_total")
        if self.images_failed > self.images_done:
            raise ValueError("images_failed cannot exceed images_done")
        return self


class JobStatus(BaseSchema):
    job_id: UUID
    status: JobState
    progress: JobProgress
    created_at: UtcTimestamp
    updated_at: UtcTimestamp
    error: ErrorBody | None = None  # present only when status == failed

    @model_validator(mode="after")
    def _error_matches_status(self) -> Self:
        if self.status is JobState.FAILED and self.error is None:
            raise ValueError("a failed job must include an error")
        if self.status is not JobState.FAILED and self.error is not None:
            raise ValueError("error is only allowed when status is 'failed'")
        if self.updated_at < self.created_at:
            raise ValueError("updated_at cannot be earlier than created_at")
        return self
