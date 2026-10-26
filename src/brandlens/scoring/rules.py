"""Map one criterion's measurements to a score using that criterion's rubric params.

Rule ids are stored on each result so a score can be traced to the configuration:

* ``pass_fail_thresholds`` — exposure, contrast, framing, and sharpness.
  Score 100 when every active bound holds, otherwise 0. A null bound the
  rule still needs, or a missing measurement, is ``unavailable_needs_review``
  rather than a failing score.
* ``linear_distance_to_0_100`` — color palette fit.
  ``clip(100 * (1 - palette_distance / palette_distance_max), 0, 100)``.
* ``linear_1_5_to_0_100`` — tone, from ``params.score_mapping``.
  ``(fit_score - fit_score_min) / (fit_score_max - fit_score_min) * 100``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

_OK = "ok"
_REVIEW = "unavailable_needs_review"
_PASS_FAIL = "pass_fail_thresholds"
_DISTANCE = "linear_distance_to_0_100"
_TONE_MAP = "linear_1_5_to_0_100"


@dataclass(frozen=True)
class RuleOutcome:
    """Score for one criterion, or the reason it could not be scored."""

    score: float | None
    availability: str
    rule_id: str
    reasons: tuple[str, ...]
    evidence: tuple[str, ...]
    label: str | None = None


def unavailable(rule_id: str, *reasons: str) -> RuleOutcome:
    """Build a review result. A reason is required so the gap stays visible."""
    text = reasons or ("Scoring inputs were incomplete.",)
    return RuleOutcome(None, _REVIEW, rule_id, text, ())


def score_exposure(measurements: dict[str, Any], params: dict[str, Any]) -> RuleOutcome:
    """Pass only inside the luminance window and clipping caps."""
    return _pass_fail(
        measurements,
        params,
        (
            ("mean_luminance", "mean_luminance_min", "gte"),
            ("mean_luminance", "mean_luminance_max", "lte"),
            ("near_black_fraction", "near_black_fraction_max", "lte"),
            ("near_white_fraction", "near_white_fraction_max", "lte"),
        ),
    )


def score_contrast(measurements: dict[str, Any], params: dict[str, Any]) -> RuleOutcome:
    """Pass only inside the spread window. Flat and harsh both fail."""
    return _pass_fail(
        measurements,
        params,
        (
            ("luminance_std", "luminance_std_min", "gte"),
            ("luminance_std", "luminance_std_max", "lte"),
            ("p5_p95_range", "p5_p95_range_min", "gte"),
            ("p5_p95_range", "p5_p95_range_max", "lte"),
            ("near_black_fraction", "near_black_fraction_max", "lte"),
            ("near_white_fraction", "near_white_fraction_max", "lte"),
        ),
    )


def score_palette(measurements: dict[str, Any], params: dict[str, Any]) -> RuleOutcome:
    """Map palette distance through the configured maximum. Lower is better."""
    named = params.get("score_mapping")
    if named not in (None, _DISTANCE):
        return unavailable(str(named), f"Unsupported score_mapping: {named}")
    maximum = _optional_bound(params, "palette_distance_max")
    if maximum is None:
        return unavailable(_DISTANCE, "Rubric threshold unset: palette_distance_max")
    if maximum <= 0:
        raise ValueError("palette_distance_max must be positive.")
    distance = _as_float(measurements.get("palette_distance"))
    if distance is None:
        return unavailable(_DISTANCE, "Missing measurement palette_distance.")
    if distance < 0:
        return unavailable(_DISTANCE, "palette_distance must be nonnegative.")
    score = min(100.0, max(0.0, 100.0 * (1.0 - distance / maximum)))
    detail = (
        f"palette_distance {_num(distance)} mapped by {_DISTANCE} "
        f"with palette_distance_max {_num(maximum)} -> {_num(score)}"
    )
    return RuleOutcome(score, _OK, _DISTANCE, (), (detail,))


def score_framing(measurements: dict[str, Any], params: dict[str, Any]) -> RuleOutcome:
    """Pass when the subject is near center or a third, and inside any margin bound."""
    position_bounds = []
    for measurement, param in (
        ("center_offset", "center_offset_max"),
        ("thirds_offset", "thirds_offset_max"),
    ):
        bound = _optional_bound(params, param)
        if bound is not None:
            position_bounds.append((measurement, param, bound))
    if not position_bounds:
        return unavailable(
            _PASS_FAIL,
            "Rubric thresholds unset: center_offset_max, thirds_offset_max",
        )

    evidence: list[str] = []
    failures: list[str] = []
    position_pass = False
    for measurement, param, bound in position_bounds:
        actual = _as_float(measurements.get(measurement))
        if actual is None:
            return unavailable(_PASS_FAIL, f"Missing measurement {measurement}.")
        detail = f"{measurement} {_num(actual)} <= {param} {_num(bound)}"
        evidence.append(detail)
        position_pass = position_pass or actual <= bound
    if not position_pass:
        failures.append(
            "subject is outside every configured center and thirds bound"
        )

    margin = _optional_bound(params, "edge_margin_min")
    if margin is not None:
        actual = _as_float(measurements.get("edge_margin_min"))
        if actual is None:
            return unavailable(_PASS_FAIL, "Missing measurement edge_margin_min.")
        detail = f"edge_margin_min {_num(actual)} >= params.edge_margin_min {_num(margin)}"
        evidence.append(detail)
        if actual < margin:
            failures.append(detail)

    if failures:
        return RuleOutcome(0.0, _OK, _PASS_FAIL, tuple(failures), tuple(evidence))
    return RuleOutcome(100.0, _OK, _PASS_FAIL, (), tuple(evidence))


def score_sharpness(measurements: dict[str, Any], params: dict[str, Any]) -> RuleOutcome:
    """Pass subject sharpness and ratio bounds. Intentional motion is not an automatic fail."""
    active = []
    unset = []
    for measurement, param in (
        ("subject_sharpness", "subject_sharpness_min"),
        ("sharpness_ratio", "sharpness_ratio_min"),
    ):
        bound = _optional_bound(params, param)
        if bound is None:
            unset.append(param)
        else:
            active.append((measurement, param, bound))
    if not active:
        return unavailable(_PASS_FAIL, "Rubric thresholds unset: " + ", ".join(unset))

    evidence: list[str] = []
    failures: list[str] = []
    for measurement, param, bound in active:
        actual = _as_float(measurements.get(measurement))
        if actual is None:
            return unavailable(_PASS_FAIL, f"Missing measurement {measurement}.")
        detail = f"{measurement} {_num(actual)} >= {param} {_num(bound)}"
        evidence.append(detail)
        if actual < bound:
            failures.append(detail)

    motion = measurements.get("intentional_motion")
    policy = params.get("intentional_motion_policy")
    if motion is True and failures:
        if policy != "needs_review_not_automatic_fail":
            return unavailable(
                _PASS_FAIL,
                "intentional_motion is true and intentional_motion_policy "
                f"is {policy!r}, which this scorer does not apply as a pass.",
            )
        return unavailable(
            _PASS_FAIL,
            "intentional_motion is true and policy is "
            "needs_review_not_automatic_fail, so a failing sharpness "
            "measurement is not scored as a fail",
        )
    if failures:
        return RuleOutcome(0.0, _OK, _PASS_FAIL, tuple(failures), tuple(evidence))
    return RuleOutcome(100.0, _OK, _PASS_FAIL, (), tuple(evidence))


def score_tone(measurements: dict[str, Any], params: dict[str, Any]) -> RuleOutcome:
    """Map an integer fit score with the rubric's named score_mapping."""
    mapping = params.get("score_mapping")
    if mapping is None:
        return unavailable(_TONE_MAP, "Rubric score_mapping unset.")
    if mapping != _TONE_MAP:
        return unavailable(str(mapping), f"Unsupported score_mapping: {mapping}")

    low = _integer_param(params, "fit_score_min", default=1)
    high = _integer_param(params, "fit_score_max", default=5)
    if high <= low:
        raise ValueError("fit_score_max must be greater than fit_score_min.")

    fit = measurements.get("fit_score")
    if isinstance(fit, bool) or not isinstance(fit, int):
        return unavailable(mapping, "fit_score must be an integer.")
    if not low <= fit <= high:
        return unavailable(mapping, f"fit_score {fit} is outside {low}..{high}.")

    label = measurements.get("label")
    if not isinstance(label, str) or not label.strip():
        return unavailable(mapping, "Missing measurement label.")
    label = label.strip()
    allowed = params.get("allowed_labels")
    if isinstance(allowed, list):
        allowed_words = {str(word).strip().casefold() for word in allowed}
        words = [word.strip() for word in label.split(",") if word.strip()]
        rejected = [word for word in words if word.casefold() not in allowed_words]
        if not words or rejected:
            shown = ", ".join(rejected or ["(empty)"])
            return unavailable(mapping, f"label not in allowed_labels: {shown}")

    evidence = measurements.get("evidence")
    if not isinstance(evidence, str) or not evidence.strip():
        return unavailable(mapping, "Missing measurement evidence.")
    score = (fit - low) / (high - low) * 100.0
    trace = (
        f"fit_score {fit} mapped by {mapping} "
        f"from fit_score_min {low}..fit_score_max {high} -> {_num(score)}"
    )
    return RuleOutcome(score, _OK, mapping, (), (evidence.strip(), trace), label=label)


