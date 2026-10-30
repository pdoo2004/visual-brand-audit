"""Optional Hugging Face RT-DETR adapter; no model loads at import time."""

from math import isfinite
from typing import Any

from PIL import Image

from ..cv_input import CVInput
from .detector_base import DetectionResult, SubjectCandidate, SubjectDetectorBase
from .region import validate_fraction


class RTDetrSubjectDetector(SubjectDetectorBase):
    """Load a local/pretrained RT-DETR pipeline on first detection and reuse it.

    Install torch, torchvision and transformers to use this adapter. The first
    call may download model weights. CPU is the default (device=-1). A model
    revision can be pinned for reproducibility. Internal model resizing is
    mapped back to the supplied image by the Hugging Face pipeline.

    The adapter returns objects, not a primary-subject decision. Model failures
    propagate. Boxes extending outside the image are clipped; degenerate boxes
    are discarded. Non-finite or malformed predictions raise an error.
    """

    def __init__(self, settings: dict[str, Any] | None = None):
        defaults = {"model_id": "PekingU/rtdetr_r18vd", "revision": None,
                    "device": -1, "confidence_threshold": 0.5}
        if settings is None:
            settings = {}
        if not isinstance(settings, dict):
            raise TypeError("settings must be a dictionary or None.")
        if set(settings) - set(defaults):
            raise ValueError("Unknown RT-DETR settings.")
        defaults.update(settings)
        if not isinstance(defaults["model_id"], str) or not defaults["model_id"].strip():
            raise ValueError("model_id must be a nonempty string.")
        revision = defaults["revision"]
        if revision is not None and (not isinstance(revision, str) or not revision.strip()):
            raise ValueError("revision must be a nonempty string or None.")
        if type(defaults["device"]) is not int or defaults["device"] < -1:
            raise ValueError("device must be -1 for CPU or a nonnegative GPU index.")
        validate_fraction("confidence_threshold", defaults["confidence_threshold"])
        self._settings = defaults
        self._pipeline = None

    @property
    def settings(self) -> dict[str, Any]:
        return dict(self._settings)

    def _get_pipeline(self):
        if self._pipeline is None:
            try:
                from transformers import pipeline
            except ImportError as error:
                raise ImportError(
                    "RT-DETR requires torch, torchvision and transformers."
                ) from error
            self._pipeline = pipeline(
                "object-detection", model=self._settings["model_id"],
                revision=self._settings["revision"], device=self._settings["device"],
            )
        return self._pipeline

    def detect(self, image: Image.Image) -> DetectionResult:
        """Normalize absolute xyxy pipeline boxes using the input width/height."""
        CVInput(image)
        pipe = self._get_pipeline()
        # Isolate third-party preprocessing from the caller's borrowed image.
        with image.copy() as working:
            predictions = pipe(working, threshold=self._settings["confidence_threshold"])
        width, height = image.size
        candidates = []
        for prediction in predictions:
            score = float(prediction["score"])
            validate_fraction("prediction confidence", score)
            if score < self._settings["confidence_threshold"]:
                continue
            box = prediction["box"]
            values = [float(box[k]) for k in ("xmin", "ymin", "xmax", "ymax")]
            if not all(isfinite(v) for v in values):
                raise ValueError("Detector returned non-finite box coordinates.")
            left, top, right, bottom = values
            if left > right or top > bottom:
                raise ValueError("Detector returned reversed box coordinates.")
            left, right = (max(0.0, min(1.0, v / width)) for v in (left, right))
            top, bottom = (max(0.0, min(1.0, v / height)) for v in (top, bottom))
            if left == right or top == bottom:
                continue
            candidates.append(SubjectCandidate(
                left, top, right, bottom, prediction["label"], score,
            ))
        config = getattr(getattr(pipe, "model", None), "config", None)
        version = getattr(config, "_commit_hash", None) or self._settings["revision"]
        return DetectionResult(tuple(candidates), self._settings["model_id"],
                               version, image.size)
