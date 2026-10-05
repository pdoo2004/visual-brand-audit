# visual-brand-audit

AI-enabled tool for evaluating marketing photography against visual brand standards. Built as a VT Capstone project,

## What it does

Users upload photos or submit a website URL. The system crawls the site for images, filters out non-photographic assets, and runs each photograph through two analysis layers:

- **Computer vision** (OpenCV, scikit-learn) — measures brightness, contrast, dominant colors, and framing
- **Vision-language model** (Gemma 4) — judges tone, approachability, and brand fit, returning structured reasoning

A scoring engine combines both layers against a configurable rubric and produces criterion-level scores with human-readable explanations. Results are displayed in a React dashboard where reviewers can mark agreement or disagreement with the AI's assessment.

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
| Data Storage | Relational DB for results + file cache for images |

## Stack

Python 3.11+, FastAPI, React, OpenCV, Pillow, NumPy, scikit-learn, BeautifulSoup, Playwright, Gemma 4 (31B). No paid APIs or licenses required.

test