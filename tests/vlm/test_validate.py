"""Valid model JSON parses. Malformed and incomplete replies fail closed."""

import json
import unittest

from brandlens.vlm import validate_model_output

VALID = {
    "criteria": [
        {
            "id": "B1",
            "name": "Tone and approachability",
            "tone_label": "aesthetic, premium, lifestyle, casual",
            "fit_score": 4,
            "evidence": (
                "The careful latte art and the dark, moody lighting "
                "give the image a premium and aesthetic feel."
            ),
        }
    ]
}


def _dump(payload: dict) -> str:
    return json.dumps(payload)


class TestValidateModelOutput(unittest.TestCase):
    def test_a_complete_b1_reply_parses(self):
        result = validate_model_output(_dump(VALID))

        self.assertTrue(result.ok)
        self.assertEqual(result.errors, ())
        judgment = result.criteria[0]
        self.assertEqual(judgment.id, "B1")
        self.assertEqual(judgment.fit_score, 4)
        self.assertEqual(
            judgment.tone_words,
            ("aesthetic", "premium", "lifestyle", "casual"),
        )
        self.assertIn("latte art", judgment.evidence)

    def test_tone_words_are_matched_in_lowercase(self):
        payload = json.loads(_dump(VALID))
        payload["criteria"][0]["tone_label"] = "Casual, Lifestyle"
        result = validate_model_output(json.dumps(payload))

        self.assertTrue(result.ok)
        self.assertEqual(result.criteria[0].tone_label, "casual, lifestyle")

    def test_invalid_json_is_a_validation_failure(self):
        result = validate_model_output("```json\n" + _dump(VALID) + "\n```")

        self.assertFalse(result.ok)
        self.assertEqual(result.criteria, ())
        self.assertEqual(result.errors, ("response is not valid JSON",))

    def test_a_missing_score_is_a_validation_failure(self):
        payload = json.loads(_dump(VALID))
        del payload["criteria"][0]["fit_score"]
        result = validate_model_output(json.dumps(payload))

        self.assertFalse(result.ok)
        self.assertEqual(result.errors, ("B1 is missing fit_score",))

    def test_a_score_outside_1_to_5_is_a_validation_failure(self):
        payload = json.loads(_dump(VALID))
        payload["criteria"][0]["fit_score"] = 9
        result = validate_model_output(json.dumps(payload))

        self.assertFalse(result.ok)
        self.assertEqual(result.errors, ("B1 fit_score must be an integer from 1 to 5",))

    def test_a_string_score_is_a_validation_failure(self):
        payload = json.loads(_dump(VALID))
        payload["criteria"][0]["fit_score"] = "4"
        result = validate_model_output(json.dumps(payload))

        self.assertFalse(result.ok)
        self.assertEqual(result.errors, ("B1 fit_score must be an integer from 1 to 5",))

    def test_an_off_list_tone_word_is_a_validation_failure(self):
        payload = json.loads(_dump(VALID))
        payload["criteria"][0]["tone_label"] = "authentic, industrial"
        result = validate_model_output(json.dumps(payload))

        self.assertFalse(result.ok)
        self.assertEqual(result.criteria, ())
        self.assertEqual(
            result.errors,
            ('B1 tone_label contains "industrial", which is not a target tone word',),
        )

    def test_empty_evidence_is_a_validation_failure(self):
        payload = json.loads(_dump(VALID))
        payload["criteria"][0]["evidence"] = "   "
        result = validate_model_output(json.dumps(payload))

        self.assertFalse(result.ok)
        self.assertEqual(
            result.errors,
            ("B1 evidence must be one sentence naming something visible",),
        )

    def test_the_wrong_criterion_is_a_validation_failure(self):
        payload = json.loads(_dump(VALID))
        payload["criteria"][0]["id"] = "Q1"
        result = validate_model_output(json.dumps(payload))

        self.assertFalse(result.ok)
        self.assertEqual(result.errors, ("criteria ids are ['Q1'], expected ['B1']",))

    def test_an_unexpected_field_is_a_validation_failure(self):
        payload = json.loads(_dump(VALID))
        payload["criteria"][0]["notes"] = "extra"
        result = validate_model_output(json.dumps(payload))

        self.assertFalse(result.ok)
        self.assertEqual(result.errors, ('B1 has unexpected field "notes"',))
