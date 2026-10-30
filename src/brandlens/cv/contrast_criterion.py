"""Whole-image contrast criterion."""

from typing import Any

import numpy as np

from ._intensity import get_intensity, measure_fractions, validate_cutoffs
from .criterion_base import CriterionBase
from .cv_input import CVInput


class ContrastCriterion(CriterionBase):
    """Measure intensity spread and extreme-intensity fractions.

    Settings: near_black_max (default 10), near_white_min (default 245).
    Input must already be RGB/sRGB. Population std and linear percentiles
    match the original measurement definitions. No brand scoring is applied.
    """

    criterion_id = "contrast"
    implementation_id = "pillow_grayscale_contrast"
    method_version = "1"

    def __init__(self, settings: dict[str, Any] | None = None):
        super().__init__(settings, defaults=self.default_settings())

    @classmethod
    def settings_spec(cls) -> dict[str, Any]:
        return {
            "near_black_max": {
                "type": "number",
                "default": 10,
                "description": "0–255; below near_white_min.",
            },
            "near_white_min": {
                "type": "number",
                "default": 245,
                "description": "0–255; above near_black_max.",
            },
        }

    @classmethod
    def measurement_specs(cls) -> dict[str, Any]:
        return {
            "luminance_std": {"type": "number", "unit": "grayscale_0_255"},
            "p5_p95_range": {"type": "number", "unit": "grayscale_0_255"},
            "near_black_fraction": {"type": "number", "unit": "fraction_0_1"},
            "near_white_fraction": {"type": "number", "unit": "fraction_0_1"},
        }

    def _validate_settings(self, settings: dict[str, Any]) -> None:
        validate_cutoffs(settings)

    def analyze(self, data: CVInput) -> dict[str, Any]:
        """Return luminance_std, p5_p95_range and extreme fractions.

        Population standard deviation ranges from 0 to 127.5. P95 minus P5
        ranges from 0 to 255. Fractions range from 0 to 1. This measures global
        spread, not subject/background separation. Invalid inputs raise errors.
        """
        if not isinstance(data, CVInput):
            raise TypeError("data must be an AnalysisInput object.")
        intensity = get_intensity(data.image)
        p5, p95 = np.percentile(intensity, [5, 95], method="linear")
        measurements = {
            "luminance_std": float(np.std(intensity, ddof=0)),
            "p5_p95_range": float(p95 - p5),
            **measure_fractions(intensity, self._settings),
        }
        return self._make_result(
            measurements,
        )
