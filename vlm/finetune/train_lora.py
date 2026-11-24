"""QLoRA fine-tune of Gemma 4 12B on the BrandLens B1 chat JSONL.

Default base model: google/gemma-4-12B-it
Writes a PEFT adapter under --output-dir (default outputs/gemma4-12b-b1-lora).

Designed for one ARC GPU with ~40+ GB (A100 40/80, H100, L40S). Uses 4-bit
weights + LoRA so a full 12B BF16 copy is not required in VRAM.

Vision path (transformers 5 / Gemma4UnifiedProcessor):
  Do NOT put PIL images inside message content dicts — that trips
  fetch_images(TypeError: got dict). Follow the TRL/Google pattern:
  messages use {"type": "image"} placeholders; PIL lives in an `images`
  column; SFTTrainer skips its default tokenizer and a collator calls
  processor(text=..., images=...).
"""

from __future__ import annotations

import argparse
import inspect
import json
from pathlib import Path

import torch
from datasets import Dataset
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
from PIL import Image
from transformers import (
    AutoModelForImageTextToText,
    AutoProcessor,
    BitsAndBytesConfig,
)
from trl import SFTConfig, SFTTrainer


def load_jsonl(path: Path) -> list[dict]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def example_from_row(row: dict) -> dict:
    """TRL vision format: messages with image placeholders + separate PIL."""
    image_path: str | None = None
    user_text: str | None = None
    assistant_text: str | None = None
    for turn in row["messages"]:
        role = turn["role"]
        for part in turn["content"]:
            if part.get("type") == "image":
                image_path = part["path"]
            elif part.get("type") == "text" and role == "user":
                user_text = part["text"]
            elif part.get("type") == "text" and role == "assistant":
                assistant_text = part["text"]
    if not image_path or user_text is None or assistant_text is None:
        raise ValueError(f"incomplete row: {row.get('file')}")
    return {
        "file": row.get("file"),
        "images": Image.open(image_path).convert("RGB"),
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "image"},
                    {"type": "text", "text": user_text},
                ],
            },
            {
                "role": "assistant",
                "content": [{"type": "text", "text": assistant_text}],
            },
        ],
    }


def make_vision_collator(processor, max_length: int):
    """Collate with processor(text=..., images=...) — avoids PIL-in-message bug."""

    chat_kw = {}
    # Prefer disabling thinking channel when the processor supports it.
    try:
        sig = inspect.signature(processor.apply_chat_template)
        if "enable_thinking" in sig.parameters:
            chat_kw["enable_thinking"] = False
    except (TypeError, ValueError):
        pass

    def collate(examples: list[dict]) -> dict:
        texts: list[str] = []
        prompt_texts: list[str] = []
        images: list[list] = []
        for ex in examples:
            messages = ex["messages"]
            texts.append(
                processor.apply_chat_template(
                    messages,
                    tokenize=False,
                    add_generation_prompt=False,
                    **chat_kw,
                )
            )
            prompt_texts.append(
                processor.apply_chat_template(
                    messages[:1],
                    tokenize=False,
                    add_generation_prompt=True,
                    **chat_kw,
                )
            )
            img = ex["images"]
            images.append([img] if not isinstance(img, list) else img)

        batch = processor(
            text=texts,
            images=images,
            return_tensors="pt",
            padding=True,
            truncation=True,
            max_length=max_length,
        )
        labels = batch["input_ids"].clone()
        labels[batch["attention_mask"] == 0] = -100

        # Mask the user/prompt prefix so loss is on the assistant JSON.
        prompt_tok = processor(
            text=prompt_texts,
            images=images,
            return_tensors="pt",
            padding=True,
            truncation=True,
            max_length=max_length,
        )
        for i in range(labels.size(0)):
            prompt_len = int(prompt_tok["attention_mask"][i].sum().item())
            labels[i, : min(prompt_len, labels.size(1))] = -100

        batch["labels"] = labels
        return batch

    return collate


