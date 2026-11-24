#!/bin/bash
#SBATCH --job-name=brandlens-serve12b
#SBATCH --output=logs/%x-%j.out
#SBATCH --error=logs/%x-%j.err
#SBATCH --time=01:00:00
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=64G
#SBATCH --gres=gpu:1
#SBATCH --partition=a100_normal_q
#SBATCH --account=pbl_r8h19uj7to6v

# Serve fine-tuned merged Gemma 4 12B for demo / tunnel smoke tests.
# Listen on 0.0.0.0 so laptop can: ssh -L 8000:$SLURM_NODELIST:8000 ...
set -euo pipefail

VLM_ROOT=/scratch/krishna2026/vlm
MODEL_DIR="${VLM_ROOT}/finetune/outputs/gemma4-12b-b1-merged"
# Needs gemma4_unified support (transformers newer than the Oct gemma4 sif).
SIF="${VLM_ROOT}/vllm-openai_gemma4_unified.sif"
PORT="${VLM_PORT:-8000}"

cd "${SLURM_SUBMIT_DIR:-${VLM_ROOT}/finetune}"
mkdir -p logs

module load apptainer/1.4.0
module load CUDA/12.4.0 2>/dev/null || true

if [[ -f "${HOME}/.config/brandlens/env" ]]; then
  # shellcheck disable=SC1091
  source "${HOME}/.config/brandlens/env"
fi

export HF_HOME="${HF_HOME:-${VLM_ROOT}/hf-cache}"
export TRANSFORMERS_CACHE="${TRANSFORMERS_CACHE:-$HF_HOME}"
mkdir -p "$HF_HOME"

test -f "$SIF"
test -d "$MODEL_DIR"

HOST="$(hostname)"
echo "host=$HOST job=${SLURM_JOB_ID:-local} port=$PORT"
echo "$HOST" > "logs/serve-host-${SLURM_JOB_ID}.txt"
nvidia-smi -L || true

apptainer exec --nv \
  --bind "${VLM_ROOT}:${VLM_ROOT}" \
  "$SIF" \
  vllm serve "$MODEL_DIR" \
  --max-model-len "${VLM_MAX_MODEL_LEN:-4096}" \
  --gpu-memory-utilization 0.90 \
  --limit-mm-per-prompt '{"image":1,"audio":0}' \
  --hf-overrides '{"num_key_value_heads":8,"text_config":{"num_key_value_heads":8,"num_attention_heads":16}}' \
  --host 0.0.0.0 \
  --port "$PORT" \
  > "logs/vllm-serve-${SLURM_JOB_ID}.out" 2>&1 &
VLLM_PID=$!
echo "vllm_pid=$VLLM_PID"

cleanup() {
  kill "$VLLM_PID" 2>/dev/null || true
  wait "$VLLM_PID" 2>/dev/null || true
}
trap cleanup EXIT

READY=0
for i in $(seq 1 120); do
  if curl -sf "http://127.0.0.1:${PORT}/v1/models" >/dev/null 2>&1; then
    READY=1
    echo "vllm_ready after ~$((i * 10))s"
    curl -s "http://127.0.0.1:${PORT}/v1/models" || true
    echo
    break
  fi
  if ! kill -0 "$VLLM_PID" 2>/dev/null; then
    echo "vLLM exited early; tail of log:" >&2
    tail -n 100 "logs/vllm-serve-${SLURM_JOB_ID}.out" >&2 || true
    exit 1
  fi
  sleep 10
done
if [[ "$READY" -ne 1 ]]; then
  echo "vLLM did not become ready in time" >&2
  tail -n 120 "logs/vllm-serve-${SLURM_JOB_ID}.out" >&2 || true
  exit 1
fi

echo "serve_ok host=$HOST port=$PORT"
echo "tunnel_hint: ssh -L 8000:${HOST}:8000 krishna2026@tinkercliffs1.arc.vt.edu"
# Keep allocation alive until walltime or scancel.
wait "$VLLM_PID"
