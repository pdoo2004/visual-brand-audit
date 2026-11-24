"""Run the holdout set through a base model + optional LoRA adapter.

Checks:
  1. Reply parses with brandlens.vlm.validate_model_output
  2. Optional: fit_score absolute error vs gold label

Usage on ARC after training:
  python eval_holdout.py --adapter outputs/gemma4-12b-b1-lora
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import torch
from peft import PeftModel
from PIL import Image
from transformers import AutoModelForImageTextToText, AutoProcessor

ROOT = Path(__file__).resolve().parent
# Laptop repo: visual-brand-audit/src. ARC umbrella: /scratch/.../vlm/src.
REPO_SRC = next(
    (p for p in (ROOT.parent / "src", ROOT.parents[1] / "src") if (p / "brandlens").is_dir()),
    ROOT.parents[1] / "src",
)
if str(REPO_SRC) not in sys.path:
    sys.path.insert(0, str(REPO_SRC))

from brandlens.vlm.validate import validate_model_output


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def gold_fit(row: dict) -> int | None:
    text = row["messages"][1]["content"][0]["text"]
    try:
        return int(json.loads(text)["criteria"][0]["fit_score"])
    except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError):
        return None


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--model", default="google/gemma-4-12B-it")
    p.add_argument("--adapter", type=Path, default=None)
    p.add_argument("--holdout", type=Path, default=ROOT / "data" / "holdout.jsonl")
    p.add_argument("--limit", type=int, default=0, help="0 = all holdout rows")
    p.add_argument("--max-new-tokens", type=int, default=256)
    p.add_argument("--out", type=Path, default=ROOT / "outputs" / "holdout_eval.jsonl")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    rows = load_jsonl(args.holdout)
    if args.limit:
        rows = rows[: args.limit]

    processor = AutoProcessor.from_pretrained(args.model, trust_remote_code=True)
    model = AutoModelForImageTextToText.from_pretrained(
        args.model,
        torch_dtype=torch.bfloat16,
        device_map="auto",
        trust_remote_code=True,
        attn_implementation="sdpa",
    )
    if args.adapter:
        model = PeftModel.from_pretrained(model, str(args.adapter))
    model.eval()

    args.out.parent.mkdir(parents=True, exist_ok=True)
    ok = 0
    abs_err: list[int] = []
    with args.out.open("w", encoding="utf-8") as fh:
        for row in rows:
            user = row["messages"][0]["content"]
            image = Image.open(next(p["path"] for p in user if p["type"] == "image")).convert("RGB")
            prompt = next(p["text"] for p in user if p["type"] == "text")
            messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "image", "image": image},
                        {"type": "text", "text": prompt},
                    ],
                }
            ]
            inputs = processor.apply_chat_template(
                messages,
                add_generation_prompt=True,
                tokenize=True,
                return_dict=True,
                return_tensors="pt",
            ).to(model.device)
            with torch.inference_mode():
                out = model.generate(**inputs, max_new_tokens=args.max_new_tokens, do_sample=False)
            text = processor.decode(out[0][inputs["input_ids"].shape[-1] :], skip_special_tokens=True)
            result = validate_model_output(text)
            gold = gold_fit(row)
            pred = result.criteria[0].fit_score if result.ok else None
            if result.ok:
                ok += 1
            if gold is not None and pred is not None:
                abs_err.append(abs(gold - pred))
            fh.write(
                json.dumps(
                    {
                        "file": row.get("file"),
                        "ok": result.ok,
                        "errors": list(result.errors),
                        "gold_fit": gold,
                        "pred_fit": pred,
                        "content": text,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
            print(row.get("file"), "ok" if result.ok else result.errors)

    mae = sum(abs_err) / len(abs_err) if abs_err else None
    print(f"valid JSON {ok}/{len(rows)}")
    print(f"fit MAE {mae}")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
