#!/bin/bash
# One-time TinkerCliffs env for BrandLens B1 QLoRA.
set -euo pipefail

module load CUDA/12.4.0 2>/dev/null || module load cuda/12.4 2>/dev/null || true

VENV="${BRANDLENS_VENV_DIR:-$HOME/venvs/brandlens-train}"
REQ="${1:-/scratch/krishna2026/vlm/finetune/requirements-train.txt}"

python3 -m venv "$VENV"
# shellcheck disable=SC1091
source "$VENV/bin/activate"
pip install -U pip
pip install -U torch torchvision --index-url https://download.pytorch.org/whl/cu124
pip install -r "$REQ"
python - <<'PY'
import bitsandbytes
import peft
import torch
import transformers
import trl

print("torch", torch.__version__, "cuda_built", torch.version.cuda)
print("transformers", transformers.__version__)
print("peft", peft.__version__)
print("trl", trl.__version__)
print("bitsandbytes", bitsandbytes.__version__)
print("ok")
PY
