#!/bin/bash
#SBATCH --job-name=brandlens-b1-12b
#SBATCH --output=logs/%x-%j.out
#SBATCH --error=logs/%x-%j.err
#SBATCH --time=06:00:00
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=64G
#SBATCH --gres=gpu:1
# TinkerCliffs — CapOne BrandLens B1 (account pbl_r8h19uj7to6v)
#SBATCH --partition=a100_normal_q
#SBATCH --account=pbl_r8h19uj7to6v

set -euo pipefail

# Run from the finetune directory on the shared filesystem after you copy
# visual-brand-audit/vlm/finetune there (images + data + scripts).
# Recommended path: /scratch/krishna2026/vlm/finetune  (symlink: ~/vlm)
cd "${SLURM_SUBMIT_DIR:-.}"
mkdir -p logs outputs

module load CUDA/12.4.0 2>/dev/null || module load cuda/12.4 2>/dev/null || true
# Venv was built with ARC Python/3.11; loading it keeps dynamic libs consistent.
module load Python/3.11.5-GCCcore-13.2.0 2>/dev/null || true
source "${BRANDLENS_VENV:-$HOME/venvs/brandlens-train/bin/activate}"

# brandlens package lives at ~/vlm/src on ARC (and repo/src on the laptop).
export PYTHONPATH="/scratch/krishna2026/vlm/src${PYTHONPATH:+:$PYTHONPATH}"

# All VLM storage lives under /scratch/krishna2026/vlm/
export HF_HOME="${HF_HOME:-/scratch/krishna2026/vlm/hf-cache}"
export TRANSFORMERS_CACHE="${TRANSFORMERS_CACHE:-$HF_HOME}"
mkdir -p "$HF_HOME"

# Permanent token: ~/.config/brandlens/env  (chmod 600; not in git)
#   export HF_TOKEN=hf_...
if [[ -f "${HOME}/.config/brandlens/env" ]]; then
  # shellcheck disable=SC1091
  source "${HOME}/.config/brandlens/env"
fi
if [[ -z "${HF_TOKEN:-}" ]]; then
  echo "HF_TOKEN is required. Create ~/.config/brandlens/env with: export HF_TOKEN=hf_..." >&2
  exit 1
fi

echo "host=$(hostname) gpu=$(nvidia-smi -L || true)"
python -c "import torch; print('cuda', torch.cuda.is_available(), torch.cuda.get_device_name(0) if torch.cuda.is_available() else None)"

python prepare_sft.py
python train_lora.py \
  --model "${VLM_MODEL:-google/gemma-4-12B-it}" \
  --train data/train.jsonl \
  --eval data/holdout.jsonl \
  --output-dir outputs/gemma4-12b-b1-lora \
  --epochs "${EPOCHS:-2}" \
  --batch-size 1 \
  --grad-accum 8

python eval_holdout.py \
  --model "${VLM_MODEL:-google/gemma-4-12B-it}" \
  --adapter outputs/gemma4-12b-b1-lora \
  --holdout data/holdout.jsonl \
  --out outputs/holdout_eval.jsonl
