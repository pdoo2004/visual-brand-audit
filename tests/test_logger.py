
"""Tests for pipeline instrumentation."""

import logging

import pytest

from brandlens.logger import track_stage


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
