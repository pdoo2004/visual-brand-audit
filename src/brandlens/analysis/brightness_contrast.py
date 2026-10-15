"""Measure whole-image brightness and contrast.

Input images must already be standardized to RGB/sRGB.

Intensity is calculated using Pillow's RGB-to-L conversion:
    Y = 0.299 R + 0.587 G + 0.114 B

Pillow rounds the result to an 8-bit grayscale value.
Measurements do not modify the input image or assign brand scores.
"""

from dataclasses import asdict, dataclass
from math import isfinite

import numpy as np
from PIL import Image

@dataclass(frozen=True)
class MeasurementSettings:
    """Settings shared by brightness and contrast measurements.

    Attributes:
        near_black_max: Highest intensity counted as near-black.
        near_white_min: Lowest intensity counted as near-white.

    Notes:
        Intensities use a fixed 0–255 scale. Acceptance thresholds,
        such as mean_luminance_min, belong to the evaluation step.
    """

    near_black_max: float = 10
    near_white_min: float = 245

    def __post_init__(self):
        """Validate cutoff types, ranges, and ordering."""
        for name, value in (
            ("near_black_max", self.near_black_max),
            ("near_white_min", self.near_white_min),
        ):
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise TypeError(f"{name} must be a number.")

            if not isfinite(value) or not 0 <= value <= 255:
                raise ValueError(f"{name} must be finite and between 0 and 255.")

        if self.near_black_max >= self.near_white_min:
            raise ValueError(
                "near_black_max must be less than near_white_min."
            )

    def to_dict(self) -> dict[str, float]:
        """Return the settings as a dictionary."""
        return asdict(self)


def _resolve_settings(
    settings: MeasurementSettings | None,
) -> MeasurementSettings:
    """Return default settings or validate the supplied settings."""
    

    return settings


def _get_intensity(image: Image.Image) -> np.ndarray:
    """Return grayscale intensities as a float64 array.

    Raises:
        TypeError: If image is not a Pillow image.
        ValueError: If image is empty, multi-frame, or not RGB.
    """
    if not isinstance(image, Image.Image):
        raise TypeError("image must be a Pillow Image.Image object.")

    if min(image.size) <= 0:
        raise ValueError("Image dimensions must be positive.")

    if getattr(image, "n_frames", 1) > 1:
        raise ValueError("Animated or multi-frame images are not supported.")

    if image.mode != "RGB":
        raise ValueError(
            "image must be standardized to RGB before measurement."
        )

    with image.convert("L") as grayscale:
        return np.array(grayscale, dtype=np.float64)


def _measure_fractions(
    intensity: np.ndarray,
    settings: MeasurementSettings,
) -> dict[str, float]:
    """Calculate near-black and near-white fractions, including cutoffs."""
    return {
        "near_black_fraction": float(
            np.mean(intensity <= settings.near_black_max)
        ),
        "near_white_fraction": float(
            np.mean(intensity >= settings.near_white_min)
        ),
    }


def measure_brightness(
    image: Image.Image,
    settings: MeasurementSettings | None = None,
) -> dict[str, float]:
    """Measure average intensity and extreme-intensity fractions.

    Args:
        image: Standardized RGB/sRGB Pillow image.
        settings: Measurement cutoffs. None uses defaults.

    Returns:
        Dictionary containing:
            mean_luminance: Mean grayscale intensity, from 0 to 255.
            near_black_fraction: Fraction at or below near_black_max.
            near_white_fraction: Fraction at or above near_white_min.

        Both fractions range from 0 to 1.

    Raises:
        TypeError: If image or settings has an incorrect type.
        ValueError: If the image is empty, multi-frame, or not RGB.

    Notes:
        Returns measurements only. Does not evaluate acceptable exposure
        or establish whether the main subject is readable.
    """
    if settings is None:
        settings = MeasurementSettings()
    
    if not isinstance(settings, MeasurementSettings):
        raise TypeError("settings must be a MeasurementSettings object.")
        
    intensity = _get_intensity(image)

    return {
        "mean_luminance": float(np.mean(intensity)),
        **_measure_fractions(intensity, settings),
    }


def measure_contrast(
    image: Image.Image,
    settings: MeasurementSettings | None = None,
) -> dict[str, float]:
    """Measure global intensity spread and extreme-intensity fractions.

    Args:
        image: Standardized RGB/sRGB Pillow image.
        settings: Measurement cutoffs. None uses defaults.

    Returns:
        Dictionary containing:
            luminance_std: Population standard deviation, from 0 to 127.5.
            p5_p95_range: 95th minus 5th percentile, from 0 to 255.
            near_black_fraction: Fraction at or below near_black_max.
            near_white_fraction: Fraction at or above near_white_min.

        Both fractions range from 0 to 1.

    Raises:
        TypeError: If image or settings has an incorrect type.
        ValueError: If the image is empty, multi-frame, or not RGB.

    Notes:
        Uses population standard deviation (ddof=0) and linear percentile
        interpolation. Does not evaluate subject/background separation.
    """
    if settings is None:
        settings = MeasurementSettings()
    
    if not isinstance(settings, MeasurementSettings):
        raise TypeError("settings must be a MeasurementSettings object.")
    
    intensity = _get_intensity(image)
    p5, p95 = np.percentile(intensity, [5, 95], method="linear")

    return {
        "luminance_std": float(np.std(intensity, ddof=0)),
        "p5_p95_range": float(p95 - p5),
        **_measure_fractions(intensity, settings),
    }