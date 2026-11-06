"""Tests for pipeline instrumentation."""

import logging

import pytest

from brandlens.logger import (
    image_logging_context,
    log_image_event,
    track_current_stage,
    track_stage,
)


def test_successful_stage_logging(caplog):
    with caplog.at_level(logging.INFO, logger="brandlens.pipeline"):
        with track_stage("job-1", "img-1", "preprocessing"):
            pass

    assert "status=started" in caplog.text
    assert "status=completed" in caplog.text
    assert "duration_ms=" in caplog.text
    assert "job=job-1" in caplog.text
    assert "image=img-1" in caplog.text


def test_failed_stage_logging_is_private(caplog):
    secret = "/private/customer_photo.png"

    with caplog.at_level(logging.INFO, logger="brandlens.pipeline"):
        with pytest.raises(ValueError):
            with track_stage("job-2", "img-2", "brightness"):
                raise ValueError(f"Failed processing {secret}")

    assert "status=failed" in caplog.text
    assert "error_type=ValueError" in caplog.text
    assert secret not in caplog.text


def test_context_propagates_and_resets(caplog):
    with caplog.at_level(logging.INFO, logger="brandlens.pipeline"):
        with image_logging_context("job-abc", "image-123"):
            with track_current_stage("photo_filter"):
                pass
            log_image_event("photo_filter", "filtered_out", reason="too_small")
        with track_current_stage("should_not_log"):
            pass

    assert "job=job-abc image=image-123 stage=photo_filter" in caplog.text
    assert "status=filtered_out reason=too_small" in caplog.text
    assert "should_not_log" not in caplog.text


def test_outcome_does_not_log_untrusted_reason(caplog):
    private_path = "/private/users/client-name.png"
    with caplog.at_level(logging.INFO, logger="brandlens.pipeline"):
        with image_logging_context("job-a", "image-b"):
            log_image_event("photo_filter", "filtered_out", reason=private_path)
    assert "reason=other" in caplog.text
    assert private_path not in caplog.text
