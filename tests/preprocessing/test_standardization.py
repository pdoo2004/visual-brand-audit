import unittest
from PIL import Image, ImageCms

from brandlens.preprocessing.standardization import StandardizationSettings, standardize_image

class TestStandardizationSettings(unittest.TestCase):
    """Test default settings and parameter validation."""

    def test_default_settings(self):
        settings = StandardizationSettings()

        self.assertIsNone(settings.max_size)
        self.assertEqual(settings.background, (255, 255, 255))

    def test_custom_settings(self):
        settings = StandardizationSettings(
            max_size=(800, 600),
            background=(10, 20, 30),
        )

        self.assertEqual(settings.max_size, (800, 600))
        self.assertEqual(settings.background, (10, 20, 30))

    def test_invalid_max_size_type(self):
        for value in ([800, 600], "800", 800, (800.0, 600), (True, 600)):
            with self.subTest(value=value):
                with self.assertRaises(TypeError):
                    StandardizationSettings(max_size=value)

    def test_invalid_max_size_value(self):
        for value in ((), (800,), (800, 600, 400), (0, 600), (800, -1)):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    StandardizationSettings(max_size=value)

    def test_invalid_background_type(self):
        for value in ([255, 255, 255], None, (255.0, 0, 0), (True, 0, 0)):
            with self.subTest(value=value):
                with self.assertRaises(TypeError):
                    StandardizationSettings(background=value)

    def test_invalid_background_value(self):
        for value in ((), (255, 255), (0, 0, 0, 0), (-1, 0, 0), (256, 0, 0)):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    StandardizationSettings(background=value)


