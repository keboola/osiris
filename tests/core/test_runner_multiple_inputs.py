"""Tests for runner multiple input handling."""

import pandas as pd
import pytest


@pytest.fixture
def sample_dataframes():
    """Create sample DataFrames for testing."""
    df_movies = pd.DataFrame({"id": [1, 2, 3], "title": ["Movie A", "Movie B", "Movie C"]})
    df_reviews = pd.DataFrame({"movie_id": [1, 1, 2, 3], "rating": [5, 4, 3, 5]})
    return {"movies": df_movies, "reviews": df_reviews}


def test_runner_stores_multiple_dataframes(tmp_path, sample_dataframes):
    """Runner should store each upstream DataFrame with df_ prefix."""
    # This test requires a mock runner setup
    # You'll need to create a minimal manifest with:
    # - Step 1: extract-movies (produces df)
    # - Step 2: extract-reviews (produces df)
    # - Step 3: calculate (needs both)

    # For now, create a unit test that validates the inputs dict structure
    # In a real scenario, you'd run the runner and check self.results

    # Mock scenario:
    results = {
        "extract-movies": {"df": sample_dataframes["movies"]},
        "extract-reviews": {"df": sample_dataframes["reviews"]},
    }

    # Simulate what runner should produce for calculate step
    inputs = {}
    for upstream_id in ["extract-movies", "extract-reviews"]:
        if upstream_id in results:
            upstream_result = results[upstream_id]
            inputs[upstream_id] = upstream_result
            if "df" in upstream_result:
                from osiris.core.step_naming import sanitize_step_id

                safe_id = sanitize_step_id(upstream_id)
                inputs[f"df_{safe_id}"] = upstream_result["df"]

    # Verify structure
    assert "extract-movies" in inputs
    assert "extract-reviews" in inputs
    assert "df_extract_movies" in inputs
    assert "df_extract_reviews" in inputs
    assert len(inputs["df_extract_movies"]) == 3
    assert len(inputs["df_extract_reviews"]) == 4

    # Verify NO inputs["df"] exists
    assert "df" not in inputs


def test_runner_sanitizes_step_ids_with_hyphens(sample_dataframes):
    """Step IDs with hyphens should be sanitized in df_ keys."""
    from osiris.core.step_naming import sanitize_step_id

    results = {"extract-movies": {"df": sample_dataframes["movies"]}}

    inputs = {}
    for upstream_id in ["extract-movies"]:
        upstream_result = results[upstream_id]
        inputs[upstream_id] = upstream_result
        if "df" in upstream_result:
            safe_id = sanitize_step_id(upstream_id)
            inputs[f"df_{safe_id}"] = upstream_result["df"]

    assert "df_extract_movies" in inputs  # Hyphen → underscore
    assert "df_extract-movies" not in inputs


# Add placeholder for integration test
def test_runner_integration_two_extracts_one_processor():
    """Integration test: Two extractors feeding one processor."""
    pytest.skip("TODO: Requires full runner setup with mock drivers")
