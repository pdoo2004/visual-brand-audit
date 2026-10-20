"""Whole-image brightness criterion."""

from typing import Any

import numpy as np

from ._intensity import get_intensity, measure_fractions, validate_cutoffs
from .analysis_input import AnalysisInput
from .criterion_base import CriterionBase


class BrightnessCriterion(CriterionBase):
    """Measure mean intensity and extreme-intensity fractions.

    Settings: near_black_max (default 10), near_white_min (default 245).
    A partial dictionary overrides just the supplied defaults. Cutoffs describe
    measurements, not acceptable brand exposure. Input must be RGB/sRGB.
    """

    criterion_id = "exposure_brightness"
    method_id = "pillow_grayscale_brightness"
    method_version = "1"
    
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
        """Return mean_luminance (0–255) and fractions (0–1).

        Values use rounded grayscale intensity, not physical luminance.
        Raises TypeError/ValueError for invalid inputs. Does not evaluate
        subject readability, modify the input, or assign a brand score.
        """
        if not isinstance(data, AnalysisInput):
            raise TypeError("data must be an AnalysisInput object.")
        intensity = get_intensity(data.image)
        measurements = {
            "mean_luminance": float(np.mean(intensity)),
            **measure_fractions(intensity, self._settings),
        }
        return self._make_result(
            measurements,
            units={
                "mean_luminance": "grayscale_0_255",
                "near_black_fraction": "fraction_0_1",
                "near_white_fraction": "fraction_0_1",
            },
        )
