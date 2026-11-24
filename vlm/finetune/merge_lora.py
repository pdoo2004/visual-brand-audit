#!/usr/bin/env python3
"""Merge a LoRA adapter into the base Gemma 4 12B weights for vLLM serving.

vLLM can also load LoRA adapters dynamically; merging is the simplest path for
a single BrandLens checkpoint.

  python merge_lora.py \\
    --adapter outputs/gemma4-12b-b1-lora \\
    --out outputs/gemma4-12b-b1-merged
"""

from __future__ import annotations

import argparse
from pathlib import Path

import torch
from peft import PeftModel
from transformers import AutoModelForImageTextToText, AutoProcessor


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--model", default="google/gemma-4-12B-it")
    p.add_argument("--adapter", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()

    processor = AutoProcessor.from_pretrained(args.model, trust_remote_code=True)
    base = AutoModelForImageTextToText.from_pretrained(
        args.model,
        torch_dtype=torch.bfloat16,
        device_map="cpu",
        trust_remote_code=True,
    )
    model = PeftModel.from_pretrained(base, str(args.adapter))
    merged = model.merge_and_unload()
    args.out.mkdir(parents=True, exist_ok=True)
    merged.save_pretrained(str(args.out), safe_serialization=True)
    processor.save_pretrained(str(args.out))
    print(f"merged model written to {args.out}")


if __name__ == "__main__":
    main()
