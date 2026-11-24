# visual-brand-audit

AI-enabled tool for evaluating marketing photography against visual brand standards. Built as a VT Capstone project.

## What it does

Users upload photos or submit a website URL. The system crawls the site for images, filters out non-photographic assets, and runs each photograph through two analysis layers:

- **Computer vision** (OpenCV, scikit-learn) — measures brightness, contrast, dominant colors, and framing
- **Vision-language model** (Gemma 4) — judges tone, approachability, and brand fit, returning structured reasoning

A scoring engine combines both layers against a configurable rubric and produces criterion-level scores with human-readable explanations. Results are displayed in a React dashboard where reviewers can mark agreement or disagreement with the AI's assessment.

## Current status

| Component | Status |
|---|---|
| Image preprocessing | Built |
| CV analyzer (brightness, contrast, color palette, framing, sharpness) | Built |
| VLM model client (Ollama / vLLM) | Built |
| Scoring engine | Built |
| FastAPI backend | Built |
| React/TypeScript UI (upload, job polling, results dashboard) | Built |
| Docker Compose (frontend + API + GPU model service) | Built |
| Test dataset (12 fixture images, pytest fixtures) | Built |
| MVP regression suite (54 tests, `pytest -m regression`) | Built |
| Worker pipeline integration (CV + VLM wired into job worker) | Built |
| Web crawler (URL submission, downloader, bounded page traversal) | Built |
| Rubric threshold calibration | In progress |

## Getting started

Requires Python 3.11+.

```bash
pip install -e ".[dev]"
```

Run the full test suite:

```bash
pytest tests/
```

Run only the MVP regression suite (54 tests, no external dependencies, ~3 s):

```bash
pytest -m regression
```

The regression suite covers 10 backend MVP acceptance criteria (preprocessing, CV, VLM, scoring, API, persistence, and batch orchestration). The React frontend and URL-submission workflow are not included in this selection. Criteria are derived from the completed SCRUM backlog items:

| Acceptance criterion | SCRUM tickets |
|---|---|
| Photo filter rejects images by geometry | SCRUM-117 |
| Images standardized before analysis | SCRUM-118, 128 |
| CV criteria each produce a score and explanation | SCRUM-129, 130, 131, 132 |
| VLM client sends a valid request and parses the reply | SCRUM-137, 138 |
| VLM failure falls back to CV-only with a needs-review flag | SCRUM-139 |
| Scoring engine combines CV + VLM into an overall score | SCRUM-121, 122, 123 |
| API accepts an image upload and returns a job ID | SCRUM-152, 153, 154, 155 |
| Results and feedback are persisted and retrievable | SCRUM-158, 159, 160 |
| Full pipeline completes end-to-end on representative images | SCRUM-166, 169 |
| Batch orchestration processes multiple images and isolates failures | SCRUM-167 |

Run only the fixture image smoke tests:

```bash
pytest tests/fixtures/ -v
```

The `tests/fixtures/images/` directory contains 12 representative images (10 scoreable + 2 filter-rejection cases) covering all six scoring criteria. See `tests/fixtures/images/manifest.json` for per-image source attribution and expected verdicts.

### VLM tone scoring (local)

Requires [Ollama](https://ollama.com). Pull the development model (~6.6 GB) once:

```bash
ollama pull gemma4:e4b
```

If your machine does not have enough GPU memory, pull a lighter alternative instead:

```bash
ollama pull gemma4:e2b
ollama pull qwen2.5vl:3b
```

Run the B1 (tone and approachability) scorer on one photograph (use `python3` on Mac, `python` on Windows):

**Mac:**
```bash
python3 vlm/run_local.py vlm/samples/01-coffee-shop.jpg
```

**Windows:**
```powershell
python vlm/run_local.py vlm/samples/01-coffee-shop.jpg
```

To use a different model, pass `--model`:

```bash
python3 vlm/run_local.py --model qwen2.5vl:3b vlm/samples/01-coffee-shop.jpg
```

See `vlm/OLLAMA.md` for setup details and `vlm/BENCHMARK.md` for the model selection rationale. Do not pull `gemma4:26b` or `gemma4:31b` on a laptop — those weights are for the GPU host.

## Running with Docker

Requires [Docker Desktop](https://www.docker.com/products/docker-desktop/).

### 1. Configure environment

```bash
cp .env.example .env
```

Edit `.env` if needed. The defaults point the API at Ollama running on the host machine (`host.docker.internal:11434`). Pull the model first if you haven't:

```bash
ollama pull gemma4:e4b
```

### 2. Start the stack

```bash
docker compose up --build
```

- Frontend: http://localhost
- API: http://localhost:8000
- API docs: http://localhost:8000/docs

### 3. GPU host (vLLM instead of Ollama)

On a machine with a GPU and the NVIDIA Container Toolkit, the `gpu` profile starts a vLLM server instead:

```bash
HF_TOKEN=<your-token> \
BRANDLENS_MODEL_BASE_URL=http://vlm:8000/v1 \
BRANDLENS_MODEL_NAME=google/gemma-4-E4B-it \
docker compose --profile gpu up --build
```

Gemma 4 E4B weights are gated on Hugging Face — `HF_TOKEN` is required on the first run. Weights are cached in the `hf-cache` Docker volume so subsequent starts skip the download.

## Architecture

| Component | Role |
|---|---|
| React/TypeScript UI | Upload, job status, dashboard, reviewer feedback |
| FastAPI backend | Coordinates all components, manages background jobs |
| Web Crawler | Playwright + BeautifulSoup, bounded page traversal |
| Image Preprocessor | Filters logos/icons, standardizes photos for analysis |
| Computer Vision Analyzer | OpenCV/NumPy/scikit-learn — quantifiable attributes |
| Model Serving | vLLM over `POST /v1/chat/completions`. Default `google/gemma-4-E4B-it`; a larger Gemma is a `VLM_MODEL` change |
| Scoring Engine | Combines CV + VLM output against JSON rubric |
| Data Storage | SQLite for results + file cache for images |

## CI

Three GitHub Actions workflows run on every push and pull request to `main`:

| Workflow | What it checks |
|---|---|
| `lint` | Ruff static analysis |
| `tests` | Full pytest suite (500 tests) |
| `docker-smoke` | Builds the API image and confirms `GET /health` returns `{"status":"ok"}` |

To run only the MVP acceptance criteria gate locally before pushing:

```bash
pytest -m regression
```

## Stack

Python 3.11+, FastAPI, React, OpenCV, Pillow, NumPy, scikit-learn, BeautifulSoup, Playwright, Gemma 4 E4B (31B remains the larger-host candidate). No paid APIs or licenses required.
