# Local model endpoint

Sprint 1, backlog 4.2. This is how a teammate runs a tone judgment on one photograph before the shared vLLM endpoint exists.

The development model is `gemma4:e4b`. The choice is explained in `BENCHMARK.md`. The server model is still the design-doc candidate, Gemma 4 31B, on the cloud GPU host.

## Setup

Install [Ollama](https://ollama.com), then pull the development model:

```powershell
ollama pull gemma4:e4b
```

The tag is about 6.6 GB and needs ~5.7 GB of GPU memory at runtime. Do not load `gemma4:26b` or `gemma4:31b` on a laptop. Those weights are for the GPU host.

If your machine does not have enough GPU memory for `gemma4:e4b`, pull one of these lighter alternatives:

```powershell
ollama pull gemma4:e2b
ollama pull qwen2.5vl:3b
```

## Command the rest of the pipeline can mirror

From this folder (use `python3` on Mac, `python` on Windows):

**Mac:**
```bash
python3 run_local.py samples/01-coffee-shop.jpg
```

**Windows:**
```powershell
python run_local.py samples/01-coffee-shop.jpg
```

To use a different model, pass `--model`:

```bash
python3 run_local.py --model qwen2.5vl:3b samples/01-coffee-shop.jpg
```

That sends the B1 prompt in `prompt_template.py` and one image to:

`POST http://127.0.0.1:11434/api/chat`

The body uses model `gemma4:e4b`, thinking off, temperature 0.2, and `num_ctx` 2048. The reply is the B1 JSON. The backend client (backlog 4.5) should send the same kind of request. In deployment the host changes from localhost to the vLLM endpoint. The JSON shape does not.

On a 6 GB GPU the model uses about 5.7 GB, so the short context is required. The first photograph takes about 20–27 seconds while the weights load. Later photographs take about 1–2 seconds.

```powershell
ollama ps
ollama stop gemma4:e4b
```
