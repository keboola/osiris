"""Tests for fingerprinting utilities."""

from osiris.core.fingerprint import (
    combine_fingerprints,
    compute_fingerprint,
    fingerprint_dict,
    verify_fingerprint,
)


class TestComputeFingerprint:
    def test_string_input(self):
        """Fingerprint from string."""
        fp = compute_fingerprint("hello world")
        assert fp.startswith("sha256:")
        assert len(fp) == 71  # "sha256:" + 64 hex chars

    def test_bytes_input(self):
        """Fingerprint from bytes."""
        fp = compute_fingerprint(b"hello world")
        assert fp.startswith("sha256:")

    def test_deterministic(self):
        """Same input produces same fingerprint."""
        fp1 = compute_fingerprint("test data")
        fp2 = compute_fingerprint("test data")
        assert fp1 == fp2

    def test_different_inputs(self):
        """Different inputs produce different fingerprints."""
        fp1 = compute_fingerprint("data1")
        fp2 = compute_fingerprint("data2")
        assert fp1 != fp2

    def test_empty_input(self):
        """Empty input has valid fingerprint."""
        fp = compute_fingerprint("")
        assert fp.startswith("sha256:")


class TestCombineFingerprints:
    def test_combine_multiple(self):
        """Combine multiple fingerprints."""
        fp1 = compute_fingerprint("data1")
        fp2 = compute_fingerprint("data2")

        combined = combine_fingerprints([fp1, fp2])
        assert combined.startswith("sha256:")

    def test_order_independent(self):
        """Combined fingerprint is order-independent due to sorting."""
        fp1 = compute_fingerprint("data1")
        fp2 = compute_fingerprint("data2")
        fp3 = compute_fingerprint("data3")

        combined1 = combine_fingerprints([fp1, fp2, fp3])
        combined2 = combine_fingerprints([fp3, fp1, fp2])

        assert combined1 == combined2

    def test_single_fingerprint(self):
        """Single fingerprint combines correctly."""
        fp = compute_fingerprint("data")
        combined = combine_fingerprints([fp])

        # Should be fingerprint of the single fingerprint
        assert combined != fp  # Not the same as input
        assert combined.startswith("sha256:")


class TestFingerprintDict:
    def test_dict_fingerprints(self):
        """Compute fingerprints for dictionary values."""
        data = {"key1": "value1", "key2": {"nested": "value2"}, "key3": [1, 2, 3]}

        fps = fingerprint_dict(data)

        assert len(fps) == 3
        assert all(fp.startswith("sha256:") for fp in fps.values())
        assert fps["key1"] != fps["key2"]
        assert fps["key2"] != fps["key3"]

    def test_deterministic_dict(self):
        """Dictionary fingerprints are deterministic."""
        data = {"z": 1, "a": 2}

        fps1 = fingerprint_dict(data)
        fps2 = fingerprint_dict(data)

        assert fps1 == fps2


class TestVerifyFingerprint:
    def test_verify_valid(self):
        """Verify correct fingerprint."""
        data = "test data"
        fp = compute_fingerprint(data)

        assert verify_fingerprint(data, fp) is True

    def test_verify_invalid(self):
        """Verify incorrect fingerprint."""
        data = "test data"
        wrong_fp = "sha256:0000000000000000000000000000000000000000000000000000000000000000"

        assert verify_fingerprint(data, wrong_fp) is False

    def test_verify_bytes(self):
        """Verify fingerprint of bytes."""
        data = b"binary data"
        fp = compute_fingerprint(data)

        assert verify_fingerprint(data, fp) is True
