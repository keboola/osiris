"""Fingerprints must be stable, prefixed, and enforceable."""

import pytest

from osiris.determinism.fingerprint import (
    FingerprintMismatch,
    combine_fingerprints,
    compute_fingerprint,
    require_fingerprint,
    verify_fingerprint,
)


def test_fingerprint_is_prefixed_and_64_hex():
    fp = compute_fingerprint("hello")
    assert fp.startswith("sha256:")
    assert len(fp) == len("sha256:") + 64


def test_str_and_bytes_agree():
    assert compute_fingerprint("hello") == compute_fingerprint(b"hello")


def test_combine_is_order_independent():
    a, b = compute_fingerprint("a"), compute_fingerprint("b")
    assert combine_fingerprints([a, b]) == combine_fingerprints([b, a])


def test_verify_accepts_matching_and_rejects_mutated():
    fp = compute_fingerprint("payload")
    assert verify_fingerprint("payload", fp) is True
    assert verify_fingerprint("payload!", fp) is False


def test_require_fingerprint_raises_on_mutation():
    """The guarantee test: a mutated artifact MUST abort, not warn."""
    fp = compute_fingerprint("payload")
    with pytest.raises(FingerprintMismatch) as exc:
        require_fingerprint("payload-tampered", fp)
    assert exc.value.expected == fp
    assert exc.value.actual == compute_fingerprint("payload-tampered")


def test_require_fingerprint_passes_when_intact():
    fp = compute_fingerprint("payload")
    require_fingerprint("payload", fp)
