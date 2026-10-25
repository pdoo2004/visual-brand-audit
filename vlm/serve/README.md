# Model server

SCRUM-136. vLLM serves Gemma 4 at `POST /v1/chat/completions`. The backend sends a prompt and one image. The model name is configuration.

Default model: `google/gemma-4-E4B-it`.

## Swap the model later

Change `VLM_MODEL` and restart the server. The request shape stays the same.

| Size | `VLM_MODEL` | Where it runs |
|---|---|---|
| E4B (selected) | `google/gemma-4-E4B-it` | GPU host. BF16 weights are about 15 GB, so plan on about 24 GB |
| E2B | `google/gemma-4-E2B-it` | Same kind of host as BF16 E4B |
| 26B-A4B | `google/gemma-4-26B-A4B-it` | About 80 GB |
| 31B | `google/gemma-4-31B-it` | About 80 GB |

`VLM_MAX_MODEL_LEN` is the other knob. The tone prompt fits in 4096 tokens. Raise it only if a larger prompt needs the room. The client reads the same `VLM_MODEL` and puts it in the `model` field. Prompt text, image field, and the B1 JSON shape do not change.

Gemma 4 weights on Hugging Face are gated. Set `HF_TOKEN` before the first start.

```powershell
$env:HF_TOKEN = "<token>"
$env:VLM_MODEL = "google/gemma-4-E4B-it"
docker compose up
```

The compose file does not enable vLLM's reasoning parser. The client also sends `reasoning_effort: "none"`. Gemma 4 otherwise fills the reply with thinking and leaves the answer empty. That field stays on the request for every model size.

The server listens on port 8000. A check from `visual-brand-audit/vlm`:

```powershell
$env:VLM_BASE_URL = "http://127.0.0.1:8000/v1"
$env:VLM_MODEL = "google/gemma-4-E4B-it"
python serve/infer_one.py samples/01-coffee-shop.jpg
```

## This laptop

The RTX 3060 has 6 GB. vLLM's BF16 E4B checkpoint does not fit. Google's 3.7 GB mobile checkpoint (`google/gemma-4-E4B-it-qat-mobile-ct`) also does not load: `vllm/vllm-openai:gemma4` (vLLM 0.19.1.dev6) and `vllm/vllm-openai:gemma4-unified` both reject its compressed-tensors layout. Ollama's `gemma4:e4b` tag fits, and it speaks the same `/v1/chat/completions` path.

```powershell
ollama pull gemma4:e4b
$env:VLM_BASE_URL = "http://127.0.0.1:11434/v1"
$env:VLM_MODEL = "gemma4:e4b"
python serve/infer_one.py samples/01-coffee-shop.jpg
```

Point `VLM_BASE_URL` at the vLLM host when that GPU exists. No client rewrite.
