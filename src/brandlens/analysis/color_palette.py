"""Extract dominant colors from standardized RGB/sRGB images.

Clustering uses floating-point CIELAB with a D65 white point.

K-means is fitted on all pixels or a reproducible random sample.
Cluster proportions are calculated by assigning every image pixel
to its nearest fitted cluster.

This module extracts colors only. Palette-distance measurement and
brand scoring are separate operations.
"""

from dataclasses import asdict, dataclass
from typing import TypedDict

import cv2
import re
import numpy as np
from collections.abc import Mapping, Sequence
from math import isclose, isfinite
from numbers import Real
from PIL import Image
from sklearn.cluster import KMeans

class DominantColor(TypedDict):
    """One representative color and its whole-image proportion."""

    rgb: list[int]
    hex: str
    lab: list[float]
    proportion: float


@dataclass(frozen=True)
class DominantColorSettings:
    """Settings for reproducible dominant-color extraction.

    Attributes:
        n_clusters: Requested maximum number of representative colors.
        random_seed: Seed for pixel sampling and K-means initialization.
        max_sample_pixels: Maximum pixels used for fitting. None uses all.

    Notes:
        Color space is fixed to CIELAB D65.
        K-means uses k-means++, 10 initializations, Lloyd's algorithm,
        a maximum of 300 iterations, and tolerance 1e-4.
    """

    n_clusters: int = 5
    random_seed: int = 42
    max_sample_pixels: int | None = 50_000

    def __post_init__(self):
        """Validate settings before image processing."""
        if isinstance(self.n_clusters, bool) or not isinstance(
            self.n_clusters, int
        ):
            raise TypeError("n_clusters must be an integer.")

        if self.n_clusters < 1:
            raise ValueError("n_clusters must be positive.")

        if isinstance(self.random_seed, bool) or not isinstance(
            self.random_seed, int
        ):
            raise TypeError("random_seed must be an integer.")

        if not 0 <= self.random_seed <= 2**32 - 1:
            raise ValueError(
                "random_seed must be between 0 and 2**32 - 1."
            )

        if self.max_sample_pixels is not None:
            if isinstance(self.max_sample_pixels, bool) or not isinstance(
                self.max_sample_pixels, int
            ):
                raise TypeError(
                    "max_sample_pixels must be an integer or None."
                )

            if self.max_sample_pixels < self.n_clusters:
                raise ValueError(
                    "max_sample_pixels must be at least n_clusters."
                )

    def to_dict(self) -> dict[str, int | None]:
        """Return settings as a new dictionary."""
        return asdict(self)


def _get_rgb_pixels(image: Image.Image) -> np.ndarray:
    """Validate input and return an N-by-3 array of RGB pixels."""
    if not isinstance(image, Image.Image):
        raise TypeError("image must be a Pillow Image.Image object.")

    if min(image.size) <= 0:
        raise ValueError("Image dimensions must be positive.")

    if getattr(image, "n_frames", 1) > 1:
        raise ValueError(
            "Animated or multi-frame images are not supported."
        )

    if image.mode != "RGB":
        raise ValueError(
            "image must be standardized to RGB before analysis."
        )

    return np.array(image, dtype=np.uint8).reshape(-1, 3)


def _rgb_to_lab(rgb: np.ndarray) -> np.ndarray:
    """Convert N-by-3 uint8 sRGB values to conventional Lab units.

    Float RGB input is normalized to 0–1 before OpenCV conversion.
    The returned values are not OpenCV's encoded 8-bit Lab values.
    """
    normalized = rgb.astype(np.float32).reshape(-1, 1, 3) / 255.0
    lab = cv2.cvtColor(normalized, cv2.COLOR_RGB2Lab)
    return lab.reshape(-1, 3).astype(np.float64)


def _lab_to_rgb(lab: np.ndarray) -> np.ndarray:
    """Convert Lab centers to clipped, rounded RGB display colors."""
    values = lab.astype(np.float32).reshape(-1, 1, 3)
    rgb = cv2.cvtColor(values, cv2.COLOR_Lab2RGB)
    return np.rint(
        np.clip(rgb.reshape(-1, 3), 0.0, 1.0) * 255.0
    ).astype(np.uint8)