def parse_args() -> argparse.Namespace:
    root = Path(__file__).resolve().parent
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--model", default="google/gemma-4-12B-it")
    p.add_argument("--train", type=Path, default=root / "data" / "train.jsonl")
    p.add_argument("--eval", type=Path, default=root / "data" / "holdout.jsonl")
    p.add_argument("--output-dir", type=Path, default=root / "outputs" / "gemma4-12b-b1-lora")
    p.add_argument("--epochs", type=float, default=2.0)
    p.add_argument("--lr", type=float, default=1e-4)
    p.add_argument("--batch-size", type=int, default=1)
    p.add_argument("--grad-accum", type=int, default=8)
    p.add_argument("--max-length", type=int, default=2048)
    p.add_argument("--lora-r", type=int, default=16)
    p.add_argument("--lora-alpha", type=int, default=32)
    p.add_argument("--seed", type=int, default=7)
    p.add_argument("--no-4bit", action="store_true", help="Load BF16 instead of 4-bit (needs more VRAM)")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    if not args.train.is_file():
        raise SystemExit(f"missing train file: {args.train} (run prepare_sft.py first)")

    train_rows = load_jsonl(args.train)
    eval_rows = load_jsonl(args.eval) if args.eval.is_file() else []
    print(f"train={len(train_rows)} eval={len(eval_rows)} model={args.model}")

    processor = AutoProcessor.from_pretrained(args.model, trust_remote_code=True)
    if getattr(processor, "tokenizer", None) is not None and processor.tokenizer.pad_token is None:
        processor.tokenizer.pad_token = processor.tokenizer.eos_token
    if getattr(processor, "tokenizer", None) is not None:
        processor.tokenizer.padding_side = "right"

    # Gemma 4 unified: prefer eager attn; transformers 5 uses dtype= over torch_dtype=.
    load_kw = {
        "device_map": "auto",
        "trust_remote_code": True,
        "attn_implementation": "eager",
        "dtype": torch.bfloat16,
    }
    if args.no_4bit:
        model = AutoModelForImageTextToText.from_pretrained(args.model, **load_kw)
    else:
        quant = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_use_double_quant=True,
            bnb_4bit_compute_dtype=torch.bfloat16,
        )
        model = AutoModelForImageTextToText.from_pretrained(
            args.model,
            quantization_config=quant,
            **load_kw,
        )
        model = prepare_model_for_kbit_training(model)

    lora = LoraConfig(
        r=args.lora_r,
        lora_alpha=args.lora_alpha,
        lora_dropout=0.05,
        bias="none",
        task_type="CAUSAL_LM",
        target_modules="all-linear",
    )
    model = get_peft_model(model, lora)
    model.print_trainable_parameters()

    train_ds = Dataset.from_list([example_from_row(r) for r in train_rows])
    # Holdout stays offline for this job (eval_strategy="no"); keep eval_rows for logs only.
    if eval_rows:
        print(f"holdout rows reserved (not scored in-loop): {len(eval_rows)}")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    collator = make_vision_collator(processor, args.max_length)

    sft = SFTConfig(
        output_dir=str(args.output_dir),
        num_train_epochs=args.epochs,
        learning_rate=args.lr,
        per_device_train_batch_size=args.batch_size,
        per_device_eval_batch_size=1,
        gradient_accumulation_steps=args.grad_accum,
        logging_steps=5,
        save_strategy="epoch",
        # Custom collator owns tokenization; skip TRL's map() path that embeds PIL
        # into message dicts (breaks Gemma4UnifiedProcessor.fetch_images).
        eval_strategy="no",
        bf16=True,
        optim="paged_adamw_8bit" if not args.no_4bit else "adamw_torch",
        lr_scheduler_type="cosine",
        warmup_steps=3,
        max_length=args.max_length,
        seed=args.seed,
        report_to=[],
        remove_unused_columns=False,
        dataset_kwargs={"skip_prepare_dataset": True},
    )

    trainer = SFTTrainer(
        model=model,
        args=sft,
        train_dataset=train_ds,
        eval_dataset=None,
        processing_class=processor,
        data_collator=collator,
    )
    trainer.train()
    trainer.save_model(str(args.output_dir))
    processor.save_pretrained(str(args.output_dir))
    (args.output_dir / "train_args.json").write_text(
        json.dumps(vars(args), default=str, indent=2), encoding="utf-8"
    )
    print(f"adapter saved to {args.output_dir}")


if __name__ == "__main__":
    main()
