"""Offline unit tests for rtdetr_detector."""

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from PIL import Image

from brandlens.cv.subject.rtdetr_detector import RTDetrSubjectDetector


class TestRTDetrSubjectDetector(unittest.TestCase):

    def pipe(self, predictions):
        pipe = Mock(return_value=predictions)
        pipe.model = SimpleNamespace(config=SimpleNamespace(_commit_hash='resolved_commit'))
        return pipe

    def prediction(self, box=None, score=.9):
        return {'label': 'person', 'score': score,
                'box': box or {'xmin': 20, 'ymin': 10, 'xmax': 80, 'ymax': 40}}

    def test_normalization_and_provenance(self):
        detector = RTDetrSubjectDetector()
        pipe = self.pipe([self.prediction()])
        with Image.new('RGB', (100, 50)) as image, patch.object(
            detector, '_get_pipeline', return_value=pipe
        ):
            result = detector.detect(image)
        c = result.candidates[0]
        self.assertEqual((c.left, c.top, c.right, c.bottom), (.2, .2, .8, .8))
        self.assertEqual(result.image_size, (100, 50))
        self.assertEqual(result.source_version, 'resolved_commit')

    def test_clipping_degenerate_and_low_confidence(self):
        predictions = [self.prediction({'xmin': -10, 'ymin': 0, 'xmax': 110, 'ymax': 50}),
                       self.prediction({'xmin': 110, 'ymin': 0, 'xmax': 120, 'ymax': 50}),
                       self.prediction(score=.2)]
        detector = RTDetrSubjectDetector()
        with Image.new('RGB', (100, 50)) as image, patch.object(
            detector, '_get_pipeline', return_value=self.pipe(predictions)
        ):
            result = detector.detect(image)
        self.assertEqual(len(result.candidates), 1)
        self.assertEqual(result.candidates[0].left, 0)
        self.assertEqual(result.candidates[0].right, 1)

    def test_invalid_predictions_raise(self):
        detector = RTDetrSubjectDetector()
        for value in (float('nan'), 90):
            prediction = self.prediction({'xmin': value, 'ymin': 0, 'xmax': 80, 'ymax': 50})
            with Image.new('RGB', (100, 50)) as image, patch.object(
                detector, '_get_pipeline', return_value=self.pipe([prediction])
            ), self.assertRaises(ValueError):
                detector.detect(image)

    def test_inference_error_is_not_empty_scene(self):
        detector = RTDetrSubjectDetector()
        with Image.new('RGB', (100, 50)) as image, patch.object(
            detector, '_get_pipeline', side_effect=RuntimeError('model failed')
        ), self.assertRaises(RuntimeError):
            detector.detect(image)

    def test_third_party_cannot_mutate_caller_image(self):
        def mutate(image, **kwargs):
            image.paste('white', (0, 0, 100, 50))
            image.info['extra'] = True
            return []
        detector = RTDetrSubjectDetector()
        with Image.new('RGB', (100, 50)) as image, patch.object(
            detector, '_get_pipeline', return_value=mutate
        ):
            before = image.tobytes()
            detector.detect(image)
            self.assertEqual(image.tobytes(), before)
            self.assertEqual(image.info, {})

    def test_lazy_cached_load(self):
        detector = RTDetrSubjectDetector()
        fake = SimpleNamespace(pipeline=Mock(return_value=self.pipe([])))
        with patch.dict('sys.modules', {'transformers': fake}):
            self.assertIs(detector._get_pipeline(), detector._get_pipeline())
        fake.pipeline.assert_called_once()

    def test_settings_validation_and_copy(self):
        detector = RTDetrSubjectDetector()
        detector.settings['model_id'] = 'changed'
        self.assertEqual(detector.settings['model_id'], 'PekingU/rtdetr_r18vd')
        for settings in ({'device': True}, {'model_id': ''}, {'confidence_threshold': 2},
                         {'revision': ''}, {'typo': 1}):
            with self.subTest(settings=settings), self.assertRaises((TypeError, ValueError)):
                RTDetrSubjectDetector(settings)


if __name__ == "__main__":
    unittest.main()
