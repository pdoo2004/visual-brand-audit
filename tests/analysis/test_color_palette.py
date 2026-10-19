"""Task 3.6: public-interface tests with known colors and Lab distances."""
import copy
import io
import json
import unittest
from dataclasses import FrozenInstanceError

import numpy as np
from PIL import Image

from brandlens.analysis.color_palette import (
    DominantColorSettings,
    extract_dominant_colors,
    measure_color_palette,
    measure_palette_distance,
)


def striped_image(colors, counts):
    image = Image.new("RGB", (sum(counts), 1))
    image.putdata([color for color, count in zip(colors, counts) for _ in range(count)])
    return image


class TestSettings(unittest.TestCase):
    def test_defaults_and_copy(self):
        settings = DominantColorSettings()
        self.assertEqual(settings.to_dict(), {
            "n_clusters": 5, "random_seed": 42, "max_sample_pixels": 50_000,
        })
        data = settings.to_dict()
        data["n_clusters"] = 2
        self.assertEqual(settings.n_clusters, 5)
        with self.assertRaises(FrozenInstanceError):
            settings.n_clusters = 2

    def test_invalid_types(self):
        for field in ("n_clusters", "random_seed", "max_sample_pixels"):
            for value in (True, 2.5, "5"):
                with self.subTest(field=field, value=value), self.assertRaises(TypeError):
                    DominantColorSettings(**{field: value})
        for field in ("n_clusters", "random_seed"):
            with self.subTest(field=field), self.assertRaises(TypeError):
                DominantColorSettings(**{field: None})

    def test_invalid_values(self):
        for kwargs in ({"n_clusters": 0}, {"n_clusters": -1},
                       {"random_seed": -1}, {"random_seed": 2**32},
                       {"max_sample_pixels": 4}, {"max_sample_pixels": 0}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                DominantColorSettings(**kwargs)

    def test_all_pixels_and_seed_endpoints(self):
        for seed in (0, 2**32 - 1):
            settings = DominantColorSettings(random_seed=seed, max_sample_pixels=None)
            self.assertIsNone(settings.max_sample_pixels)


class TestExtraction(unittest.TestCase):
    def test_solid_color_returns_one(self):
        with Image.new("RGB", (8, 8), (255, 0, 0)) as image:
            colors = extract_dominant_colors(image)
            self.assertEqual(len(colors), 1)
            self.assertEqual(colors[0]["proportion"], 1.0)
            np.testing.assert_allclose(colors[0]["rgb"], [255, 0, 0], atol=1)

    def test_known_proportions_and_order(self):
        with striped_image([(255, 0, 0), (0, 0, 255)], [75, 25]) as image:
            colors = extract_dominant_colors(image)
            self.assertEqual([c["proportion"] for c in colors], [0.75, 0.25])
            np.testing.assert_allclose(colors[0]["rgb"], [255, 0, 0], atol=1)
            np.testing.assert_allclose(colors[1]["rgb"], [0, 0, 255], atol=1)

    def test_one_pixel(self):
        with Image.new("RGB", (1, 1), "white") as image:
            self.assertEqual(extract_dominant_colors(image)[0]["proportion"], 1.0)

    def test_actual_kmeans_path_and_repeatability(self):
        # More distinct colors than clusters ensures K-means is exercised.
        with striped_image([(0, 0, 0), (255, 0, 0), (0, 255, 0),
                            (0, 0, 255), (255, 255, 255)], [20] * 5) as image:
            settings = DominantColorSettings(n_clusters=3, max_sample_pixels=None)
            first = extract_dominant_colors(image, settings)
            second = extract_dominant_colors(image, settings)
            self.assertEqual(len(first), 3)
            for a, b in zip(first, second):
                np.testing.assert_allclose(a["lab"], b["lab"], atol=1e-8, rtol=0)
                self.assertAlmostEqual(a["proportion"], b["proportion"])
            self.assertAlmostEqual(sum(c["proportion"] for c in first), 1.0)

    def test_sampling_proportions_use_all_pixels(self):
        # 20,000 pixels spans multiple assignment chunks; fit uses only 100.
        with striped_image([(0, 0, 0), (255, 255, 255)], [14_000, 6_000]) as image:
            settings = DominantColorSettings(n_clusters=2, max_sample_pixels=100)
            colors = extract_dominant_colors(image, settings)
            self.assertEqual([c["proportion"] for c in colors], [0.7, 0.3])
            self.assertEqual(colors, extract_dominant_colors(image, settings))

    def test_tie_order(self):
        with striped_image([(255, 255, 255), (0, 0, 0)], [10, 10]) as image:
            colors = extract_dominant_colors(image)
            self.assertLess(colors[0]["lab"][0], colors[1]["lab"][0])

    def test_defaults_and_output_format(self):
        with Image.new("RGB", (5, 5), "white") as image:
            colors = extract_dominant_colors(image)
            self.assertEqual(colors, extract_dominant_colors(image, None))
            self.assertEqual(colors, extract_dominant_colors(image, DominantColorSettings()))
            for color in colors:
                self.assertEqual(set(color), {"rgb", "hex", "lab", "proportion"})
                self.assertRegex(color["hex"], r"^#[0-9A-F]{6}$")
                self.assertEqual(len(color["rgb"]), 3)
                self.assertEqual(len(color["lab"]), 3)
                for value in color["rgb"]:
                    self.assertIs(type(value), int)
                    self.assertTrue(0 <= value <= 255)
                self.assertTrue(np.isfinite(color["lab"]).all())
                self.assertIs(type(color["proportion"]), float)
            json.dumps(colors, allow_nan=False)

    def test_invalid_inputs(self):
        for value in (None, 123, "image.png", []):
            with self.subTest(value=value), self.assertRaises(TypeError):
                extract_dominant_colors(value)
        with Image.new("RGB", (2, 2)) as image:
            with self.assertRaises(TypeError):
                extract_dominant_colors(image, {})
        for mode in ("L", "P", "RGBA", "CMYK"):
            with Image.new(mode, (2, 2)) as image, self.assertRaises(ValueError):
                extract_dominant_colors(image)
        for size in ((0, 2), (2, 0)):
            with Image.new("RGB", size) as image, self.assertRaises(ValueError):
                extract_dominant_colors(image)

    def test_multiframe_rgb_rejected(self):
        with io.BytesIO() as buffer, Image.new("RGB", (2, 2)) as a, Image.new("RGB", (2, 2), "white") as b:
            a.save(buffer, format="TIFF", save_all=True, append_images=[b])
            buffer.seek(0)
            with Image.open(buffer) as image, self.assertRaises(ValueError):
                extract_dominant_colors(image)


class TestPaletteDistance(unittest.TestCase):
    def test_known_weighted_distance(self):
        # Black is Lab [0, 0, 0]; distances are exactly 10 and 40.
        colors = [{"lab": [10, 0, 0], "proportion": 0.7},
                  {"lab": [40, 0, 0], "proportion": 0.3}]
        self.assertAlmostEqual(measure_palette_distance(colors, ["#000000"]), 19.0)

    def test_euclidean_all_three_coordinates(self):
        colors = [{"lab": [0, 3, 4], "proportion": 1.0}]
        self.assertAlmostEqual(measure_palette_distance(colors, ["#000000"]), 5.0)

    def test_nearest_not_average_and_palette_order(self):
        colors = [{"lab": [0, 0, 0], "proportion": 1.0}]
        self.assertEqual(measure_palette_distance(colors, ["#FFFFFF", "#000000"]), 0.0)
        self.assertEqual(measure_palette_distance(colors, ["#000000", "#FFFFFF"]), 0.0)

    def test_exact_colors_match_own_palette(self):
        with striped_image([(0, 73, 119), (208, 48, 39)], [70, 30]) as image:
            result = measure_color_palette(image, ["#004977", "#d03027"])
            self.assertAlmostEqual(result["palette_distance"], 0.0, places=8)
            self.assertEqual(set(result), {"dominant_colors", "palette_distance"})
            json.dumps(result, allow_nan=False)

    def test_uses_lab_not_display_rgb(self):
        colors = [{"lab": [0, 0, 0], "rgb": [255, 255, 255],
                   "hex": "#FFFFFF", "proportion": 1.0}]
        self.assertEqual(measure_palette_distance(colors, ["#000000"]), 0.0)

    def test_roundoff_normalization(self):
        colors = [{"lab": [10, 0, 0], "proportion": 0.9999999}]
        self.assertAlmostEqual(measure_palette_distance(colors, ["#000000"]), 10.0)

    def test_invalid_palettes(self):
        colors = [{"lab": [0, 0, 0], "proportion": 1.0}]
        for palette in (None, "#000000", 123, [123]):
            with self.subTest(palette=palette), self.assertRaises(TypeError):
                measure_palette_distance(colors, palette)
        for palette in ([], ["#FFF"], ["000000"], ["#GG0000"], ["#00000000"]):
            with self.subTest(palette=palette), self.assertRaises(ValueError):
                measure_palette_distance(colors, palette)

    def test_invalid_colors(self):
        for colors in (None, "colors", 123, [123]):
            with self.subTest(colors=colors), self.assertRaises(TypeError):
                measure_palette_distance(colors, ["#000000"])
        for colors in ([], [{}], [{"lab": [0, 0, 0]}]):
            with self.subTest(colors=colors), self.assertRaises(ValueError):
                measure_palette_distance(colors, ["#000000"])

    def test_invalid_lab(self):
        for lab, exception in (("abc", TypeError), ([True, 0, 0], TypeError),
                               (["0", 0, 0], TypeError), ([0, 0], ValueError),
                               ([101, 0, 0], ValueError), ([-1, 0, 0], ValueError),
                               ([0, float("nan"), 0], ValueError),
                               ([0, 0, float("inf")], ValueError)):
            with self.subTest(lab=lab), self.assertRaises(exception):
                measure_palette_distance([{"lab": lab, "proportion": 1.0}], ["#000000"])

    def test_invalid_weights(self):
        for weight, exception in ((True, TypeError), ("1", TypeError),
                                  (-0.1, ValueError), (1.1, ValueError),
                                  (float("nan"), ValueError), (float("inf"), ValueError),
                                  (0.0, ValueError), (0.8, ValueError)):
            with self.subTest(weight=weight), self.assertRaises(exception):
                measure_palette_distance([{"lab": [0, 0, 0], "proportion": weight}], ["#000000"])

    def test_input_preservation(self):
        palette = ["#000000", "#FFFFFF"]
        with Image.new("RGB", (4, 4), "black") as image:
            image.info["description"] = "original"
            image.getexif()[274] = 1
            before = (image.tobytes(), image.size, image.mode, image.info.copy(), dict(image.getexif()))
            colors = extract_dominant_colors(image)
            original_colors = copy.deepcopy(colors)
            measure_palette_distance(colors, palette)
            measure_color_palette(image, palette)
            self.assertEqual(colors, original_colors)
            self.assertEqual(palette, ["#000000", "#FFFFFF"])
            self.assertEqual(before, (image.tobytes(), image.size, image.mode, image.info.copy(), dict(image.getexif())))


if __name__ == "__main__":
    unittest.main()