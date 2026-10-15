"""Public-interface tests for task 3.5; synthetic inputs need no downloads."""
import io
import math
import unittest
from dataclasses import FrozenInstanceError

from PIL import Image

from brandlens.analysis.brightness_contrast import (
    MeasurementSettings,
    measure_brightness,
    measure_contrast,
)

def gray_image(values):
    image = Image.new("RGB", (len(values), 1))
    image.putdata([(value, value, value) for value in values])
    return image


class TestMeasurementSettings(unittest.TestCase):
    def test_defaults_and_dictionary_copy(self):
        settings = MeasurementSettings()
        self.assertEqual(settings.to_dict(), {"near_black_max": 10, "near_white_min": 245})
        result = settings.to_dict()
        result["near_black_max"] = 20
        self.assertEqual(settings.near_black_max, 10)

    def test_frozen(self):
        with self.assertRaises(FrozenInstanceError):
            MeasurementSettings().near_black_max = 20

    def test_invalid_types(self):
        for field in ("near_black_max", "near_white_min"):
            for value in (True, False, None, "10", [], 1j):
                with self.subTest(field=field, value=value), self.assertRaises(TypeError):
                    MeasurementSettings(**{field: value})

    def test_invalid_values(self):
        for field in ("near_black_max", "near_white_min"):
            for value in (-1, 256, float("inf"), float("-inf"), float("nan")):
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    MeasurementSettings(**{field: value})

    def test_cutoff_order(self):
        for black, white in ((10, 10), (245, 10)):
            with self.subTest(black=black, white=white), self.assertRaises(ValueError):
                MeasurementSettings(black, white)

    def test_valid_endpoints_and_fractional_cutoffs(self):
        self.assertEqual(MeasurementSettings(0, 255).near_white_min, 255)
        self.assertEqual(MeasurementSettings(10.5, 244.5).near_black_max, 10.5)


