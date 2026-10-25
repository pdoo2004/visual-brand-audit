"""Offline unit tests for subject_sharpness_criterion."""

import json
import unittest

import numpy as np
from PIL import Image, ImageFilter

from brandlens.analysis.analysis_input import AnalysisInput
from brandlens.analysis.subject.region import SubjectRegion
from brandlens.analysis.subject_sharpness_criterion import SubjectSharpnessCriterion


def region(*coords, **kwargs):
    return SubjectRegion(*(coords or (.25, .25, .75, .75)),
                         reliable=kwargs.pop('reliable', True), source='manual', **kwargs)

class TestSubjectSharpnessCriterion(unittest.TestCase):

    def image(self, subject=True):
        checker = ((np.indices((64, 64)).sum(axis=0) % 2) * 255).astype('uint8')
        if subject:
            checker[:16] = checker[48:] = 0
            checker[:, :16] = checker[:, 48:] = 0
        else:
            checker[16:48, 16:48] = 0
        return Image.fromarray(np.repeat(checker[..., None], 3, axis=2))

    def test_known_laplacian_variance_and_emphasis(self):
        with self.image() as image:
            m = SubjectSharpnessCriterion().analyze(AnalysisInput(image, region()))['measurements']
        self.assertEqual(m['subject_laplacian_variance'], 1020**2)
        self.assertEqual(m['background_laplacian_variance'], 0)
        self.assertEqual(m['detail_emphasis_index'], 1)
        self.assertEqual(m['subject_sample_pixels'], 30**2)

    def test_background_more_detailed(self):
        with self.image(False) as image:
            m = SubjectSharpnessCriterion().analyze(AnalysisInput(image, region()))['measurements']
        self.assertEqual(m['detail_emphasis_index'], -1)

    def test_blur_reduces_detail(self):
        with self.image() as image, image.filter(ImageFilter.GaussianBlur(2)) as blurred:
            criterion = SubjectSharpnessCriterion()
            a = criterion.analyze(AnalysisInput(image, region()))['measurements']
            b = criterion.analyze(AnalysisInput(blurred, region()))['measurements']
            self.assertLess(b['subject_laplacian_variance'], a['subject_laplacian_variance'])

    def test_box_edge_does_not_create_detail(self):
        a = np.zeros((64, 64, 3), dtype='uint8')
        a[16:48, 16:48] = 255
        with Image.fromarray(a) as image:
            result = SubjectSharpnessCriterion().analyze(AnalysisInput(image, region()))
        m = result['measurements']
        self.assertEqual(m['subject_laplacian_variance'], 0)
        self.assertEqual(m['background_laplacian_variance'], 0)
        self.assertIsNone(m['detail_emphasis_index'])
        self.assertEqual(result['status'], 'unavailable_needs_review')

    def test_full_frame_and_tiny_regions(self):
        with self.image() as image:
            for box, missing in ((region(0, 0, 1, 1), 'background'),
                                 (region(.5, .5, .51, .51), 'subject')):
                result = SubjectSharpnessCriterion().analyze(AnalysisInput(image, box))
                self.assertIsNone(result['measurements'][missing+'_laplacian_variance'])
                self.assertEqual(result['status'], 'unavailable_needs_review')

    def test_tiny_image_missing_and_unreliable_subject(self):
        with Image.new('RGB', (2, 2)) as image:
            for box in (region(), region(reliable=False), None):
                result = SubjectSharpnessCriterion().analyze(AnalysisInput(image, box))
                self.assertEqual(result['status'], 'unavailable_needs_review')

    def test_settings_validation(self):
        for value in (True, 1, 2.5, '16'):
            with self.subTest(value=value), self.assertRaises((TypeError, ValueError)):
                SubjectSharpnessCriterion({'min_region_pixels': value})

    def test_results_repeatable_json_and_input_unchanged(self):
        with self.image() as image:
            image.info['example'] = 'preserve'
            original = image.tobytes()
            for criterion in (SubjectSharpnessCriterion(),):
                data = AnalysisInput(image, region())
                a, b = criterion.analyze(data), criterion.analyze(data)
                self.assertEqual(a, b)
                json.dumps(a, allow_nan=False)
                self.assertEqual(set(a['measurements']), set(a['units']))
            self.assertEqual(image.tobytes(), original)
            self.assertEqual(image.info, {'example': 'preserve'})


if __name__ == "__main__":
    unittest.main()
