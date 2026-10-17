"""Integration tests using the real filter and standardization modules."""

import unittest
from unittest.mock import patch

from PIL import Image

from brandlens.preprocessing.photo_filter import FilterSettings
from brandlens.preprocessing.preprocessor import preprocess_batch, preprocess_image
from brandlens.preprocessing.standardization import StandardizationSettings


class TestPreprocessor(unittest.TestCase):
    """Check processing order, results, and error isolation."""

    def image(self, mode="RGB", size=(200, 100), color=0):
        image = Image.new(mode, size, color)
        self.addCleanup(image.close)
        return image

    def track(self, result):
        for image in result["accepted"].values():
            self.addCleanup(image.close)
        return result

    def test_single_image_returns_new_rgb_image(self):
        original = self.image("L", color=75)
        output = preprocess_image(original)
        self.addCleanup(output.close)
        self.assertIsNot(output, original)
        self.assertEqual(output.mode, "RGB")
        self.assertEqual(output.getpixel((0, 0)), (75, 75, 75))

    def test_excluded_image_skips_standardization(self):
        with patch("brandlens.preprocessing.preprocessor.standardize_image") as standardize:
            self.assertIsNone(preprocess_image(self.image(size=(32, 32))))
            standardize.assert_not_called()

    def test_filter_runs_before_resize(self):
        output = preprocess_image(
            self.image(), standardization_settings=StandardizationSettings(max_size=(32, 32))
        )
        self.addCleanup(output.close)
        self.assertEqual(output.size, (32, 16))

    def test_custom_filter_settings(self):
        self.assertIsNone(preprocess_image(self.image(), FilterSettings(min_short_side=128)))

    def test_mixed_batch_and_continuation(self):
        invalid = self.image()
        invalid.info["icc_profile"] = b"invalid profile"
        images = {
            "small": self.image(size=(32, 32)),
            "wide": self.image(size=(600, 100)),
            "invalid_profile": invalid,
            "not_image": None,
            "good_after_errors": self.image("L", color=75),
        }
        result = self.track(preprocess_batch(images))
        self.assertEqual(set(result["accepted"]), {"good_after_errors"})
        self.assertEqual(set(result["excluded"]), {"small", "wide"})
        self.assertEqual(set(result["errors"]), {"invalid_profile", "not_image"})
        ids = [key for group in result.values() for key in group]
        self.assertCountEqual(ids, images)
        self.assertEqual(len(ids), len(set(ids)))

    def test_orientation_transparency_and_original_preservation(self):
        original = self.image("RGBA", (100, 200), (200, 20, 40, 0))
        original.getexif()[274] = 6
        original.info["exif"] = original.getexif().tobytes()
        pixels, metadata = original.tobytes(), original.info.copy()
        result = self.track(preprocess_batch(
            {"photo": original},
            standardization_settings=StandardizationSettings(
                max_size=(100, 100), background=(10, 20, 30)
            ),
        ))
        output = result["accepted"]["photo"]
        self.assertEqual(output.size, (100, 50))
        self.assertEqual(output.getpixel((0, 0)), (10, 20, 30))
        self.assertIn("icc_profile", output.info)
        self.assertNotIn(274, output.getexif())
        self.assertEqual(original.size, (100, 200))
        self.assertEqual(original.tobytes(), pixels)
        self.assertEqual(original.info, metadata)

    def test_empty_batch(self):
        self.assertEqual(preprocess_batch({}), {"accepted": {}, "excluded": {}, "errors": {}})

    def test_all_excluded(self):
        result = preprocess_batch({"small": self.image(size=(32, 32))})
        self.assertEqual(result["accepted"], {})
        self.assertEqual(result["errors"], {})
        self.assertIn("small", result["excluded"])

    def test_all_errors(self):
        result = preprocess_batch({"invalid": None})
        self.assertEqual(result["accepted"], {})
        self.assertIn("invalid", result["errors"])

    def test_invalid_batch_container(self):
        for value in (None, [], "images"):
            with self.subTest(value=value), self.assertRaises(TypeError):
                preprocess_batch(value)

    def test_invalid_ids_rejected_before_processing(self):
        with patch("brandlens.preprocessing.preprocessor.filter_photo") as filter_mock:
            for bad_id, error_type in ((1, TypeError), (" ", ValueError)):
                with self.subTest(bad_id=bad_id), self.assertRaises(error_type):
                    preprocess_batch({"valid": self.image(), bad_id: self.image()})
            filter_mock.assert_not_called()

    def test_invalid_configuration_raises_even_for_empty_batch(self):
        with self.assertRaises(TypeError):
            preprocess_batch({}, filter_settings={})
        with self.assertRaises(TypeError):
            preprocess_batch({}, standardization_settings={})

    def test_single_image_error_propagates(self):
        with self.assertRaises(TypeError):
            preprocess_image(None)

    def test_unexpected_errors_are_not_silenced(self):
        with patch("brandlens.preprocessing.preprocessor.standardize_image",
                   side_effect=RuntimeError("unexpected")):
            with self.assertRaises(RuntimeError):
                preprocess_batch({"image": self.image()})


if __name__ == "__main__":
    unittest.main()
