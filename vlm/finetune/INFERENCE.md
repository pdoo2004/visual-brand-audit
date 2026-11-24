# Frozen B1 inference settings

Recorded so another teammate can reproduce CapOne BrandLens tone scoring without guessing paths or knobs.

**Freeze date:** 2026-11-24  
**Owner:** Krishna Mattaparthi  
**Status:** MVP freeze for Sprint 4 demo

## Model

| Setting | Value |
|---|---|
| Base | `google/gemma-4-12B-it` |
| Adapter | QLoRA B1 fine-tune → merged checkpoint |
| Merged path (ARC) | `/scratch/krishna2026/vlm/finetune/outputs/gemma4-12b-b1-merged/` |
| LoRA path (ARC) | `/scratch/krishna2026/vlm/finetune/outputs/gemma4-12b-b1-lora/` |
| Served model id | `/scratch/krishna2026/vlm/finetune/outputs/gemma4-12b-b1-merged` |

## Serve stack (ARC)

| Setting | Value |
|---|---|
| Cluster | TinkerCliffs |
| Account | `pbl_r8h19uj7to6v` |
| Partition | `a100_normal_q` |
| Apptainer image | `/scratch/krishna2026/vlm/vllm-openai_gemma4_unified.sif` |
| Serve script | `/scratch/krishna2026/vlm/finetune/scripts/serve_merged.slurm` |
| Config patch (required once after merge) | `scripts/patch_merged_config_for_vllm.py` (`num_global_key_value_heads`, `global_head_dim`) |
| API | OpenAI-compatible `http://<gpu-node>:8000/v1` |

Do **not** use `vllm-openai_gemma4.sif` for this checkpoint (missing `gemma4_unified`).

## Prompt / schema (repo)

| Setting | Value |
|---|---|
| Template | `src/brandlens/serving/prompt_template.py` |
| Criterion scored by VLM | B1 only (`tone_approachability` in rubric JSON) |
| Evidence style | One short sentence: **visible cue + why fit_score matches/misses target tone** |
| Empty `tone_label` | Allowed when `fit_score` ≤ 2 (hard negatives) |
| Validator | `src/brandlens/vlm/validate.py` |

Local scripts re-export the same template via `vlm/prompt_template.py`.

## Sampling (BrandLens client)

| Setting | Value |
|---|---|
| Temperature | `0.2` (`brandlens.serving.models.TEMPERATURE`) |
| Max tokens | `256` (`brandlens.serving.models.MAX_TOKENS`) |
| Retries | 1 (`BRANDLENS_MODEL_MAX_RETRIES`, default) |

BrandLens env for laptop + tunnel:

```powershell
$env:BRANDLENS_MODEL_BASE_URL = "http://127.0.0.1:8000/v1"
$env:BRANDLENS_MODEL_NAME = "/scratch/krishna2026/vlm/finetune/outputs/gemma4-12b-b1-merged"
$env:BRANDLENS_PORT = "8001"
```

## Acceptance notes

- Hard negatives (empty scene / neon clutter): low `fit_score`, empty `tone_label` accepted and scored (not `invalid_output`).
- End-to-end: UI → API → SSH tunnel → ARC merged 12B.

Step-by-step demo day runbook: [`DEMO.md`](./DEMO.md).  
How to train / merge on ARC: [`ARC.md`](./ARC.md).
