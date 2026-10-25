"""Send one photograph to the configured model server.

From the vlm directory:

    python serve/infer_one.py samples/01-coffee-shop.jpg

VLM_BASE_URL defaults to the vLLM port, http://127.0.0.1:8000/v1.
VLM_MODEL defaults to google/gemma-4-E4B-it.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

VLM_DIR = Path(__file__).resolve().parents[1]
SRC = VLM_DIR.parent / "src"
sys.path.insert(0, str(VLM_DIR))
sys.path.insert(0, str(SRC))

from prompt_template import render_prompt

from brandlens.serving.client import infer
from brandlens.serving.models import DEFAULT_BASE_URL, DEFAULT_MODEL


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: python serve/infer_one.py <image>")
    path = Path(sys.argv[1])
    if not path.is_file():
        raise SystemExit(f"image not found: {path}")
    base_url = os.environ.get("VLM_BASE_URL", DEFAULT_BASE_URL)
    model = os.environ.get("VLM_MODEL", DEFAULT_MODEL)
    text = infer(render_prompt(["B1"]), path.read_bytes(), base_url=base_url, model=model)
    print(f"server={base_url} model={model}")
    print(text)


if __name__ == "__main__":
    main()
