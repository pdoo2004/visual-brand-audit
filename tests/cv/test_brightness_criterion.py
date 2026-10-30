"""Numerical and interface tests for BrightnessCriterion."""

import json
import math
import unittest

from PIL import Image

from brandlens.cv.brightness_criterion import BrightnessCriterion
from brandlens.cv.cv_input import CVInput


class TestBrightnessCriterion(unittest.TestCase):
    def analyze_values(self, values, settings=None):
        with Image.new("RGB", (len(values), 1)) as image:
            image.putdata([(v, v, v) for v in values])
            return BrightnessCriterion(settings).analyze(CVInput(image))

    def test_default_partial_and_empty_settings(self):
        expected = {"near_black_max": 10, "near_white_min": 245}
        for settings in (None, {}):
            self.assertEqual(BrightnessCriterion(settings).settings, expected)
        self.assertEqual(
            BrightnessCriterion({"near_black_max": 20}).settings,
            {"near_black_max": 20, "near_white_min": 245},
        )

    def test_settings_are_isolated(self):
        supplied = {"near_black_max": 20}
        a = BrightnessCriterion(supplied)
        b = BrightnessCriterion()
        supplied["near_black_max"] = 200
        snapshot = a.settings
        snapshot["near_white_min"] = 1
        self.assertEqual(a.settings, {"near_black_max": 20, "near_white_min": 245})
        self.assertEqual(b.settings["near_black_max"], 10)

    def test_invalid_settings_rejected(self):
        for settings in ([], "settings", True, {1: 10}, {"near_black_max": True}):
            with self.subTest(settings=settings), self.assertRaises(TypeError):
                BrightnessCriterion(settings)
        for settings in (
            {"typo": 10},
            {"near_black_max": -1},
            {"near_white_min": float("nan")},
            {"near_black_max": 245, "near_white_min": 245},
        ):
            with self.subTest(settings=settings), self.assertRaises(ValueError):
                BrightnessCriterion(settings)

    def test_requires_analysis_input(self):
        with Image.new("RGB", (1, 1)) as image:
            for value in (image, None, {}, "image"):
                with self.subTest(value=type(value)), self.assertRaises(TypeError):
                    BrightnessCriterion().analyze(value)

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
        self.assertEqual(result["criterion_id"], "exposure_brightness")
        self.assertEqual(result["method"]["id"], "pillow_grayscale_brightness")
        self.assertEqual(result["method"]["version"], "1")
        self.assertEqual(result["method"]["parameters"], BrightnessCriterion().settings)
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
            criterion = BrightnessCriterion()
            data = CVInput(image)
            first = criterion.analyze(data)
            second = criterion.analyze(data)
            self.assertEqual(first, second)
            first["measurements"].clear()
            first["method"]["parameters"]["near_black_max"] = -1
            self.assertEqual(criterion.analyze(data), second)
            self.assertEqual(image.tobytes(), before)
            self.assertEqual(image.info, {"example": "keep"})

    def test_uniform_and_single_pixel_images(self):
        for value in (0, 10, 128, 245, 255):
            for count in (1, 7):
                with self.subTest(value=value, count=count):
                    m = self.analyze_values([value] * count)["measurements"]
                    self.assertEqual(m["mean_luminance"], float(value))
                    self.assertEqual(m["near_black_fraction"], float(value <= 10))
                    self.assertEqual(m["near_white_fraction"], float(value >= 245))

    def test_black_white_mean(self):
        self.assertEqual(
            self.analyze_values([0, 255])["measurements"]["mean_luminance"], 127.5
        )

    def test_pillow_rounded_rgb_mean(self):
        with Image.new("RGB", (3, 1)) as image:
            image.putdata([(255, 0, 0), (0, 255, 0), (0, 0, 255)])
            result = BrightnessCriterion().analyze(CVInput(image))
            self.assertEqual(result["measurements"]["mean_luminance"], 85.0)
