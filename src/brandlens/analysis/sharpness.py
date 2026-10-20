"""Proposed task 3.10: subject/background Laplacian variance.

No resizing, smoothing, absolute-value conversion or contrast adjustment.
Uses Pillow's rounded RGB-to-L grayscale values, OpenCV CV_64F Laplacian
with ksize=1 (four-neighbor stencil), and population variance (ddof=0).
Resolution, texture, noise and contrast affect the result. Native input
resolution is reported; calibrate only under a fixed preprocessing policy.
"""
from dataclasses import asdict, dataclass
from math import isfinite
from numbers import Real

import cv2
import numpy as np
from PIL import Image

from .subject_region import SubjectRegion, region_unavailable_reason, validate_image


@dataclass(frozen=True)
class SharpnessSettings:
    """Numerical validity settings, not brand acceptance thresholds.

    min_region_pixels is the minimum valid stencil centers per region.
    background_epsilon defines a numerically unusable denominator.
    """

    min_region_pixels: int = 16
    background_epsilon: float = 1e-12

    def __post_init__(self):
        if isinstance(self.min_region_pixels, bool) or not isinstance(self.min_region_pixels, int):
            raise TypeError("min_region_pixels must be an integer.")
        if self.min_region_pixels < 2:
            raise ValueError("min_region_pixels must be at least 2.")
        value = self.background_epsilon
        if isinstance(value, bool) or not isinstance(value, Real):
            raise TypeError("background_epsilon must be a real number.")
        if not isfinite(value) or value < 0:
            raise ValueError("background_epsilon must be finite and nonnegative.")
        object.__setattr__(self, "background_epsilon", float(value))

    def to_dict(self):
        return asdict(self)


def measure_sharpness(
    image: Image.Image,
    region: SubjectRegion | None = None,
    settings: SharpnessSettings | None = None,
) -> dict:
    """Return subject/background sharpness and their ratio, without scoring.

    The rectangular subject proxy is rasterized with floor/ceil bounds.
    Background is its complement. A one-pixel cross-shaped erosion keeps
    only Laplacian stencils entirely within each region and image, preventing
    the subject-box boundary from creating spurious sharpness.

    If either region has too few valid pixels, retain any available variance
    and return review status. If background variance <= epsilon, ratio is
    None (never infinity or an arbitrary capped score). Missing/unreliable
    regions also return review status. Validity is not an aesthetic verdict.
    """
    validate_image(image)
    if settings is None:
        settings = SharpnessSettings()
    if not isinstance(settings, SharpnessSettings):
        raise TypeError("settings must be SharpnessSettings or None.")
    measurements = {"subject_sharpness": None, "background_sharpness": None,
                    "sharpness_ratio": None}
    metadata = {"analysis_size": list(image.size), "analysis_resolution": "native_no_resize",
                "sharpness_measure": "variance_of_laplacian", "laplacian_ksize": 1,
                "grayscale": "Pillow_RGB_to_L", "settings": settings.to_dict()}
    reason = region_unavailable_reason(region)
    if reason:
        return {"status": "unavailable_needs_review", "measurements": measurements,
                "reasons": [reason], "metadata": metadata}

    left, top, right, bottom = region.pixel_bounds(image)
    subject = np.zeros((image.height, image.width), dtype=np.uint8)
    subject[top:bottom, left:right] = 1
    stencil = np.array([[0, 1, 0], [1, 1, 1], [0, 1, 0]], dtype=np.uint8)
    masks = [cv2.erode(mask, stencil, borderType=cv2.BORDER_CONSTANT, borderValue=0).astype(bool)
             for mask in (subject, 1 - subject)]
    with image.convert("L") as gray_image:
        gray = np.array(gray_image, dtype=np.float64)
    laplacian = cv2.Laplacian(gray, cv2.CV_64F, ksize=1, borderType=cv2.BORDER_REFLECT_101)
    reasons = []
    counts = {}
    for name, mask in zip(("subject", "background"), masks):
        count = int(mask.sum())
        counts[name] = count
        if count < settings.min_region_pixels:
            reasons.append(f"{name}_region_too_small")
        else:
            measurements[f"{name}_sharpness"] = float(np.var(laplacian[mask], ddof=0))

    subject_value = measurements["subject_sharpness"]
    background_value = measurements["background_sharpness"]
    if background_value is not None and background_value <= settings.background_epsilon:
        reasons.append("background_sharpness_near_zero")
    elif subject_value is not None and background_value is not None:
        ratio = subject_value / background_value
        if isfinite(ratio):
            measurements["sharpness_ratio"] = float(ratio)
        else:
            reasons.append("sharpness_ratio_nonfinite")
    metadata.update(subject_source=region.source, subject_bbox=region.bbox(),
                    subject_pixel_bounds=[left, top, right, bottom], valid_pixel_counts=counts)
    return {"status": "unavailable_needs_review" if reasons else "available",
            "measurements": measurements, "reasons": reasons, "metadata": metadata}
