"""Test Pillow rounding, cutoff validation and inclusive pixel fractions."""

import io
import unittest

import numpy as np
from PIL import Image

from brandlens.cv._intensity import (
    get_intensity,
    measure_fractions,
    validate_cutoffs,
)


class TestIntensity(unittest.TestCase):
    def test_known_rgb_conversion_shape_and_dtype(self):
        with Image.new("RGB", (4, 1)) as image:
            image.putdata([(255, 0, 0), (0, 255, 0), (0, 0, 255), (1, 1, 1)])
            pixels = image.tobytes()
            actual = get_intensity(image)
            np.testing.assert_array_equal(actual, [[76.0, 150.0, 29.0, 1.0]])
            self.assertEqual(actual.dtype, np.float64)
            actual[0, 0] = 0
            self.assertEqual(image.tobytes(), pixels)

    def test_rejects_invalid_image_inputs(self):
        for value in (None, "image", np.zeros((2, 2))):
            with self.subTest(value=type(value)), self.assertRaises(TypeError):
                get_intensity(value)
        for mode, size in (("L", (2, 2)), ("RGBA", (2, 2)), ("RGB", (0, 1))):
            with self.subTest(mode=mode, size=size), Image.new(mode, size) as image:
                with self.assertRaises(ValueError):
                    get_intensity(image)

    def test_rejects_rgb_multiframe(self):
        with io.BytesIO() as buffer:
            with Image.new("RGB", (2, 2), "red") as a:
                with Image.new("RGB", (2, 2), "blue") as b:
                    a.save(buffer, format="TIFF", save_all=True, append_images=[b])
            buffer.seek(0)
            with Image.open(buffer) as image, self.assertRaises(ValueError):
                get_intensity(image)

    def test_valid_endpoints_and_fractional_cutoffs(self):
        for black, white in ((0, 255), (10, 245), (10.5, 244.5)):
            validate_cutoffs({"near_black_max": black, "near_white_min": white})

    def test_invalid_cutoff_types(self):
        for key in ("near_black_max", "near_white_min"):
            for value in (True, False, "10", None, [], 1 + 2j):
                settings = {"near_black_max": 10, "near_white_min": 245, key: value}
                with self.subTest(key=key, value=value), self.assertRaises(TypeError):
                    validate_cutoffs(settings)

    def test_invalid_cutoff_values_and_order(self):
        for key in ("near_black_max", "near_white_min"):
            for value in (-1, 256, float("nan"), float("inf"), -float("inf")):
                settings = {"near_black_max": 10, "near_white_min": 245, key: value}
                with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                    validate_cutoffs(settings)
        for black, white in ((10, 10), (245, 10)):
            with self.subTest(black=black), self.assertRaises(ValueError):
                validate_cutoffs({"near_black_max": black, "near_white_min": white})

    def test_inclusive_and_fractional_fractions(self):
        values = np.array([[0, 10, 11, 244, 245, 255]], dtype=np.float64)
        for settings in (
            {"near_black_max": 10, "near_white_min": 245},
            {"near_black_max": 10.5, "near_white_min": 244.5},
        ):
            result = measure_fractions(values, settings)
            self.assertEqual(
                result, {"near_black_fraction": 1 / 3, "near_white_fraction": 1 / 3}
            )
            self.assertTrue(all(type(value) is float for value in result.values()))
