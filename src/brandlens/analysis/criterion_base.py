"""Common interface for independent image measurement criteria."""

from abc import ABC, abstractmethod
from copy import deepcopy
from typing import Any

from .analysis_input import AnalysisInput


class CriterionBase(ABC):
    """Base interface: dictionary settings in, measurement dictionary out.

    Subclasses must implement analyze(). Each criterion owns its measurement
    definitions and settings validation. Brand scoring is a separate step.
    Settings are copied on construction and on access, preventing accidental
    changes through the caller's dictionary. Construct a new instance to change
    settings. Input images are borrowed and must never be modified or closed.
    """

    def __init__(
        self,
        settings: dict[str, Any] | None = None,
        *,
        defaults: dict[str, Any] | None = None,
    ):
        if settings is None:
            settings = {}
        if not isinstance(settings, dict):
            raise TypeError("settings must be a dictionary or None.")

        if any(not isinstance(key, str) for key in settings):
            raise TypeError("Setting names must be strings.")

        resolved = deepcopy(defaults) if defaults is not None else {}

        # Everything in settings must be in defaults (but reverse is not necessary.).
        unknown = set(settings) - set(resolved) 
        if unknown:
            raise ValueError(f"Unknown settings: {', '.join(sorted(unknown))}")

        resolved.update(deepcopy(settings))
        self._validate_settings(resolved)
        self._settings = resolved

    @property
    def settings(self) -> dict[str, Any]:
        """Return an independent dictionary of the resolved settings."""
        return deepcopy(self._settings)

    def _validate_settings(self, settings: dict[str, Any]) -> None:
        """Override when a criterion has settings requiring validation."""

    @abstractmethod
    def analyze(self, data: AnalysisInput) -> dict[str, Any]:
        """Measure a standardized RGB/sRGB image without assigning a score.

        Return criterion_id, status, measurements, method, units and reasons
        using _make_result(). Invalid inputs should raise a clear exception.
        Missing measurements must be flagged, not replaced with zero scores.
        """
        raise NotImplementedError

    def _make_result(
        self,
        measurements: dict[str, Any],
        units: dict[str, str],
        *,
        status: str = "available",
        reasons: list[str] | None = None,
    ) -> dict[str, Any]:
        """Build a consistent result; available means computable, not a pass.

        This is a local measurement format, not the existing HTTP API schema.
        Subclasses are responsible for finite, JSON-compatible metric values.
        """
        if status not in ("available", "unavailable_needs_review"):
            raise ValueError("Unknown measurement status.")
        if status == "unavailable_needs_review" and not reasons:
            raise ValueError("Unavailable measurements must include a reason.")
        return {
            "schema_version": "1.0.0",
            "criterion_id": self.criterion_id,
            "status": status,
            "measurements": deepcopy(measurements),
            "method": {
                "id": self.method_id,
                "version": self.method_version,
                "parameters": self.settings,
            },
            "units": deepcopy(units),
            "reasons": list(reasons or []),
        }
