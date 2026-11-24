"""Conservative primary-subject selection, independent of the detector."""

from dataclasses import dataclass
from typing import Any

from .detector_base import DetectionResult
from .region import SubjectRegion, validate_fraction


@dataclass(frozen=True)
class SubjectSelection:
    """Selection decision; preserve reason when no subject can be selected."""

    subject_region: SubjectRegion | None
    reason: str | None


_MULTI_POLICIES = frozenset({"review", "highest_confidence", "largest_area"})


class SingleSubjectSelector:
    """Pick a primary subject after confidence/optional label filtering.

    Default ``multi_policy=review`` keeps the conservative MVP rule: more than
    one candidate → needs human review (no largest-object guess).

    API demos may set ``multi_policy=highest_confidence`` (or ``largest_area``)
    so framing/sharpness can still score on busy photos.
    min_confidence defaults to 0.7 as a starting setting, not a calibrated limit.
    """

    def __init__(self, settings: dict[str, Any] | None = None):
        if settings is None:
            settings = {}
        if not isinstance(settings, dict):
            raise TypeError("settings must be a dictionary or None.")
        if set(settings) - {"min_confidence", "labels", "multi_policy"}:
            raise ValueError("Unknown selector settings.")
        self._minimum = settings.get("min_confidence", 0.7)
        validate_fraction("min_confidence", self._minimum)
        labels = settings.get("labels")
        if labels is not None:
            if not isinstance(labels, (list, tuple)) or not labels or any(
                not isinstance(v, str) or not v.strip() for v in labels
            ):
                raise ValueError("labels must be a nonempty list/tuple of names or None.")
            labels = tuple(labels)
        self._labels = labels
        policy = settings.get("multi_policy", "review")
        if policy not in _MULTI_POLICIES:
            raise ValueError(
                "multi_policy must be one of: review, highest_confidence, largest_area."
            )
        self._multi_policy = policy

    @property
    def settings(self) -> dict[str, Any]:
        return {
            "min_confidence": self._minimum,
            "labels": list(self._labels) if self._labels is not None else None,
            "multi_policy": self._multi_policy,
        }

    def select(self, detections: DetectionResult) -> SubjectSelection:
        """Return an explicit decision, preserving model provenance."""
        if not isinstance(detections, DetectionResult):
            raise TypeError("detections must be a DetectionResult.")
        candidates = [
            c for c in detections.candidates
            if c.confidence >= self._minimum
            and (self._labels is None or c.label in self._labels)
        ]
        if not candidates:
            return SubjectSelection(None, "No candidate meets the subject-selection settings.")
        if len(candidates) != 1:
            if self._multi_policy == "review":
                return SubjectSelection(None, "Multiple candidate subjects require review.")
            if self._multi_policy == "highest_confidence":
                c = max(candidates, key=lambda item: (item.confidence, _area(item)))
                method = "highest_confidence_v1"
            else:
                c = max(candidates, key=lambda item: (_area(item), item.confidence))
                method = "largest_area_v1"
            return SubjectSelection(
                SubjectRegion(
                    c.left, c.top, c.right, c.bottom, reliable=True,
                    source=detections.source, source_version=detections.source_version,
                    label=c.label, confidence=c.confidence,
                    selection_method=method,
                ),
                None,
            )
        c = candidates[0]
        return SubjectSelection(SubjectRegion(
            c.left, c.top, c.right, c.bottom, reliable=True,
            source=detections.source, source_version=detections.source_version,
            label=c.label, confidence=c.confidence,
            selection_method="single_candidate_v1",
        ), None)


def _area(candidate: Any) -> float:
    return max(0.0, (candidate.right - candidate.left) * (candidate.bottom - candidate.top))
