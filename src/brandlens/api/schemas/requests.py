"""Request bodies for submitting an analysis (endpoints #3 and #4)."""

from pydantic import AnyHttpUrl, Field, field_validator

from brandlens.api.schemas.base import BaseSchema, Slug

# Proposed upper bound on crawled pages (stretch feature). Over the cap is rejected,
# not silently clamped, so the caller always knows what will actually run.
MAX_CRAWL_PAGES = 50


class AnalysisOptions(BaseSchema):
    """Fields shared by both ways of submitting images."""

    rubric_id: Slug
    # Omitted = evaluate every criterion in the rubric. If given, it must be non-empty.
    criterion_ids: list[Slug] | None = Field(default=None, min_length=1)

    @field_validator("criterion_ids")
    @classmethod
    def _no_duplicates(cls, value: list[str] | None) -> list[str] | None:
        if value is not None and len(set(value)) != len(value):
            raise ValueError("criterion_ids must not contain duplicates")
        return value


class UploadRequest(AnalysisOptions):
    """The non-file form fields of POST /api/v1/analyses/uploads.

    The image files themselves arrive as FastAPI `UploadFile`s (SCRUM-125), which
    also enforce file type and size. This model validates the remaining form fields.
    """


class UrlSubmission(AnalysisOptions):
    """Body of POST /api/v1/analyses/urls. [STRETCH] - the MVP endpoint returns 501."""

    url: AnyHttpUrl  # http or https only
    max_pages: int | None = Field(default=None, ge=1, le=MAX_CRAWL_PAGES)
