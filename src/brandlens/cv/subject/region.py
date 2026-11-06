"""Model-independent subject geometry and provenance."""

from dataclasses import asdict, dataclass, field
from math import isfinite


def validate_fraction(name: str, value: float) -> None:
    """Require a finite built-in number in [0, 1], excluding booleans."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be a number.")
    if not isfinite(value) or not 0 <= value <= 1:
        raise ValueError(f"{name} must be finite and between 0 and 1.")


@dataclass(frozen=True)
class SubjectRegion:
    """Selected box in normalized, standardized-image coordinates.

    reliable is mandatory and keyword-only: the caller must explicitly accept
    or reject the selection. It is not a calibrated probability. confidence
    describes object detection, not whether this is the intended main subject.
    Manual selections should leave confidence=None. source identifies the
    detector/model or manual annotation source. source_version may be a model
    revision or annotation version; selection_method records the selection rule.
    """

    left: float
    top: float
    right: float
    bottom: float
    reliable: bool = field(kw_only=True)
    source: str = field(kw_only=True)
    source_version: str | None = None
    label: str | None = None
    confidence: float | None = None
    selection_method: str = "manual"

    def __post_init__(self):
        for name in ("left", "top", "right", "bottom"):
            validate_fraction(name, getattr(self, name))
        if self.left >= self.right or self.top >= self.bottom:
            raise ValueError("Subject box must have positive width and height.")
        if not isinstance(self.reliable, bool):
            raise TypeError("reliable must be a bool.")
        for name in ("source", "selection_method"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a nonempty string.")
        for name in ("source_version", "label"):
            value = getattr(self, name)
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise ValueError(f"{name} must be a nonempty string or None.")
        if self.confidence is not None:
            validate_fraction("confidence", self.confidence)

    def to_dict(self) -> dict:
        """Return independent JSON-compatible geometry and provenance."""
        return asdict(self)
