"""Tests for step naming utilities."""

from osiris.core.step_naming import build_dataframe_keys, sanitize_step_id


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


# Tests for build_dataframe_keys function


def test_build_dataframe_keys_empty_list():
    """Empty list should return empty dict."""
    assert build_dataframe_keys([]) == {}


def test_build_dataframe_keys_single_id_no_collision():
    """Single step ID with no collision should use simple key."""
    result = build_dataframe_keys(["extract-movies"])
    assert result == {"extract-movies": "df_extract_movies"}


def test_build_dataframe_keys_multiple_ids_no_collision():
    """Multiple step IDs with no collisions should use simple keys."""
    result = build_dataframe_keys(["extract-movies", "extract-reviews"])
    assert result == {
        "extract-movies": "df_extract_movies",
        "extract-reviews": "df_extract_reviews",
    }


def test_build_dataframe_keys_collision_hyphen_vs_underscore():
    """Step IDs that collide after sanitization should get hash suffixes.

    This tests the critical bug fix: when "extract-movies" and "extract_movies"
    collide, both should get unique hash suffixes, not raise KeyError.
    """
    result = build_dataframe_keys(["extract-movies", "extract_movies"])

    # Both keys should exist
    assert "extract-movies" in result
    assert "extract_movies" in result

    # Both should start with df_extract_movies
    assert result["extract-movies"].startswith("df_extract_movies_")
    assert result["extract_movies"].startswith("df_extract_movies_")

    # They should be different
    assert result["extract-movies"] != result["extract_movies"]

    # Both should have 8-char hex suffix (SHA256[:8])
    suffix1 = result["extract-movies"].split("_")[-1]
    suffix2 = result["extract_movies"].split("_")[-1]
    assert len(suffix1) == 8 and all(c in "0123456789abcdef" for c in suffix1)
    assert len(suffix2) == 8 and all(c in "0123456789abcdef" for c in suffix2)


def test_build_dataframe_keys_collision_digit_prefix():
    """Step IDs that become identical after sanitization should get hash suffixes."""
    # "movies-1" and "movies_1" both sanitize to "movies_1"
    result = build_dataframe_keys(["movies-1", "movies_1"])

    # Both keys should exist
    assert "movies-1" in result
    assert "movies_1" in result

    # Both should have hash suffixes to distinguish them
    assert result["movies-1"].startswith("df_movies_1_")
    assert result["movies_1"].startswith("df_movies_1_")

    # They should be different
    assert result["movies-1"] != result["movies_1"]


def test_build_dataframe_keys_multiple_collisions():
    """Multiple sets of collisions should each get unique hashes."""
    result = build_dataframe_keys([
        "extract-movies",
        "extract_movies",
        "extract.reviews",
        "extract-reviews",
    ])

    # All keys should exist
    assert len(result) == 4
    assert all(key in result for key in [
        "extract-movies",
        "extract_movies",
        "extract.reviews",
        "extract-reviews",
    ])

    # extract-movies and extract_movies collide → should have hash suffixes
    # Both should have format: df_extract_movies_<8-hex-chars>
    assert result["extract-movies"].startswith("df_extract_movies_")
    assert result["extract_movies"].startswith("df_extract_movies_")

    # Verify hash suffix is exactly 8 hex chars
    suffix1 = result["extract-movies"].rsplit("_", 1)[-1]
    suffix2 = result["extract_movies"].rsplit("_", 1)[-1]
    assert len(suffix1) == 8 and all(c in "0123456789abcdef" for c in suffix1)
    assert len(suffix2) == 8 and all(c in "0123456789abcdef" for c in suffix2)

    # extract.reviews and extract-reviews collide → should have hash suffixes
    assert result["extract.reviews"].startswith("df_extract_reviews_")
    assert result["extract-reviews"].startswith("df_extract_reviews_")

    suffix3 = result["extract.reviews"].rsplit("_", 1)[-1]
    suffix4 = result["extract-reviews"].rsplit("_", 1)[-1]
    assert len(suffix3) == 8 and all(c in "0123456789abcdef" for c in suffix3)
    assert len(suffix4) == 8 and all(c in "0123456789abcdef" for c in suffix4)

    # All should be unique
    values = list(result.values())
    assert len(values) == len(set(values))
