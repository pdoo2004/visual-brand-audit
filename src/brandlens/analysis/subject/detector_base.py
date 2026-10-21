"""Detection contract shared by replaceable model adapters."""

from abc import ABC, abstractmethod
from dataclasses import dataclass

from PIL import Image

from .region import SubjectRegion, validate_fraction


@dataclass(frozen=True)
class SubjectCandidate:
    """One detected object. Coordinates use the standardized image, in [0, 1]."""

    left: float
    top: float
    right: float
    bottom: float
    label: str
    confidence: float

    def __post_init__(self):
        if not isinstance(self.label, str) or not self.label.strip():
            raise ValueError("label must be a nonempty string.")
        SubjectRegion(
            self.left, self.top, self.right, self.bottom,
            reliable=False, source="candidate_validation", label=self.label,
            confidence=self.confidence,
        )
        validate_fraction("confidence", self.confidence)


@dataclass(frozen=True)
class DetectionResult:
    """Candidates and provenance. Empty candidates mean no usable detections.

    Model/dependency failures raise exceptions rather than masquerading as an
    empty scene. image_size is (width, height) of the standardized input image.
    """

    candidates: tuple[SubjectCandidate, ...]
    source: str
    source_version: str | None
    image_size: tuple[int, int]

    def __post_init__(self):
        if not isinstance(self.candidates, tuple) or any(
            not isinstance(c, SubjectCandidate) for c in self.candidates
        ):
            raise TypeError("candidates must be a tuple of SubjectCandidate objects.")
        if not isinstance(self.source, str) or not self.source.strip():
            raise ValueError("source must be a nonempty string.")
        if self.source_version is not None and (
            not isinstance(self.source_version, str) or not self.source_version.strip()
        ):
            raise ValueError("source_version must be a nonempty string or None.")
        if not isinstance(self.image_size, tuple) or len(self.image_size) != 2:
            raise TypeError("image_size must be a (width, height) tuple.")
        if any(type(v) is not int or v <= 0 for v in self.image_size):
            raise ValueError("image_size must contain positive integers.")


class SubjectDetectorBase(ABC):
    """Return candidates without deciding which is the primary subject.

    Implementations borrow a single-frame RGB/sRGB Pillow image, preserve its
    pixels/metadata, and return normalized boxes in that image's coordinates.
    """

    @abstractmethod
    def detect(self, image: Image.Image) -> DetectionResult:
        """Detect objects. Invalid input or inference failures raise errors."""
        raise NotImplementedError
