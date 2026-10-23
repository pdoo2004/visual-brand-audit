"""The model HTTP body stays the same when the model name changes."""

import json
import unittest
from unittest.mock import patch

from brandlens.serving.client import infer
from brandlens.serving.contract import (
    build_chat_request,
    chat_completions_url,
    parse_chat_response,
)
from brandlens.serving.models import VLLM_MODELS

JPEG = b"\xff\xd8\xff\x00fake-jpeg"


class TestChatContract(unittest.TestCase):
    def test_request_uses_the_shared_chat_completions_shape(self):
        body = build_chat_request("Score B1.", JPEG, VLLM_MODELS["e4b"])

        self.assertEqual(body["model"], "google/gemma-4-E4B-it")
        self.assertEqual(body["temperature"], 0.2)
        self.assertEqual(body["max_tokens"], 256)
        self.assertFalse(body["stream"])
        self.assertEqual(body["reasoning_effort"], "none")
        self.assertEqual(body["response_format"], {"type": "json_object"})
        self.assertNotIn("images", body)
        self.assertNotIn("think", body)
        content = body["messages"][0]["content"]
        self.assertEqual(content[0]["text"], "Score B1.")
        self.assertTrue(content[1]["image_url"]["url"].startswith("data:image/jpeg;base64,"))

    def test_a_larger_model_changes_only_the_model_field(self):
        small = build_chat_request("Score B1.", JPEG, VLLM_MODELS["e4b"])
        large = build_chat_request("Score B1.", JPEG, VLLM_MODELS["31b"])

        self.assertEqual(large["model"], "google/gemma-4-31B-it")
        small_without_model = {key: value for key, value in small.items() if key != "model"}
        large_without_model = {key: value for key, value in large.items() if key != "model"}
        self.assertEqual(small_without_model, large_without_model)

    def test_url_accepts_a_root_or_a_v1_base(self):
        self.assertEqual(
            chat_completions_url("http://127.0.0.1:8000"),
            "http://127.0.0.1:8000/v1/chat/completions",
        )
        self.assertEqual(
            chat_completions_url("http://127.0.0.1:8000/v1/"),
            "http://127.0.0.1:8000/v1/chat/completions",
        )

    def test_parse_reads_string_or_part_content(self):
        string_body = {"choices": [{"message": {"content": "{\"criteria\": []}"}}]}
        part_body = {
            "choices": [
                {"message": {"content": [{"type": "text", "text": "{\"criteria\": []}"}]}}
            ]
        }

        self.assertEqual(parse_chat_response(string_body), "{\"criteria\": []}")
        self.assertEqual(parse_chat_response(part_body), "{\"criteria\": []}")

    def test_parse_rejects_an_empty_choice_list(self):
        with self.assertRaises(ValueError):
            parse_chat_response({"choices": []})

    def test_infer_posts_the_selected_model_and_returns_the_text(self):
        captured = {}

        def fake_post(base_url, body, timeout):
            captured["base_url"] = base_url
            captured["body"] = body
            captured["timeout"] = timeout
            return {"choices": [{"message": {"content": "{\"ok\": true}"}}]}

        with patch("brandlens.serving.client.post_chat", fake_post):
            text = infer(
                "Score B1.",
                JPEG,
                base_url="http://gpu-host:8000/v1",
                model=VLLM_MODELS["31b"],
                timeout=30,
            )

        self.assertEqual(text, "{\"ok\": true}")
        self.assertEqual(captured["base_url"], "http://gpu-host:8000/v1")
        self.assertEqual(captured["body"]["model"], "google/gemma-4-31B-it")
        self.assertEqual(captured["timeout"], 30)
        json.dumps(captured["body"])
