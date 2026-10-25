"""Offline unit tests for analysis_input."""

import io
import unittest
from dataclasses import FrozenInstanceError

from PIL import Image

from brandlens.analysis.analysis_input import AnalysisInput
from brandlens.analysis.subject.region import SubjectRegion


def region(*coords, **kwargs):
    return SubjectRegion(*(coords or (.25, .25, .75, .75)),
                         reliable=kwargs.pop('reliable', True), source='manual', **kwargs)

class TestSubjectAnalysisInput(unittest.TestCase):

    def test_input_backward_compatibility(self):
        with Image.new('RGB', (10, 10)) as image:
            self.assertIsNone(AnalysisInput(image).subject_region)

    def test_invalid_input(self):
        for image in ('x', Image.new('L', (5, 5)), Image.new('RGB', (0, 5))):
            with self.subTest(image=image), self.assertRaises((TypeError, ValueError)):
                AnalysisInput(image)
        with Image.new('RGB', (5, 5)) as image:
            with self.assertRaises(TypeError):
                AnalysisInput(image, (.1, .1, .9, .9))
            with self.assertRaises(ValueError):
                AnalysisInput(image, region(), 'ambiguous')


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


if __name__ == "__main__":
    unittest.main()
