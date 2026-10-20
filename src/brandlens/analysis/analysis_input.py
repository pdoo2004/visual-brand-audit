"""Shared input for image-analysis criteria."""

from dataclasses import dataclass

from PIL import Image


@dataclass(frozen=True)
class AnalysisInput:
    """A borrowed, standardized RGB/sRGB image.

    Criteria must not modify or close the image.
    """

    image: Image.Image

    def __post_init__(self):
        if not isinstance(self.image, Image.Image):
            raise TypeError("image must be a Pillow Image.Image object.")

        if min(self.image.size) <= 0:
            raise ValueError("Image dimensions must be positive.")

        if getattr(self.image, "n_frames", 1) > 1:
            raise ValueError("Multi-frame images are not supported.")

        if self.image.mode != "RGB":
            raise ValueError("image must be standardized to RGB/sRGB.")