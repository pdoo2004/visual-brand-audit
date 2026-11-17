"""Settings and integration tests for the modular standardization pipeline."""

import unittest

from PIL import Image

from brandlens.preprocessing.photo_standardization import (
    StandardizationSettings,
    standardize_image,
)


class TestStandardizationSettings(unittest.TestCase):
    """Test default settings and parameter validation."""

    def test_default_settings(self):
        settings = StandardizationSettings()

        self.assertIsNone(settings.max_size)
        self.assertEqual(settings.background, (255, 255, 255))
        self.assertTrue(settings.orientation_enabled)

    def test_custom_settings(self):
        settings = StandardizationSettings(
            max_size=(800, 600),
            background=(10, 20, 30),
        )

        self.assertEqual(settings.max_size, (800, 600))
        self.assertEqual(settings.background, (10, 20, 30))

    def test_invalid_max_size_type(self):
        for value in ([800, 600], "800", 800, (800.0, 600), (True, 600)):
            with self.subTest(value=value), self.assertRaises(TypeError):
                StandardizationSettings(max_size=value)

    def test_invalid_max_size_value(self):
        for value in ((), (800,), (800, 600, 400), (0, 600), (800, -1)):
            with self.subTest(value=value), self.assertRaises(ValueError):
                StandardizationSettings(max_size=value)

    def test_invalid_background_type(self):
        for value in ([255, 255, 255], None, (255.0, 0, 0), (True, 0, 0)):
            with self.subTest(value=value), self.assertRaises(TypeError):
                StandardizationSettings(background=value)

    def test_invalid_background_value(self):
        for value in ((), (255, 255), (0, 0, 0, 0), (-1, 0, 0), (256, 0, 0)):
            with self.subTest(value=value), self.assertRaises(ValueError):
                StandardizationSettings(background=value)


    def test_orientation_toggle_requires_boolean(self):
        for value in (None, 0, 1, "false"):
            with self.subTest(value=value), self.assertRaises(TypeError):
                StandardizationSettings(orientation_enabled=value)


class TestStandardizeImage(unittest.TestCase):
    """Check the combined pipeline, validation, and caller ownership."""

    def test_defaults_preserve_rgb_pixels_and_size(self):
        with Image.new("RGB", (120, 80), (20, 40, 60)) as image:
            with standardize_image(image) as processed:
                self.assertEqual(processed.mode, "RGB")
                self.assertEqual(processed.size, image.size)
                self.assertEqual(processed.tobytes(), image.tobytes())
                self.assertIsNot(processed, image)

    def test_orientation_can_be_disabled(self):
        with Image.new("RGB", (2, 3)) as image:
            image.putdata([(i, 2 * i, 3 * i) for i in range(6)])
            image.getexif()[274] = 6
            image.info["exif"] = image.getexif().tobytes()
            pixels = image.tobytes()
            with standardize_image(image) as enabled:
                self.assertEqual(enabled.size, (3, 2))
            with standardize_image(
                image, StandardizationSettings(orientation_enabled=False)
            ) as disabled:
                self.assertEqual(disabled.size, (2, 3))
                self.assertEqual(disabled.tobytes(), pixels)
                self.assertNotIn(274, disabled.getexif())
            self.assertEqual(image.getexif()[274], 6)
            self.assertEqual(image.tobytes(), pixels)

    def test_invalid_image_type(self):
        for value in (None, "image.png", 123):
            with self.subTest(value=value), self.assertRaises(TypeError):
                standardize_image(value)

    def test_invalid_settings_type(self):
        with Image.new("RGB", (10, 10)) as image, self.assertRaises(TypeError):
            standardize_image(image, {"max_size": (100, 100)})

    def test_zero_dimension_is_rejected(self):
        with Image.new("RGB", (0, 10)) as image, self.assertRaises(ValueError):
            standardize_image(image)

    def test_original_pixels_and_metadata_are_unchanged(self):
        settings = StandardizationSettings(max_size=(20, 20))

        with Image.new("RGBA", (80, 40), (20, 40, 60, 128)) as image:
            image.info["description"] = "original image"
            image.getexif()[274] = 6
            
            original_pixels = image.tobytes()
            original_metadata = image.info.copy()
            original_exif = image.getexif().tobytes()

            with standardize_image(image, settings) as processed:
                self.assertIsNot(processed, image)
                self.assertNotIn("description", processed.info)
                self.assertIn("icc_profile", processed.info)

            self.assertEqual(image.size, (80, 40))
            self.assertEqual(image.mode, "RGBA")
            self.assertEqual(image.tobytes(), original_pixels)
            self.assertEqual(image.info, original_metadata)
            self.assertEqual(image.getexif().tobytes(), original_exif)


if __name__ == "__main__":
    unittest.main()
