"""Building blocks reused by every schema."""

from datetime import UTC, datetime
from typing import Annotated

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    PlainSerializer,
    StringConstraints,
)

# Identifiers such as "exposure_brightness" or "default-v1": lowercase, digits, _ or -.
Slug = Annotated[
    str,
    StringConstraints(pattern=r"^[a-z0-9]+(?:[_-][a-z0-9]+)*$", min_length=1, max_length=64),
]

# Scores run 0-100; weights run 0-1 (see interface contracts, section 1).
Score = Annotated[float, Field(ge=0, le=100)]
Weight = Annotated[float, Field(ge=0, le=1)]


class BaseSchema(BaseModel):
    """Base for all API models. Unknown fields are rejected, so typos fail loudly."""

    model_config = ConfigDict(extra="forbid")


def _require_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("timestamp must include a timezone, e.g. 2026-10-05T14:03:22.123Z")
    # Keep millisecond precision only, so a value always equals what is stored and sent.
    utc = value.astimezone(UTC)
    return utc.replace(microsecond=utc.microsecond // 1000 * 1000)


def _format_timestamp(value: datetime) -> str:
    """Contract format: ISO 8601 UTC with millisecond precision and a trailing Z."""
    value = value.astimezone(UTC)
    return value.strftime("%Y-%m-%dT%H:%M:%S.") + f"{value.microsecond // 1000:03d}Z"


UtcTimestamp = Annotated[
    datetime,
    AfterValidator(_require_utc),
    PlainSerializer(_format_timestamp, return_type=str, when_used="json"),
]
