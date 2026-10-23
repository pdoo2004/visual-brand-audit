"""Gemma 4 ids the model server can load.

The scorer never imports this table. It sends whatever model name the
server was started with. A larger Gemma is a different id in that name,
not a different request.
"""

from __future__ import annotations

# vLLM loads these Hugging Face repos. E4B is the selected development model.
VLLM_MODELS = {
    "e4b": "google/gemma-4-E4B-it",
    "e2b": "google/gemma-4-E2B-it",
    "26b": "google/gemma-4-26B-A4B-it",
    "31b": "google/gemma-4-31B-it",
}

# Ollama tags for the same family. Used when the laptop GPU cannot hold
# the BF16 checkpoint vLLM serves.
OLLAMA_MODELS = {
    "e4b": "gemma4:e4b",
    "e2b": "gemma4:e2b",
    "26b": "gemma4:26b",
    "31b": "gemma4:31b",
}

DEFAULT_MODEL = VLLM_MODELS["e4b"]
DEFAULT_BASE_URL = "http://127.0.0.1:8000/v1"

# Same sampling budget as the SCRUM-119 laptop runs.
TEMPERATURE = 0.2
MAX_TOKENS = 256
