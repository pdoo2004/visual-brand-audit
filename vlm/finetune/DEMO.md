# BrandLens mentor demo — ARC fine-tuned Gemma 4 12B

Proven working path (2026-11-21; re-verified 2026-11-24): laptop UI/API → SSH tunnel → ARC A100 vLLM serving `gemma4-12b-b1-merged`.

Frozen model / prompt / sampling knobs: [`INFERENCE.md`](./INFERENCE.md).

## What stays on ARC

| Item | Path |
|---|---|
| Merged weights | `/scratch/krishna2026/vlm/finetune/outputs/gemma4-12b-b1-merged/` |
| LoRA adapter | `/scratch/krishna2026/vlm/finetune/outputs/gemma4-12b-b1-lora/` |
| vLLM image (unified) | `/scratch/krishna2026/vlm/vllm-openai_gemma4_unified.sif` |
| Serve script | `~/vlm/finetune/scripts/serve_merged.slurm` |
| Config patch (required once) | `scripts/patch_merged_config_for_vllm.py` |

Old sif `vllm-openai_gemma4.sif` cannot load `gemma4_unified`. Do not use it for this checkpoint.

Account / partition: `--account=pbl_r8h19uj7to6v`, `--partition=a100_normal_q`.

## Demo day checklist

### 0. Prep (once per machine)
- VT VPN if off-campus (SSH to ARC must work).
- Laptop: Python env with BrandLens deps; `frontend/node_modules` installed.
- Merged `config.json` already patched on ARC (re-run patch script if you re-merge).

### 1. Start GPU serve on ARC
```bash
ssh krishna2026@tinkercliffs1.arc.vt.edu
cd /scratch/krishna2026/vlm/finetune
# if config was re-merged from scratch:
python3 scripts/patch_merged_config_for_vllm.py
sbatch scripts/serve_merged.slurm
squeue -u $USER
# wait until logs show serve_ok; note NODE e.g. tc-dgx003
tail -f logs/brandlens-serve12b-<JOBID>.out
```

### 2. Tunnel from laptop (leave this window open)
```powershell
ssh -L 8000:<NODE>:8000 krishna2026@tinkercliffs1.arc.vt.edu
```
Smoke:
```powershell
curl.exe http://127.0.0.1:8000/v1/models
```
Expect model id = `/scratch/krishna2026/vlm/finetune/outputs/gemma4-12b-b1-merged`.

### 3. BrandLens on laptop (API ≠ tunnel port)
Tunnel owns **8000**. API uses **8001**. UI uses **5173**.

```powershell
cd visual-brand-audit
$env:BRANDLENS_MODEL_BASE_URL = "http://127.0.0.1:8000/v1"
$env:BRANDLENS_MODEL_NAME = "/scratch/krishna2026/vlm/finetune/outputs/gemma4-12b-b1-merged"
$env:BRANDLENS_HOST = "127.0.0.1"
$env:BRANDLENS_PORT = "8001"
$env:BRANDLENS_CORS_ORIGINS = "http://localhost:5173,http://127.0.0.1:5173"
$env:BRANDLENS_MODEL_TIMEOUT_S = "180"
$env:BRANDLENS_ANALYZER = "pipeline"
$env:PYTHONPATH = "src"
python -m brandlens.api
```

Other terminal:
```powershell
cd visual-brand-audit/frontend
npm run dev -- --host 127.0.0.1 --port 5173
```

Open: http://127.0.0.1:5173/  
Select criteria (include **Tone and approachability**), upload images, wait for results.

Optional one-shot VLM check (no UI):
```powershell
cd visual-brand-audit/vlm
$env:VLM_BASE_URL = "http://127.0.0.1:8000/v1"
$env:VLM_MODEL = "/scratch/krishna2026/vlm/finetune/outputs/gemma4-12b-b1-merged"
python serve/infer_one.py samples/01-coffee-shop.jpg
```

### 4. Tear down
```powershell
# stop API + Vite locally (Ctrl+C)
```
```bash
# on ARC
scancel <JOBID>
```

## Public link for mentors (optional)

Laptop `localhost` is **not** reachable by others. For a shareable URL:

1. Host UI+API somewhere public (Fly/Render/campus VM), **or** share the presenter screen.
2. From the ARC GPU job, open a **reverse** tunnel (Cloudflare / ngrok / `ssh -R` to a VPS) so vLLM’s `:8000` gets a public HTTPS URL.
3. Set hosted API:
   - `BRANDLENS_MODEL_BASE_URL=https://<tunnel>/v1`
   - `BRANDLENS_MODEL_NAME=/scratch/.../gemma4-12b-b1-merged`
4. Keep the Slurm job + tunnel up only for the demo window.

Do **not** pull huge Apptainer images on the login node — use `interact` / CPU Slurm (ARC AUP).

## Known demo caveats

- Framing / sharpness need a subject detector (`BRANDLENS_SUBJECT_DETECTOR=1`, default). First run may download RT-DETR weights.
- Serve job walltime is finite (`serve_merged.slurm` ~1h); start early, extend `--time` if needed.
- PowerShell: use `curl.exe`, not `curl` (alias for Invoke-WebRequest).

## Team one-liner

> We run BrandLens on a laptop (or hosted UI) and serve CapOne’s fine-tuned Gemma 4 12B on ARC via vLLM; an SSH tunnel (or reverse tunnel for public demos) connects the app to that GPU for the session only.
