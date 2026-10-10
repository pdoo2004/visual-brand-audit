# 1.3 — Brand standards configuration summary

**Jira:** SCRUM-181  
**Owner:** Sanish  
**Estimate:** 4 hours  
**Function:** Standards schema

## Objective

Define a manageable, reproducible photography rubric and the configuration fields needed by the evaluation pipeline. This task uses the six criteria locked in Subtask 1.2 and follows the proposed interface from Subtask 1.4, with draft settings and internal fields documented explicitly.

## Files

| File | Purpose |
| --- | --- |
| `config/brand_standards.json` | Criterion definitions, evaluation evidence, methods, weights, parameters, required evaluator outputs, and rubric metadata. |
| `config/brand_standards.schema.json` | Required fields, types, allowed methods, score/weight ranges, and palette formatting. |
| `examples/1_3_brand_standards_example.ipynb` | Loads the files, validates the configuration, checks the MVP criterion IDs, and displays the resulting fields. |

## MVP evaluation plan

| Criterion ID | Method | Planned evidence |
| --- | --- | --- |
| `exposure_brightness` | CV | Mean luminance and near-black/near-white pixel fractions compared with provisional exposure bounds. |
| `contrast` | CV | Luminance standard deviation, fifth-to-ninety-fifth percentile range, and clipping fractions. |
| `color_palette_fit` | CV | Dominant colors and proportions from clustering; proportion-weighted mean distance to the nearest configured palette colors. |
| `framing_subject_position` | CV | Subject bounding box, offsets from center and thirds, and minimum frame margin. |
| `sharpness_subject_emphasis` | CV | Subject/background sharpness and their ratio; intentional motion and visual dominance require additional evidence or review. |
| `tone_approachability` | VLM | Tone label, integer fit score of 1–5, and one sentence citing visible evidence. The placeholder target is “approachable, competent.” |

The configuration describes the required evaluation evidence. Image-specific human-readable explanations are generated later by the evaluation/scoring pipeline and returned with each criterion result; they are not stored as fixed reviews in this file.

## Schema design

The schema allows additional criterion IDs without changing its structure. Each criterion selects either `cv` or `vlm`. The current schema requires at least six entries; the notebook separately checks unique IDs and the presence of all six locked MVP criteria.

`params` remains flexible so criterion-specific settings can evolve. The common schema does not validate every parameter value, threshold relationship, or cross-criterion weight total. Those checks belong in subsequent parameter validation and scoring-readiness checks.

## Draft settings and limitations

- Exposure and contrast thresholds are placeholders requiring calibration.
- Palette colors and tone words are not confirmed Capital One standards.
- Weights, the overall flag threshold, and several criterion thresholds remain unset.
- `scoring_ready` remains `false`; CV score mappings and aggregation settings are not finalized.
- Missing required evidence or failed model evaluation is marked `unavailable_needs_review`, while available results should continue. This is a declared pipeline policy, not behavior implemented by the configuration itself.
- Whole-image exposure/contrast statistics do not establish subject readability or separation by themselves. Sharpness ratio alone does not establish subject emphasis.
- `required_measurements` identifies required evaluator outputs for both CV and VLM.

`schema_version` identifies the configuration structure. `rubric_id` identifies the rubric version recorded for a job. Preserve immutable rubric versions once jobs use them.

## Verification

The example notebook:

1. Loads both JSON files from `config/`.
2. Checks that the JSON Schema itself is valid.
3. Validates the configuration against the schema.
4. Checks that criterion IDs are unique and all six locked criteria are present.
5. Displays each criterion's method, weight, required outputs, and parameter keys.
6. Reports configuration acceptance separately from scoring readiness.

The saved notebook output shows successful schema validation and the presence of all six unique MVP criteria. It reports the configuration as a draft with scoring readiness set to false. Rerun all cells against the committed repository files to produce submission evidence.

**Acceptance criterion:** When the configuration is loaded, all MVP criteria parse successfully and expose the fields required by the scoring/evaluation pipeline.

The notebook demonstrates this at the configuration level. Image-analysis accuracy, model calls, unavailable-result handling, API/database integration, and final scoring behavior are outside this verification.