class TestMeasurements(unittest.TestCase):
    def test_uniform_images(self):
        for level in (0, 128, 255):
            with self.subTest(level=level), Image.new("RGB", (8, 8), (level,) * 3) as image:
                self.assertEqual(measure_brightness(image), {
                    "mean_luminance": float(level),
                    "near_black_fraction": float(level <= 10),
                    "near_white_fraction": float(level >= 245),
                })
                self.assertEqual(measure_contrast(image), {
                    "luminance_std": 0.0, "p5_p95_range": 0.0,
                    "near_black_fraction": float(level <= 10),
                    "near_white_fraction": float(level >= 245),
                })

    def test_equal_black_white_maximum_std(self):
        with gray_image([0] * 10 + [255] * 10) as image:
            self.assertEqual(measure_brightness(image)["mean_luminance"], 127.5)
            self.assertEqual(measure_contrast(image), {
                "luminance_std": 127.5, "p5_p95_range": 255.0,
                "near_black_fraction": 0.5, "near_white_fraction": 0.5,
            })

    def test_population_std_and_linear_percentiles(self):
        # Two samples: p5=12, p95=48; population std=20 (not sample std).
        with gray_image([10, 50]) as image:
            result = measure_contrast(image)
            self.assertEqual(result["luminance_std"], 20.0)
            self.assertAlmostEqual(result["p5_p95_range"], 36.0)

    def test_single_pixel(self):
        with gray_image([123]) as image:
            self.assertEqual(measure_brightness(image)["mean_luminance"], 123.0)
            self.assertEqual(measure_contrast(image)["p5_p95_range"], 0.0)

    def test_rgb_weighting(self):
        for color, expected in (((255, 0, 0), 76), ((0, 255, 0), 150), ((0, 0, 255), 29)):
            with self.subTest(color=color), Image.new("RGB", (2, 2), color) as image:
                self.assertEqual(measure_brightness(image)["mean_luminance"], expected)

    def test_inclusive_cutoff_boundaries(self):
        with gray_image([9, 10, 11, 244, 245, 246]) as image:
            for measure in (measure_brightness, measure_contrast):
                with self.subTest(function=measure.__name__):
                    result = measure(image)
                    self.assertAlmostEqual(result["near_black_fraction"], 2 / 6)
                    self.assertAlmostEqual(result["near_white_fraction"], 2 / 6)

    def test_custom_settings_and_separate_criteria(self):
        with gray_image([10, 20, 230, 245]) as image:
            brightness = measure_brightness(image, MeasurementSettings(10, 245))
            contrast = measure_contrast(image, MeasurementSettings(20, 230))
            self.assertEqual(brightness["near_black_fraction"], 0.25)
            self.assertEqual(brightness["near_white_fraction"], 0.25)
            self.assertEqual(contrast["near_black_fraction"], 0.5)
            self.assertEqual(contrast["near_white_fraction"], 0.5)

    def test_fractional_cutoffs(self):
        with gray_image([10, 11, 244, 245]) as image:
            for measure in (measure_brightness, measure_contrast):
                result = measure(image, MeasurementSettings(10.5, 244.5))
                self.assertEqual(result["near_black_fraction"], 0.25)
                self.assertEqual(result["near_white_fraction"], 0.25)

    def test_defaults_none_and_explicit_settings_agree(self):
        with gray_image([0, 10, 128, 245, 255]) as image:
            for measure in (measure_brightness, measure_contrast):
                self.assertEqual(measure(image), measure(image, None))
                self.assertEqual(measure(image), measure(image, MeasurementSettings()))

    def test_deterministic_float_ranges_and_input_preservation(self):
        with gray_image(list(range(256))) as image:
            image.info["description"] = "unchanged"
            image.getexif()[274] = 1
            before = (image.tobytes(), image.size, image.mode, image.info.copy(), dict(image.getexif()))
            bounds = {"mean_luminance": 255, "luminance_std": 127.5,
                      "p5_p95_range": 255, "near_black_fraction": 1, "near_white_fraction": 1}
            for measure in (measure_brightness, measure_contrast):
                result = measure(image)
                self.assertEqual(result, measure(image))
                for key, value in result.items():
                    self.assertIs(type(value), float)
                    self.assertTrue(math.isfinite(value))
                    self.assertGreaterEqual(value, 0)
                    self.assertLessEqual(value, bounds[key])
            self.assertEqual(before, (image.tobytes(), image.size, image.mode, image.info.copy(), dict(image.getexif())))

    def test_invalid_image_types(self):
        for measure in (measure_brightness, measure_contrast):
            for value in (None, "photo.jpg", 123, []):
                with self.subTest(function=measure.__name__, value=value), self.assertRaises(TypeError):
                    measure(value)

    def test_invalid_settings_types(self):
        with gray_image([128]) as image:
            for measure in (measure_brightness, measure_contrast):
                for value in ({}, 10, "default", True):
                    with self.subTest(function=measure.__name__, value=value), self.assertRaises(TypeError):
                        measure(image, value)

    def test_non_rgb_modes(self):
        for mode in ("L", "RGBA", "P", "CMYK"):
            with Image.new(mode, (4, 4)) as image:
                for measure in (measure_brightness, measure_contrast):
                    with self.subTest(mode=mode, function=measure.__name__), self.assertRaises(ValueError):
                        measure(image)

    def test_empty_images(self):
        for size in ((0, 4), (4, 0), (0, 0)):
            with Image.new("RGB", size) as image:
                for measure in (measure_brightness, measure_contrast):
                    with self.subTest(size=size, function=measure.__name__), self.assertRaises(ValueError):
                        measure(image)

    def test_rgb_multiframe_image(self):
        # Real multi-page RGB TIFF isolates frame rejection from mode rejection.
        with io.BytesIO() as buffer, Image.new("RGB", (4, 4), "black") as first, Image.new("RGB", (4, 4), "white") as second:
            first.save(buffer, format="TIFF", save_all=True, append_images=[second])
            buffer.seek(0)
            with Image.open(buffer) as image:
                self.assertEqual(image.mode, "RGB")
                self.assertEqual(image.n_frames, 2)
                for measure in (measure_brightness, measure_contrast):
                    with self.subTest(function=measure.__name__), self.assertRaises(ValueError):
                        measure(image)


if __name__ == "__main__":
    unittest.main()
