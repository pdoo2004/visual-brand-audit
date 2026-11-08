# SCRUM-140 — Integrated VLM/scoring evaluation

Generated: `2026-11-08T01:58:38.706220+00:00`
Mode: `offline-mock`
Config: `config\brand_standards.json`

## Acceptance

When the integrated pipeline runs on the review set, scoring/explanation
mismatches are documented here. Blocking issues should be filed in Jira
before midterm (SCRUM-140).

## Review set

Uses `vlm/samples/` (coffee, office, neon) — same SCRUM-119 benchmark trio.

## Results

### `01-coffee-shop.jpg`

- Expectation: Warm lifestyle / candid coffee scene; should fit Capital One tone list.
- Status: `partial` | overall: `69.95030015296618` | flagged: `False`
- Summary: Overall score 70/100 (partial). Needs review: framing_subject_position, sharpness_subject_emphasis.
- Mismatches: none recorded in this run
- Criteria:
  - `exposure_brightness` (ok, score=100.0): exposure brightness: passed (mean_luminance 95.6864 >= mean_luminance_min 40).
  - `contrast` (ok, score=100.0): contrast: passed (luminance_std 68.6466 >= luminance_std_min 20).
  - `color_palette_fit` (ok, score=19.826050535381633): color palette fit: score 20/100 (palette_distance 32.0696 mapped by linear_distance_to_0_100 with palette_distance_max 40 -> 19.8261).
  - `framing_subject_position` (unavailable_needs_review, score=None): framing subject position: needs review — No subject detector was supplied.
  - `sharpness_subject_emphasis` (unavailable_needs_review, score=None): sharpness subject emphasis: needs review — No subject detector was supplied.
  - `tone_approachability` (ok, score=75.0): tone approachability: score 75/100 (label: casual, lifestyle, candid). Evidence: Hands and a latte under warm indoor light..

### `02-glass-office.jpg`

- Expectation: Bright workplace; lifestyle/casual possible; less warm than coffee.
- Status: `partial` | overall: `41.27775683804913` | flagged: `True`
- Summary: Overall score 41/100 (partial). Needs review: framing_subject_position, sharpness_subject_emphasis. Flagged below the rubric threshold.
- Mismatches: none recorded in this run
- Criteria:
  - `exposure_brightness` (ok, score=100.0): exposure brightness: passed (mean_luminance 111.939 >= mean_luminance_min 40).
  - `contrast` (ok, score=0.0): contrast: failed — p5_p95_range 248 <= p5_p95_range_max 240.
  - `color_palette_fit` (ok, score=19.47214893317192): color palette fit: score 19/100 (palette_distance 32.2111 mapped by linear_distance_to_0_100 with palette_distance_max 40 -> 19.4721).
  - `framing_subject_position` (unavailable_needs_review, score=None): framing subject position: needs review — No subject detector was supplied.
  - `sharpness_subject_emphasis` (unavailable_needs_review, score=None): sharpness subject emphasis: needs review — No subject detector was supplied.
  - `tone_approachability` (ok, score=50.0): tone approachability: score 50/100 (label: lifestyle, casual, natural). Evidence: A bright open office with one person at a desk..

### `03-neon-city.jpg`

- Expectation: Technical night city, no people; should not read as approachable lifestyle.
- Status: `partial` | overall: `61.44967154039675` | flagged: `False`
- Summary: Overall score 61/100 (partial). Needs review: framing_subject_position, sharpness_subject_emphasis.
- Mismatches: none recorded in this run
- Criteria:
  - `exposure_brightness` (ok, score=100.0): exposure brightness: passed (mean_luminance 76.4099 >= mean_luminance_min 40).
  - `contrast` (ok, score=100.0): contrast: passed (luminance_std 61.2162 >= luminance_std_min 20).
  - `color_palette_fit` (ok, score=40.073850391388596): color palette fit: score 40/100 (palette_distance 23.9705 mapped by linear_distance_to_0_100 with palette_distance_max 40 -> 40.0739).
  - `framing_subject_position` (unavailable_needs_review, score=None): framing subject position: needs review — No subject detector was supplied.
  - `sharpness_subject_emphasis` (unavailable_needs_review, score=None): sharpness subject emphasis: needs review — No subject detector was supplied.
  - `tone_approachability` (ok, score=25.0): tone approachability: score 25/100 (label: aesthetic, bright). Evidence: A night city seen through blue neon mesh with no people..

## Fallback check

Forced ModelFailure on 01-coffee-shop.jpg → PASS: partial CV-only score with tone needs-review.

## Follow-ups

- No blocking mismatches in this run. Re-run with --live before midterm if Ollama/vLLM is up.