def extract_dominant_colors(
    image: Image.Image,
    settings: DominantColorSettings | None = None,
) -> list[DominantColor]:
    """Extract representative colors and their pixel proportions.

    Args:
        image: Already standardized RGB/sRGB Pillow image.
        settings: Extraction settings. None uses defaults.

    Returns:
        Colors sorted by decreasing proportion, with Lab coordinates
        used to break ties consistently.

        Each entry contains:
            rgb: Three Python integers in the range 0–255.
            hex: RGB display color in #RRGGBB format.
            lab: Unrounded cluster center in CIELAB D65.
            proportion: Fraction of all image pixels in this cluster.

        Proportions sum to approximately one. Empty clusters are omitted.
        Fewer than n_clusters entries may be returned if the fitted
        sample contains too few distinct colors.

    Raises:
        TypeError: If image or settings has an incorrect type.
        ValueError: If image is empty, multi-frame, or not RGB.

    Notes:
        Does not modify the input image or perform color management.
        RGB/hex values are display approximations; retain Lab centers
        for later palette-distance calculations.

        Sampling can miss rare colors. Set max_sample_pixels=None
        to fit using every pixel, at higher computational cost.

        Repeatability assumes the same input, settings, and numerical
        software environment; cross-version bitwise equality is not
        guaranteed.
    """
    if settings is None:
        settings = DominantColorSettings()

    if not isinstance(settings, DominantColorSettings):
        raise TypeError(
            "settings must be a DominantColorSettings object."
        )

    pixels = _get_rgb_pixels(image)
    pixel_count = len(pixels)

    # Sample original pixels without resizing or interpolating colors.
    if (
        settings.max_sample_pixels is not None
        and pixel_count > settings.max_sample_pixels
    ):
        rng = np.random.default_rng(settings.random_seed)
        indices = rng.choice(
            pixel_count,
            size=settings.max_sample_pixels,
            replace=False,
        )
        sample_rgb = pixels[indices]
    else:
        sample_rgb = pixels

    sample_lab = _rgb_to_lab(sample_rgb)

    # Count distinct colors after conversion, since numerical conversion
    # can map different RGB values to the same Lab coordinates.
    unique_lab = np.unique(sample_lab, axis=0)
    cluster_count = min(settings.n_clusters, len(unique_lab))

    if cluster_count == len(unique_lab):
        # Every distinct sampled color can be represented exactly.
        centers = unique_lab
    else:
        model = KMeans(
            n_clusters=cluster_count,
            init="k-means++",
            n_init=10,
            max_iter=300,
            tol=1e-4,
            random_state=settings.random_seed,
            algorithm="lloyd",
        )
        model.fit(sample_lab)
        centers = model.cluster_centers_

    # Canonical center order also makes nearest-center ties consistent.
    order = np.lexsort(
        (centers[:, 2], centers[:, 1], centers[:, 0])
    )
    centers = centers[order]

    # Assign all pixels in chunks to limit temporary memory use.
    counts = np.zeros(len(centers), dtype=np.int64)
    chunk_size = 10_000

    for start in range(0, pixel_count, chunk_size):
        chunk_lab = _rgb_to_lab(
            pixels[start : start + chunk_size]
        )
        squared_distances = np.sum(
            (chunk_lab[:, None, :] - centers[None, :, :]) ** 2,
            axis=2,
        )
        labels = np.argmin(squared_distances, axis=1)
        counts += np.bincount(
            labels,
            minlength=len(centers),
        )

    display_rgb = _lab_to_rgb(centers)
    colors: list[DominantColor] = []

    for center, rgb, count in zip(centers, display_rgb, counts):
        if count == 0:
            continue

        rgb_values = [int(value) for value in rgb]

        colors.append(
            {
                "rgb": rgb_values,
                "hex": "#{:02X}{:02X}{:02X}".format(*rgb_values),
                "lab": [float(value) for value in center],
                "proportion": float(count / pixel_count),
            }
        )

    colors.sort(
        key=lambda color: (
            -color["proportion"],
            *color["lab"],
        )
    )

    return colors

