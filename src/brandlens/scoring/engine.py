"""Apply a rubric's rules and weights to CV measurements and model judgments.

``score_image`` scores only the selected criteria. A criterion with missing
inputs, an analyzer status of ``unavailable_needs_review``, or a null threshold
the rule needs stays unavailable and does not block the others.

Weights come from the rubric. Null weights on every selected criterion mean
equal weight. Applied weights are renormalized over the criteria that scored,
and unavailable criteria get applied weight 0. The overall score is the
weighted mean of the available scores. Image status is ``scored`` when every
selected criterion scored, ``partial`` when only some did, and ``failed`` when
none did. ``flagged`` is true when ``flag_threshold`` is set and the overall
score is below it.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from brandlens.scoring.rules import CV_RULES, RuleOutcome, score_tone, unavailable

_OK = "ok"
_REVIEW = "unavailable_needs_review"
_VLM_ALIASES = {
    "tone_approachability": ("tone_approachability", "B1"),
}


@dataclass(frozen=True)
class CriterionScore:
    """One criterion after rubric rules and weight renormalization."""

    criterion_id: str
    score: float | None
    weight: float
    configured_weight: float
    source: str
    label: str | None
    evidence: tuple[str, ...]
    availability: str
    rule_id: str
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class ImageScore:
    """Criterion rows plus the weighted image summary."""

    rubric_id: str | None
    criteria: tuple[CriterionScore, ...]
    overall_score: float | None
    flagged: bool
    status: str


@dataclass(frozen=True)
class _Spec:
    criterion_id: str
    method: str
    weight: float | None
    params: dict[str, Any]
    required_measurements: tuple[str, ...]


def score_image(
    rubric: Mapping[str, Any],
    *,
    cv_results: Mapping[str, Any] | None = None,
    vlm_results: Mapping[str, Any] | None = None,
    criterion_ids: Sequence[str] | None = None,
) -> ImageScore:
    """Score one image from analyzer envelopes and model judgments.

    ``cv_results`` is keyed by criterion id. Values are analyzer envelopes
    (``status``, ``measurements``, ``reasons``) or a bare measurements dict.
    ``vlm_results`` is keyed by criterion id, or by ``B1`` for
    ``tone_approachability``. A value is a mapping or object with
    ``fit_score``, ``label`` or ``tone_label``, and ``evidence``.

    Raises:
        TypeError: ``rubric`` is not a mapping.
        ValueError: the rubric or the selection is not usable (unknown ids,
            duplicate ids, mixed null and numeric weights, a non-positive
            weight total).
    """
    specs = _select(_parse_rubric(rubric), criterion_ids)
    cv = dict(cv_results or {})
    vlm = dict(vlm_results or {})
    outcomes = [_score_spec(spec, cv, vlm) for spec in specs]
    shares = _configured_shares(specs)
    applied = _applied_weights(specs, outcomes, shares)

    criteria = tuple(
        CriterionScore(
            criterion_id=spec.criterion_id,
            score=outcome.score,
            weight=applied[spec.criterion_id],
            configured_weight=shares[spec.criterion_id],
            source=spec.method,
            label=outcome.label,
            evidence=outcome.evidence,
            availability=outcome.availability,
            rule_id=outcome.rule_id,
            reasons=outcome.reasons,
        )
        for spec, outcome in zip(specs, outcomes, strict=True)
    )
    overall = _overall(criteria)
    status = _status(criteria)
    return ImageScore(
        rubric_id=_rubric_id(rubric),
        criteria=criteria,
        overall_score=overall,
        flagged=_flagged(rubric, overall),
        status=status,
    )


def _parse_rubric(rubric: Mapping[str, Any]) -> list[_Spec]:
    if not isinstance(rubric, Mapping):
        raise TypeError("rubric must be a mapping.")
    raw_criteria = rubric.get("criteria")
    if not isinstance(raw_criteria, list) or not raw_criteria:
        raise ValueError("rubric criteria must be a non-empty list.")
    specs: list[_Spec] = []
    seen: set[str] = set()
    for raw in raw_criteria:
        if not isinstance(raw, Mapping):
            raise TypeError("each criterion must be an object.")
        criterion_id = raw.get("criterion_id")
        if not isinstance(criterion_id, str) or not criterion_id:
            raise ValueError("each criterion needs a criterion_id.")
        if criterion_id in seen:
            raise ValueError(f"duplicate criterion_id: {criterion_id}")
        seen.add(criterion_id)
        method = raw.get("method")
        if method not in ("cv", "vlm"):
            raise ValueError(f"{criterion_id} method must be 'cv' or 'vlm'.")
        weight = _weight(criterion_id, raw.get("weight"))
        params = raw.get("params") or {}
        if not isinstance(params, Mapping):
            raise TypeError(f"{criterion_id} params must be an object.")
        required = raw.get("required_measurements") or []
        if not isinstance(required, list) or not all(isinstance(item, str) for item in required):
            raise TypeError(f"{criterion_id} required_measurements must be a list of strings.")
        specs.append(
            _Spec(
                criterion_id=criterion_id,
                method=method,
                weight=weight,
                params=dict(params),
                required_measurements=tuple(required),
            )
        )
    return specs


def _weight(criterion_id: str, value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{criterion_id} weight must be a number or null.")
    if not math.isfinite(value) or not 0 <= value <= 1:
        raise ValueError(f"{criterion_id} weight must be from 0 to 1.")
    return float(value)


def _select(specs: list[_Spec], criterion_ids: Sequence[str] | None) -> list[_Spec]:
    by_id = {spec.criterion_id: spec for spec in specs}
    if criterion_ids is None:
        return specs
    if not criterion_ids:
        raise ValueError("criterion_ids must list at least one criterion.")
    unknown = [criterion_id for criterion_id in criterion_ids if criterion_id not in by_id]
    if unknown:
        raise ValueError("Unknown criterion ids: " + ", ".join(unknown))
    if len(set(criterion_ids)) != len(criterion_ids):
        raise ValueError("criterion_ids must not repeat a criterion.")
    return [by_id[criterion_id] for criterion_id in criterion_ids]


def _score_spec(
    spec: _Spec,
    cv_results: Mapping[str, Any],
    vlm_results: Mapping[str, Any],
) -> RuleOutcome:
    if spec.method == "cv":
        return _score_cv(spec, cv_results.get(spec.criterion_id))
    return _score_vlm(spec, _lookup_vlm(vlm_results, spec.criterion_id))


def _score_cv(spec: _Spec, raw: Any) -> RuleOutcome:
    rule = CV_RULES.get(spec.criterion_id)
    rule_id = "pass_fail_thresholds" if rule is None else _rule_name(spec)
    if raw is None:
        return unavailable(rule_id, f"No CV result for {spec.criterion_id}.")
    status, measurements, reasons = _parse_cv(raw)
    if status == _REVIEW:
        return unavailable(rule_id, *(reasons or (f"{spec.criterion_id} measurement is unavailable.",)))
    if status != "available":
        return unavailable(rule_id, f"Unknown measurement status: {status}.")
    missing = _missing(measurements, spec.required_measurements)
    if missing:
        return unavailable(rule_id, "Missing measurements: " + ", ".join(missing) + ".")
    if rule is None:
        return unavailable(
            "unsupported_criterion",
            f"No scoring rule is registered for {spec.criterion_id}.",
        )
    return rule(measurements, spec.params)


def _score_vlm(spec: _Spec, raw: Any) -> RuleOutcome:
    mapping = spec.params.get("score_mapping")
    named = mapping if isinstance(mapping, str) else "linear_1_5_to_0_100"
    if raw is None:
        return unavailable(named, f"No model result for {spec.criterion_id}.")
    if isinstance(raw, Mapping) and raw.get("ok") is False:
        errors = raw.get("errors") or (f"{spec.criterion_id} model output was rejected.",)
        return unavailable(named, *(str(error) for error in errors))
    measurements = _vlm_measurements(raw)
    if measurements is None:
        return unavailable(named, f"Model result for {spec.criterion_id} could not be read.")
    missing = _missing(measurements, spec.required_measurements)
    if missing:
        return unavailable(named, "Missing measurements: " + ", ".join(missing) + ".")
    return score_tone(measurements, spec.params)


def _rule_name(spec: _Spec) -> str:
    if spec.criterion_id == "color_palette_fit":
        return "linear_distance_to_0_100"
    if spec.method == "vlm":
        mapping = spec.params.get("score_mapping")
        return mapping if isinstance(mapping, str) else "linear_1_5_to_0_100"
    return "pass_fail_thresholds"


def _parse_cv(raw: Any) -> tuple[str, dict[str, Any], tuple[str, ...]]:
    if not isinstance(raw, Mapping):
        return _REVIEW, {}, ("CV result is not an object.",)
    if "measurements" in raw or "status" in raw:
        measurements = raw.get("measurements") or {}
        if not isinstance(measurements, Mapping):
            return _REVIEW, {}, ("measurements is not an object.",)
        reasons = raw.get("reasons") or ()
        if not isinstance(reasons, (list, tuple)):
            reasons = (str(reasons),)
        return str(raw.get("status") or "available"), dict(measurements), tuple(
            str(reason) for reason in reasons
        )
    return "available", dict(raw), ()


def _lookup_vlm(results: Mapping[str, Any], criterion_id: str) -> Any:
    for key in _VLM_ALIASES.get(criterion_id, (criterion_id,)):
        if key in results:
            return results[key]
    return None


def _vlm_measurements(raw: Any) -> dict[str, Any] | None:
    if isinstance(raw, Mapping):
        label = raw.get("label", raw.get("tone_label"))
        return {
            "label": label,
            "fit_score": raw.get("fit_score"),
            "evidence": raw.get("evidence"),
        }
    fit = getattr(raw, "fit_score", None)
    label = getattr(raw, "tone_label", None)
    if label is None:
        label = getattr(raw, "label", None)
    evidence = getattr(raw, "evidence", None)
    if fit is None and label is None and evidence is None:
        return None
    return {"label": label, "fit_score": fit, "evidence": evidence}


def _missing(measurements: Mapping[str, Any], required: tuple[str, ...]) -> list[str]:
    missing: list[str] = []
    for key in required:
        if _blank(measurements.get(key)):
            missing.append(key)
    return missing


def _blank(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    return isinstance(value, float) and not math.isfinite(value)


def _configured_shares(specs: Sequence[_Spec]) -> dict[str, float]:
    weights = [spec.weight for spec in specs]
    if all(weight is None for weight in weights):
        share = 1.0 / len(specs)
        return {spec.criterion_id: share for spec in specs}
    if any(weight is None for weight in weights):
        raise ValueError(
            "Rubric weights must all be numbers or all be null. Null means equal weight."
        )
    total = sum(weight or 0.0 for weight in weights)
    if total <= 0:
        raise ValueError("Selected criteria need a positive total weight.")
    return {spec.criterion_id: float(spec.weight or 0.0) / total for spec in specs}


def _applied_weights(
    specs: Sequence[_Spec],
    outcomes: Sequence[RuleOutcome],
    shares: Mapping[str, float],
) -> dict[str, float]:
    available = [
        spec.criterion_id
        for spec, outcome in zip(specs, outcomes, strict=True)
        if outcome.availability == _OK
    ]
    available_share = sum(shares[criterion_id] for criterion_id in available)
    applied: dict[str, float] = {}
    if available and available_share <= 0:
        equal = 1.0 / len(available)
        available_set = set(available)
        for spec in specs:
            applied[spec.criterion_id] = equal if spec.criterion_id in available_set else 0.0
        return applied
    for spec, outcome in zip(specs, outcomes, strict=True):
        if outcome.availability == _OK and available_share > 0:
            applied[spec.criterion_id] = shares[spec.criterion_id] / available_share
        else:
            applied[spec.criterion_id] = 0.0
    return applied


def _overall(criteria: Sequence[CriterionScore]) -> float | None:
    scored = [row for row in criteria if row.availability == _OK and row.score is not None]
    if not scored:
        return None
    return sum(row.score * row.weight for row in scored if row.score is not None)


def _status(criteria: Sequence[CriterionScore]) -> str:
    available = sum(1 for row in criteria if row.availability == _OK)
    if available == 0:
        return "failed"
    if available == len(criteria):
        return "scored"
    return "partial"


def _flagged(rubric: Mapping[str, Any], overall: float | None) -> bool:
    threshold = rubric.get("flag_threshold")
    if threshold is None or overall is None:
        return False
    if isinstance(threshold, bool) or not isinstance(threshold, (int, float)):
        raise TypeError("flag_threshold must be a number or null.")
    if not math.isfinite(threshold) or not 0 <= threshold <= 100:
        raise ValueError("flag_threshold must be from 0 to 100.")
    return overall < float(threshold)


def _rubric_id(rubric: Mapping[str, Any]) -> str | None:
    rubric_id = rubric.get("rubric_id")
    if rubric_id is None:
        return None
    if not isinstance(rubric_id, str):
        raise TypeError("rubric_id must be a string.")
    return rubric_id
