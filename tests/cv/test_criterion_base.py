"""Test required analyze(), settings isolation and the result envelope."""

import json
import unittest

from brandlens.cv.criterion_base import CriterionBase


class ExampleCriterion(CriterionBase):
    criterion_id = "example"
    implementation_id = "example_method"
    method_version = "1"
    def analyze(self, data):
        return self._make_result({"value": 2.0}, {"value": "example_units"})


class TestCriterionBase(unittest.TestCase):
    def test_analyze_is_required(self):
        class MissingAnalyze(CriterionBase):
            pass

        for cls in (CriterionBase, MissingAnalyze):
            with self.subTest(cls=cls), self.assertRaises(TypeError):
                cls()

    def test_empty_and_partial_settings(self):
        self.assertEqual(ExampleCriterion().settings, {})
        criterion = ExampleCriterion({"a": 3}, defaults={"a": 1, "b": 2})
        self.assertEqual(criterion.settings, {"a": 3, "b": 2})

    def test_copies_nested_settings_and_defaults(self):
        defaults = {"a": {"items": [1]}, "b": [2]}
        overrides = {"a": {"items": [3]}}
        criterion = ExampleCriterion(overrides, defaults=defaults)
        defaults["b"].append(99)
        overrides["a"]["items"].append(99)
        snapshot = criterion.settings
        snapshot["a"]["items"].append(99)
        self.assertEqual(criterion.settings, {"a": {"items": [3]}, "b": [2]})

    def test_rejects_invalid_settings(self):
        for value in ([], 1, "settings", True):
            with self.subTest(value=value), self.assertRaises(TypeError):
                ExampleCriterion(value)
        with self.assertRaises(TypeError):
            ExampleCriterion({1: 2})
        with self.assertRaises(ValueError):
            ExampleCriterion({"typo": 1}, defaults={"known": 2})

    def test_validation_hook_receives_merged_settings(self):
        class PositiveCriterion(ExampleCriterion):
            def _validate_settings(self, settings):
                if settings["minimum"] <= 0:
                    raise ValueError("minimum must be positive")

        with self.assertRaises(ValueError):
            PositiveCriterion({"minimum": -1}, defaults={"minimum": 1})
        self.assertEqual(
            PositiveCriterion(defaults={"minimum": 1}).settings, {"minimum": 1}
        )

    def test_result_contract_and_default_method_version(self):
        result = ExampleCriterion().analyze(None)
        self.assertEqual(
            result,
            {
                "schema_version": "1.0.0",
                "criterion_id": "example",
                "status": "available",
                "measurements": {"value": 2.0},
                "method": {"id": "example_method", "version": "1", "parameters": {}},
                "units": {"value": "example_units"},
                "reasons": [],
            },
        )
        self.assertEqual(json.loads(json.dumps(result, allow_nan=False)), result)
        self.assertNotIn("score", result)

    def test_subclass_can_override_method_version(self):
        class VersionTwo(ExampleCriterion):
            method_version = "2"

        self.assertEqual(VersionTwo().analyze(None)["method"]["version"], "2")

    def test_unavailable_requires_reason(self):
        criterion = ExampleCriterion()
        for status, reasons in (
            ("invalid", None),
            ("unavailable_needs_review", None),
            ("unavailable_needs_review", []),
        ):
            with (
                self.subTest(status=status, reasons=reasons),
                self.assertRaises(ValueError),
            ):
                criterion._make_result({}, {}, status=status, reasons=reasons)
        result = criterion._make_result(
            {"value": None},
            {},
            status="unavailable_needs_review",
            reasons=["Missing subject"],
        )
        self.assertIsNone(result["measurements"]["value"])
        self.assertEqual(result["reasons"], ["Missing subject"])

    def test_result_is_independent_of_inputs_and_instance_settings(self):
        criterion = ExampleCriterion(defaults={"a": [1]})
        values, units, reasons = {"nested": [2]}, {"nested": "pixels"}, ["example"]
        result = criterion._make_result(values, units, reasons=reasons)
        values["nested"].append(3)
        units["nested"] = "changed"
        reasons.append("changed")
        self.assertEqual(result["measurements"], {"nested": [2]})
        self.assertEqual(result["units"], {"nested": "pixels"})
        self.assertEqual(result["reasons"], ["example"])
        result["method"]["parameters"]["a"].append(99)
        self.assertEqual(criterion.settings, {"a": [1]})
