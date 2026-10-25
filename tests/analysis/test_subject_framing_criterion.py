"""Offline unit tests for subject_framing_criterion."""

import json
import unittest
from math import hypot

from PIL import Image

from brandlens.analysis.analysis_input import AnalysisInput
from brandlens.analysis.subject.region import SubjectRegion
from brandlens.analysis.subject_framing_criterion import SubjectFramingCriterion


def region(*coords, **kwargs):
    return SubjectRegion(*(coords or (.25, .25, .75, .75)),
                         reliable=kwargs.pop('reliable', True), source='manual', **kwargs)

class TestSubjectFramingCriterion(unittest.TestCase):

    def setUp(self):
        self.image = Image.new('RGB', (200, 100))
        self.addCleanup(self.image.close)

    def test_center_coverage_margins(self):
        result = SubjectFramingCriterion().analyze(AnalysisInput(self.image, region()))
        m = result['measurements']
        self.assertEqual(m['center_distance'], 0)
        self.assertEqual(m['subject_box_area_fraction'], .25)
        self.assertEqual(m['left_margin'], .25)
        self.assertFalse(m['near_edge'])
        self.assertEqual(result['subject_region']['source'], 'manual')

    def test_thirds_anchor(self):
        box = region(1/3-.05, 2/3-.05, 1/3+.05, 2/3+.05)
        m = SubjectFramingCriterion().analyze(AnalysisInput(self.image, box))['measurements']
        self.assertAlmostEqual(m['nearest_thirds_distance'], 0)

    def test_distance_respects_aspect_ratio(self):
        box = region(.1, .1, .3, .3)
        m = SubjectFramingCriterion().analyze(AnalysisInput(self.image, box))['measurements']
        self.assertAlmostEqual(m['center_distance'], hypot(60, 30)/hypot(200, 100))

    def test_edge_threshold_inclusive(self):
        box = region(.02, .2, .8, .8)
        m = SubjectFramingCriterion().analyze(AnalysisInput(self.image, box))['measurements']
        self.assertTrue(m['near_edge'])

    def test_missing_and_unreliable(self):
        for box in (None, region(reliable=False)):
            result = SubjectFramingCriterion().analyze(AnalysisInput(self.image, box, 'Review subject'))
            self.assertEqual(result['status'], 'unavailable_needs_review')
            self.assertEqual(result['reasons'], ['Review subject'])
            self.assertEqual(result['measurements'], {})

    def test_settings_validation(self):
        for settings in ({'edge_margin_fraction': True}, {'edge_margin_fraction': -.1},
                         {'edge_margin_fraction': float('nan')}, {'typo': 1}):
            with self.subTest(settings=settings), self.assertRaises((TypeError, ValueError)):
                SubjectFramingCriterion(settings)

    def test_results_repeatable_json_and_input_unchanged(self):
        self.image.info["example"] = "preserve"
        original = self.image.tobytes()
        criterion = SubjectFramingCriterion()
        data = AnalysisInput(self.image, region())
        a, b = criterion.analyze(data), criterion.analyze(data)
        self.assertEqual(a, b)
        json.dumps(a, allow_nan=False)
        self.assertEqual(set(a["measurements"]), set(a["units"]))
        self.assertEqual(self.image.tobytes(), original)
        self.assertEqual(self.image.info, {"example": "preserve"})


if __name__ == "__main__":
    unittest.main()
