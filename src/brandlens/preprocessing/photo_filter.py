from dataclasses import dataclass
from math import isfinite

from PIL import Image


@dataclass(frozen=True)
class FilterSettings:
    """
    Settings for filtering images by size and aspect ratio.
    
    Attributes:
        min_short_side (int): Minimum allowed length of the shorter
            image side, in pixels. Defaults to 64.
        max_aspect_ratio (float): Maximum allowed ratio of the longer
            side to the shorter side. Defaults to 5.0.
    """

    min_short_side: int = 64
    max_aspect_ratio: float = 5.0

    def __post_init__(self):
        # Check minimum image size.
        if type(self.min_short_side) is not int:
            raise TypeError("min_short_side must be an integer.")
        if self.min_short_side < 1:
            raise ValueError("min_short_side must be at least 1.")

        # Check maximum aspect ratio.
        if type(self.max_aspect_ratio) not in (int, float):
            raise TypeError("max_aspect_ratio must be a number.")
        if not isfinite(self.max_aspect_ratio) or self.max_aspect_ratio < 1:
            raise ValueError("max_aspect_ratio must be finite and at least 1.")

def filter_photo(
    image: Image.Image,
    settings: FilterSettings | None = None,
) -> Image.Image | None:
    """Return the original image if it passes the filter, otherwise None.

    Checks minimum side length and longest-to-shortest side ratio.
    Does not modify the image or confirm that it is a photograph.
    
    Args:
        image (Image.Image): Input Pillow image. It is not modified.
        settings (FilterSettings | None): Filtering thresholds.
            If None, the default FilterSettings are used.

    """
    if not isinstance(image, Image.Image):
        raise TypeError("image must be a Pillow Image. Image object.")

    if settings is None:
        settings = FilterSettings()
    elif not isinstance(settings, FilterSettings):
        raise TypeError("settings must be a FilterSettings object.")

    # Get image dimensions.
    width, height = image.size
    short_side = min(width, height)
    long_side = max(width, height)

    if short_side <= 0:
        raise ValueError("Image dimensions must be positive.")
    if short_side < settings.min_short_side:
        return None
    if long_side / short_side > settings.max_aspect_ratio:
        return None

    return image