"""RGB/sRGB conversion and transparency handling."""

from io import BytesIO

from PIL import Image, ImageCms

def convert_to_rgb(
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