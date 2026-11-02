"""Tests for CV implementation discovery and its configuration catalog."""

import json
import unittest
from unittest.mock import patch

from brandlens.cv.criterion_base import CriterionBase
from brandlens.cv.registry import CV_REGISTRY, get_cv_catalog


class TestRegistry(unittest.TestCase):
    def test_five_mvp_criteria_are_registered_as_classes(self):
        self.assertEqual(
            {cls.criterion_id for cls in CV_REGISTRY.values()},
            {
                "exposure_brightness",
                "contrast",
                "color_palette_fit",
                "framing_subject_position",
                "sharpness_subject_emphasis",
            },
        )
        for implementation_id, cls in CV_REGISTRY.items():
            with self.subTest(implementation_id=implementation_id):
                self.assertTrue(issubclass(cls, CriterionBase))
                self.assertEqual(implementation_id, cls.implementation_id)

    def test_catalog_exposes_configuration_contract_as_finite_json(self):
        catalog = get_cv_catalog()
        self.assertEqual(json.loads(json.dumps(catalog, allow_nan=False)), catalog)
        self.assertEqual(len(catalog), len(CV_REGISTRY))
        self.assertEqual(
            {row["implementation_id"] for row in catalog}, set(CV_REGISTRY)
        )
        for row in catalog:
            with self.subTest(implementation_id=row["implementation_id"]):
                cls = CV_REGISTRY[row["implementation_id"]]
                self.assertEqual(row["criterion_id"], cls.criterion_id)
                self.assertEqual(row["settings"], cls.settings_spec())
                self.assertEqual(row["measurements"], cls.measurement_specs())
                self.assertEqual(row["input_requirements"], cls.input_requirements())
                self.assertEqual(row["method"], "cv")
                self.assertTrue(row["description"])

    def test_catalog_does_not_construct_criteria_or_models(self):
        with patch.object(
            CriterionBase, "__init__", side_effect=AssertionError("Unexpected construction")
        ):
            self.assertEqual(len(get_cv_catalog()), len(CV_REGISTRY))

    def test_excluding_defaults_preserves_other_metadata(self):
        complete = get_cv_catalog()
        without_defaults = get_cv_catalog(include_defaults=False)
        for original, stripped in zip(complete, without_defaults, strict=True):
            self.assertEqual(original["measurements"], stripped["measurements"])
            for name, spec in original["settings"].items():
                self.assertIn("default", spec)
                self.assertEqual(
                    stripped["settings"][name],
                    {key: value for key, value in spec.items() if key != "default"},
                )
        self.assertEqual(get_cv_catalog(), complete)

    def test_catalog_mutation_does_not_change_class_specs(self):
        before = get_cv_catalog()
        modified = get_cv_catalog()
        brightness = next(
            row for row in modified if row["criterion_id"] == "exposure_brightness"
        )
        brightness["settings"]["near_black_max"]["default"] = -1
        brightness["measurements"]["mean_luminance"]["unit"] = "changed"
        brightness["input_requirements"]["reliable_subject_region"] = True
        self.assertEqual(get_cv_catalog(), before)
