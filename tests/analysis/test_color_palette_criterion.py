"""Tests for the dictionary-settings ColorPaletteCriterion interface."""

import json
import unittest

import numpy as np
from PIL import Image

from brandlens.analysis.analysis_input import AnalysisInput
from brandlens.analysis.color_palette_criterion import ColorPaletteCriterion


class TestColorPaletteCriterion(unittest.TestCase):
    def image(self, pixels):
        image = Image.new("RGB", (len(pixels), 1))
        image.putdata(pixels)
        self.addCleanup(image.close)
        return image

    def test_defaults_and_partial_override(self):
        self.assertEqual(
            ColorPaletteCriterion().settings,
            {
                "n_clusters": 5,
                "random_seed": 42,
                "max_sample_pixels": 50_000,
                "brand_palette": None,
            },
        )
        self.assertEqual(
            ColorPaletteCriterion({"n_clusters": 2}).settings["random_seed"], 42
        )

    def test_settings_are_deep_copied(self):
        supplied = {"brand_palette": ["#000000"]}
        criterion = ColorPaletteCriterion(supplied)
        supplied["brand_palette"].append("#FFFFFF")
        snapshot = criterion.settings
        snapshot["brand_palette"].append("#FF0000")
        self.assertEqual(criterion.settings["brand_palette"], ["#000000"])

    def test_invalid_types(self):
        cases = [
            [],
            True,
            {"n_clusters": True},
            {"n_clusters": 2.5},
            {"random_seed": False},
            {"max_sample_pixels": 5.5},
            {"brand_palette": "#FFFFFF"},
            {"brand_palette": ("#FFFFFF",)},
            {"brand_palette": [123]},
        ]
        for settings in cases:
            with self.subTest(settings=settings), self.assertRaises(TypeError):
                ColorPaletteCriterion(settings)

    def test_invalid_values(self):
        cases = [
            {"n_clusters": 0},
            {"random_seed": -1},
            {"random_seed": 2**32},
            {"max_sample_pixels": 4},
            {"brand_palette": []},
            {"brand_palette": ["red"]},
            {"brand_palette": ["#FFF"]},
            {"brand_palette": ["#GG0000"]},
            {"typo": 1},
        ]
        for settings in cases:
            with self.subTest(settings=settings), self.assertRaises(ValueError):
                ColorPaletteCriterion(settings)

    def test_requires_analysis_input(self):
        for value in (None, {}, self.image([(0, 0, 0)])):
            with self.subTest(value=type(value)), self.assertRaises(TypeError):
                ColorPaletteCriterion().analyze(value)

    def test_uniform_image_returns_one_color_and_zero_match_distance(self):
        image = self.image([(255, 255, 255)] * 10)
        result = ColorPaletteCriterion({"brand_palette": ["#FFFFFF"]}).analyze(
            AnalysisInput(image)
        )
        colors = result["measurements"]["dominant_colors"]
        self.assertEqual(len(colors), 1)
        self.assertEqual(colors[0]["rgb"], [255, 255, 255])
        self.assertEqual(colors[0]["hex"], "#FFFFFF")
        self.assertEqual(colors[0]["proportion"], 1.0)
        self.assertEqual(result["measurements"]["palette_distance"], 0.0)

    def test_known_black_white_weighted_distance(self):
        image = self.image([(0, 0, 0)] * 3 + [(255, 255, 255)])
        result = ColorPaletteCriterion({"brand_palette": ["#000000"]}).analyze(
            AnalysisInput(image)
        )
        colors = result["measurements"]["dominant_colors"]
        self.assertEqual([c["proportion"] for c in colors], [0.75, 0.25])
        # Black and white have Lab distance 100: 0.75*0 + 0.25*100 = 25.
        self.assertAlmostEqual(
            result["measurements"]["palette_distance"], 25.0, places=5
        )

    def test_each_color_matches_its_nearest_palette_entry(self):
        image = self.image([(0, 0, 0)] * 3 + [(255, 255, 255)])
        criterion = ColorPaletteCriterion({"brand_palette": ["#FFFFFF", "#000000"]})
        result = criterion.analyze(AnalysisInput(image))
        self.assertEqual(result["measurements"]["palette_distance"], 0.0)

    def test_missing_palette_retains_colors_and_reports_reason(self):
        result = ColorPaletteCriterion().analyze(
            AnalysisInput(self.image([(30, 40, 50)]))
        )
        self.assertEqual(result["status"], "unavailable_needs_review")
        self.assertIsNone(result["measurements"]["palette_distance"])
        self.assertEqual(len(result["measurements"]["dominant_colors"]), 1)
        self.assertTrue(result["reasons"])

    def test_palette_case_and_duplicates_do_not_change_distance(self):
        data = AnalysisInput(self.image([(30, 40, 50)]))
        a = ColorPaletteCriterion({"brand_palette": ["#aAbBcC"]}).analyze(data)
        b = ColorPaletteCriterion({"brand_palette": ["#AABBCC", "#AABBCC"]}).analyze(
            data
        )
        self.assertEqual(a["measurements"], b["measurements"])

    def test_real_kmeans_center_uses_lab_mean(self):
        data = AnalysisInput(self.image([(0, 0, 0), (255, 255, 255)]))
        result = ColorPaletteCriterion(
            {"n_clusters": 1, "brand_palette": ["#000000"]}
        ).analyze(data)
        color = result["measurements"]["dominant_colors"][0]
        np.testing.assert_allclose(color["lab"], [50, 0, 0], atol=1e-6)
        self.assertEqual(color["proportion"], 1.0)
        self.assertAlmostEqual(result["measurements"]["palette_distance"], 50.0)
        # A Lab midpoint is not the RGB midpoint 128.
        self.assertNotEqual(color["rgb"], [128, 128, 128])

    def test_sampling_counts_all_pixels_not_just_sample(self):
        pixels = [(0, 0, 0)] * 151 + [(255, 255, 255)] * 50
        data = AnalysisInput(self.image(pixels))
        result = ColorPaletteCriterion(
            {"n_clusters": 2, "max_sample_pixels": 31}
        ).analyze(data)
        colors = result["measurements"]["dominant_colors"]
        self.assertEqual(len(colors), 2)
        self.assertEqual([c["proportion"] for c in colors], [151 / 201, 50 / 201])

    def test_chunked_assignment_and_equal_proportion_order(self):
        image = self.image([(255, 255, 255)] * 5001 + [(0, 0, 0)] * 5001)
        result = ColorPaletteCriterion(
            {"n_clusters": 2, "max_sample_pixels": 31}
        ).analyze(AnalysisInput(image))
        colors = result["measurements"]["dominant_colors"]
        self.assertEqual([c["proportion"] for c in colors], [0.5, 0.5])
        self.assertEqual([c["hex"] for c in colors], ["#000000", "#FFFFFF"])

    def test_deterministic_full_and_sampled_kmeans(self):
        rng = np.random.default_rng(123)
        with Image.fromarray(
            rng.integers(0, 256, (12, 16, 3), dtype=np.uint8)
        ) as image:
            data = AnalysisInput(image)
            for limit in (None, 41):
                criterion = ColorPaletteCriterion(
                    {
                        "n_clusters": 3,
                        "max_sample_pixels": limit,
                        "brand_palette": ["#000000", "#FFFFFF"],
                    }
                )
                first = criterion.analyze(data)
                self.assertEqual(first, criterion.analyze(data))
                colors = first["measurements"]["dominant_colors"]
                self.assertEqual(len(colors), 3)
                self.assertAlmostEqual(sum(c["proportion"] for c in colors), 1.0)
                self.assertEqual(
                    colors, sorted(colors, key=lambda c: (-c["proportion"], *c["lab"]))
                )

    def test_result_schema_json_and_input_preservation(self):
        image = self.image([(0, 0, 0), (255, 255, 255)])
        image.info["example"] = "keep"
        pixels = image.tobytes()
        criterion = ColorPaletteCriterion({"brand_palette": ["#000000"]})
        result = criterion.analyze(AnalysisInput(image))
        self.assertEqual(result["criterion_id"], "color_palette_fit")
        self.assertEqual(result["status"], "available")
        self.assertEqual(result["reasons"], [])
        self.assertEqual(result["method"]["version"], "1")
        self.assertEqual(result["method"]["parameters"], criterion.settings)
        self.assertEqual(result["units"]["palette_distance"], "delta_e_76")
        self.assertNotIn("score", result)
        self.assertEqual(json.loads(json.dumps(result, allow_nan=False)), result)
        self.assertEqual(image.tobytes(), pixels)
        self.assertEqual(image.info, {"example": "keep"})
        for color in result["measurements"]["dominant_colors"]:
            self.assertEqual(set(color), {"rgb", "hex", "lab", "proportion"})
            self.assertTrue(all(type(v) is int and 0 <= v <= 255 for v in color["rgb"]))
            self.assertEqual(len(color["lab"]), 3)
        result["method"]["parameters"]["brand_palette"].append("#FFFFFF")
        self.assertEqual(criterion.settings["brand_palette"], ["#000000"])


if __name__ == "__main__":
    unittest.main()