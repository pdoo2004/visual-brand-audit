"""Offline unit tests for region."""

import unittest
from dataclasses import FrozenInstanceError

from brandlens.cv.subject.region import SubjectRegion


def region(*coords, **kwargs):
    return SubjectRegion(*(coords or (.25, .25, .75, .75)),
                         reliable=kwargs.pop('reliable', True), source='manual', **kwargs)

class TestSubjectRegion(unittest.TestCase):

    def test_explicit_reliability_and_source_required(self):
        with self.assertRaises(TypeError):
            SubjectRegion(.1, .1, .9, .9)

    def test_invalid_boxes(self):
        for coords in ((0, 0, 0, 1), (.8, 0, .2, 1), (-.1, 0, 1, 1),
                       (0, 0, float('nan'), 1), (True, 0, 1, 1)):
            with self.subTest(coords=coords), self.assertRaises((TypeError, ValueError)):
                region(*coords)

    def test_invalid_metadata(self):
        for kwargs in ({'reliable': 1}, {'confidence': float('inf')},
                       {'confidence': True}, {'label': ''}, {'source_version': 4}):
            with self.subTest(kwargs=kwargs), self.assertRaises((TypeError, ValueError)):
                region(**kwargs)

    def test_frozen_and_independent_serialization(self):
        box = region()
        with self.assertRaises(FrozenInstanceError):
            box.left = .2
        values = box.to_dict()
        values['left'] = 0
        self.assertEqual(box.left, .25)


if __name__ == "__main__":
    unittest.main()
