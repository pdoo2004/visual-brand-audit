"""SCRUM-122 / SCRUM-123: criterion explanations and image-level summaries."""

import unittest

from brandlens.scoring import (
    CriterionScore,
    ImageScore,
    explain_criterion,
    explained_results,
    score_image,
    summarize_image,
)


def _row(**kwargs):
    defaults = {
        "criterion_id": "exposure_brightness",
        "score": 100.0,
        "weight": 1.0,
        "configured_weight": 1.0,
        "source": "cv",
        "label": None,
        "evidence": ("mean_luminance 128 >= mean_luminance_min 40",),
        "availability": "ok",
        "rule_id": "pass_fail_thresholds",
        "reasons": (),
    }
    defaults.update(kwargs)
    return CriterionScore(**defaults)


class TestExplanations(unittest.TestCase):
    def test_pass_explanation_cites_evidence(self):
        text = explain_criterion(_row())
        self.assertIn("passed", text.lower())
        self.assertIn("mean_luminance", text)

    def test_fail_explanation_cites_reason(self):
        text = explain_criterion(
            _row(score=0.0, evidence=(), reasons=("mean_luminance 10 < mean_luminance_min 40",))
        )
        self.assertIn("failed", text.lower())
        self.assertIn("mean_luminance", text)

    def test_vlm_explanation_includes_label_and_evidence(self):
        text = explain_criterion(
            _row(
                criterion_id="tone_approachability",
                source="vlm",
                score=80.0,
                label="casual, lifestyle",
                evidence=("warm indoor light on a coffee cup",),
            )
        )
        self.assertIn("casual, lifestyle", text)
        self.assertIn("coffee cup", text)
        self.assertIn("80", text)

    def test_unavailable_marks_needs_review(self):
        text = explain_criterion(
            _row(
                criterion_id="tone_approachability",
                source="vlm",
                score=None,
                availability="unavailable_needs_review",
                evidence=(),
                reasons=("VLM timeout: request timed out",),
            )
        )
        self.assertIn("needs review", text.lower())
        self.assertIn("timeout", text.lower())

    def test_summary_identifies_partial_and_review(self):
        scored = ImageScore(
            rubric_id="test",
            criteria=(
                _row(weight=0.5, configured_weight=0.5),
                _row(
                    criterion_id="tone_approachability",
                    source="vlm",
                    score=None,
                    weight=0.0,
                    configured_weight=0.5,
                    availability="unavailable_needs_review",
                    evidence=(),
                    reasons=("VLM timeout",),
                ),
            ),
            overall_score=100.0,
            flagged=False,
            status="partial",
        )
        summary = summarize_image(scored)
        self.assertIn("Overall score 100/100 (partial)", summary)
        self.assertIn("Needs review: tone_approachability", summary)

    def test_summary_notes_flagged(self):
        scored = ImageScore(
            rubric_id="test",
            criteria=(_row(score=20.0, weight=1.0),),
            overall_score=20.0,
            flagged=True,
            status="scored",
        )
        self.assertIn("Flagged", summarize_image(scored))

    def test_attach_explanations_ready_for_persistence(self):
        rubric = {
            "rubric_id": "t",
            "flag_threshold": None,
            "criteria": [
                {
                    "criterion_id": "exposure_brightness",
                    "method": "cv",
                    "weight": 0.5,
                    "params": {
                        "mean_luminance_min": 40,
                        "mean_luminance_max": 215,
                        "near_black_fraction_max": 0.2,
                        "near_white_fraction_max": 0.2,
                    },
                    "required_measurements": [
                        "mean_luminance",
                        "near_black_fraction",
                        "near_white_fraction",
                    ],
                },
                {
                    "criterion_id": "tone_approachability",
                    "method": "vlm",
                    "weight": 0.5,
                    "params": {
                        "fit_score_min": 1,
                        "fit_score_max": 5,
                        "score_mapping": "linear_1_5_to_0_100",
                    },
                    "required_measurements": ["label", "fit_score", "evidence"],
                },
            ],
        }
        image = score_image(
            rubric,
            cv_results={
                "exposure_brightness": {
                    "mean_luminance": 128.0,
                    "near_black_fraction": 0.0,
                    "near_white_fraction": 0.0,
                }
            },
            vlm_results={
                "tone_approachability": {
                    "ok": False,
                    "errors": ["VLM timeout: request timed out"],
                }
            },
        )
        rows, summary = explained_results(image)
        self.assertEqual(image.status, "partial")
        self.assertEqual(len(rows), 2)
        tone = next(r for r in rows if r["criterion_id"] == "tone_approachability")
        self.assertIsNone(tone["score"])
        self.assertEqual(tone["availability"], "unavailable_needs_review")
        self.assertIn("needs review", tone["explanation"].lower())
        self.assertIn("Needs review: tone_approachability", summary)
        # Explanations must not invent a tone score when unavailable.
        self.assertNotIn("score 80", tone["explanation"])


if __name__ == "__main__":
    unittest.main()
