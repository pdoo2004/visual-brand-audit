# How to add a CV criterion or implementation

This is a developer guide for the project team. Brand configuration authors can use the catalog to discover existing implementations without editing Python.

## 1. Implement the shared interface

Create one module under `src/brandlens/cv/` and subclass `CriterionBase`. Declare:

- `criterion_id`: the stable evaluated attribute.
- `implementation_id`: a unique implementation identifier.
- `method_version`: the calculation version.
- `settings_spec()`: accepted setting names, descriptions, and fresh defaults.
- `_validate_settings()`: type, range, and cross-setting validation.
- `measurement_specs()`: native output names, types, units, and nullability.
- `input_requirements()` when a reliable subject region is needed.
- `analyze(data)`: measurements from one shared `CVInput`.

Use `_make_result()` to return the existing result envelope. Settings defaults and units come from the specifications, so they do not need a second definition in the registry or JSON schema. The class docstring supplies its catalog description.

Borrow the image without modifying pixels or metadata. Input must already be standardized to RGB/sRGB. Reuse upstream subject information instead of detecting it inside every criterion. Return explicit unavailable/review results with reasons for unsupported image-specific cases. Preserve any meaningful partial measurements. Do not invent a zero or assign a brand score.

An alternate implementation can share an existing criterion ID but must have its own implementation ID. Compatible output names alone are insufficient: units and measurement meanings must also fit the evaluator. Changed semantics require scoring-owner review and appropriate calibration.

## 2. Register the class

In `cv/registry.py`, import the class and add it to `_IMPLEMENTATIONS`. The dictionary is built from each class's own `implementation_id`. Duplicate implementation IDs are rejected at import.

```python
CV_REGISTRY[implementation_id]  # Returns a class, not an instance or wrapper.
```

Do not repeat descriptions, defaults, units, or calculation logic here.

## 3. Inspect the catalog

```python
from brandlens.cv.registry import get_cv_catalog

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
from brandlens.config import load_cv_config
from brandlens.cv.cv_input import CVInput

rubric, criteria = load_cv_config("config/brand_standards.json")
# image is a caller-owned, already standardized RGB/sRGB Pillow image.
# Supply a reliable subject_region when running subject-based criteria.
data = CVInput(image)
cv_results = {cid: criterion.analyze(data) for cid, criterion in criteria.items()}
```

The shared loader lives at `src/brandlens/config.py`; CV implementations and their registry live under `cv/`. The loader validates the rubric against the JSON schema and checks CV settings and requested measurements before constructing CV instances. VLM entries and scoring parameters stay in `rubric` for their components; this loader does not validate the VLM's supported tones or the scorer's rule semantics. There is no additional registry helper class, config container, or analyzer class to extend.

Load configuration once before processing a batch, then reuse `(rubric, criteria)` for each image. A JSON file source uses `brand_standards.schema.json` beside that file by default. A dictionary source uses the repository's `config/brand_standards.schema.json`. Pass `schema_path` explicitly when storing configuration and schema separately.

If an implementation declares new measurement names, the scoring owner must support those names and semantics before end-to-end scoring can be claimed. New output arrays/objects must be validated by the implementation and its tests; the loop does not perform generic nested-result validation.

## 6. Verify

Add a test file under `tests/cv/` for the new CV source module. Cover meaningful numerical fixtures, supported settings, invalid settings, input preservation, and applicable unavailable cases. Add an integration case proving JSON settings reach the class and unsupported requested measurements fail before analysis.

Update the catalog-inventory expectations in `tests/cv/test_registry.py` when adding a new registered criterion. An alternative implementation of the same criterion can share its criterion ID. Run the relevant criterion and scoring tests, plus the bridge/discovery tests:

```bash
python -m pytest tests/test_config.py tests/cv/test_registry.py
```

Update the example notebook and document new scorer dependencies when applicable.
