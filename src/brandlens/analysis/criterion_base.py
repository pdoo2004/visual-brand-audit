"""Common interface for independent image measurement criteria."""

from abc import ABC, abstractmethod
from copy import deepcopy
from inspect import getdoc
from typing import Any

from .analysis_input import AnalysisInput


class CriterionBase(ABC):
    """Base interface: dictionary settings in, measurement dictionary out.

    Each implementation owns settings_spec(), measurement_specs(), and its
    calculation. Settings defaults and result units are read from those specs.
    Scoring is separate. Input images are borrowed and must not be modified.
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
        resolved = (
            deepcopy(defaults) if defaults is not None else self.default_settings()
        )
        unknown = set(settings) - set(resolved)
        if unknown:
            raise ValueError(f"Unknown settings: {', '.join(sorted(unknown))}")
        resolved.update(deepcopy(settings))
        self._validate_settings(resolved)
        self._settings = resolved

    @classmethod
    def settings_spec(cls) -> dict[str, Any]:
        """Describe supported settings; each current setting has a default.

        Metadata is for the catalog. _validate_settings() remains the authority
        for value types, ranges, and relationships between settings.
        """
        return {}

    @classmethod
    def default_settings(cls) -> dict[str, Any]:
        """Read fresh defaults from the specification without constructing a model."""
        return {
            name: deepcopy(spec["default"])
            for name, spec in cls.settings_spec().items()
        }

    @classmethod
    def measurement_specs(cls) -> dict[str, Any]:
        """Describe native measurement names, types, units, and nullable values."""
        return {}

    @classmethod
    def input_requirements(cls) -> dict[str, Any]:
        """Describe the common input contract; subject criteria extend it."""
        return {
            "image": "single_frame_RGB_sRGB",
            "reliable_subject_region": False,
        }

    @classmethod
    def describe(cls, *, include_defaults: bool = True) -> dict[str, Any]:
        """Return independent JSON-compatible metadata without analyzing an image."""
        settings = deepcopy(cls.settings_spec())
        if not include_defaults:
            for spec in settings.values():
                spec.pop("default", None)
        return {
            "criterion_id": cls.criterion_id,
            "implementation_id": cls.implementation_id,
            "method_version": cls.method_version,
            "method": "cv",
            "name": cls.__name__,
            "description": getdoc(cls) or "",
            "settings": settings,
            "measurements": deepcopy(cls.measurement_specs()),
            "input_requirements": deepcopy(cls.input_requirements()),
        }

    @property
    def settings(self) -> dict[str, Any]:
        """Return an independent dictionary of resolved settings."""
        return deepcopy(self._settings)

    def _validate_settings(self, settings: dict[str, Any]) -> None:
        """Validate values and cross-setting constraints in the implementation."""

    @abstractmethod
    def analyze(self, data: AnalysisInput) -> dict[str, Any]:
        """Measure standardized input without modifying it or assigning a score."""
        raise NotImplementedError

    def _make_result(
        self,
        measurements: dict[str, Any],
        units: dict[str, str] | None = None,
        *,
        status: str = "available",
        reasons: list[str] | None = None,
    ) -> dict[str, Any]:
        """Build the existing envelope; derive units for returned measurements.

        Explicit units remain supported for older subclasses. The five current
        criteria use measurement_specs(), so their units have one definition.
        Unavailable results can omit measurements and retain any partial values.
        """
        if status not in ("available", "unavailable_needs_review"):
            raise ValueError("Unknown measurement status.")
        if status == "unavailable_needs_review" and not reasons:
            raise ValueError("Unavailable measurements must include a reason.")
        if units is None:
            specs = self.measurement_specs()
            unknown = set(measurements) - set(specs)
            if unknown:
                raise ValueError(
                    f"Undeclared measurements: {', '.join(sorted(unknown))}"
                )
            units = {name: specs[name]["unit"] for name in measurements}
        return {
            "schema_version": "1.0.0",
            "criterion_id": self.criterion_id,
            "status": status,
            "measurements": deepcopy(measurements),
            "method": {
                "id": self.implementation_id,
                "version": self.method_version,
                "parameters": self.settings,
            },
            "units": deepcopy(units),
            "reasons": list(reasons or []),
        }
