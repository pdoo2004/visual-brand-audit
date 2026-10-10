"""Single error envelope used by every endpoint: {"error": {"code", "message", "details"}}."""

from typing import Any

from pydantic import Field

from brandlens.api.schemas.base import BaseSchema
from brandlens.api.schemas.enums import ErrorCode


class ErrorBody(BaseSchema):
    code: ErrorCode
    message: str = Field(min_length=1)
    details: list[Any] = Field(default_factory=list)


class ErrorResponse(BaseSchema):
    error: ErrorBody
