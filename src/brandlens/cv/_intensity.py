"""Shared intensity helpers for brightness and contrast, not all criteria."""

from math import isfinite
from typing import Any

import numpy as np
from PIL import Image


def validate_cutoffs(settings: dict[str, Any]) -> None:
    """Require finite, ordered cutoffs on the fixed 0–255 intensity scale."""
    for name in ("near_black_max", "near_white_min"):
        value = settings[name]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError(f"{name} must be a number.")
        if not 0 <= value <= 255 or not isfinite(value):
            raise ValueError(f"{name} must be finite and between 0 and 255.")
    if settings["near_black_max"] >= settings["near_white_min"]:
        raise ValueError("near_black_max must be less than near_white_min.")


def get_intensity(image: Image.Image) -> np.ndarray:
    """Return Pillow's rounded 8-bit RGB-to-L values as float64.

    Y = 0.299 R + 0.587 G + 0.114 B, rounded by Pillow.
    RGB mode alone cannot prove sRGB provenance. Color standardization is
    the caller's responsibility. No input pixels or metadata are modified.
    """
    if not isinstance(image, Image.Image):
        raise TypeError("image must be a Pillow Image.Image object.")
    if min(image.size) <= 0:
        raise ValueError("Image dimensions must be positive.")
    if getattr(image, "n_frames", 1) > 1:
        raise ValueError("Animated or multi-frame images are not supported.")
    if image.mode != "RGB":
        raise ValueError("image must be standardized to RGB before measurement.")
    with image.convert("L") as grayscale:
        return np.array(grayscale, dtype=np.float64)


def measure_fractions(
    intensity: np.ndarray, settings: dict[str, Any]
) -> dict[str, float]:
    """Count extreme intensities, including both cutoff boundaries."""
    return {
        "near_black_fraction": float(np.mean(intensity <= settings["near_black_max"])),
        "near_white_fraction": float(np.mean(intensity >= settings["near_white_min"])),
    }
