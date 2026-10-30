"""Shared input for image-analysis criteria."""

from dataclasses import dataclass

from PIL import Image

from .subject.region import SubjectRegion


@dataclass(frozen=True)
class CVInput:
    """A borrowed, standardized RGB/sRGB image.

    Criteria must not modify or close the image.
    
    """

    image: Image.Image
    subject_region: SubjectRegion | None = None
    subject_unavailable_reason: str | None = None
    
    def __post_init__(self):
        if not isinstance(self.image, Image.Image):
            raise TypeError("image must be a Pillow Image.Image object.")

        if min(self.image.size) <= 0:
            raise ValueError("Image dimensions must be positive.")

        if getattr(self.image, "n_frames", 1) > 1:
            raise ValueError("Multi-frame images are not supported.")

        if self.image.mode != "RGB":
            raise ValueError("image must be standardized to RGB/sRGB.")
        
        if self.subject_region is not None and not isinstance(
            self.subject_region, SubjectRegion
        ):
            raise TypeError("subject_region must be a SubjectRegion or None.")

        reason = self.subject_unavailable_reason
        if reason is not None and (not isinstance(reason, str) or not reason.strip()):
            raise ValueError("subject_unavailable_reason must be a nonempty string or None.")
        if reason is not None and self.subject_region is not None and self.subject_region.reliable:
            raise ValueError("A reliable subject cannot have an unavailable reason.")
