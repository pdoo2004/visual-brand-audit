"""Scoring engine: rubric rules, weights, and CV/VLM result shapes."""

import json
import unittest
from pathlib import Path

from PIL import Image

from brandlens.analysis.analysis_input import AnalysisInput
from brandlens.analysis.brightness_criterion import BrightnessCriterion
from brandlens.analysis.contrast_criterion import ContrastCriterion
from brandlens.api.schemas.results import CriterionResult
from brandlens.scoring import score_image
from brandlens.vlm.validate import ParsedCriterion

ROOT = Path(__file__).resolve().parents[2]
RUBRIC_PATH = ROOT / "config" / "brand_standards.json"


def _criterion(criterion_id, method, weight, params, required):
    return {
        "criterion_id": criterion_id,
        "method": method,
        "weight": weight,
        "params": params,
        "required_measurements": required,
    }


def _rubric(*criteria, flag_threshold=None, rubric_id="test-v1"):
    return {
        "rubric_id": rubric_id,
        "flag_threshold": flag_threshold,
        "criteria": list(criteria),
    }


def _exposure(**measurements):
    base = {
        "mean_luminance": 128.0,
        "near_black_fraction": 0.0,
        "near_white_fraction": 0.0,
    }
    base.update(measurements)
    return base


EXPOSURE_PARAMS = {
    "mean_luminance_min": 40,
    "mean_luminance_max": 215,
    "near_black_fraction_max": 0.2,
    "near_white_fraction_max": 0.2,
}


