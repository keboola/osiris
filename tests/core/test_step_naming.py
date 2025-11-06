"""Tests for step naming utilities."""

import pytest
from osiris.core.step_naming import sanitize_step_id


def test_sanitize_alphanumeric_unchanged():
    """Alphanumeric with underscores should pass through unchanged."""
    assert sanitize_step_id("extract_movies") == "extract_movies"
    assert sanitize_step_id("step123") == "step123"
    assert sanitize_step_id("my_step_name") == "my_step_name"


def test_sanitize_hyphens_to_underscores():
    """Hyphens should be replaced with underscores."""
    assert sanitize_step_id("extract-movies") == "extract_movies"
    assert sanitize_step_id("my-step-name") == "my_step_name"


def test_sanitize_dots_to_underscores():
    """Dots should be replaced with underscores."""
    assert sanitize_step_id("extract.movies") == "extract_movies"
    assert sanitize_step_id("step.1.2") == "step_1_2"


def test_sanitize_leading_digit():
    """Names starting with digits should be prefixed with underscore."""
    assert sanitize_step_id("123movies") == "_123movies"
    assert sanitize_step_id("1extract") == "_1extract"


def test_sanitize_mixed_invalid_chars():
    """Multiple types of invalid characters."""
    assert sanitize_step_id("extract-movies.v2") == "extract_movies_v2"
    assert sanitize_step_id("step@123#test") == "step_123_test"


def test_sanitize_empty_string():
    """Empty string should return empty string."""
    assert sanitize_step_id("") == ""
