"""SHA-256 fingerprinting utilities."""

import hashlib
from typing import Any


def compute_fingerprint(data: str | bytes) -> str:
    """
    Compute SHA-256 fingerprint of data.

    Args:
        data: String or bytes to fingerprint

    Returns:
        Hex-encoded SHA-256 digest
    """
    if isinstance(data, str):
        data = data.encode("utf-8")

    hasher = hashlib.sha256()
    hasher.update(data)
    return f"sha256:{hasher.hexdigest()}"


def combine_fingerprints(fingerprints: list[str]) -> str:
    """
    Combine multiple fingerprints into a single one.

    Args:
        fingerprints: List of fingerprint strings

    Returns:
        Combined fingerprint
    """
    # Sort for determinism
    sorted_fps = sorted(fingerprints)
    combined = "\n".join(sorted_fps)
    return compute_fingerprint(combined)


def fingerprint_dict(data: dict[str, Any]) -> dict[str, str]:
    """
    Compute fingerprints for a dictionary's values.

    Args:
        data: Dictionary with string keys

    Returns:
        Dictionary mapping keys to their fingerprints
    """
    from .canonical import canonical_bytes

    result = {}
    for key in sorted(data.keys()):
        value_bytes = canonical_bytes(data[key], format="json")
        result[key] = compute_fingerprint(value_bytes)

    return result


def verify_fingerprint(data: str | bytes, expected_fp: str) -> bool:
    """
    Verify that data matches expected fingerprint.

    Args:
        data: Data to verify
        expected_fp: Expected fingerprint

    Returns:
        True if fingerprint matches
    """
    actual_fp = compute_fingerprint(data)
    return actual_fp == expected_fp