class TestScoringEngine(unittest.TestCase):
    def test_exposure_pass_and_fail_use_rubric_bounds(self):
        rubric = _rubric(
            _criterion(
                "exposure_brightness",
                "cv",
                1,
                EXPOSURE_PARAMS,
                ["mean_luminance", "near_black_fraction", "near_white_fraction"],
            )
        )
        passed = score_image(rubric, cv_results={"exposure_brightness": _exposure()})
        failed = score_image(
            rubric,
            cv_results={
                "exposure_brightness": _exposure(mean_luminance=10, near_black_fraction=0.9)
            },
        )

        self.assertEqual(passed.criteria[0].score, 100.0)
        self.assertEqual(passed.criteria[0].rule_id, "pass_fail_thresholds")
        self.assertIn("mean_luminance_min", passed.criteria[0].evidence[0])
        self.assertEqual(passed.status, "scored")

        self.assertEqual(failed.criteria[0].score, 0.0)
        self.assertEqual(failed.criteria[0].availability, "ok")
        self.assertTrue(any("mean_luminance_min" in reason for reason in failed.criteria[0].reasons))
        self.assertTrue(
            any("near_black_fraction_max" in reason for reason in failed.criteria[0].reasons)
        )

    def test_contrast_fails_when_flat_or_harsh(self):
        params = {
            "luminance_std_min": 20,
            "luminance_std_max": 90,
            "p5_p95_range_min": 50,
            "p5_p95_range_max": 240,
            "near_black_fraction_max": 0.2,
            "near_white_fraction_max": 0.2,
        }
        required = [
            "luminance_std",
            "p5_p95_range",
            "near_black_fraction",
            "near_white_fraction",
        ]
        rubric = _rubric(_criterion("contrast", "cv", 1, params, required))

        def measure(**overrides):
            values = {
                "luminance_std": 40.0,
                "p5_p95_range": 100.0,
                "near_black_fraction": 0.0,
                "near_white_fraction": 0.0,
            }
            values.update(overrides)
            return values

        self.assertEqual(
            score_image(rubric, cv_results={"contrast": measure()}).criteria[0].score,
            100.0,
        )
        self.assertEqual(
            score_image(
                rubric, cv_results={"contrast": measure(luminance_std=5)}
            ).criteria[0].score,
            0.0,
        )
        self.assertEqual(
            score_image(
                rubric, cv_results={"contrast": measure(luminance_std=120)}
            ).criteria[0].score,
            0.0,
        )

    def test_palette_distance_maps_through_configured_maximum(self):
        rubric = _rubric(
            _criterion(
                "color_palette_fit",
                "cv",
                1,
                {"palette_distance_max": 20},
                ["dominant_colors", "palette_distance"],
            )
        )
        scored = score_image(
            rubric,
            cv_results={
                "color_palette_fit": {
                    "dominant_colors": [{"hex": "#004977"}],
                    "palette_distance": 5,
                }
            },
        )
        row = scored.criteria[0]
        self.assertEqual(row.rule_id, "linear_distance_to_0_100")
        self.assertAlmostEqual(row.score, 75.0)
        self.assertIn("palette_distance_max", row.evidence[0])

        unset = _rubric(
            _criterion(
                "color_palette_fit",
                "cv",
                1,
                {"palette_distance_max": None},
                ["dominant_colors", "palette_distance"],
            )
        )
        blocked = score_image(
            unset,
            cv_results={
                "color_palette_fit": {
                    "dominant_colors": [{"hex": "#004977"}],
                    "palette_distance": 5,
                }
            },
        )
        self.assertIsNone(blocked.criteria[0].score)
        self.assertIn("palette_distance_max", blocked.criteria[0].reasons[0])

    def test_tone_mapping_and_allowed_labels(self):
        rubric = _rubric(
            _criterion(
                "tone_approachability",
                "vlm",
                1,
                {
                    "allowed_labels": ["approachable", "competent"],
                    "fit_score_min": 1,
                    "fit_score_max": 5,
                    "score_mapping": "linear_1_5_to_0_100",
                },
                ["label", "fit_score", "evidence"],
            )
        )
        scores = {}
        for fit, expected in ((1, 0.0), (3, 50.0), (5, 100.0)):
            result = score_image(
                rubric,
                vlm_results={
                    "B1": ParsedCriterion(
                        id="B1",
                        name="Tone and approachability",
                        tone_label="approachable",
                        tone_words=("approachable",),
                        fit_score=fit,
                        evidence="The person is smiling in a bright room.",
                    )
                },
            )
            scores[fit] = result.criteria[0].score
            self.assertEqual(result.criteria[0].rule_id, "linear_1_5_to_0_100")
            self.assertEqual(result.criteria[0].label, "approachable")
            self.assertAlmostEqual(result.criteria[0].score, expected)
        self.assertEqual(scores, {1: 0.0, 3: 50.0, 5: 100.0})

        rejected = score_image(
            rubric,
            vlm_results={
                "tone_approachability": {
                    "tone_label": "authentic",
                    "fit_score": 5,
                    "evidence": "Natural light falls across the table.",
                }
            },
        )
        self.assertEqual(rejected.criteria[0].availability, "unavailable_needs_review")
        self.assertIn("allowed_labels", rejected.criteria[0].reasons[0])

    def test_unavailable_criterion_does_not_block_others_and_renormalizes_weights(self):
        rubric = _rubric(
            _criterion("exposure_brightness", "cv", 0.25, EXPOSURE_PARAMS, []),
            _criterion(
                "tone_approachability",
                "vlm",
                0.75,
                {"score_mapping": "linear_1_5_to_0_100", "allowed_labels": ["calm"]},
                ["label", "fit_score", "evidence"],
            ),
            flag_threshold=60,
        )
        result = score_image(
            rubric,
            cv_results={"exposure_brightness": _exposure()},
            vlm_results={},
        )
        exposure, tone = result.criteria
        self.assertEqual(exposure.score, 100.0)
        self.assertAlmostEqual(exposure.weight, 1.0)
        self.assertAlmostEqual(exposure.configured_weight, 0.25)
        self.assertIsNone(tone.score)
        self.assertEqual(tone.weight, 0.0)
        self.assertAlmostEqual(tone.configured_weight, 0.75)
        self.assertEqual(result.overall_score, 100.0)
        self.assertEqual(result.status, "partial")
        self.assertFalse(result.flagged)

    def test_equal_weights_when_rubric_weights_are_null(self):
        rubric = _rubric(
            _criterion("exposure_brightness", "cv", None, EXPOSURE_PARAMS, []),
            _criterion(
                "contrast",
                "cv",
                None,
                {
                    "luminance_std_min": 20,
                    "luminance_std_max": 90,
                    "p5_p95_range_min": 50,
                    "p5_p95_range_max": 240,
                    "near_black_fraction_max": 0.2,
                    "near_white_fraction_max": 0.2,
                },
                [],
            ),
        )
        result = score_image(
            rubric,
            cv_results={
                "exposure_brightness": _exposure(),
                "contrast": {
                    "luminance_std": 1.0,
                    "p5_p95_range": 100.0,
                    "near_black_fraction": 0.0,
                    "near_white_fraction": 0.0,
                },
            },
        )
        self.assertAlmostEqual(result.criteria[0].weight, 0.5)
        self.assertAlmostEqual(result.criteria[1].weight, 0.5)
        self.assertAlmostEqual(result.overall_score, 50.0)
        self.assertEqual(result.status, "scored")

    def test_flag_threshold_and_total_failure(self):
        rubric = _rubric(
            _criterion("exposure_brightness", "cv", 1, EXPOSURE_PARAMS, []),
            flag_threshold=50,
        )
        low = score_image(
            rubric,
            cv_results={"exposure_brightness": _exposure(mean_luminance=0)},
        )
        self.assertEqual(low.overall_score, 0.0)
        self.assertTrue(low.flagged)

        empty = score_image(rubric, cv_results={})
        self.assertIsNone(empty.overall_score)
        self.assertEqual(empty.status, "failed")
        self.assertFalse(empty.flagged)

    def test_analyzer_envelope_and_api_schema(self):
        rubric = json.loads(RUBRIC_PATH.read_text(encoding="utf-8"))
        with Image.new("RGB", (4, 4), (128, 128, 128)) as image:
            brightness = BrightnessCriterion().analyze(AnalysisInput(image))
            contrast = ContrastCriterion().analyze(AnalysisInput(image))
        result = score_image(
            rubric,
            cv_results={
                "exposure_brightness": brightness,
                "contrast": contrast,
                "color_palette_fit": {
                    "status": "available",
                    "measurements": {
                        "dominant_colors": [{"hex": "#004977", "proportion": 1.0}],
                        "palette_distance": 10.0,
                    },
                },
            },
            criterion_ids=["exposure_brightness", "contrast", "color_palette_fit"],
        )
        by_id = {row.criterion_id: row for row in result.criteria}
        self.assertEqual(by_id["exposure_brightness"].score, 100.0)
        self.assertEqual(by_id["contrast"].availability, "ok")
        self.assertIsNone(by_id["color_palette_fit"].score)
        self.assertIn("palette_distance_max", by_id["color_palette_fit"].reasons[0])
        self.assertEqual(result.status, "partial")
        self.assertEqual(result.rubric_id, rubric["rubric_id"])

        for row in result.criteria:
            CriterionResult(
                criterion_id=row.criterion_id,
                score=row.score,
                weight=row.weight,
                source=row.source,
                label=row.label,
                evidence=list(row.evidence),
                availability=row.availability,
            )

    def test_framing_passes_on_thirds_when_center_misses(self):
        rubric = _rubric(
            _criterion(
                "framing_subject_position",
                "cv",
                1,
                {
                    "center_offset_max": 0.1,
                    "thirds_offset_max": 0.05,
                    "edge_margin_min": 0.05,
                },
                ["subject_bbox", "center_offset", "thirds_offset", "edge_margin_min"],
            )
        )
        result = score_image(
            rubric,
            cv_results={
                "framing_subject_position": {
                    "status": "available",
                    "measurements": {
                        "subject_bbox": [0.3, 0.3, 0.2, 0.2],
                        "center_offset": 0.4,
                        "thirds_offset": 0.02,
                        "edge_margin_min": 0.1,
                    },
                }
            },
        )
        self.assertEqual(result.criteria[0].score, 100.0)

    def test_sharpness_motion_is_review_not_a_fail(self):
        rubric = _rubric(
            _criterion(
                "sharpness_subject_emphasis",
                "cv",
                1,
                {
                    "subject_sharpness_min": 100,
                    "sharpness_ratio_min": 1.5,
                    "intentional_motion_policy": "needs_review_not_automatic_fail",
                },
                ["subject_sharpness", "background_sharpness", "sharpness_ratio"],
            )
        )
        result = score_image(
            rubric,
            cv_results={
                "sharpness_subject_emphasis": {
                    "subject_sharpness": 10,
                    "background_sharpness": 40,
                    "sharpness_ratio": 0.25,
                    "intentional_motion": True,
                }
            },
        )
        row = result.criteria[0]
        self.assertIsNone(row.score)
        self.assertIn("needs_review_not_automatic_fail", row.reasons[0])

    def test_mixed_weights_and_unknown_ids_are_rejected(self):
        mixed = _rubric(
            _criterion("exposure_brightness", "cv", 1, EXPOSURE_PARAMS, []),
            _criterion("contrast", "cv", None, {}, []),
        )
        with self.assertRaises(ValueError):
            score_image(mixed, cv_results={})
        rubric = _rubric(_criterion("exposure_brightness", "cv", 1, EXPOSURE_PARAMS, []))
        with self.assertRaises(ValueError):
            score_image(rubric, criterion_ids=["missing"])

    def test_cv_unavailable_status_is_preserved(self):
        rubric = _rubric(
            _criterion("exposure_brightness", "cv", 1, EXPOSURE_PARAMS, [])
        )
        result = score_image(
            rubric,
            cv_results={
                "exposure_brightness": {
                    "status": "unavailable_needs_review",
                    "measurements": {},
                    "reasons": ["subject region missing"],
                }
            },
        )
        self.assertEqual(result.criteria[0].reasons, ("subject region missing",))
        self.assertEqual(result.status, "failed")


if __name__ == "__main__":
    unittest.main()
