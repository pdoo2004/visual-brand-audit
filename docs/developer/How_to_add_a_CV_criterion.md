# How to add a CV criterion or implementation

This is a developer guide for the project team. Brand configuration authors can use the catalog to discover existing implementations without editing Python.

## 1. Implement the shared interface

Create one module under `src/brandlens/analysis/` and subclass `CriterionBase`. Declare:

- `criterion_id`: the stable evaluated attribute.
- `implementation_id`: a unique implementation identifier.
- `method_version`: the calculation version.
- `settings_spec()`: accepted setting names, descriptions, and fresh defaults.
- `_validate_settings()`: type, range, and cross-setting validation.
- `measurement_specs()`: native output names, types, units, and nullability.
- `input_requirements()` when a reliable subject region is needed.
- `analyze(data)`: measurements from one shared `AnalysisInput`.

Use `_make_result()` to return the existing result envelope. Settings defaults and units come from the specifications, so they do not need a second definition in the registry or JSON schema. The class docstring supplies its catalog description.

Borrow the image without modifying pixels or metadata. Input must already be standardized to RGB/sRGB. Reuse upstream subject information instead of detecting it inside every criterion. Return explicit unavailable/review results with reasons for unsupported image-specific cases. Preserve any meaningful partial measurements. Do not invent a zero or assign a brand score.

An alternate implementation can share an existing criterion ID but must have its own implementation ID. Compatible output names alone are insufficient: units and measurement meanings must also fit the evaluator. Changed semantics require scoring-owner review and appropriate calibration.

## 2. Register the class

In `analysis/registry.py`, import the class and add it to `_IMPLEMENTATIONS`. The dictionary is built from each class's own `implementation_id`. Duplicate implementation IDs are rejected at import.

```python
CV_REGISTRY[implementation_id]  # Returns a class, not an instance or wrapper.
```

Do not repeat descriptions, defaults, units, or calculation logic here.

## 3. Inspect the catalog

```python
from brandlens.analysis.registry import get_cv_catalog

catalog = get_cv_catalog()
```

The catalog is JSON-compatible and describes implementations without constructing criterion instances. Its `include_defaults=False` option omits defaults from the descriptions.

## 4. Configure a complete rubric entry

The CV entry chooses `criterion_id`, `implementation_id`, `settings`, and `required_measurements`. Keep scoring parameters under `params`; retain the schema's other required entry fields. The following is a field fragment, not a complete rubric:

```json
{
  "criterion_id": "exposure_brightness",
  "implementation_id": "pillow_grayscale_brightness",
  "settings": {"near_black_max": 20},
  "required_measurements": ["mean_luminance", "near_black_fraction"]
}
```

The full rubric uses schema version 1.1.0. Missing setting values use the implementation defaults. For a palette implementation, the loader explicitly passes the top-level brand palette. Conflicting local palettes are rejected.

## 5. Load and run

```python
from brandlens.analysis.config import load_cv_config

rubric, criteria = load_cv_config("config/brand_standards.json")
cv_results = {cid: criterion.analyze(data) for cid, criterion in criteria.items()}
```

The loader validates the whole rubric and constructs its CV instances. VLM entries and scoring configuration stay in `rubric` for their components. There is no additional registry helper class, config container, or analyzer class to extend.

If an implementation declares new measurement names, the scoring owner must support those names and semantics before end-to-end scoring can be claimed. New output arrays/objects must be validated by the implementation and its tests; the loop does not perform generic nested-result validation.

## 6. Verify

Add a test file for the new source module. Cover meaningful numerical fixtures, supported settings, invalid settings, input preservation, and applicable unavailable cases. Add an integration case proving JSON settings reach the class and unsupported requested measurements fail before analysis.

Update catalog-inventory expectations when adding a new registered implementation. Run the relevant criterion, config/registry, and scoring tests. Update the example notebook and document new scorer dependencies when applicable.
