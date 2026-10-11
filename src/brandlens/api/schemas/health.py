"""Response for GET /health."""

from typing import Literal

from pydantic import Field

from brandlens.api.schemas.base import BaseSchema


class HealthResponse(BaseSchema):
    status: Literal["ok"]
    version: str = Field(min_length=1)