class TestStandardizeImage(unittest.TestCase):
    """Test size, orientation, color conversion, and input preservation."""

    def test_defaults_preserve_rgb_pixels_and_size(self):
        with Image.new("RGB", (120, 80), (20, 40, 60)) as image:
            with standardize_image(image) as processed:
                self.assertEqual(processed.mode, "RGB")
                self.assertEqual(processed.size, image.size)
                self.assertEqual(processed.tobytes(), image.tobytes())
                self.assertIsNot(processed, image)

    def test_resize_preserves_aspect_ratio(self):
        settings = StandardizationSettings(max_size=(200, 200))

        cases = [
            ((600, 300), (200, 100)),
            ((300, 600), (100, 200)),
            ((400, 400), (200, 200)),
        ]

        for original_size, expected_size in cases:
            with self.subTest(size=original_size):
                with Image.new("RGB", original_size) as image:
                    with standardize_image(image, settings) as processed:
                        self.assertEqual(processed.size, expected_size)

    def test_non_square_bounding_box(self):
        settings = StandardizationSettings(max_size=(300, 100))

        with Image.new("RGB", (800, 400)) as image:
            with standardize_image(image, settings) as processed:
                self.assertEqual(processed.size, (200, 100))

    def test_small_image_is_not_upscaled(self):
        settings = StandardizationSettings(max_size=(1024, 1024))

        with Image.new("RGB", (80, 60)) as image:
            with standardize_image(image, settings) as processed:
                self.assertEqual(processed.size, (80, 60))

    def test_none_disables_resizing(self):
        settings = StandardizationSettings(max_size=None)

        with Image.new("RGB", (1200, 100)) as image:
            with standardize_image(image, settings) as processed:
                self.assertEqual(processed.size, (1200, 100))

    def test_exif_orientation_rotates_pixels(self):
        with Image.new("RGB", (2, 3)) as image:
            image.putdata([
                (255, 0, 0), (0, 255, 0),
                (0, 0, 255), (255, 255, 0),
                (255, 0, 255), (0, 255, 255),
            ])
            image.getexif()[274] = 6  # Rotate 90 degrees clockwise.
            image.info["exif"] = image.getexif().tobytes()

            with standardize_image(image) as processed:
                self.assertEqual(processed.size, (3, 2))
                self.assertEqual(processed.getpixel((0, 0)), (255, 0, 255))
                self.assertEqual(processed.getpixel((2, 0)), (255, 0, 0))
                self.assertNotIn(274, processed.getexif())

            self.assertEqual(image.size, (2, 3))
            self.assertEqual(image.getexif()[274], 6)

    def test_grayscale_converts_to_rgb(self):
        with Image.new("L", (10, 10), 75) as image:
            with standardize_image(image) as processed:
                self.assertEqual(processed.mode, "RGB")
                self.assertEqual(processed.getpixel((0, 0)), (75, 75, 75))

    def test_binary_image_converts_to_rgb(self):
        with Image.new("1", (10, 10), 1) as image:
            with standardize_image(image) as processed:
                self.assertEqual(processed.getpixel((0, 0)), (255, 255, 255))

    def test_rgba_transparency_on_custom_background(self):
        settings = StandardizationSettings(background=(10, 20, 30))

        with Image.new("RGBA", (2, 1)) as image:
            image.putdata([
                (200, 100, 50, 0),
                (200, 100, 50, 255),
            ])

            with standardize_image(image, settings) as processed:
                self.assertEqual(processed.getpixel((0, 0)), (10, 20, 30))
                self.assertEqual(processed.getpixel((1, 0)), (200, 100, 50))

    def test_partial_transparency(self):
        with Image.new("RGBA", (1, 1), (255, 0, 0, 128)) as image:
            with standardize_image(image) as processed:
                # Half-transparent red composited onto white.
                self.assertEqual(processed.getpixel((0, 0)), (255, 127, 127))

    def test_grayscale_with_alpha(self):
        with Image.new("LA", (1, 1), (0, 128)) as image:
            with standardize_image(image) as processed:
                self.assertEqual(processed.getpixel((0, 0)), (127, 127, 127))

    def test_palette_transparency(self):
        with Image.new("P", (2, 1)) as image:
            palette = [0] * 768
            palette[0:3] = [255, 0, 0]
            palette[3:6] = [0, 255, 0]
            image.putpalette(palette)
            image.putdata([0, 1])
            image.info["transparency"] = 0

            with standardize_image(image) as processed:
                self.assertEqual(processed.getpixel((0, 0)), (255, 255, 255))
                self.assertEqual(processed.getpixel((1, 0)), (0, 255, 0))

    def test_rgb_color_key_transparency(self):
        with Image.new("RGB", (2, 1)) as image:
            image.putdata([(255, 0, 0), (0, 255, 0)])
            image.info["transparency"] = (255, 0, 0)

            with standardize_image(image) as processed:
                self.assertEqual(processed.getpixel((0, 0)), (255, 255, 255))
                self.assertEqual(processed.getpixel((1, 0)), (0, 255, 0))

    def test_valid_srgb_profile(self):
        profile = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB"))

        with Image.new("RGB", (10, 10), (40, 100, 180)) as image:
            image.info["icc_profile"] = profile.tobytes()

            with standardize_image(image) as processed:
                self.assertEqual(processed.mode, "RGB")

                actual = processed.getpixel((0, 0))
                for actual_channel, expected_channel in zip(actual, (40, 100, 180)):
                    self.assertAlmostEqual(
                        actual_channel,
                        expected_channel,
                        delta=1,
                    )

                output_profile = ImageCms.ImageCmsProfile(
                    __import__("io").BytesIO(processed.info["icc_profile"])
                )
                self.assertIn(
                    "srgb",
                    ImageCms.getProfileDescription(output_profile).lower(),
                )

    def test_invalid_profile_raises_error(self):
        with Image.new("RGB", (10, 10)) as image:
            image.info["icc_profile"] = b"invalid profile"

            with self.assertRaisesRegex(ValueError, "color profile"):
                standardize_image(image)

    def test_unprofiled_cmyk_is_rejected(self):
        with Image.new("CMYK", (10, 10)) as image:
            with self.assertRaisesRegex(ValueError, "CMYK"):
                standardize_image(image)

    def test_unsupported_modes_are_rejected(self):
        for mode in ("I", "F", "I;16"):
            with self.subTest(mode=mode):
                with Image.new(mode, (10, 10)) as image:
                    with self.assertRaisesRegex(ValueError, "Unsupported image mode"):
                        standardize_image(image)

    def test_invalid_image_type(self):
        for value in (None, "image.png", 123):
            with self.subTest(value=value):
                with self.assertRaises(TypeError):
                    standardize_image(value)

    def test_invalid_settings_type(self):
        with Image.new("RGB", (10, 10)) as image:
            with self.assertRaises(TypeError):
                standardize_image(image, {"max_size": (100, 100)})

    def test_zero_dimension_is_rejected(self):
        with Image.new("RGB", (0, 10)) as image:
            with self.assertRaises(ValueError):
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