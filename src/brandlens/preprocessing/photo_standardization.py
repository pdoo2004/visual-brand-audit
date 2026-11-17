from dataclasses import dataclass

from PIL import Image

from .steps.color import convert_to_rgb
from .steps.orientation import correct_orientation
from .steps.resize import resize_to_fit


def _validate_image(image: Image.Image) -> None:
    """Check that the input is a Pillow image with positive dimensions."""
    if not isinstance(image, Image.Image):
        raise TypeError("image must be a Pillow image.")

    if min(image.size) <= 0:
        raise ValueError("Image dimensions must be positive.")

    if getattr(image, "n_frames", 1) > 1:
        raise ValueError("Animated or multi-frame images are not supported.")

@dataclass(frozen=True)
class StandardizationSettings:
    """Settings for image standardization.

    Attributes:
        max_size: Maximum width and height in pixels. None preserves
            the dimensions after orientation correction.
        background: RGB background used for transparent pixels.

    Notes:
        Images are never cropped or upscaled.
        Output uses RGB mode and the sRGB color space.
    """

    max_size: tuple[int, int] | None = None
    background: tuple[int, int, int] = (255, 255, 255)
    orientation_enabled: bool = True

    def __post_init__(self):
        """Validate settings.

        Raises:
            TypeError: If settings have incorrect types.
            ValueError: If dimensions or RGB values are invalid.
        """
        if self.max_size is not None:
            if not isinstance(self.max_size, tuple):
                raise TypeError("max_size must be a tuple or None.")
            if len(self.max_size) != 2:
                raise ValueError("max_size must contain width and height.")
            if any(type(value) is not int for value in self.max_size):
                raise TypeError("max_size values must be integers.")
            if any(value < 1 for value in self.max_size):
                raise ValueError("max_size values must be positive.")

        if type(self.orientation_enabled) is not bool:
            raise TypeError("orientation_enabled must be a boolean.")
        if not isinstance(self.background, tuple):
            raise TypeError("background must be a tuple.")
        if len(self.background) != 3:
            raise ValueError("background must contain three RGB values.")
        if any(type(value) is not int for value in self.background):
            raise TypeError("background values must be integers.")
        if any(value < 0 or value > 255 for value in self.background):
            raise ValueError("background values must be between 0 and 255.")

def standardize_image(
    image: Image.Image,
    settings: StandardizationSettings | None = None,
) -> Image.Image:
    """Apply orientation correction, RGB conversion, and optional resizing.

    Args:
        image: Input Pillow image.
        settings: Standardization settings. None uses defaults.

    Notes:
        The input remains owned by the caller and is not modified.
        The caller owns the returned RGB/sRGB image.

        Orientation correction is enabled by default. Disable it when
        orientation has already been handled. None disables resizing.
        
        Metadata other than the output ICC profile is omitted.
    """
    if settings is None:
        settings = StandardizationSettings()

    if not isinstance(settings, StandardizationSettings):
        raise TypeError(
            "settings must be a StandardizationSettings object."
        )

    _validate_image(image)

    oriented = (
        correct_orientation(image)
        if settings.orientation_enabled
        else image.copy()
    )

    try:
        processed = convert_to_rgb(
            oriented,
            background=settings.background,
        )
    finally:
        oriented.close()

    try:
        return resize_to_fit(processed, settings.max_size)
    except BaseException:
        # Release the owned output, then propagate the failure.
        processed.close()
        raise