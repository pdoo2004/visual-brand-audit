import tempfile
import unittest
from pathlib import Path

from PIL import Image, UnidentifiedImageError, features

from brandlens.preprocessing.image_io import load_image


class TestLoadImage(unittest.TestCase):
    """Test supported formats, input validation, and file handling."""

    def setUp(self):
        """Create a temporary directory for test images."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.directory = Path(self.temp_dir.name)

    def _save_image(
        self,
        filename,
        image_format="PNG",
        size=(100, 80),
    ):
        """Create an RGB test image and return its path."""
        path = self.directory / filename

        with Image.new("RGB", size, (20, 40, 60)) as image:
            image.save(path, format=image_format)

        return path

    def test_load_png(self):
        path = self._save_image("image.png")

        with load_image(path) as image:
            self.assertIsInstance(image, Image.Image)
            self.assertEqual(image.size, (100, 80))
            self.assertEqual(image.mode, "RGB")
            self.assertEqual(image.getpixel((0, 0)), (20, 40, 60))

    def test_load_jpeg(self):
        path = self._save_image("image.jpg", image_format="JPEG")

        with load_image(path) as image:
            self.assertEqual(image.size, (100, 80))
            self.assertEqual(image.mode, "RGB")

    @unittest.skipUnless(
        features.check("webp"),
        "Pillow installation does not support WebP.",
    )
    def test_load_static_webp(self):
        path = self._save_image("image.webp", image_format="WEBP")

        with load_image(path) as image:
            self.assertEqual(image.size, (100, 80))
            self.assertEqual(image.mode, "RGB")

    def test_accepts_string_path(self):
        path = self._save_image("image.png")

        with load_image(str(path)) as image:
            self.assertEqual(image.size, (100, 80))

    def test_detects_format_from_contents(self):
        # PNG contents with a misleading JPEG extension.
        path = self._save_image("image.jpg", image_format="PNG")

        with load_image(path, supported_formats=("PNG",)) as image:
            self.assertEqual(image.size, (100, 80))

    def test_custom_format_allowlist(self):
        path = self._save_image("image.bmp", image_format="BMP")

        with load_image(path, supported_formats=("BMP",)) as image:
            self.assertEqual(image.size, (100, 80))

    def test_lowercase_format_names(self):
        path = self._save_image("image.png")

        with load_image(path, supported_formats=("png",)) as image:
            self.assertEqual(image.size, (100, 80))

    def test_unsupported_format(self):
        path = self._save_image("image.bmp", image_format="BMP")

        with self.assertRaises(UnidentifiedImageError):
            load_image(path)

    def test_format_excluded_by_custom_allowlist(self):
        path = self._save_image("image.jpg", image_format="JPEG")

        with self.assertRaises(UnidentifiedImageError):
            load_image(path, supported_formats=("PNG",))

    def test_pixel_limit_exceeded(self):
        path = self._save_image("image.png", size=(100, 80))

        with self.assertRaisesRegex(ValueError, "exceeds"):
            load_image(path, max_pixels=7_999)

    def test_exact_pixel_limit_is_allowed(self):
        path = self._save_image("image.png", size=(100, 80))

        with load_image(path, max_pixels=8_000) as image:
            self.assertEqual(image.size, (100, 80))

    def test_animated_png_is_rejected(self):
        path = self.directory / "animated.png"

        with Image.new("RGB", (20, 20), "red") as first:
            with Image.new("RGB", (20, 20), "blue") as second:
                first.save(
                    path,
                    format="PNG",
                    save_all=True,
                    append_images=[second],
                    duration=100,
                    loop=0,
                )

        # Confirm the fixture really contains multiple frames.
        with Image.open(path) as image:
            self.assertEqual(image.n_frames, 2)

        with self.assertRaisesRegex(ValueError, "multi-frame"):
            load_image(path)

    def test_missing_file(self):
        path = self.directory / "missing.png"

        with self.assertRaises(FileNotFoundError):
            load_image(path)

    def test_non_image_file(self):
        path = self.directory / "invalid.png"
        path.write_bytes(b"This is not an image.")

        with self.assertRaises(UnidentifiedImageError):
            load_image(path)

    def test_truncated_pixel_data(self):
        path = self._save_image("truncated.bmp", image_format="BMP")

        # Keep the BMP headers but remove most of the pixel data.
        contents = path.read_bytes()
        path.write_bytes(contents[:100])

        with self.assertRaises(OSError):
            load_image(path, supported_formats=("BMP",))

    def test_returned_image_is_independent_of_file(self):
        path = self._save_image("image.png")

        with load_image(path) as image:
            # On Windows, deletion also checks that the file was closed.
            path.unlink()

            self.assertEqual(image.getpixel((0, 0)), (20, 40, 60))
            self.assertEqual(len(image.tobytes()), 100 * 80 * 3)

    def test_original_file_is_unchanged(self):
        path = self._save_image("image.png")
        original_bytes = path.read_bytes()

        with load_image(path) as image:
            image.putpixel((0, 0), (255, 0, 0))

        self.assertEqual(path.read_bytes(), original_bytes)

    def test_preserves_transparency_and_orientation_metadata(self):
        path = self.directory / "transparent.png"
        exif = Image.Exif()
        exif[274] = 6

        with Image.new("RGBA", (20, 10), (20, 40, 60, 128)) as original:
            original.save(path, exif=exif)

        with load_image(path) as image:
            # Loading should not perform standardization.
            self.assertEqual(image.mode, "RGBA")
            self.assertEqual(image.size, (20, 10))
            self.assertEqual(image.getpixel((0, 0)), (20, 40, 60, 128))
            self.assertEqual(image.getexif().get(274), 6)

    def test_invalid_path_type(self):
        for value in (None, 123, ["image.png"]):
            with self.subTest(value=value), self.assertRaises(TypeError):
                load_image(value)

    def test_invalid_supported_formats_type(self):
        for value in ("PNG", ["PNG"], None, (123,)):
            with self.subTest(value=value), self.assertRaises(TypeError):
                load_image(
                    self.directory / "unused.png",
                    supported_formats=value,
                )

    def test_empty_supported_formats(self):
        with self.assertRaises(ValueError):
            load_image(
                self.directory / "unused.png",
                supported_formats=(),
            )

    def test_invalid_max_pixels_type(self):
        for value in (True, 100.0, "100", None):
            with self.subTest(value=value), self.assertRaises(TypeError):
                load_image(
                    self.directory / "unused.png",
                    max_pixels=value,
                )

    def test_invalid_max_pixels_value(self):
        for value in (0, -1):
            with self.subTest(value=value), self.assertRaises(ValueError):
                load_image(
                    self.directory / "unused.png",
                    max_pixels=value,
                )


if __name__ == "__main__":
    unittest.main()