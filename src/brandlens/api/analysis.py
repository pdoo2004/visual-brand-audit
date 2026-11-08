"""Adapter between the scoring pipeline and the job worker (SCRUM-166 / 167).

The pipeline (``brandlens.pipeline``) returns scorer dataclasses and raw CV and
model results. The worker and ``db.save_image_result`` want plain mappings. This
module is the only place that translates one into the other, so neither side
has to know the other's types.

    worker  --(standardized image, selected criterion ids)-->  PipelineAnalyzer
    PipelineAnalyzer  -->  pipeline.score_standardized_image(...)
                      -->  (ImageScore, cv_results, vlm_results)
                      -->  to_image_analysis(...)  -->  ImageAnalysis  -->  worker

Preprocessing is not done here: the worker already filtered and standardized the
image, and ``score_standardized_image`` deliberately does not repeat it.
"""

from __future__ import annotations

import logging
import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, is_dataclass, replace
from typing import Any

from PIL import Image

from brandlens.api.worker import ImageAnalysis
from brandlens.scoring.engine import CriterionScore, ImageScore
from brandlens.scoring.explanations import explain_criterion

log = logging.getLogger(__name__)

_IMAGE_STATUSES = {"scored", "partial", "failed"}

# (image, configuration, vlm_client, **keywords) -> (ImageScore, cv_results, vlm_results)
ScoreFn = Callable[..., tuple[ImageScore, Mapping[str, Any], Mapping[str, Any]]]


def to_image_analysis(
    scored: ImageScore,
    cv_results: Mapping[str, Any] | None = None,
    vlm_results: Mapping[str, Any] | None = None,
) -> ImageAnalysis:
    """Convert the scorer's output into what the worker stores for one image.

    Every selected criterion is kept, including unavailable ones: they are stored
    with a null score and ``unavailable_needs_review`` so the dashboard can send
    them to a human reviewer instead of dropping them.
    """
    status = scored.status if scored.status in _IMAGE_STATUSES else "failed"
    error_code = error_message = None
    if status == "failed":
        error_code = "NO_CRITERIA_AVAILABLE"
        error_message = "No selected criterion could be scored; every result needs review."

    return ImageAnalysis(
        status=status,
        overall_score=None if status == "failed" else scored.overall_score,
        flagged=bool(scored.flagged),
        criteria=[_criterion_mapping(c) for c in scored.criteria],
        measurements=_measurements(cv_results, vlm_results),
        error_code=error_code,
        error_message=error_message,
    )


def _criterion_mapping(criterion: CriterionScore) -> dict[str, Any]:
    """One CriterionScore -> the mapping ``db.save_image_result`` accepts."""
    available = criterion.availability == "ok" and criterion.score is not None
    # The database requires availability "ok" to come with a score. If the scorer ever
    # reports "ok" without one, explain it as needing review rather than fail the image.
    explained = criterion if available else replace(
        criterion, availability="unavailable_needs_review"
    )
    return {
        "criterion_id": criterion.criterion_id,
        "score": float(criterion.score) if available else None,
        "weight": float(criterion.weight),
        "source": criterion.source,
        "label": criterion.label,
        "explanation": explain_criterion(explained),
        "evidence": [str(item) for item in criterion.evidence],
        "availability": "ok" if available else "unavailable_needs_review",
    }


def _measurements(
    cv_results: Mapping[str, Any] | None,
    vlm_results: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    """Raw CV measurements and model judgments, made JSON-safe for storage."""
    if not cv_results and not vlm_results:
        return None
    return {
        "cv": _jsonable(dict(cv_results or {})),
        "vlm": _jsonable(dict(vlm_results or {})),
    }


def _jsonable(value: Any) -> Any:
    """Convert analyzer output (numpy scalars, tuples, dataclasses, NaN) to JSON."""
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, Mapping):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_jsonable(v) for v in value]
    if is_dataclass(value) and not isinstance(value, type):
        return _jsonable(asdict(value))
    tolist = getattr(value, "tolist", None)  # numpy arrays and scalars
    if callable(tolist):
        return _jsonable(tolist())
    return str(value)


class PipelineAnalyzer:
    """The worker's ``analyze`` hook, backed by the real scoring pipeline.

    Build it once at startup: it holds the loaded rubric/configuration, the model
    client and an optional subject detector, so none of that is rebuilt per image.
    Call it with ``(standardized_image, criterion_ids)``.

    Failures propagate. The worker records an exception as that image failing and
    carries on with the rest of the batch.
    """

    def __init__(
        self,
        configuration: Any,
        vlm_client: Any = None,
        *,
        subject_detector: Any = None,
        subject_selector: Any = None,
        score_fn: ScoreFn | None = None,
    ) -> None:
        if score_fn is None:
            from brandlens.pipeline import score_standardized_image as score_fn
        self._configuration = configuration
        self._vlm_client = vlm_client
        self._subject_detector = subject_detector
        self._subject_selector = subject_selector
        self._score_fn = score_fn

    @classmethod
    def from_settings(cls, settings: Any, *, subject_detector: Any = None) -> PipelineAnalyzer:
        """Load the rubric and create the model client from the API settings.

        Raises the configuration loader's error if the rubric file is invalid, so
        a bad configuration is found at startup, not on the first image.
        """
        from brandlens.api.model_client import ModelClient
        from brandlens.config import load_cv_config

        configuration = load_cv_config(settings.rubric_path)
        rubric = configuration[0]
        needs_model = any(c.get("method") == "vlm" for c in rubric.get("criteria", []))
        client = ModelClient.from_settings(settings) if needs_model else None
        log.info(
            "pipeline analyzer ready: rubric %s, model client %s",
            rubric.get("rubric_id"), "on" if client else "off (no VLM criteria)",
        )
        return cls(configuration, client, subject_detector=subject_detector)

    def __call__(self, image: Image.Image, criterion_ids: Sequence[str]) -> ImageAnalysis:
        scored, cv_results, vlm_results = self._score_fn(
            image,
            self._configuration,
            self._vlm_client,
            criterion_ids=list(criterion_ids),
            subject_detector=self._subject_detector,
            subject_selector=self._subject_selector,
        )
        return to_image_analysis(scored, cv_results, vlm_results)

    def close(self) -> None:
        """Release the model client's connection pool."""
        close = getattr(self._vlm_client, "close", None)
        if callable(close):
            close()
