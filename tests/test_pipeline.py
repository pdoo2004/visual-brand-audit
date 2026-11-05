"""Worker integration boundaries: selection, preprocessing, and image ownership."""
from unittest.mock import Mock

import pytest
from PIL import Image

from brandlens import pipeline


@pytest.fixture
def components(monkeypatch):
    cv = Mock()
    cv.input_requirements.return_value = {}
    cv.analyze.return_value = {"measurements": {"example": 10}}
    subject = Mock()
    subject.input_requirements.return_value = {"reliable_subject_region": True}
    rubric = {"criteria": [
        {"criterion_id": "brightness", "method": "cv"},
        {"criterion_id": "subject", "method": "cv"},
        {"criterion_id": "tone_approachability", "method": "vlm",
         "settings": {"target_tone": "premium"}},
    ]}
    scoring = Mock(return_value=object())
    model_run = Mock(return_value={"tone_approachability": {"fit_score": 4}})
    preprocessing = Mock(side_effect=AssertionError("Preprocessing repeated"))
    monkeypatch.setattr(pipeline, "score_image", scoring)
    monkeypatch.setattr(pipeline, "_run_vlm", model_run)
    monkeypatch.setattr(pipeline, "preprocess_image", preprocessing)
    return (rubric, {"brightness": cv, "subject": subject}), scoring, model_run, preprocessing


def test_standardized_selection_skips_unselected_components_and_preserves_image(components):
    configuration, scoring, model_run, preprocessing = components
    detector = Mock()
    image = Image.new("RGB", (100, 100))
    before = image.tobytes()
    try:
        scored, cv, vlm = pipeline.score_standardized(
            image, configuration, criterion_ids=["brightness"], subject_detector=detector,
        )
        assert scored is scoring.return_value
        assert cv == {"brightness": configuration[1]["brightness"].analyze.return_value}
        assert vlm == model_run.return_value
        assert configuration[1]["brightness"].analyze.call_args.args[0].image is image
        configuration[1]["subject"].analyze.assert_not_called()
        detector.detect.assert_not_called()
        preprocessing.assert_not_called()
        model_run.assert_called_once_with(image, [], None)
        scoring.assert_called_once_with(
            configuration[0], cv_results=cv, vlm_results=vlm, criterion_ids=["brightness"],
        )
        assert image.tobytes() == before
    finally:
        image.close()


def test_vlm_only_does_not_run_cv(components):
    configuration, scoring, model_run, _ = components
    client = Mock()
    image = Image.new("RGB", (100, 100))
    try:
        _, cv, _ = pipeline.score_standardized(
            image, configuration, client, criterion_ids=["tone_approachability"],
        )
        assert cv == {}
        for criterion in configuration[1].values():
            criterion.analyze.assert_not_called()
        assert model_run.call_args.args[2] is client
        assert scoring.call_args.kwargs["criterion_ids"] == ["tone_approachability"]
    finally:
        image.close()


@pytest.mark.parametrize("selection", [[], ["missing"], ["brightness", "brightness"], "brightness"])
def test_invalid_selection_stops_components(components, selection):
    configuration, scoring, model_run, preprocessing = components
    with pytest.raises((TypeError, ValueError)):
        pipeline.score_standardized(None, configuration, criterion_ids=selection)
    scoring.assert_not_called()
    model_run.assert_not_called()
    preprocessing.assert_not_called()


def test_non_rgb_input_is_rejected_without_conversion(components):
    configuration, scoring, _, preprocessing = components
    image = Image.new("L", (100, 100))
    try:
        with pytest.raises(ValueError, match="standardized"):
            pipeline.score_standardized(image, configuration, criterion_ids=["brightness"])
        assert image.getpixel((0, 0)) == 0
        preprocessing.assert_not_called()
        scoring.assert_not_called()
    finally:
        image.close()


def test_standardized_failure_does_not_close_borrowed_image(components):
    configuration, scoring, _, _ = components
    configuration[1]["brightness"].analyze.side_effect = RuntimeError("CV failed")
    image = Image.new("RGB", (100, 100))
    try:
        with pytest.raises(RuntimeError, match="CV failed"):
            pipeline.score_standardized(image, configuration, criterion_ids=["brightness"])
        assert image.getpixel((0, 0)) == (0, 0, 0)
        scoring.assert_not_called()
    finally:
        image.close()


@pytest.mark.parametrize("fails", [False, True])
def test_raw_wrapper_preprocesses_once_and_closes_only_owned_image(components, monkeypatch, fails):
    configuration, _, _, preprocessing = components
    raw = Image.new("RGB", (100, 100))
    standardized = raw.copy()
    preprocessing.side_effect = None
    preprocessing.return_value = standardized
    analysis = Mock(return_value=(object(), {}, {}))
    if fails:
        analysis.side_effect = RuntimeError("Analysis failed")
    monkeypatch.setattr(pipeline, "score_standardized", analysis)
    try:
        if fails:
            with pytest.raises(RuntimeError, match="Analysis failed"):
                pipeline.score_photo(raw, configuration, criterion_ids=["brightness"])
        else:
            assert pipeline.score_photo(raw, configuration, criterion_ids=["brightness"]) is analysis.return_value
        preprocessing.assert_called_once_with(raw, None, None)
        assert analysis.call_args.args[0] is standardized
        assert analysis.call_args.kwargs["criterion_ids"] == ["brightness"]
        with pytest.raises(ValueError, match="closed"):
            standardized.getpixel((0, 0))
        assert raw.getpixel((0, 0)) == (0, 0, 0)
    finally:
        raw.close()
        standardized.close()


def test_filtered_out_image_does_not_reach_analysis(components, monkeypatch):
    configuration, _, _, preprocessing = components
    preprocessing.side_effect = None
    preprocessing.return_value = None
    analysis = Mock()
    monkeypatch.setattr(pipeline, "score_standardized", analysis)
    with pytest.raises(ValueError, match="geometry"):
        pipeline.score_photo(None, configuration)
    analysis.assert_not_called()
