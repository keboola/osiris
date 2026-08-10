"""SHA-256 fingerprinting with an enforceable check.

v0.5.4 computed fingerprints and never verified them. `require_fingerprint`
exists so that verification has a caller that aborts rather than warns.
"""

import hashlib


class FingerprintMismatch(Exception):
    """Raised when data does not match its recorded fingerprint."""

    def __init__(self, expected: str, actual: str) -> None:
        super().__init__(f"fingerprint mismatch: expected {expected}, got {actual}")
        self.expected = expected
        self.actual = actual


def compute_fingerprint(data: str | bytes) -> str:
    """SHA-256 of data, returned as 'sha256:<hex>'."""
    if isinstance(data, str):
        data = data.encode("utf-8")
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def combine_fingerprints(fingerprints: list[str]) -> str:
    """Order-independent combination of fingerprints."""
    return compute_fingerprint("\n".join(sorted(fingerprints)))


def verify_fingerprint(data: str | bytes, expected_fp: str) -> bool:
    """True when data matches expected_fp."""
    return compute_fingerprint(data) == expected_fp


def require_fingerprint(data: str | bytes, expected_fp: str) -> None:
    """Abort unless data matches expected_fp."""
    actual = compute_fingerprint(data)
    if actual != expected_fp:
        raise FingerprintMismatch(expected=expected_fp, actual=actual)
