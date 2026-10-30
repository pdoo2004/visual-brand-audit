"""Bridge brand JSON to configured CV criterion instances."""

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, SchemaError, ValidationError

from .cv.criterion_base import CriterionBase
from .cv.registry import CV_REGISTRY

DEFAULT_SCHEMA_PATH = (
    Path(__file__).resolve().parents[3] / "config" / "brand_standards.schema.json"
)


class ConfigurationError(ValueError):
    """Invalid brand configuration."""


def _object(pairs: list[tuple[str, Any]]):
    """Build a JSON object while rejecting duplicate keys.

    Args:
        pairs: Key/value pairs supplied by the JSON parser for one object.

    Returns:
        dict: The parsed object with unique keys.

    Raises:
        ConfigurationError: If the same key occurs more than once.
    """
    result = {}
    for key, value in pairs:
        if key in result:
            raise ConfigurationError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def _nonfinite(value: str):
    """Reject non-finite constants encountered by the JSON parser.

    Args:
        value: A constant such as NaN, Infinity, or -Infinity.

    Raises:
        ConfigurationError: Always, because these constants are not allowed.
    """
    raise ConfigurationError(f"Non-finite JSON number: {value}")


def _read_json(path: Path):
    """Read a UTF-8 JSON file whose top-level value must be an object.

    Args:
        path: Path to the JSON file.

    Returns:
        dict: The parsed JSON document.

    Raises:
        ConfigurationError: If reading or parsing fails, the top-level value
            is not an object, or duplicate keys/non-finite constants occur.
    """
    try:
        result = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_object,
            parse_constant=_nonfinite,
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ConfigurationError(f"Cannot read JSON from {path}: {exc}") from exc
    if not isinstance(result, dict):
        raise ConfigurationError(f"{path}: expected a JSON object.")
    return result


def load_cv_config(
    source: str | Path | dict[str, Any],
    *,
    schema_path: str | Path | None = None,
    registry: dict[str, type[CriterionBase]] | None = None,
):
    """Load brand configuration and construct its configured CV criteria.

    Args:
        source: A JSON file path or an already-loaded rubric dictionary.
            A dictionary is copied so the caller's original is preserved.
        schema_path: Optional path to the JSON schema. For a file source,
            defaults to brand_standards.schema.json beside that file. For a
            dictionary source, defaults to the repository config directory.
        registry: Optional dictionary mapping implementation IDs to criterion
            classes. If omitted, uses the project's CV_REGISTRY.

    Returns:
        tuple: Two ordinary dictionaries, (rubric, criteria):
            rubric contains the validated configuration with resolved CV
            settings, while retaining scoring parameters and VLM entries.
            criteria maps criterion IDs to initialized CV criterion objects.

    Raises:
        ConfigurationError: If the JSON/schema is invalid, criterion IDs
            repeat, an implementation is unsupported or incompatible,
            measurements/settings are unsupported, or palette values conflict.

    Notes:
        Every CV entry is checked and constructed before returning. The caller
        chooses which instances to analyze. VLM entries are retained for the
        model component; scoring parameters are retained for the scorer.
    """
    # 1. Read the JSON file or copy a supplied dictionary. Choose the default
    # schema location without changing the source file or caller's dictionary.
    if isinstance(source, dict):
        rubric = deepcopy(source)
        default_schema = DEFAULT_SCHEMA_PATH
    else:
        path = Path(source)
        rubric = _read_json(path)
        default_schema = path.with_name("brand_standards.schema.json")

    # 2. Check that the configuration contains finite JSON-compatible values.
    # This serialization is only a check; it does not write a file.
    try:
        json.dumps(rubric, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ConfigurationError(
            f"Rubric must contain finite JSON values: {exc}"
        ) from exc

    # 3. Read the selected schema and validate both the schema itself and the
    # rubric structure. Include the offending field's path in validation errors.
    schema = _read_json(
        Path(schema_path) if schema_path is not None else default_schema
    )
    try:
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(rubric)
    except SchemaError as exc:
        raise ConfigurationError(f"Invalid rubric schema: {exc.message}") from exc
    except ValidationError as exc:
        location = ".".join(map(str, exc.absolute_path)) or "rubric"
        raise ConfigurationError(f"{location}: {exc.message}") from exc

    # 4. Select the implementation lookup and prepare the output dictionary.
    # Registry values are classes; criteria values will be initialized objects.
    implementations = CV_REGISTRY if registry is None else registry
    criteria = {}
    seen = set()
    for entry in rubric["criteria"]:
        # 5. Reject duplicate IDs across the whole rubric. Keep VLM entries in
        # the rubric, but construct only entries marked as CV.
        cid = entry["criterion_id"]
        if cid in seen:
            raise ConfigurationError(f"Duplicate criterion_id: {cid}")
        seen.add(cid)
        if entry["method"] != "cv":
            continue

        # 6. Find the implementation class and check both IDs. Different
        # implementations may support the same criterion, so both must match.
        implementation_id = entry["implementation_id"]
        cls = implementations.get(implementation_id)
        if cls is None:
            raise ConfigurationError(
                f"{cid}: unsupported implementation {implementation_id}"
            )
        if cls.criterion_id != cid:
            raise ConfigurationError(f"{implementation_id} does not support {cid}.")
        if cls.implementation_id != implementation_id:
            raise ConfigurationError(
                f"{cid}: registry key does not match implementation_id."
            )

        # 7. Check requested measurement names against the class's declarations.
        # A supported subset is allowed; it does not filter the eventual output.
        unknown = set(entry["required_measurements"]) - set(cls.measurement_specs())
        if unknown:
            raise ConfigurationError(
                f"{cid}: unsupported measurements: {', '.join(sorted(unknown))}"
            )
        # 8. Keep measurement settings separate from scoring parameters. Value
        # validation for accepted settings belongs to the criterion constructor.
        misplaced = set(entry["params"]) & set(cls.settings_spec())
        if misplaced:
            raise ConfigurationError(
                f"{cid}: measurement settings belong under settings, not params: "
                f"{', '.join(sorted(misplaced))}"
            )

        # 9. Copy the requested settings. For an implementation accepting a
        # brand palette, explicitly inject the top-level palette and reject a
        # conflicting local value instead of silently overriding it.
        settings = deepcopy(entry["settings"])
        if "brand_palette" in cls.settings_spec():
            palette = rubric["brand_palette"]
            if "brand_palette" in settings and settings["brand_palette"] != palette:
                raise ConfigurationError(
                    f"{cid}: conflicting brand_palette in settings."
                )
            settings["brand_palette"] = deepcopy(palette)

        # 10. Construct the selected class. Its constructor fills defaults and
        # validates setting names, values, and relationships between settings.
        try:
            criteria[cid] = cls(settings)
        except (TypeError, ValueError) as exc:
            raise ConfigurationError(f"{cid}: {exc}") from exc
        # Record the resolved settings in the returned rubric copy, including
        # constructor defaults and any injected palette. Nothing is saved to disk.
        entry["settings"] = criteria[cid].settings

    # Return configuration data and ready-to-use CV objects separately.
    # The caller's execution loop will pass an AnalysisInput to each object.
    return rubric, criteria