def measure_palette_distance(
    dominant_colors: Sequence[DominantColor],
    brand_palette: Sequence[str],
) -> float:
    """Measure proportion-weighted nearest-palette Delta E 76 distance.

    Args:
        dominant_colors: Output from extract_dominant_colors().
            Lab coordinates must use conventional CIELAB D65 units.
        brand_palette: Nonempty sequence of sRGB hex colors (#RRGGBB).

    Returns:
        Nonnegative Python float. Lower means closer palette similarity.
        This is a distance in Lab units, not a normalized 0–1 score.

    Raises:
        TypeError: If inputs or their values have incorrect types.
        ValueError: If inputs are empty, malformed, nonfinite, or have
            invalid proportions.

    Notes:
        Uses original Lab cluster centers, not rounded RGB/hex colors.
        Does not modify inputs or apply an acceptance threshold.
        Multiple dominant colors may match the same brand color.
    """
    if isinstance(dominant_colors, (str, bytes)) or not isinstance(
        dominant_colors, Sequence
    ):
        raise TypeError("dominant_colors must be a sequence.")

    if not dominant_colors:
        raise ValueError("dominant_colors must not be empty.")

    if isinstance(brand_palette, (str, bytes)) or not isinstance(
        brand_palette, Sequence
    ):
        raise TypeError("brand_palette must be a sequence of hex colors.")

    if not brand_palette:
        raise ValueError("brand_palette must not be empty.")

    # Parse configured sRGB colors using strict #RRGGBB notation.
    palette_rgb = []

    for color in brand_palette:
        if not isinstance(color, str):
            raise TypeError("Each brand palette color must be a string.")

        if re.fullmatch(r"#[0-9a-fA-F]{6}", color) is None:
            raise ValueError(
                f"Invalid palette color {color!r}; expected #RRGGBB."
            )

        palette_rgb.append(
            [int(color[index : index + 2], 16) for index in (1, 3, 5)]
        )

    centers = []
    proportions = []

    for index, color in enumerate(dominant_colors):
        if not isinstance(color, Mapping):
            raise TypeError(
                f"dominant_colors[{index}] must be a mapping."
            )

        if "lab" not in color or "proportion" not in color:
            raise ValueError(
                f"dominant_colors[{index}] requires lab and proportion."
            )

        lab = color["lab"]
        proportion = color["proportion"]

        if isinstance(lab, (str, bytes)) or not isinstance(lab, Sequence):
            raise TypeError("lab must be a sequence of three numbers.")

        if len(lab) != 3:
            raise ValueError("lab must contain exactly three values.")

        for value in lab:
            if isinstance(value, bool) or not isinstance(value, Real):
                raise TypeError("Lab coordinates must be numeric.")

            if not isfinite(value):
                raise ValueError("Lab coordinates must be finite.")

        if not 0 <= lab[0] <= 100:
            raise ValueError("Lab lightness must be between 0 and 100.")

        if isinstance(proportion, bool) or not isinstance(proportion, Real):
            raise TypeError("proportion must be numeric.")

        if not isfinite(proportion) or not 0 <= proportion <= 1:
            raise ValueError(
                "proportion must be finite and between 0 and 1."
            )

        centers.append([float(value) for value in lab])
        proportions.append(float(proportion))

    weights = np.asarray(proportions, dtype=np.float64)
    total_weight = float(weights.sum())

    if not isclose(total_weight, 1.0, rel_tol=0.0, abs_tol=1e-6):
        raise ValueError("Dominant-color proportions must sum to one.")

    # Correct only negligible floating-point drift.
    weights = weights / total_weight

    centers_lab = np.asarray(centers, dtype=np.float64)
    palette_lab = _rgb_to_lab(
        np.asarray(palette_rgb, dtype=np.uint8)
    )

    # Shape: number of dominant colors × number of brand colors.
    distances = np.linalg.norm(
        centers_lab[:, None, :] - palette_lab[None, :, :],
        axis=2,
    )

    nearest_distances = distances.min(axis=1)

    return float(np.dot(weights, nearest_distances))


class ColorPaletteMeasurements(TypedDict):
    """Required measurements for the color_palette_fit criterion."""

    dominant_colors: list[DominantColor]
    palette_distance: float


def measure_color_palette(
    image: Image.Image,
    brand_palette: Sequence[str],
    settings: DominantColorSettings | None = None,
) -> ColorPaletteMeasurements:
    """Extract dominant colors and measure their brand-palette distance.

    Input must already be standardized to RGB/sRGB.
    Returns measurements only, without scoring or pass/fail evaluation.
    """
    dominant_colors = extract_dominant_colors(image, settings)

    return {
        "dominant_colors": dominant_colors,
        "palette_distance": measure_palette_distance(
            dominant_colors,
            brand_palette,
        ),
    }