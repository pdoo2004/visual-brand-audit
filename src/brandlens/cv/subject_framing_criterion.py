"""Measure primary-subject placement without judging composition quality."""

from math import hypot, isfinite
from typing import Any

from .criterion_base import CriterionBase
from .cv_input import CVInput


class SubjectFramingCriterion(CriterionBase):
    """Box center, coverage, edge margins and distance to composition anchors.

    Distances use pixel geometry divided by the image diagonal, preserving
    aspect ratio. Margins use the relevant image dimension. A small distance
    to a thirds intersection is a measurement, not a universally good score.
    Box coverage is not segmented subject area. Edge proximity does not prove
    that a subject was cropped.
    """

    criterion_id = "framing_subject_position"
    implementation_id = "normalized_subject_box_geometry"
    method_version = "1"

    def __init__(self, settings: dict[str, Any] | None = None):
        super().__init__(settings, defaults=self.default_settings())

    @classmethod
    def settings_spec(cls) -> dict[str, Any]:
        return {
            "edge_margin_fraction": {
                "type": "number",
                "default": 0.02,
                "description": "Near-edge cutoff, 0–0.5.",
            }
        }

    @classmethod
    def measurement_specs(cls) -> dict[str, Any]:
        return {
            "subject_center_x": {"type": "number", "unit": "fraction"},
            "subject_center_y": {"type": "number", "unit": "fraction"},
            "subject_box_area_fraction": {"type": "number", "unit": "fraction"},
            "center_distance": {"type": "number", "unit": "image_diagonal_fraction"},
            "nearest_thirds_distance": {
                "type": "number",
                "unit": "image_diagonal_fraction",
            },
            "left_margin": {"type": "number", "unit": "fraction"},
            "right_margin": {"type": "number", "unit": "fraction"},
            "top_margin": {"type": "number", "unit": "fraction"},
            "bottom_margin": {"type": "number", "unit": "fraction"},
            "near_edge": {"type": "boolean", "unit": "boolean"},
        }

    @classmethod
    def input_requirements(cls) -> dict[str, Any]:
        return {**super().input_requirements(), "reliable_subject_region": True}

    def _validate_settings(self, settings: dict[str, Any]) -> None:
        value = settings["edge_margin_fraction"]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError("edge_margin_fraction must be a number.")
        if not isfinite(value) or not 0 <= value <= 0.5:
            raise ValueError("edge_margin_fraction must be between 0 and 0.5.")

    def analyze(self, data: CVInput) -> dict[str, Any]:
        """Return geometry or an explicit unavailable status for missing subject."""
        if not isinstance(data, CVInput):
            raise TypeError("data must be an AnalysisInput.")
        data.__post_init__()  # Revalidate the borrowed, mutable Pillow image.
        box = data.subject_region
        if box is None or not box.reliable:
            return self._make_result(
                {},
                status="unavailable_needs_review",
                reasons=[data.subject_unavailable_reason or
                         "Primary subject region is missing or unreliable."],
            )
        width, height = data.image.size
        diagonal = hypot(width, height)
        cx = (box.left + box.right) / 2
        cy = (box.top + box.bottom) / 2
        margins = {
            "left_margin": box.left, "right_margin": 1 - box.right,
            "top_margin": box.top, "bottom_margin": 1 - box.bottom,
        }
        measurements = {
            "subject_center_x": cx,
            "subject_center_y": cy,
            "subject_box_area_fraction": (box.right - box.left) * (box.bottom - box.top),
            "center_distance": hypot((cx - 0.5) * width, (cy - 0.5) * height) / diagonal,
            "nearest_thirds_distance": min(
                hypot((cx - x) * width, (cy - y) * height) / diagonal
                for x in (1 / 3, 2 / 3) for y in (1 / 3, 2 / 3)
            ),
            **margins,
            "near_edge": any(
                value <= self._settings["edge_margin_fraction"]
                for value in margins.values()
            ),
        }
        result = self._make_result(measurements)
        result["subject_region"] = box.to_dict()
        return result
