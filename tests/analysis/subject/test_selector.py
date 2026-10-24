"""Offline unit tests for selector."""

import unittest

from brandlens.analysis.subject.detector_base import DetectionResult, SubjectCandidate
from brandlens.analysis.subject.selector import SingleSubjectSelector


def candidate(score=.9, label='person'):
    return SubjectCandidate(.25, .25, .75, .75, label, score)

def detection(*candidates):
    return DetectionResult(tuple(candidates), 'test_detector', 'abc123', (80, 60))

class TestSingleSubjectSelector(unittest.TestCase):

    def test_selection_single_preserves_provenance(self):
        selected = SingleSubjectSelector().select(detection(candidate())).subject_region
        self.assertTrue(selected.reliable)
        self.assertEqual(selected.source_version, 'abc123')
        self.assertEqual(selected.selection_method, 'single_candidate_v1')
        self.assertEqual(selected.confidence, .9)

    def test_selection_missing_low_confidence_and_multiple(self):
        for result in (detection(), detection(candidate(.2)),
                       detection(candidate(), candidate(.8, 'dog'))):
            selected = SingleSubjectSelector().select(result)
            self.assertIsNone(selected.subject_region)
            self.assertTrue(selected.reason)

    def test_selection_inclusive_threshold_and_label_filter(self):
        selector = SingleSubjectSelector({'min_confidence': .7, 'labels': ['person']})
        selected = selector.select(detection(candidate(.7), candidate(.99, 'dog')))
        self.assertEqual(selected.subject_region.label, 'person')

    def test_selector_settings_copy_and_validation(self):
        settings = {'labels': ['person']}
        selector = SingleSubjectSelector(settings)
        settings['labels'].append('dog')
        selector.settings['labels'].append('cat')
        self.assertEqual(selector.settings['labels'], ['person'])
        for settings in ({'typo': 1}, {'labels': 'person'}, {'labels': []},
                         {'min_confidence': True}, {'min_confidence': 2}):
            with self.subTest(settings=settings), self.assertRaises((TypeError, ValueError)):
                SingleSubjectSelector(settings)


if __name__ == "__main__":
    unittest.main()
