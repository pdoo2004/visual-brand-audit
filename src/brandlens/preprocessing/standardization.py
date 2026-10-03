from dataclasses import dataclass
from io import BytesIO

from PIL import Image, ImageCms, ImageOps

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

        if not isinstance(self.background, tuple):
            raise TypeError("background must be a tuple.")
        if len(self.background) != 3:
            raise ValueError("background must contain three RGB values.")
        if any(type(value) is not int for value in self.background):
            raise TypeError("background values must be integers.")
        if any(value < 0 or value > 255 for value in self.background):
            raise ValueError("background values must be between 0 and 255.")

def _convert_to_rgb(
    image: Image.Image,
    background: tuple[int, int, int] = (255, 255, 255),
) -> Image.Image:
    """
    Convert an oriented image to opaque RGB/sRGB.
    Unprofiled RGB, grayscale, and palette images are assumed to represent sRGB colors. 
    Transparency is composited after color conversion.
    
    Only the output ICC profile is retained as metadata. Unprofiled CMYK is rejected.
    
    Args:
        image: Input image, in RGB, RGBA, L, LA, P, 1, or CMYK mode, whose EXIF orientation has already been applied.
        background: Background color expressed as sRGB values.

    """
    supported_modes = ("RGB", "RGBA", "L", "LA", "P", "1", "CMYK")
    if image.mode not in supported_modes:
        raise ValueError(f"Unsupported image mode: {image.mode}.")

    source = image.copy()
    profile_bytes = source.info.get("icc_profile")

    if source.mode == "CMYK" and not profile_bytes:
        raise ValueError("CMYK images require an embedded ICC profile.")

    # Preserve transparency separately from the color channels.
    has_transparency = (
        "A" in source.getbands()
        or "transparency" in source.info
    )
    
    alpha = None
    if has_transparency:
        alpha = source.convert("RGBA").getchannel("A")

    srgb_profile = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB"))

    if profile_bytes:
        # Preserve the source channel representation expected by its profile. 
        if source.mode in ("RGB", "CMYK", "L"):
            color_image = source
        elif source.mode in ("LA", "1"):
            color_image = source.convert("L")
        else:
            color_image = source.convert("RGB")

        try:
            input_profile = ImageCms.ImageCmsProfile(
                BytesIO(profile_bytes)
            )
            rgb = ImageCms.profileToProfile(
                color_image,
                input_profile,
                srgb_profile,
                outputMode="RGB",
                renderingIntent=ImageCms.Intent.RELATIVE_COLORIMETRIC,
            )
        except (ImageCms.PyCMSError, OSError, TypeError, ValueError) as exc:
            raise ValueError(
                "Could not convert the embedded color profile to sRGB."
            ) from exc
    else:
        rgb = source.convert("RGB")

    # Composite transparent pixels onto the configured background.
    if alpha is not None:
        backdrop = Image.new("RGB", rgb.size, background)
        rgb = Image.composite(rgb, backdrop, alpha)

    # Keep only metadata describing the resulting color space.
    rgb.info.clear()
    rgb.info["icc_profile"] = srgb_profile.tobytes()

    return rgb

def standardize_image(
    image: Image.Image,
    settings: StandardizationSettings | None = None,
) -> Image.Image:
    """Apply orientation correction, RGB conversion, and optional resizing.

    Args:
        image: Input Pillow image.
        settings: Standardization settings. None uses defaults.

    Notes:
        Does not adjust brightness, contrast, or sharpness.
        Default settings retain full resolution after orientation
        correction. Metadata other than the output ICC profile is omitted.
    """
    if settings is None:
        settings = StandardizationSettings()

    if not isinstance(settings, StandardizationSettings):
        raise TypeError(
            "settings must be a StandardizationSettings object."
        )

    _validate_image(image)
    
    # Correct orientation on a separate image.
    processed = ImageOps.exif_transpose(image.copy())
    
    # Convert to RGB/sRGB and handle transparency.
    processed = _convert_to_rgb(
        processed,
        background=settings.background,
    )
    
    # Resize within the bounding box without cropping or upscaling.
    if settings.max_size is not None:
        processed.thumbnail(
            settings.max_size,
            resample=Image.Resampling.LANCZOS,
        )

    return processed