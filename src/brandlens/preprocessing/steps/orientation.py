"""EXIF orientation correction."""

from PIL import Image, ImageOps


def correct_orientation(image: Image.Image) -> Image.Image:
    """Return an oriented copy without modifying the caller's image."""
    return ImageOps.exif_transpose(image.copy())