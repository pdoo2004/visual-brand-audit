"""Fixed vocabularies shared by the API (values match docs/architecture contracts)."""

from enum import StrEnum


class JobState(StrEnum):
    """Lifecycle of one analysis job."""

    QUEUED = "queued"
    CRAWLING = "crawling"  # only used by the [STRETCH] URL path
    PREPROCESSING = "preprocessing"
    ANALYZING = "analyzing"
    SCORING = "scoring"
    COMPLETED = "completed"
    COMPLETED_WITH_ERRORS = "completed_with_errors"
    FAILED = "failed"

    @property
    def is_terminal(self) -> bool:
        """True once the job will not change state again."""
        return self in {JobState.COMPLETED, JobState.COMPLETED_WITH_ERRORS, JobState.FAILED}


class InputType(StrEnum):
    UPLOAD = "upload"
    URL = "url"  # stretch


class ImageStatus(StrEnum):
    """Outcome for a single image. `partial` = CV-only score, tone unavailable."""

    SCORED = "scored"
    PARTIAL = "partial"
    FAILED = "failed"
    FILTERED_OUT = "filtered_out"


class RejectReason(StrEnum):
    """Why the preprocessor removed an image (matches database `images.reject_reason`)."""

    UNSUPPORTED_FORMAT = "unsupported_format"
    TOO_MANY_PIXELS = "too_many_pixels"
    ANIMATED = "animated"
    TOO_SMALL = "too_small"
    EXTREME_ASPECT_RATIO = "extreme_aspect_ratio"
    UNPROCESSABLE = "unprocessable"


class CriterionSource(StrEnum):
    """Which analyzer produces a criterion's evidence."""

    CV = "cv"
    VLM = "vlm"


class Availability(StrEnum):
    OK = "ok"
    UNAVAILABLE_NEEDS_REVIEW = "unavailable_needs_review"


class Verdict(StrEnum):
    AGREE = "agree"
    DISAGREE = "disagree"


class ErrorCode(StrEnum):
    """Error codes from the contract's error table (plus CRAWL_FAILED for the stretch path)."""

    VALIDATION_ERROR = "VALIDATION_ERROR"
    UNSUPPORTED_FILE_TYPE = "UNSUPPORTED_FILE_TYPE"
    FILE_TOO_LARGE = "FILE_TOO_LARGE"
    NOT_FOUND = "NOT_FOUND"
    JOB_NOT_FINISHED = "JOB_NOT_FINISHED"
    NOT_IMPLEMENTED = "NOT_IMPLEMENTED"
    CRAWL_FAILED = "CRAWL_FAILED"
    INTERNAL_ERROR = "INTERNAL_ERROR"
