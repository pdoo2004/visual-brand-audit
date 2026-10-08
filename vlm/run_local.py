"""Send one photograph to the selected local model.

Development command for SCRUM-120. Model is gemma4:e4b via Ollama.

    python run_local.py samples/01-coffee-shop.jpg
"""

from __future__ import annotations

import sys
from pathlib import Path

from benchmark import post_chat
from prompt_template import render_prompt

MODEL = "gemma4:e4b"


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: python run_local.py <image.jpg>")
    path = Path(sys.argv[1])
    if not path.is_file():
        raise SystemExit(f"image not found: {path}")
    import base64

    image_b64 = base64.b64encode(path.read_bytes()).decode("ascii")
    payload = post_chat(MODEL, render_prompt(["B1"]), image_b64, timeout=180)
    message = payload.get("message") or {}
    print(message.get("content") or "")


if __name__ == "__main__":
    main()
