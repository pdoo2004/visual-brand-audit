"""Pydantic request/response schemas for the Backend API (SCRUM-153).

Source of truth: docs/architecture/ interface contracts (section 3.1) and the
database schema. Import from here: `from brandlens.api.schemas import JobStatus`.
"""

from brandlens.api.schemas.enums import (
    Availability,
    CriterionSource,
    ErrorCode,
    ImageStatus,
    InputType,
    JobState,
    RejectReason,
    Verdict,
)
from brandlens.api.schemas.errors import ErrorBody, ErrorResponse
from brandlens.api.schemas.feedback import FeedbackRecord, FeedbackSubmission
from brandlens.api.schemas.health import HealthResponse
from brandlens.api.schemas.jobs import JobAccepted, JobProgress, JobStatus
from brandlens.api.schemas.requests import (
    MAX_CRAWL_PAGES,
    AnalysisOptions,
    UploadRequest,
    UrlSubmission,
)
from brandlens.api.schemas.results import (
    CriterionResult,
    ImageResult,
    JobResults,
    ResultsSummary,
    ScoreBucket,
)
from brandlens.api.schemas.rubrics import CriterionInfo, RubricInfo, RubricList

__all__ = [
    "MAX_CRAWL_PAGES",
    "AnalysisOptions",
    "Availability",
    "CriterionInfo",
    "CriterionResult",
    "CriterionSource",
    "ErrorBody",
    "ErrorCode",
    "ErrorResponse",
    "FeedbackRecord",
    "FeedbackSubmission",
    "HealthResponse",
    "ImageResult",
    "ImageStatus",
    "InputType",
    "JobAccepted",
    "JobProgress",
    "JobResults",
    "JobState",
    "JobStatus",
    "RejectReason",
    "ResultsSummary",
    "RubricInfo",
    "RubricList",
    "ScoreBucket",
    "UploadRequest",
    "UrlSubmission",
    "Verdict",
]
