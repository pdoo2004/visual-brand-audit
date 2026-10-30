"""Numerical and interface tests for ContrastCriterion."""

import json
import math
import unittest

from PIL import Image

from brandlens.cv.cv_input import CVInput
from brandlens.cv.contrast_criterion import ContrastCriterion


class TestContrastCriterion(unittest.TestCase):
    def analyze_values(self, values, settings=None):
        with Image.new("RGB", (len(values), 1)) as image:
            image.putdata([(v, v, v) for v in values])
            return ContrastCriterion(settings).analyze(CVInput(image))

    def test_default_partial_and_empty_settings(self):
        expected = {"near_black_max": 10, "near_white_min": 245}
        for settings in (None, {}):
            self.assertEqual(ContrastCriterion(settings).settings, expected)
        self.assertEqual(
            ContrastCriterion({"near_black_max": 20}).settings,
            {"near_black_max": 20, "near_white_min": 245},
        )

    def test_settings_are_isolated(self):
        supplied = {"near_black_max": 20}
        a = ContrastCriterion(supplied)
        b = ContrastCriterion()
        supplied["near_black_max"] = 200
        snapshot = a.settings
        snapshot["near_white_min"] = 1
        self.assertEqual(a.settings, {"near_black_max": 20, "near_white_min": 245})
        self.assertEqual(b.settings["near_black_max"], 10)

    def test_invalid_settings_rejected(self):
        for settings in ([], "settings", True, {1: 10}, {"near_black_max": True}):
            with self.subTest(settings=settings), self.assertRaises(TypeError):
                ContrastCriterion(settings)
        for settings in (
            {"typo": 10},
            {"near_black_max": -1},
            {"near_white_min": float("nan")},
            {"near_black_max": 245, "near_white_min": 245},
        ):
            with self.subTest(settings=settings), self.assertRaises(ValueError):
                ContrastCriterion(settings)

    def test_requires_analysis_input(self):
        with Image.new("RGB", (1, 1)) as image:
            for value in (image, None, {}, "image"):
                with self.subTest(value=type(value)), self.assertRaises(TypeError):
                    ContrastCriterion().analyze(value)

    def test_result_contract(self):
        result = self.analyze_values([0, 255])
        self.assertEqual(
            set(result),
            {
                "schema_version",
                "criterion_id",
                "status",
                "measurements",
                "method",
                "units",
                "reasons",
            },
        )
        self.assertEqual(result["criterion_id"], "contrast")
        self.assertEqual(result["method"]["id"], "pillow_grayscale_contrast")
        self.assertEqual(result["method"]["version"], "1")
        self.assertEqual(result["method"]["parameters"], ContrastCriterion().settings)
        self.assertEqual(result["schema_version"], "1.0.0")
        self.assertEqual(result["status"], "available")
        self.assertEqual(result["reasons"], [])
        self.assertEqual(set(result["units"]), set(result["measurements"]))
        for key, unit in result["units"].items():
            expected = "fraction_0_1" if key.endswith("fraction") else "grayscale_0_255"
            self.assertEqual(unit, expected)
        self.assertNotIn("score", result)
        self.assertEqual(json.loads(json.dumps(result, allow_nan=False)), result)
        self.assertTrue(
            all(
                type(v) is float and math.isfinite(v)
                for v in result["measurements"].values()
            )
        )

    def test_default_and_custom_inclusive_fractions(self):
        values = [0, 10, 11, 244, 245, 255]
        default = self.analyze_values(values)["measurements"]
        custom = self.analyze_values(
            values, {"near_black_max": 11, "near_white_min": 244}
        )["measurements"]
        self.assertEqual(default["near_black_fraction"], 1 / 3)
        self.assertEqual(default["near_white_fraction"], 1 / 3)
        self.assertEqual(custom["near_black_fraction"], 0.5)
        self.assertEqual(custom["near_white_fraction"], 0.5)

    def test_repeatable_and_preserves_input_and_settings(self):
        with Image.new("RGB", (3, 2), (20, 30, 40)) as image:
            image.info["example"] = "keep"
            before = image.tobytes()
            criterion = ContrastCriterion()
            data = CVInput(image)
            first = criterion.analyze(data)
            second = criterion.analyze(data)
            self.assertEqual(first, second)
            first["measurements"].clear()
            first["method"]["parameters"]["near_black_max"] = -1
            self.assertEqual(criterion.analyze(data), second)
            self.assertEqual(image.tobytes(), before)
            self.assertEqual(image.info, {"example": "keep"})

    def test_uniform_and_single_pixel_have_zero_spread(self):
        for value in (0, 128, 255):
            for count in (1, 7):
                with self.subTest(value=value, count=count):
                    m = self.analyze_values([value] * count)["measurements"]
                    self.assertEqual(m["luminance_std"], 0.0)
                    self.assertEqual(m["p5_p95_range"], 0.0)

    def test_population_std_and_linear_percentiles(self):
        m = self.analyze_values([0, 10, 20, 30])["measurements"]
        self.assertAlmostEqual(m["luminance_std"], math.sqrt(125))
        self.assertAlmostEqual(m["p5_p95_range"], 27.0)

    def test_equal_black_white_maximum_std(self):
        m = self.analyze_values([0, 255])["measurements"]
        self.assertEqual(m["luminance_std"], 127.5)
        self.assertEqual(m["p5_p95_range"], 229.5)
        # Enough pixels at each extreme makes the percentile range 255.
        m = self.analyze_values([0] * 10 + [255] * 10)["measurements"]
        self.assertEqual(m["p5_p95_range"], 255.0)
