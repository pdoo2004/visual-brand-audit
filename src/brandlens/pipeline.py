"""Connect preprocessing, configured CV, the existing VLM client, and scoring.

Configuration, model clients and optional subject detectors are initialized
outside the per-image function. This module owns orchestration and adapters;
measurement, inference, validation and scoring stay with their components.
"""

from dataclasses import asdict
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from brandlens.api.schemas.vlm import ModelCriterion, ModelRequest
from brandlens.config import ConfigurationError
from brandlens.cv.cv_input import CVInput
from brandlens.cv.subject.selector import SingleSubjectSelector
from brandlens.preprocessing.preprocessor import preprocess_image
from brandlens.scoring import score_image
from brandlens.vlm.criteria import RECOMMENDED_TONES


def _check_vlm_entry(entry):
    """Reject configuration that the unchanged fixed-B1 client cannot honor.

    This is an adapter compatibility check, not another JSON-schema load.
    The existing client ignores request criteria when rendering its prompt.
    Until that interface changes, accepting arbitrary configured tones here
    would silently analyze different tones from those selected by the brand.
    """
    cid = entry["criterion_id"]
    if cid != "tone_approachability":
        raise ConfigurationError(f"Existing VLM client does not support criterion {cid}.")

    params = entry["params"]
    target = params.get("target_tone")
    labels = params.get("allowed_labels")
    if not isinstance(target, str) or not isinstance(labels, list) or any(
        not isinstance(label, str) for label in labels
    ):
        raise ConfigurationError(
            f"{cid}: target_tone and allowed_labels must match the fixed B1 tone list."
        )
    supported = {word.casefold() for word in RECOMMENDED_TONES}
    target_words = {word.strip().casefold() for word in target.split(",")}
    label_words = {word.strip().casefold() for word in labels}
    if target_words != supported or label_words != supported or len(labels) != len(label_words):
        raise ConfigurationError(
            f"{cid}: configured tones differ from the existing VLM's fixed B1 tone list. "
            "Align the configuration with the VLM owner; no tones were overridden."
        )

    for name, expected in (("fit_score_min", 1), ("fit_score_max", 5)):
        value = params.get(name, expected)
        if type(value) is not int or value != expected:
            raise ConfigurationError(f"{cid}: existing VLM client requires {name}={expected}.")
    unknown = set(entry["required_measurements"]) - {"label", "fit_score", "evidence"}
    if unknown:
        raise ConfigurationError(
            f"{cid}: existing VLM client does not produce: {', '.join(sorted(unknown))}."
        )


def _make_cv_input(image, criteria, subject_detector, subject_selector):
    """Share one optional subject-selection decision across all CV criteria."""
    needs_subject = any(
        criterion.input_requirements().get("reliable_subject_region", False)
        for criterion in criteria.values()
    )
    if not needs_subject:
        return CVInput(image)
    if subject_detector is None:
        return CVInput(image, subject_unavailable_reason="No subject detector was supplied.")

    detections = subject_detector.detect(image)
    selector = subject_selector if subject_selector is not None else SingleSubjectSelector()
    decision = selector.select(detections)
    if detections.image_size != image.size:
        raise ValueError("Subject detections must describe the standardized image's size.")
    return CVInput(
        image,
        subject_region=decision.subject_region,
        subject_unavailable_reason=decision.reason,
    )


def _run_vlm(image, entries, client):
    """Adapt the shared RGB image and configured entries to ModelClient.judge.

    The existing client owns HTTP, prompt generation, output validation and
    retries. Its path-based input is served by a temporary lossless PNG.
    """
    results = {}
    for entry in entries:
        request = ModelRequest(
            image_id=uuid4(),
            criteria=[
                ModelCriterion(
                    criterion_id=entry["criterion_id"],
                    name=entry["name"],
                    definition=entry["definition"],
                    evaluation_evidence=entry["evaluation_evidence"],
                    allowed_labels=entry["params"]["allowed_labels"],
                )
            ],
        )
        with TemporaryDirectory(prefix="brandlens-vlm-") as directory:
            path = Path(directory) / "standardized.png"
            image.save(path, format="PNG")
            result = client.judge(request, path)
        if len(result.criteria) != 1 or result.criteria[0].id != "B1":
            raise ValueError("Existing VLM client must return exactly one B1 judgment.")
        # Preserve B1 provenance inside the judgment; use the rubric ID as its
        # outer key. The existing scorer already accepts tone_label and B1.
        results[entry["criterion_id"]] = asdict(result.criteria[0])
    return results


def score_photo(
    image,
    configuration,
    vlm_client=None,
    *,
    subject_detector=None,
    subject_selector=None,
    filter_settings=None,
    standardization_settings=None,
):
    """Preprocess and score one loaded image using its configured components.

    Args:
        image: Caller-owned Pillow image, before preprocessing. Load it outside
            this function so uploaded and crawled images can use the same path.
        configuration: The (rubric, criteria) tuple from load_cv_config(). Load
            and validate it once outside an image-processing loop.
        vlm_client: An initialized client providing the existing
            judge(ModelRequest, image_path) interface and returning ModelResult. Required
            only when the JSON selects a VLM criterion; caller owns its lifecycle.
        subject_detector: Optional initialized detector with detect(image).
            It runs once when selected CV criteria need a subject region.
        subject_selector: Optional existing selector with select(detections).
            Defaults to SingleSubjectSelector when a detector is needed.
        filter_settings: Optional existing preprocessing geometry settings.
        standardization_settings: Optional existing RGB/sRGB/resize settings.

    Returns:
        tuple: (ImageScore, cv_results, vlm_results). Scores and weights come
            from the unchanged scorer; result dictionaries retain measurements
            and model judgments keyed by configured criterion ID.

    Raises:
        ConfigurationError: The selected configuration is incompatible with
            the current fixed-B1 VLM client.
        ValueError: A required VLM client is missing, preprocessing excludes
            the image, or a component returns incompatible adapter data.
        Existing preprocessing, detection, inference and scoring errors propagate.

    Notes:
        No configuration file is reread, no model is created, and no input image
        is closed or modified here. Only the new standardized image and temporary
        PNG are owned by this function. CV and VLM receive the same pixels.
        Missing/ambiguous subjects remain explicit unavailable CV results.
        VLM timeout/malformed-output fallback belongs to task 4.7, so ModelFailure
        propagates. This function does not implement API jobs or persistence.
    """
    rubric, criteria = configuration
    entries = [entry for entry in rubric["criteria"] if entry["method"] == "vlm"]
    for entry in entries:
        _check_vlm_entry(entry)
    if entries and vlm_client is None:
        raise ValueError("VLM client is required when the JSON selects a VLM criterion.")

    standardized = preprocess_image(image, filter_settings, standardization_settings)
    if standardized is None:
        raise ValueError("Image excluded by the preprocessor's geometry filter.")
    try:
        data = _make_cv_input(standardized, criteria, subject_detector, subject_selector)
        cv_results = {cid: criterion.analyze(data) for cid, criterion in criteria.items()}
        vlm_results = _run_vlm(standardized, entries, vlm_client)
    finally:
        standardized.close()

    scored = score_image(rubric, cv_results=cv_results, vlm_results=vlm_results)
    return scored, cv_results, vlm_results
