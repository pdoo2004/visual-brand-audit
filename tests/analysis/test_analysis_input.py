"""Validate the shared image-only input contract."""

import io
import unittest
from dataclasses import FrozenInstanceError

from PIL import Image

from brandlens.analysis.analysis_input import AnalysisInput


class TestAnalysisInput(unittest.TestCase):
    def test_borrows_image_without_changing_pixels_or_metadata(self):
        with Image.new("RGB", (3, 2), (12, 30, 40)) as image:
            image.info["example"] = "keep"
            pixels = image.tobytes()
            data = AnalysisInput(image)
            self.assertIs(data.image, image)
            self.assertEqual(image.tobytes(), pixels)
            self.assertEqual(image.info, {"example": "keep"})
            with self.assertRaises(FrozenInstanceError):
                data.image = None

    def test_rejects_non_images(self):
        for value in (None, "image.jpg", 1, {}, []):
            with self.subTest(value=value), self.assertRaises(TypeError):
                AnalysisInput(value)

    def test_rejects_non_rgb(self):
        for mode in ("L", "RGBA", "P", "CMYK"):
            with self.subTest(mode=mode), Image.new(mode, (2, 2)) as image:
                with self.assertRaises(ValueError):
                    AnalysisInput(image)

    def test_rejects_empty_dimensions(self):
        for size in ((0, 1), (1, 0), (0, 0)):
            with self.subTest(size=size), Image.new("RGB", size) as image:
                with self.assertRaises(ValueError):
                    AnalysisInput(image)

    def test_rejects_actual_rgb_multiframe_file(self):
        with io.BytesIO() as buffer:
            with Image.new("RGB", (2, 2), "red") as first:
                with Image.new("RGB", (2, 2), "blue") as second:
                    first.save(
                        buffer, format="TIFF", save_all=True, append_images=[second]
                    )
            buffer.seek(0)
            with Image.open(buffer) as image:
                self.assertEqual(image.mode, "RGB")
                self.assertEqual(image.n_frames, 2)
                with self.assertRaises(ValueError):
                    AnalysisInput(image)
