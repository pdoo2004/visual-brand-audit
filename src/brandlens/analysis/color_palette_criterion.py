"""Measure dominant colors and distance to a configured brand palette.

Input images must already be standardized to RGB/sRGB. Clustering uses OpenCV
floating-point CIELAB (D65) and scikit-learn k-means. Distance is the proportion-
weighted mean nearest Euclidean Lab distance (Delta E 76), not a brand score.
"""

import re
from typing import Any

import cv2
import numpy as np
from sklearn.cluster import KMeans

from .analysis_input import AnalysisInput
from .criterion_base import CriterionBase


class ColorPaletteCriterion(CriterionBase):
    """Extract dominant colors, optionally comparing them with a brand palette.

    Settings:
        n_clusters: Maximum number of colors; positive int, default 5.
        random_seed: Reproducible sampling/k-means seed, default 42.
        max_sample_pixels: Fit on at most this many pixels; default 50_000.
            None fits all pixels. Must be >= n_clusters when provided.
        brand_palette: Nonempty list of #RRGGBB strings, or None (default).
            None leaves palette_distance unavailable. No brand colors are
            silently assumed.

    Proportions count ALL pixels assigned to the fitted centers, even when
    fitting uses a sample. Fewer colors may be returned for uniform images or
    low-diversity samples. Sampling can miss small regions. RGB/hex centroids
    are display approximations; distance uses the original Lab centers.
    """

    criterion_id = "color_palette_fit"
    implementation_id = "lab_kmeans_weighted_nearest_delta_e_76"
    method_version = "1"

    def __init__(self, settings: dict[str, Any] | None = None):
        super().__init__(settings, defaults=self.default_settings())

    @classmethod
    def settings_spec(cls) -> dict[str, Any]:
        return {
            "n_clusters": {
                "type": "integer",
                "default": 5,
                "description": "Positive maximum color count.",
            },
            "random_seed": {
                "type": "integer",
                "default": 42,
                "description": "0 through 2**32 - 1.",
            },
            "max_sample_pixels": {
                "type": "integer",
                "default": 50000,
                "nullable": True,
                "description": "At least n_clusters; null fits all pixels.",
            },
            "brand_palette": {
                "type": "array",
                "default": None,
                "nullable": True,
                "description": "Nonempty #RRGGBB list; null leaves "
                "distance unavailable.",
            },
        }

    @classmethod
    def measurement_specs(cls) -> dict[str, Any]:
        return {
            "dominant_colors": {
                "type": "array",
                "unit": "RGB_0_255_hex_CIELAB_D65_proportion_0_1",
                "description": "Each color contains rgb, hex, lab, and proportion.",
            },
            "palette_distance": {
                "type": "number",
                "unit": "delta_e_76",
                "nullable": True,
            },
        }

    def _validate_settings(self, settings: dict[str, Any]) -> None:
        for name in ("n_clusters", "random_seed"):
            if type(settings[name]) is not int:
                raise TypeError(f"{name} must be an integer.")
        if settings["n_clusters"] < 1:
            raise ValueError("n_clusters must be positive.")
        if not 0 <= settings["random_seed"] <= 2**32 - 1:
            raise ValueError("random_seed must be between 0 and 2**32 - 1.")
        limit = settings["max_sample_pixels"]
        if limit is not None:
            if type(limit) is not int:
                raise TypeError("max_sample_pixels must be an integer or None.")
            if limit < settings["n_clusters"]:
                raise ValueError("max_sample_pixels must be at least n_clusters.")
        palette = settings["brand_palette"]
        if palette is not None:
            if not isinstance(palette, list):
                raise TypeError(
                    "brand_palette must be a list of #RRGGBB strings or None."
                )
            if not palette:
                raise ValueError(
                    "brand_palette must not be empty; use None if unknown."
                )
            for color in palette:
                if not isinstance(color, str):
                    raise TypeError("Each brand palette color must be a string.")
                if re.fullmatch(r"#[0-9a-fA-F]{6}", color) is None:
                    raise ValueError(
                        f"Invalid palette color: {color!r}; expected #RRGGBB."
                    )

    @staticmethod
    def _rgb_to_lab(rgb: np.ndarray) -> np.ndarray:
        """Convert RGB uint8 values to conventional float Lab units."""
        normalized = rgb.astype(np.float32).reshape(-1, 1, 3) / 255.0
        return (
            cv2.cvtColor(normalized, cv2.COLOR_RGB2Lab)
            .reshape(-1, 3)
            .astype(np.float64)
        )

    @staticmethod
    def _lab_to_rgb(lab: np.ndarray) -> np.ndarray:
        """Convert Lab centers to rounded/clipped display RGB values."""
        rgb = cv2.cvtColor(lab.astype(np.float32).reshape(-1, 1, 3), cv2.COLOR_Lab2RGB)
        return np.rint(np.clip(rgb.reshape(-1, 3), 0, 1) * 255).astype(np.uint8)

    def _extract_colors(self, pixels: np.ndarray) -> list[dict[str, Any]]:
        """Fit on a seeded sample and count full-image cluster membership."""
        pixel_count = len(pixels)
        limit = self._settings["max_sample_pixels"]
        if limit is not None and pixel_count > limit:
            indices = np.random.default_rng(self._settings["random_seed"]).choice(
                pixel_count, size=limit, replace=False
            )
            sample = pixels[indices]
        else:
            sample = pixels
        sample_lab = self._rgb_to_lab(sample)
        unique_lab = np.unique(sample_lab, axis=0)
        cluster_count = min(self._settings["n_clusters"], len(unique_lab))
        if cluster_count == len(unique_lab):
            centers = unique_lab
        else:
            model = KMeans(
                n_clusters=cluster_count,
                init="k-means++",
                n_init=10,
                max_iter=300,
                tol=1e-4,
                random_state=self._settings["random_seed"],
                algorithm="lloyd",
            )
            model.fit(sample_lab)
            centers = model.cluster_centers_
        # Stable ordering also makes exact-distance ties resolve consistently.
        centers = centers[np.lexsort((centers[:, 2], centers[:, 1], centers[:, 0]))]
        counts = np.zeros(len(centers), dtype=np.int64)
        for start in range(0, pixel_count, 10_000):
            lab = self._rgb_to_lab(pixels[start : start + 10_000])
            squared_distance = np.sum(
                (lab[:, None, :] - centers[None, :, :]) ** 2, axis=2
            )
            labels = np.argmin(squared_distance, axis=1)
            counts += np.bincount(labels, minlength=len(centers))
        colors = []
        for center, rgb, count in zip(
            centers, self._lab_to_rgb(centers), counts, strict=True
        ):
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
        colors.sort(key=lambda color: (-color["proportion"], *color["lab"]))
        return colors

    def _palette_distance(self, colors: list[dict[str, Any]]) -> float:
        """Compare full-precision Lab centers with the supplied palette."""
        palette_rgb = np.array(
            [
                [int(color[i : i + 2], 16) for i in (1, 3, 5)]
                for color in self._settings["brand_palette"]
            ],
            dtype=np.uint8,
        )
        centers = np.array([color["lab"] for color in colors], dtype=np.float64)
        weights = np.array([color["proportion"] for color in colors], dtype=np.float64)
        weights /= weights.sum()
        distances = np.linalg.norm(
            centers[:, None, :] - self._rgb_to_lab(palette_rgb)[None, :, :], axis=2
        )
        return float(np.dot(weights, distances.min(axis=1)))

    def analyze(self, data: AnalysisInput) -> dict[str, Any]:
        """Return dominant_colors and palette_distance in the shared envelope.

        Each color contains rgb, hex, lab and proportion. Colors are sorted by
        decreasing proportion, with Lab coordinates breaking ties. Distance is
        nonnegative; smaller means closer to the palette, without a universal
        pass/fail cutoff. It does not measure whether every brand color appears.

        If no palette is supplied, retain dominant colors, return distance None,
        and use unavailable_needs_review with a reason. Invalid inputs raise
        TypeError/ValueError. Never modifies or closes the input image.
        """
        if not isinstance(data, AnalysisInput):
            raise TypeError("data must be an AnalysisInput object.")
        # Revalidate because a borrowed Pillow image remains mutable.
        AnalysisInput(data.image)
        pixels = np.array(data.image, dtype=np.uint8).reshape(-1, 3)
        colors = self._extract_colors(pixels)
        has_palette = self._settings["brand_palette"] is not None
        return self._make_result(
            measurements={
                "dominant_colors": colors,
                "palette_distance": self._palette_distance(colors)
                if has_palette
                else None,
            },
            status="available" if has_palette else "unavailable_needs_review",
            reasons=[]
            if has_palette
            else ["No brand_palette configured; palette distance is unavailable."],
        )
