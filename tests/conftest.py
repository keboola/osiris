"""Shared test fixtures."""

import pytest


@pytest.fixture
def cfng_base_url() -> str:
    """Base URL used by cf-ng client tests. Overridden by OSIRIS_TEST_CFNG_URL when live."""
    import os

    return os.environ.get("OSIRIS_TEST_CFNG_URL", "https://cfng.test")
