"""Offline unit tests for detector_base."""

import unittest

from brandlens.analysis.subject.detector_base import SubjectDetectorBase


class TestSubjectDetectorBase(unittest.TestCase):

    def test_abstract_interface(self):
        with self.assertRaises(TypeError):
            SubjectDetectorBase()


if __name__ == "__main__":
    unittest.main()
