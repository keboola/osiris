"""Integration test for multi-table joins in pipelines."""

import pytest


def test_movie_pipeline_two_extracts_one_join():
    """E2E test: Extract movies + reviews, join in DuckDB."""
    pytest.skip("TODO: Requires full pipeline execution with real movie OML")
    # This will be tested by re-running the actual failing movie pipeline
