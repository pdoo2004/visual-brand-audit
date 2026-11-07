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
    
    
def _check_vlm_entry(entry):
    """Check that the brand configuration matches the current VLM behavior."""
    # The existing client evaluates B1 only. The brand JSON uses
    # "tone_approachability" as the corresponding criterion ID.
    cid = entry["criterion_id"]
    if cid != "tone_approachability":
        raise ConfigurationError(
            f"Existing VLM client does not support criterion {cid}."
        )

    target = entry["settings"].get("target_tone")

    if not isinstance(target, str):
        raise ConfigurationError(
            f"{cid}: settings.target_tone must be comma-separated text."
        )

    supported = {word.strip().casefold() for word in RECOMMENDED_TONES}
    target_words = {word.strip().casefold() for word in target.split(",")}

    if "" in target_words:
        raise ConfigurationError(
            f"{cid}: target_tone must contain at least one tone "
            "and no empty comma-separated items."
        )

    # Accept any nonempty subset of the recommended tones.
    unsupported = target_words - supported
    if unsupported:
        raise ConfigurationError(
            f"{cid}: unsupported target tones: "
            f"{', '.join(sorted(unsupported))}."
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
                    allowed_labels=RECOMMENDED_TONES,  # for now allowed_labels is recommended labels
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


def score_standardized_image(
    image,
    configuration,
    vlm_client=None,
    *,
    criterion_ids=None,
    subject_detector=None,
    subject_selector=None,
):
    """Analyze and score a borrowed, already-standardized RGB/sRGB image.

    Args:
        image: Preprocessed Pillow image owned by the caller. This function
            does not filter, standardize, resize, save a persistent PNG, or
            close it. RGB mode is checked; sRGB provenance is the caller's
            responsibility.
        configuration: Loaded (rubric, criteria) tuple from load_cv_config().
        vlm_client: Initialized judge(request, image_path) client when needed.
        criterion_ids: Selected rubric IDs, or None to run all. An explicit
            selection must be nonempty, unique, and contain known IDs.
        subject_detector: Optional initialized detector for selected criteria.
        subject_selector: Optional selector; defaults to SingleSubjectSelector.

    Returns:
        tuple: (ImageScore, cv_results, vlm_results) for the selected criteria.

    Raises:
        ValueError: Selection is invalid, a required client is absent, or an
            image/component result is incompatible.
        Existing configuration, detection, inference and scoring errors propagate.

    Notes:
        Only selected components run, and scoring receives the same selection.
        The VLM's temporary PNG is removed on failure or success. Its existing
        path-based client still needs that temporary file; preprocessing is
        not repeated. Model failures propagate under the existing policy.
    """
    rubric, criteria = configuration
    by_id = {entry["criterion_id"]: entry for entry in rubric["criteria"]}
    if isinstance(criterion_ids, (str, bytes)):
        raise TypeError("criterion_ids must be a sequence of criterion IDs.")
    selected_ids = list(by_id) if criterion_ids is None else list(criterion_ids)
    if not selected_ids:
        raise ValueError("criterion_ids must list at least one criterion.")
    if len(set(selected_ids)) != len(selected_ids):
        raise ValueError("criterion_ids must not repeat a criterion.")
    unknown = set(selected_ids) - set(by_id)
    if unknown:
        raise ValueError(f"Unknown criterion ids: {', '.join(sorted(unknown))}")

    selected_cv = {
        cid: criteria[cid] for cid in selected_ids if by_id[cid]["method"] == "cv"
    }
    selected_vlm = [by_id[cid] for cid in selected_ids if by_id[cid]["method"] == "vlm"]
    for entry in selected_vlm:
        _check_vlm_entry(entry)
    if selected_vlm and vlm_client is None:
        raise ValueError("VLM client is required when the JSON selects a VLM criterion.")

    data = _make_cv_input(image, selected_cv, subject_detector, subject_selector)
    cv_results = {cid: criterion.analyze(data) for cid, criterion in selected_cv.items()}
    vlm_results = _run_vlm(image, selected_vlm, vlm_client)
    scored = score_image(
        rubric, cv_results=cv_results, vlm_results=vlm_results,
        criterion_ids=selected_ids,
    )
    return scored, cv_results, vlm_results


def score_photo(
    image,
    configuration,
    vlm_client=None,
    *,
    criterion_ids=None,
    subject_detector=None,
    subject_selector=None,
    filter_settings=None,
    standardization_settings=None,
):
    """Preprocess a raw Pillow image, then call score_standardized_image().

    Args:
        image: Caller-owned image loaded outside this function.
        configuration: Loaded (rubric, criteria) tuple.
        vlm_client: Initialized model client, required for selected VLM entries.
        criterion_ids: Optional subset of rubric criterion IDs to execute.
        subject_detector: Optional initialized subject detector.
        subject_selector: Optional subject selector.
        filter_settings: Optional geometry-filter settings.
        standardization_settings: Optional RGB/sRGB/resize settings.

    Returns:
        tuple: (ImageScore, cv_results, vlm_results).

    Raises:
        ValueError: Preprocessing excludes the image.
        Exceptions from preprocessing or score_standardized() propagate.

    Notes:
        The caller owns the original image and initialized components. Only
        the newly preprocessed image is owned and closed by this wrapper.
        Workers that already preprocess must call score_standardized() directly.
    """
    standardized = preprocess_image(image, filter_settings, standardization_settings)
    if standardized is None:
        raise ValueError("Image excluded by the preprocessor's geometry filter.")
    try:
        return score_standardized_image(
            standardized, configuration, vlm_client,
            criterion_ids=criterion_ids,
            subject_detector=subject_detector,
            subject_selector=subject_selector,
        )
    finally:
        standardized.close()

