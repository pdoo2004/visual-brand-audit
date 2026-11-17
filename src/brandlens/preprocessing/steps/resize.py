"""Resize a working image within a bounding box."""

from PIL import Image


def resize_to_fit(
    image: Image.Image,
    max_size: tuple[int, int] | None,
) -> Image.Image:
    """Resize an owned working image in place and return it.

    None disables resizing. The image is never cropped or upscaled.
    """
    if max_size is not None:
        image.thumbnail(
            max_size,
            resample=Image.Resampling.LANCZOS,
        )
    return image