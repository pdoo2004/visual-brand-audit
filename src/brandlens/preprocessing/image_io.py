from pathlib import Path

from PIL import Image


def load_image(
    path: str | Path,
    supported_formats: tuple[str, ...] = ("JPEG", "PNG", "WEBP"),
    max_pixels: int = 25000000,
) -> Image.Image:
    """Load a supported, single-frame image.

    Args:
        path: Path to the input image.
        supported_formats: Allowed Pillow format names.
        max_pixels: Maximum allowed number of pixels.

        Format detection uses file contents, not the filename extension.
        The original file is not modified.
    """
    if not isinstance(path, (str, Path)):
        raise TypeError("path must be a string or Path.")

    if not isinstance(supported_formats, tuple):
        raise TypeError("supported_formats must be a tuple.")
    if not supported_formats:
        raise ValueError("supported_formats cannot be empty.")
    if any(not isinstance(value, str) for value in supported_formats):
        raise TypeError("supported_formats must contain strings.")

    if type(max_pixels) is not int:
        raise TypeError("max_pixels must be an integer.")
    if max_pixels < 1:
        raise ValueError("max_pixels must be positive.")

    formats = tuple(value.upper() for value in supported_formats)

    with Image.open(path, formats=formats) as image:
        if getattr(image, "n_frames", 1) > 1:
            raise ValueError("Animated or multi-frame images are not supported.")

        if image.width * image.height > max_pixels:
            raise ValueError(
                f"Image exceeds the limit of {max_pixels:,} pixels."
            )

        # Decode while the file is open, then detach the image.
        image.load()
        return image.copy()