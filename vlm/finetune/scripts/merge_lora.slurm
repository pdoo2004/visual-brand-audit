#!/bin/bash
#SBATCH --job-name=brandlens-merge-lora
#SBATCH --output=logs/%x-%j.out
#SBATCH --error=logs/%x-%j.err
#SBATCH --time=02:00:00
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=128G
# CPU-only: merge loads full 12B bf16 on CPU (~24GB+ peak).
#SBATCH --partition=normal_q
#SBATCH --account=pbl_r8h19uj7to6v

set -euo pipefail
cd "${SLURM_SUBMIT_DIR:-.}"
mkdir -p logs outputs

module load Python/3.11.5-GCCcore-13.2.0 2>/dev/null || true
source "${BRANDLENS_VENV:-$HOME/venvs/brandlens-train/bin/activate}"
export HF_HOME="${HF_HOME:-/scratch/krishna2026/vlm/hf-cache}"
export TRANSFORMERS_CACHE="${TRANSFORMERS_CACHE:-$HF_HOME}"
# shellcheck disable=SC1091
source "${HOME}/.config/brandlens/env"

echo "host=$(hostname) mem=$(free -h | awk '/^Mem:/{print $2}')"
echo "merging adapter -> outputs/gemma4-12b-b1-merged"

python merge_lora.py \
  --model "${VLM_MODEL:-google/gemma-4-12B-it}" \
  --adapter outputs/gemma4-12b-b1-lora \
  --out outputs/gemma4-12b-b1-merged

du -sh outputs/gemma4-12b-b1-merged
ls -la outputs/gemma4-12b-b1-merged | head -30
echo "merge_ok"
