import unittest

from PIL import Image

from brandlens.preprocessing.photo_filter import FilterSettings, filter_photo

class TestFilterSettings(unittest.TestCase):
    """Test default settings and validation."""

    def test_default_settings(self):
        settings = FilterSettings()

        self.assertEqual(settings.min_short_side, 64)
        self.assertEqual(settings.max_aspect_ratio, 5.0)

    def test_invalid_min_short_side_type(self):
        for value in (True, 64.0, "64", None):
            with self.subTest(value=value):
                with self.assertRaises(TypeError):
                    FilterSettings(min_short_side=value)

    def test_invalid_min_short_side_value(self):
        for value in (0, -1):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    FilterSettings(min_short_side=value)

    def test_invalid_aspect_ratio_type(self):
        for value in (True, "5", None):
            with self.subTest(value=value):
                with self.assertRaises(TypeError):
                    FilterSettings(max_aspect_ratio=value)

    def test_invalid_aspect_ratio_value(self):
        for value in (0, 0.5, -1, float("inf"), float("-inf"), float("nan")):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    FilterSettings(max_aspect_ratio=value)


class TestFilterPhoto(unittest.TestCase):
    """Test filtering decisions, boundaries, and input preservation."""

    def test_accepts_landscape_portrait_and_square(self):
        for size in ((800, 600), (600, 800), (500, 500)):
            with self.subTest(size=size):
                with Image.new("RGB", size) as image:
                    self.assertIs(filter_photo(image), image)

    def test_rejects_short_side_below_minimum(self):
        for size in ((63, 100), (100, 63)):
            with self.subTest(size=size):
                with Image.new("RGB", size) as image:
                    self.assertIsNone(filter_photo(image))

    def test_accepts_exact_minimum_size(self):
        with Image.new("RGB", (64, 100)) as image:
            self.assertIs(filter_photo(image), image)

    def test_accepts_exact_maximum_aspect_ratio(self):
        for size in ((320, 64), (64, 320)):
            with self.subTest(size=size):
                with Image.new("RGB", size) as image:
                    self.assertIs(filter_photo(image), image)

    def test_rejects_aspect_ratio_above_maximum(self):
        for size in ((321, 64), (64, 321)):
            with self.subTest(size=size):
                with Image.new("RGB", size) as image:
                    self.assertIsNone(filter_photo(image))

    def test_custom_minimum_size(self):
        settings = FilterSettings(min_short_side=100)

        with Image.new("RGB", (80, 120)) as image:
            self.assertIs(filter_photo(image), image)
            self.assertIsNone(filter_photo(image, settings))

    def test_custom_aspect_ratio(self):
        settings = FilterSettings(max_aspect_ratio=2.0)

        with Image.new("RGB", (300, 100)) as image:
            self.assertIs(filter_photo(image), image)
            self.assertIsNone(filter_photo(image, settings))

    def test_explicit_none_uses_defaults(self):
        with Image.new("RGB", (100, 100)) as image:
            self.assertIs(filter_photo(image, None), image)

    def test_invalid_image_type(self):
        for value in (None, "image.jpg", 123):
            with self.subTest(value=value):
                with self.assertRaises(TypeError):
                    filter_photo(value)

    def test_invalid_settings_type(self):
        with Image.new("RGB", (100, 100)) as image:
            with self.assertRaises(TypeError):
                filter_photo(image, {"min_short_side": 64})

    def test_zero_dimension(self):
        for size in ((0, 100), (100, 0)):
            with self.subTest(size=size):
                with Image.new("RGB", size) as image:
                    with self.assertRaises(ValueError):
                        filter_photo(image)

    def test_input_is_unchanged_when_accepted_or_excluded(self):
        for size in ((100, 100), (32, 32)):
            with self.subTest(size=size):
                with Image.new("RGBA", size, (20, 40, 60, 128)) as image:
                    image.info["description"] = "test image"

                    original_pixels = image.tobytes()
                    original_metadata = image.info.copy()

                    filter_photo(image)

                    self.assertEqual(image.size, size)
                    self.assertEqual(image.mode, "RGBA")
                    self.assertEqual(image.tobytes(), original_pixels)
                    self.assertEqual(image.info, original_metadata)


if __name__ == "__main__":
    unittest.main()