"""Unit tests for preprocessing.steps.resize."""

import unittest

from PIL import Image

from brandlens.preprocessing.steps.resize import resize_to_fit


class TestResizeToFit(unittest.TestCase):
    def test_resize_preserves_aspect_ratio(self):
        max_size = (200, 200)

        cases = [
            ((600, 300), (200, 100)),
            ((300, 600), (100, 200)),
            ((400, 400), (200, 200)),
        ]

        for original_size, expected_size in cases:
            with self.subTest(size=original_size):
                with Image.new("RGB", original_size) as image:
                    with resize_to_fit(image.copy(), max_size) as processed:
                        self.assertEqual(processed.size, expected_size)

    def test_non_square_bounding_box(self):
        max_size = (300, 100)

        with Image.new("RGB", (800, 400)) as image:
            with resize_to_fit(image.copy(), max_size) as processed:
                self.assertEqual(processed.size, (200, 100))

    def test_small_image_is_not_upscaled(self):
        max_size = (1024, 1024)

        with Image.new("RGB", (80, 60)) as image:
            with resize_to_fit(image.copy(), max_size) as processed:
                self.assertEqual(processed.size, (80, 60))

    def test_none_disables_resizing(self):
        max_size = None

        with Image.new("RGB", (1200, 100)) as image:
            with resize_to_fit(image.copy(), max_size) as processed:
                self.assertEqual(processed.size, (1200, 100))


if __name__ == "__main__":
    unittest.main()
