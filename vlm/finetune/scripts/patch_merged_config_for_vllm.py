"""Patch merged Gemma4 config so vLLM can build attention layers.

Root cause (vLLM Gemma4DecoderLayer):
  use_k_eq_v = full_attention and config.attention_k_eq_v
  num_kv_heads = getattr(config, "num_global_key_value_heads",
                         config.num_key_value_heads)

HF defines num_global_key_value_heads on the config class as None. getattr
then returns None (does NOT use the default), and Gemma4Attention crashes:
  TypeError: '>=' not supported between instances of 'NoneType' and 'int'

Full-attention layers in this checkpoint use per_layer_config kv_heads=1
and head_dim=512 — set those as num_global_key_value_heads / global_head_dim.
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

_COPY_FROM_TEXT = (
    "num_key_value_heads",
    "num_attention_heads",
    "head_dim",
    "hidden_size",
    "intermediate_size",
    "num_hidden_layers",
    "rms_norm_eps",
    "vocab_size",
    "max_position_embeddings",
    "hidden_activation",
    "attention_bias",
    "sliding_window",
    "layer_types",
    "tie_word_embeddings",
    "attention_k_eq_v",
    "final_logit_softcapping",
)


def _infer_global_kv(text: dict) -> tuple[int, int]:
    per = text.get("per_layer_config") or {}
    layer_types = text.get("layer_types") or []
    globals_: list[tuple[int, int]] = []
    for idx, kind in enumerate(layer_types):
        if kind != "full_attention":
            continue
        row = per.get(f"{idx:02d}") or {}
        kv = row.get("num_key_value_heads")
        hd = row.get("head_dim")
        if kv is not None and hd is not None:
            globals_.append((int(kv), int(hd)))
    if globals_:
        # All full layers in this merge share (1, 512).
        return globals_[0]
    return int(text["num_key_value_heads"]), int(text["head_dim"])


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--config",
        type=Path,
        default=Path("/scratch/krishna2026/vlm/finetune/outputs/gemma4-12b-b1-merged/config.json"),
    )
    args = p.parse_args()

    cfg = json.loads(args.config.read_text(encoding="utf-8"))
    text = cfg.get("text_config")
    if not isinstance(text, dict):
        raise SystemExit("text_config missing")

    kv = text.get("num_key_value_heads")
    if kv is None:
        raise SystemExit("text_config.num_key_value_heads is null")

    backup = args.config.with_suffix(".json.bak_pre_vllm")
    if not backup.exists():
        shutil.copy2(args.config, backup)
        print(f"backup {backup}")

    for key in _COPY_FROM_TEXT:
        if key in text and (key not in cfg or cfg.get(key) is None):
            cfg[key] = text[key]

    cfg["num_key_value_heads"] = kv
    text["num_key_value_heads"] = kv

    global_kv, global_hd = _infer_global_kv(text)
    # Critical: must be non-null so getattr(config, "num_global_key_value_heads", ...)
    # does not return None from the HF config class default.
    for target in (cfg, text):
        target["num_global_key_value_heads"] = global_kv
        target["global_head_dim"] = global_hd

    cfg["text_config"] = text
    args.config.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")
    print("patched", args.config)
    print("num_key_value_heads", kv)
    print("num_global_key_value_heads", global_kv)
    print("global_head_dim", global_hd)


if __name__ == "__main__":
    main()
