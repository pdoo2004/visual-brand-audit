"""Unit tests for preprocessing.steps.color."""

import unittest

from PIL import Image, ImageCms

from brandlens.preprocessing.steps.color import convert_to_rgb


class TestConvertToRGB(unittest.TestCase):
    def test_grayscale_converts_to_rgb(self):
        with Image.new("L", (10, 10), 75) as image:
            with convert_to_rgb(image) as processed:
                self.assertEqual(processed.mode, "RGB")
                self.assertEqual(processed.getpixel((0, 0)), (75, 75, 75))

    def test_binary_image_converts_to_rgb(self):
        with Image.new("1", (10, 10), 1) as image:
            with convert_to_rgb(image) as processed:
                self.assertEqual(processed.getpixel((0, 0)), (255, 255, 255))

    def test_rgba_transparency_on_custom_background(self):
        background = (10, 20, 30)

        with Image.new("RGBA", (2, 1)) as image:
            image.putdata([
                (200, 100, 50, 0),
                (200, 100, 50, 255),
            ])

            with convert_to_rgb(image, background=background) as processed:
                self.assertEqual(processed.getpixel((0, 0)), (10, 20, 30))
                self.assertEqual(processed.getpixel((1, 0)), (200, 100, 50))

    def test_partial_transparency(self):
        with Image.new("RGBA", (1, 1), (255, 0, 0, 128)) as image:
            with convert_to_rgb(image) as processed:
                # Half-transparent red composited onto white.
                self.assertEqual(processed.getpixel((0, 0)), (255, 127, 127))

    def test_grayscale_with_alpha(self):
        with Image.new("LA", (1, 1), (0, 128)) as image:
            with convert_to_rgb(image) as processed:
                self.assertEqual(processed.getpixel((0, 0)), (127, 127, 127))

    def test_palette_transparency(self):
        with Image.new("P", (2, 1)) as image:
            palette = [0] * 768
            palette[0:3] = [255, 0, 0]
            palette[3:6] = [0, 255, 0]
            image.putpalette(palette)
            image.putdata([0, 1])
            image.info["transparency"] = 0

            with convert_to_rgb(image) as processed:
                self.assertEqual(processed.getpixel((0, 0)), (255, 255, 255))
                self.assertEqual(processed.getpixel((1, 0)), (0, 255, 0))

    def test_rgb_color_key_transparency(self):
        with Image.new("RGB", (2, 1)) as image:
            image.putdata([(255, 0, 0), (0, 255, 0)])
            image.info["transparency"] = (255, 0, 0)

            with convert_to_rgb(image) as processed:
                self.assertEqual(processed.getpixel((0, 0)), (255, 255, 255))
                self.assertEqual(processed.getpixel((1, 0)), (0, 255, 0))

    def test_valid_srgb_profile(self):
        profile = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB"))

        with Image.new("RGB", (10, 10), (40, 100, 180)) as image:
            image.info["icc_profile"] = profile.tobytes()

            with convert_to_rgb(image) as processed:
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
                convert_to_rgb(image)

    def test_unprofiled_cmyk_is_rejected(self):
        with Image.new("CMYK", (10, 10)) as image:
            with self.assertRaisesRegex(ValueError, "CMYK"):
                convert_to_rgb(image)

    def test_unsupported_modes_are_rejected(self):
        for mode in ("I", "F", "I;16"):
            with self.subTest(mode=mode):
                with Image.new(mode, (10, 10)) as image:
                    with self.assertRaisesRegex(ValueError, "Unsupported image mode"):
                        convert_to_rgb(image)


if __name__ == "__main__":
    unittest.main()
