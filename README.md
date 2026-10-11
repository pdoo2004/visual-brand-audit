# visual-brand-audit

AI-enabled tool for evaluating marketing photography against visual brand standards. Built as a VT Capstone project.

## What it does

Users upload photos or submit a website URL. The system crawls the site for images, filters out non-photographic assets, and runs each photograph through two analysis layers:

- **Computer vision** (OpenCV, scikit-learn) — measures brightness, contrast, dominant colors, and framing
- **Vision-language model** (Gemma 4) — judges tone, approachability, and brand fit, returning structured reasoning

A scoring engine combines both layers against a configurable rubric and produces criterion-level scores with human-readable explanations. Results are displayed in a React dashboard where reviewers can mark agreement or disagreement with the AI's assessment.

## Current status (Sprint 1)

The preprocessing library and the VLM tone-scoring prototype are complete. The FastAPI backend, React UI, web crawler, CV analyzer, and scoring engine are in progress.

| Component | Status |
|---|---|
| Image preprocessing (`brandlens`) | Built |
| VLM tone-scoring prototype | Built |
| Database schema | Designed (`docs/architecture/database-schema.md`) |
| Interface contracts | Designed (`docs/architecture/`) |
| FastAPI backend | Planned |
| React/TypeScript UI | Planned |
| Web crawler | Planned |
| CV analyzer | Planned |
| Scoring engine | Planned |

## Getting started

Requires Python 3.11+.

```bash
pip install -e ".[dev]"
```

Run the test suite:

```bash
pytest tests/
```

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

## Architecture

| Component | Role |
|---|---|
| React/TypeScript UI | Upload, job status, dashboard, reviewer feedback |
| FastAPI backend | Coordinates all components, manages background jobs |
| Web Crawler | Playwright + BeautifulSoup, bounded page traversal |
| Image Preprocessor | Filters logos/icons, standardizes photos for analysis |
| Computer Vision Analyzer | OpenCV/NumPy/scikit-learn — quantifiable attributes |
| Model Serving | Self-hosted Gemma 4 over HTTP — qualitative judgments |
| Scoring Engine | Combines CV + VLM output against JSON rubric |
| Data Storage | SQLite for results + file cache for images |

## Stack

Python 3.11+, FastAPI, React, OpenCV, Pillow, NumPy, scikit-learn, BeautifulSoup, Playwright, Gemma 4 (31B). No paid APIs or licenses required.
