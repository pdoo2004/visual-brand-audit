# Fine-tune Gemma 4 12B on ARC (B1 tone)

This folder trains **`google/gemma-4-12B-it`** with QLoRA on the reviewed BrandLens set (`manifest.jsonl` + `images/`).

The BrandLens API does not change for training. After merge you serve the checkpoint behind the same OpenAI-compatible `/v1/chat/completions` URL. Frozen serve settings: [`INFERENCE.md`](./INFERENCE.md). Demo runbook: [`DEMO.md`](./DEMO.md).

## What you already have

| Path | Role |
|---|---|
| `manifest.jsonl` | Reviewed labels (train / holdout split) |
| `images/` | Matching photo files (kept on ARC / local; not required in git) |
| `prepare_sft.py` | Builds `data/train.jsonl` and `data/holdout.jsonl` |
| `train_lora.py` | QLoRA training |
| `eval_holdout.py` | Holdout check with `validate_model_output` |
| `merge_lora.py` | Merge adapter into a vLLM-friendly folder |
| `scripts/train_b1_12b.slurm` | One-GPU Slurm job |
| `scripts/serve_merged.slurm` | Serve merged weights with the unified vLLM sif |
| `requirements-train.txt` | Python deps for the GPU node |

## One-time ARC setup

1. Accept the Gemma license on Hugging Face for `google/gemma-4-12B-it` and create a token with read access.
2. On a login node:

```bash
module load cuda/12.4   # or whatever ARC documents today
python3 -m venv $HOME/venvs/brandlens-train
source $HOME/venvs/brandlens-train/bin/activate
pip install -U pip
pip install -U torch torchvision --index-url https://download.pytorch.org/whl/cu124
pip install -r requirements-train.txt
huggingface-cli login   # paste HF_TOKEN
```

3. Keep VLM artifacts under one tree on TinkerCliffs:

```text
/scratch/krishna2026/vlm/          # also ~/vlm (symlink)
  finetune/                        # code, images, outputs/
  prompt_template.py
  src/brandlens/                   # for eval_holdout imports
  hf-cache/                        # Hugging Face weights cache
  vllm-openai_gemma4_unified.sif   # serve image for the merged 12B
```

Do **not** rely on a laptop GPU for the 12B job.

4. Slurm is set for CapOne PBL: `--partition=a100_normal_q`, `--account=pbl_r8h19uj7to6v`.

## Train

```bash
cd /path/to/vlm/finetune
mkdir -p logs
sbatch scripts/train_b1_12b.slurm
```

Or interactively on an allocated GPU node:

```bash
source $HOME/venvs/brandlens-train/bin/activate
export HF_TOKEN=...
python prepare_sft.py
python train_lora.py --output-dir outputs/gemma4-12b-b1-lora
python eval_holdout.py --adapter outputs/gemma4-12b-b1-lora
```

Success for MVP: most holdout replies pass `validate_model_output`, and fit scores move in the right direction vs the base model.

## Serve after training

Merge once (uses CPU RAM; run on a fat node if needed):

```bash
python merge_lora.py \
  --adapter outputs/gemma4-12b-b1-lora \
  --out outputs/gemma4-12b-b1-merged
python scripts/patch_merged_config_for_vllm.py
```

Then `sbatch scripts/serve_merged.slurm` (or point any OpenAI-compatible vLLM at the merged folder).

Backend / BrandLens client:

```bash
export BRANDLENS_MODEL_BASE_URL=http://<arc-or-gpu-host>:8000/v1
export BRANDLENS_MODEL_NAME=/path/to/outputs/gemma4-12b-b1-merged
export BRANDLENS_ANALYZER=pipeline
```

Request shape stays the locked B1 prompt. No scorer rewrite.

## Laptop note

Do not expect this 12B QLoRA job on a 6–8 GB laptop. Use ARC (or another ≥40 GB GPU). Local Ollama `gemma4:e4b` remains the day-to-day smoke-test model.
