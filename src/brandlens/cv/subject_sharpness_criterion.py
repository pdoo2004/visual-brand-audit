"""Subject/background detail measurements using a discrete Laplacian."""

from typing import Any

import numpy as np

from .criterion_base import CriterionBase
from .cv_input import CVInput


class SubjectSharpnessCriterion(CriterionBase):
    """Measure Laplacian variance inside/outside a primary-subject box.

    Uses Pillow 8-bit grayscale and the fixed 4-neighbor kernel
    [[0,1,0],[1,-4,1],[0,1,0]], at original resolution. Only pixels whose full
    3x3 neighborhood lies within the same region are included. Image borders
    and subject-box boundaries are excluded, avoiding artificial edge detail.

    Noise, texture, resolution and compression affect these measurements.
    A bounding box includes some background and its complement may contain
    other subjects. These are detail proxies, not proof of focus or saliency.
    No resizing, enhancement, subject detection or brand scoring occurs.
    """

    criterion_id = "sharpness_subject_emphasis"
    implementation_id = "subject_box_laplacian_variance_4_neighbor"
    method_version = "1"

    def __init__(self, settings: dict[str, Any] | None = None):
        super().__init__(settings, defaults=self.default_settings())

    @classmethod
    def settings_spec(cls) -> dict[str, Any]:
        return {
            "min_region_pixels": {
                "type": "integer",
                "default": 16,
                "description": "At least 2 valid region samples.",
            }
        }

    @classmethod
    def measurement_specs(cls) -> dict[str, Any]:
        return {
            "image_width": {"type": "integer", "unit": "pixels"},
            "image_height": {"type": "integer", "unit": "pixels"},
            "subject_sample_pixels": {"type": "integer", "unit": "pixels"},
            "background_sample_pixels": {"type": "integer", "unit": "pixels"},
            "subject_laplacian_variance": {
                "type": "number",
                "unit": "intensity_squared",
                "nullable": True,
            },
            "background_laplacian_variance": {
                "type": "number",
                "unit": "intensity_squared",
                "nullable": True,
            },
            "detail_emphasis_index": {
                "type": "number",
                "unit": "dimensionless",
                "nullable": True,
                "description": "(subject-background)/(subject+background), "
                "[-1, 1]; null if undefined.",
            },
        }

    @classmethod
    def input_requirements(cls) -> dict[str, Any]:
        return {**super().input_requirements(), "reliable_subject_region": True}

    def _validate_settings(self, settings: dict[str, Any]) -> None:
        value = settings["min_region_pixels"]
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError("min_region_pixels must be an integer.")
        if value < 2:
            raise ValueError("min_region_pixels must be at least 2.")

    def analyze(self, data: CVInput) -> dict[str, Any]:
        """Return regional variances and their normalized difference.

        Emphasis index = (subject variance - background variance) / their sum.
        Range [-1,1], with positive values meaning more subject-region detail.
        When both variances are zero, the index is None with a review reason.
        Partial measurements can accompany unavailable_needs_review.
        """
        if not isinstance(data, CVInput):
            raise TypeError("data must be an AnalysisInput.")
        data.__post_init__()
        box = data.subject_region
        if box is None or not box.reliable:
            return self._make_result(
                {},
                status="unavailable_needs_review",
                reasons=[
                    data.subject_unavailable_reason
                    or "Primary subject region is missing or unreliable."
                ],
            )
        width, height = data.image.size
        if min(width, height) < 3:
            return self._make_result(
                {},
                status="unavailable_needs_review",
                reasons=["Image must be at least 3 by 3 pixels."],
            )
        with data.image.convert("L") as gray:
            intensity = np.array(gray, dtype=np.float64)
        lap = (
            intensity[:-2, 1:-1]
            + intensity[2:, 1:-1]
            + intensity[1:-1, :-2]
            + intensity[1:-1, 2:]
            - 4 * intensity[1:-1, 1:-1]
        )
        # Pixel centers define membership in the half-open normalized box.
        x = (np.arange(width) + 0.5) / width
        y = (np.arange(height) + 0.5) / height
        mask = (
            (y[:, None] >= box.top)
            & (y[:, None] < box.bottom)
            & (x[None, :] >= box.left)
            & (x[None, :] < box.right)
        )
        subject = np.ones(lap.shape, dtype=bool)
        background = np.ones(lap.shape, dtype=bool)
        for dy in range(3):
            for dx in range(3):
                neighbor = mask[dy : dy + height - 2, dx : dx + width - 2]
                subject &= neighbor
                background &= ~neighbor
        measurements = {"image_width": width, "image_height": height}
        reasons = []
        variances = {}
        for name, region in (("subject", subject), ("background", background)):
            count = int(np.count_nonzero(region))
            measurements[f"{name}_sample_pixels"] = count
            value = None
            if count < self._settings["min_region_pixels"]:
                reasons.append(
                    f"Too few valid {name} pixels for sharpness measurement."
                )
            else:
                value = float(np.var(lap[region], ddof=0))
            variances[name] = value
            measurements[f"{name}_laplacian_variance"] = value
        sv, bv = variances["subject"], variances["background"]
        emphasis = None
        if sv is not None and bv is not None:
            if sv + bv == 0:
                reasons.append(
                    "Both regions have zero Laplacian variance; emphasis is undefined."
                )
            else:
                emphasis = (sv - bv) / (sv + bv)
        measurements["detail_emphasis_index"] = emphasis
        result = self._make_result(
            measurements,
            status="unavailable_needs_review" if reasons else "available",
            reasons=reasons,
        )

        result["subject_region"] = box.to_dict()
        return result
