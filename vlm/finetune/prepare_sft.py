#!/usr/bin/env python3
"""Turn manifest.jsonl into chat SFT JSONL for Gemma 4 vision fine-tuning.

Writes:
  data/train.jsonl
  data/holdout.jsonl

Each row is one multimodal chat turn. The assistant target is the locked B1
JSON shape that validate_model_output accepts.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VLM = ROOT.parent
if str(VLM) not in sys.path:
    sys.path.insert(0, str(VLM))

from prompt_template import render_prompt  # noqa: E402

PROMPT = render_prompt(["B1"])


def target_json(row: dict) -> str:
    return json.dumps(
        {
            "criteria": [
                {
                    "id": "B1",
                    "name": "Tone and approachability",
                    "tone_label": row["tone_label"],
                    "fit_score": int(row["fit_score"]),
                    "evidence": row["evidence"],
                }
            ]
        },
        ensure_ascii=False,
    )


def example(row: dict, images_dir: Path) -> dict:
    image_path = (images_dir / row["file"]).resolve()
    if not image_path.is_file():
        raise FileNotFoundError(image_path)
    return {
        "file": row["file"],
        "split": row.get("split", "train"),
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "image", "path": str(image_path)},
                    {"type": "text", "text": PROMPT},
                ],
            },
            {
                "role": "assistant",
                "content": [{"type": "text", "text": target_json(row)}],
            },
        ],
    }


def main() -> None:
    manifest = ROOT / "manifest.jsonl"
    images = ROOT / "images"
    out = ROOT / "data"
    out.mkdir(exist_ok=True)

    rows = [json.loads(line) for line in manifest.read_text(encoding="utf-8").splitlines() if line.strip()]
    train, holdout = [], []
    for row in rows:
        if row.get("label_status") != "reviewed":
            raise SystemExit(f"unreviewed row: {row.get('file')}")
        item = example(row, images)
        if row.get("split") == "holdout":
            holdout.append(item)
        else:
            train.append(item)

    train_path = out / "train.jsonl"
    holdout_path = out / "holdout.jsonl"
    train_path.write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in train) + "\n", encoding="utf-8")
    holdout_path.write_text(
        "\n".join(json.dumps(x, ensure_ascii=False) for x in holdout) + "\n", encoding="utf-8"
    )
    print(f"wrote {len(train)} train -> {train_path}")
    print(f"wrote {len(holdout)} holdout -> {holdout_path}")


if __name__ == "__main__":
    main()
