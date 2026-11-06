"""Tests for the brand JSON-to-CV configuration bridge."""

import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from PIL import Image

from brandlens.config import ConfigurationError, load_cv_config
from brandlens.cv.brightness_criterion import BrightnessCriterion
from brandlens.cv.cv_input import CVInput

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "brand_standards.json"
SCHEMA_PATH = ROOT / "config" / "brand_standards.schema.json"


class TestConfig(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.document = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        cls.schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))

    def setUp(self):
        self.rubric = deepcopy(self.document)

    def entry(self, criterion_id="exposure_brightness"):
        return next(
            row for row in self.rubric["criteria"]
            if row["criterion_id"] == criterion_id
        )

    def load(self, **kwargs):
        return load_cv_config(self.rubric, schema_path=SCHEMA_PATH, **kwargs)

    def test_real_file_loads_all_cv_criteria_and_retains_vlm(self):
        for source in (CONFIG_PATH, str(CONFIG_PATH)):
            with self.subTest(source_type=type(source).__name__):
                rubric, criteria = load_cv_config(source)
                expected = {
                    row["criterion_id"] for row in self.document["criteria"]
                    if row["method"] == "cv"
                }
                self.assertEqual(set(criteria), expected)
                self.assertIsInstance(criteria["exposure_brightness"], BrightnessCriterion)
                self.assertEqual(
                    [row for row in rubric["criteria"] if row["method"] == "vlm"],
                    [row for row in self.document["criteria"] if row["method"] == "vlm"],
                )

    def test_dictionary_uses_repository_schema_by_default(self):
        # Regression: moving config.py to brandlens/ changes its schema path.
        rubric, criteria = load_cv_config(self.rubric)
        self.assertEqual(rubric["schema_version"], "1.1.0")
        self.assertIn("exposure_brightness", criteria)

    def test_file_uses_sibling_schema_and_allows_explicit_override(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "brand.json"
            path.write_text(json.dumps(self.rubric), encoding="utf-8")
            schema = deepcopy(self.schema)
            schema["properties"]["rubric_id"] = {"const": "different-brand"}
            path.with_name("brand_standards.schema.json").write_text(
                json.dumps(schema), encoding="utf-8"
            )
            with self.assertRaisesRegex(ConfigurationError, "rubric_id"):
                load_cv_config(path)
            rubric, criteria = load_cv_config(path, schema_path=SCHEMA_PATH)
            self.assertEqual(rubric["rubric_id"], self.rubric["rubric_id"])
            self.assertIn("contrast", criteria)

    def test_load_preserves_caller_and_returns_isolated_settings(self):
        self.entry()["settings"] = {"near_black_max": 20}
        before = deepcopy(self.rubric)
        rubric, criteria = self.load()
        resolved = rubric["criteria"][0]["settings"]
        self.assertEqual(resolved, {"near_black_max": 20, "near_white_min": 245})
        self.assertEqual(rubric["criteria"][0]["params"], before["criteria"][0]["params"])
        resolved["near_black_max"] = 0
        self.assertEqual(criteria["exposure_brightness"].settings["near_black_max"], 20)
        self.assertEqual(self.rubric, before)

    def test_json_setting_changes_measurement_on_same_input(self):
        self.rubric["criteria"] = [self.entry()]
        _, baseline = self.load()
        self.entry()["settings"]["near_black_max"] = 20
        _, changed = self.load()
        with Image.new("RGB", (4, 1)) as image:
            image.putdata([(value,) * 3 for value in (10, 20, 200, 250)])
            data = CVInput(image)
            first = baseline["exposure_brightness"].analyze(data)["measurements"]
            second = changed["exposure_brightness"].analyze(data)["measurements"]
        self.assertEqual(first["near_black_fraction"], 0.25)
        self.assertEqual(second["near_black_fraction"], 0.5)
        self.assertEqual(first["mean_luminance"], second["mean_luminance"])

    def test_requested_subset_validates_without_filtering_outputs(self):
        self.entry()["required_measurements"] = ["mean_luminance"]
        _, criteria = self.load()
        with Image.new("RGB", (1, 1), (128, 128, 128)) as image:
            result = criteria["exposure_brightness"].analyze(CVInput(image))
        self.assertEqual(result["measurements"]["mean_luminance"], 128.0)
        self.assertIn("near_black_fraction", result["measurements"])

    def test_palette_is_injected_and_copied(self):
        rubric, criteria = self.load()
        palette = criteria["color_palette_fit"].settings["brand_palette"]
        self.assertEqual(palette, self.rubric["brand_palette"])
        self.rubric["brand_palette"][0] = "#000000"
        rubric["brand_palette"][0] = "#111111"
        self.assertEqual(criteria["color_palette_fit"].settings["brand_palette"], palette)
        self.assertEqual(
            next(row for row in rubric["criteria"]
                 if row["criterion_id"] == "color_palette_fit")["settings"]["brand_palette"],
            palette,
        )

    def test_matching_local_palette_is_accepted(self):
        self.entry("color_palette_fit")["settings"]["brand_palette"] = deepcopy(
            self.rubric["brand_palette"]
        )
        _, criteria = self.load()
        self.assertEqual(
            criteria["color_palette_fit"].settings["brand_palette"],
            self.rubric["brand_palette"],
        )

    def test_conflicting_local_palette_is_rejected(self):
        self.entry("color_palette_fit")["settings"]["brand_palette"] = ["#000000"]
        with self.assertRaisesRegex(ConfigurationError, "conflicting brand_palette"):
            self.load()

    def test_unknown_setting_and_invalid_values_are_rejected(self):
        for settings, message in (
            ({"near_black_typo": 10}, "Unknown settings: near_black_typo"),
            ({"near_black_max": True}, "near_black_max must be a number"),
            ({"near_black_max": 250}, "near_black_max must be less"),
        ):
            with self.subTest(settings=settings):
                self.entry()["settings"] = settings
                with self.assertRaisesRegex(ConfigurationError, message):
                    self.load()

    def test_unknown_measurement_is_rejected_before_analysis(self):
        self.entry()["required_measurements"] = ["unknown_measurement"]
        with self.assertRaisesRegex(ConfigurationError, "unsupported measurements: unknown"):
            self.load()

    def test_measurement_setting_under_scoring_params_is_rejected(self):
        self.entry()["params"]["near_black_max"] = 20
        with self.assertRaisesRegex(ConfigurationError, "settings, not params"):
            self.load()

    def test_unknown_implementation_is_rejected(self):
        self.entry()["implementation_id"] = "missing_implementation"
        with self.assertRaisesRegex(ConfigurationError, "unsupported implementation"):
            self.load()

    def test_implementation_for_different_criterion_is_rejected(self):
        self.entry()["implementation_id"] = "pillow_grayscale_contrast"
        with self.assertRaisesRegex(ConfigurationError, "does not support exposure"):
            self.load()

    def test_registry_key_must_match_class_implementation_id(self):
        self.rubric["criteria"] = [self.entry()]
        self.entry()["implementation_id"] = "wrong_registry_key"
        with self.assertRaisesRegex(ConfigurationError, "registry key does not match"):
            self.load(registry={"wrong_registry_key": BrightnessCriterion})

    def test_alternative_implementation_can_be_supplied(self):
        class AlternateBrightness(BrightnessCriterion):
            implementation_id = "alternate_brightness"

        self.rubric["criteria"] = [self.entry()]
        self.entry()["implementation_id"] = AlternateBrightness.implementation_id
        _, criteria = self.load(
            registry={AlternateBrightness.implementation_id: AlternateBrightness}
        )
        self.assertIsInstance(criteria["exposure_brightness"], AlternateBrightness)
        with self.assertRaisesRegex(ConfigurationError, "unsupported implementation"):
            self.load(registry={})

    def test_duplicate_ids_are_rejected_for_cv_and_vlm(self):
        for method in ("cv", "vlm"):
            with self.subTest(method=method):
                self.rubric = deepcopy(self.document)
                row = next(row for row in self.rubric["criteria"] if row["method"] == method)
                self.rubric["criteria"].append(deepcopy(row))
                with self.assertRaisesRegex(ConfigurationError, "Duplicate criterion_id"):
                    self.load()

    def test_vlm_only_config_returns_no_cv_instances(self):
        self.rubric["criteria"] = [
            row for row in self.rubric["criteria"] if row["method"] == "vlm"
        ]
        rubric, criteria = self.load()
        self.assertEqual(criteria, {})
        self.assertEqual(rubric, self.rubric)

    def test_schema_errors_include_field_location(self):
        self.rubric["schema_version"] = "1.0.0"
        with self.assertRaisesRegex(ConfigurationError, "schema_version:"):
            self.load()

    def test_missing_cv_fields_are_rejected(self):
        for field in ("settings", "implementation_id"):
            with self.subTest(field=field):
                self.rubric = deepcopy(self.document)
                del self.entry()[field]
                with self.assertRaisesRegex(ConfigurationError, field):
                    self.load()

    def test_invalid_schema_is_wrapped(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid.schema.json"
            path.write_text('{"type": "not_a_schema_type"}', encoding="utf-8")
            with self.assertRaisesRegex(ConfigurationError, "Invalid rubric schema"):
                load_cv_config(self.rubric, schema_path=path)

    def test_duplicate_json_keys_at_any_depth_are_rejected(self):
        for text in ('{"key": 1, "key": 2}', '{"nested": {"key": 1, "key": 2}}'):
            with self.subTest(text=text), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "duplicate.json"
                path.write_text(text, encoding="utf-8")
                with self.assertRaisesRegex(ConfigurationError, "Duplicate JSON key: key"):
                    load_cv_config(path)

    def test_nonfinite_json_constants_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "nonfinite.json"
            for value in ("NaN", "Infinity", "-Infinity"):
                with self.subTest(value=value):
                    path.write_text('{"value": ' + value + '}', encoding="utf-8")
                    with self.assertRaisesRegex(ConfigurationError, "Non-finite JSON number"):
                        load_cv_config(path)

    def test_nonfinite_and_nonserializable_dictionary_values_are_rejected(self):
        for value in (float("nan"), float("inf"), float("-inf"), {"not_json"}):
            with self.subTest(value=repr(value)):
                self.rubric["criteria"][0]["params"]["test_value"] = value
                with self.assertRaisesRegex(ConfigurationError, "finite JSON values"):
                    self.load()

    def test_unreadable_malformed_and_nonobject_files_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid.json"
            with self.assertRaisesRegex(ConfigurationError, "Cannot read JSON"):
                load_cv_config(path)
            for content, message in (
                (b"\xff", "Cannot read JSON"),
                (b"{", "Cannot read JSON"),
                (b"[]", "expected a JSON object"),
            ):
                with self.subTest(content=content):
                    path.write_bytes(content)
                    with self.assertRaisesRegex(ConfigurationError, message):
                        load_cv_config(path)