CV_RULES = {
    "exposure_brightness": score_exposure,
    "contrast": score_contrast,
    "color_palette_fit": score_palette,
    "framing_subject_position": score_framing,
    "sharpness_subject_emphasis": score_sharpness,
}


def _pass_fail(
    measurements: dict[str, Any],
    params: dict[str, Any],
    bounds: tuple[tuple[str, str, str], ...],
) -> RuleOutcome:
    unset = [param for _, param, _ in bounds if _optional_bound(params, param) is None]
    if unset:
        return unavailable(_PASS_FAIL, "Rubric thresholds unset: " + ", ".join(unset))

    evidence: list[str] = []
    failures: list[str] = []
    for measurement, param, op in bounds:
        actual = _as_float(measurements.get(measurement))
        if actual is None:
            return unavailable(_PASS_FAIL, f"Missing measurement {measurement}.")
        bound = _as_bound(params[param], param)
        symbol = ">=" if op == "gte" else "<="
        detail = f"{measurement} {_num(actual)} {symbol} {param} {_num(bound)}"
        evidence.append(detail)
        passed = actual >= bound if op == "gte" else actual <= bound
        if not passed:
            failures.append(detail)
    if failures:
        return RuleOutcome(0.0, _OK, _PASS_FAIL, tuple(failures), tuple(evidence))
    return RuleOutcome(100.0, _OK, _PASS_FAIL, (), tuple(evidence))


def _optional_bound(params: dict[str, Any], name: str) -> float | None:
    if name not in params or params[name] is None:
        return None
    return _as_bound(params[name], name)


def _as_bound(value: Any, name: str) -> float:
    number = _as_float(value)
    if number is None:
        raise ValueError(f"Rubric param {name} must be a finite number.")
    return number


def _as_float(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    if not math.isfinite(number):
        return None
    return number


def _integer_param(params: dict[str, Any], name: str, default: int) -> int:
    if name not in params or params[name] is None:
        return default
    value = params[name]
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"Rubric param {name} must be an integer.")
    return value


def _num(value: float) -> str:
    return format(value, ".6g")
