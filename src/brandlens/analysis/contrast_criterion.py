"""Whole-image contrast criterion."""

from typing import Any

import numpy as np

from ._intensity import get_intensity, measure_fractions, validate_cutoffs
from .analysis_input import AnalysisInput
from .criterion_base import CriterionBase


class ContrastCriterion(CriterionBase):
    """Measure intensity spread and extreme-intensity fractions.

    Settings: near_black_max (default 10), near_white_min (default 245).
    Input must already be RGB/sRGB. Population std and linear percentiles
    match the original measurement definitions. No brand scoring is applied.
    """

    criterion_id = "contrast"
    method_id = "pillow_grayscale_contrast"
    
    def __init__(self, settings: dict[str, Any] | None = None):
        super().__init__(
            settings,
            defaults={
                "near_black_max": 10,
                "near_white_min": 245,
            },
        )

    def _validate_settings(self, settings: dict[str, Any]) -> None:
        validate_cutoffs(settings)

    def analyze(self, data: AnalysisInput) -> dict[str, Any]:
        """Return luminance_std, p5_p95_range and extreme fractions.

        Population standard deviation ranges from 0 to 127.5. P95 minus P5
        ranges from 0 to 255. Fractions range from 0 to 1. This measures global
        spread, not subject/background separation. Invalid inputs raise errors.
        """
        if not isinstance(data, AnalysisInput):
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
            units={
                "luminance_std": "grayscale_0_255",
                "p5_p95_range": "grayscale_0_255",
                "near_black_fraction": "fraction_0_1",
                "near_white_fraction": "fraction_0_1",
            },
        )
