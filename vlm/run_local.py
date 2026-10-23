"""Send one photograph to the selected local model.

Development command for SCRUM-120. Default model is gemma4:e4b via Ollama.
On machines with less than ~6 GB of GPU/unified memory, use gemma4:e2b instead.

    python run_local.py samples/01-coffee-shop.jpg
    python run_local.py --model gemma4:e2b samples/01-coffee-shop.jpg
"""

from __future__ import annotations

import argparse
import base64
from pathlib import Path

from benchmark import post_chat
from prompt_template import render_prompt

DEFAULT_MODEL = "gemma4:e4b"


def main() -> None:
    parser = argparse.ArgumentParser(description="Score one photograph with the VLM.")
    parser.add_argument("image", type=Path, help="Path to a JPEG/PNG image.")
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"Ollama model tag (default: {DEFAULT_MODEL}).",
    )
    args = parser.parse_args()

    if not args.image.is_file():
        raise SystemExit(f"image not found: {args.image}")

    image_b64 = base64.b64encode(args.image.read_bytes()).decode("ascii")
    payload = post_chat(args.model, render_prompt(["B1"]), image_b64, timeout=180)
    message = payload.get("message") or {}
    print(message.get("content") or "")


if __name__ == "__main__":
    main()
