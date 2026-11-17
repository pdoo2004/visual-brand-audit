"""Unit tests for preprocessing.steps.orientation."""

import unittest

from PIL import Image

from brandlens.preprocessing.steps.orientation import correct_orientation


class TestCorrectOrientation(unittest.TestCase):
    def test_exif_orientation_rotates_pixels(self):
        with Image.new("RGB", (2, 3)) as image:
            image.putdata([
                (255, 0, 0), (0, 255, 0),
                (0, 0, 255), (255, 255, 0),
                (255, 0, 255), (0, 255, 255),
            ])
            image.getexif()[274] = 6  # Rotate 90 degrees clockwise.
            image.info["exif"] = image.getexif().tobytes()

            with correct_orientation(image) as processed:
                self.assertEqual(processed.size, (3, 2))
                self.assertEqual(processed.getpixel((0, 0)), (255, 0, 255))
                self.assertEqual(processed.getpixel((2, 0)), (255, 0, 0))
                self.assertNotIn(274, processed.getexif())

            self.assertEqual(image.size, (2, 3))
            self.assertEqual(image.getexif()[274], 6)


if __name__ == "__main__":
    unittest.main()
