"""Regression test: Ensure no manifest_hash in index contains algorithm prefix.

This test parses .osiris/index/runs.jsonl and all per-pipeline index files
to verify that no manifest_hash field contains a colon (':'), which would
indicate an algorithm prefix like 'sha256:'.

Per FilesystemContract specification (ADR-0028), manifest_hash must be
pure hex with no algorithm prefix.
"""

import json
from pathlib import Path

import pytest


def test_index_has_no_prefixed_hashes():
    """Regression test: parse index files and fail if any manifest_hash contains ':'."""
    # Check if index directory exists
    index_dir = Path(".osiris/index")

    if not index_dir.exists():
        pytest.skip("No .osiris/index directory found (clean workspace)")

    # Collect all JSONL files to check
    files_to_check = []

    # Main index
    main_index = index_dir / "runs.jsonl"
    if main_index.exists():
        files_to_check.append(main_index)

    # Per-pipeline indexes
    by_pipeline_dir = index_dir / "by_pipeline"
    if by_pipeline_dir.exists():
        files_to_check.extend(by_pipeline_dir.glob("*.jsonl"))

    if not files_to_check:
        pytest.skip("No index files found (no runs yet)")

    # Check each file
    prefixed_hashes_found = []

    for index_file in files_to_check:
        with open(index_file) as f:
            for line_num, line in enumerate(f, start=1):
                if not line.strip():
                    continue

                try:
                    record = json.loads(line)
                    manifest_hash = record.get("manifest_hash", "")

                    # Check for colon (indicates algorithm prefix)
                    if ":" in manifest_hash:
                        prefixed_hashes_found.append(
                            {
                                "file": str(index_file),
                                "line": line_num,
                                "run_id": record.get("run_id", "unknown"),
                                "manifest_hash": manifest_hash,
                            }
                        )
                except json.JSONDecodeError:
                    # Skip malformed lines
                    pass

    # Report findings
    if prefixed_hashes_found:
        error_msg = "Found manifest_hash with algorithm prefix (should be pure hex):\n"
        for finding in prefixed_hashes_found:
            error_msg += f"  {finding['file']}:{finding['line']} - run_id={finding['run_id']}, hash={finding['manifest_hash']}\n"  # noqa: E501
        error_msg += "\nRun migration script to fix: python scripts/migrate_index_manifest_hash.py --apply"

        pytest.fail(error_msg)


def test_latest_pointers_have_pure_hex():
    """Regression test: verify latest manifest pointers use pure hex hashes."""
    latest_dir = Path(".osiris/index/latest")

    if not latest_dir.exists():
        pytest.skip("No .osiris/index/latest directory found")

    pointer_files = list(latest_dir.glob("*.txt"))

    if not pointer_files:
        pytest.skip("No latest pointer files found")

    prefixed_hashes_found = []

    for pointer_file in pointer_files:
        with open(pointer_file) as f:
            lines = f.readlines()

        if len(lines) >= 2:
            manifest_hash = lines[1].strip()  # Line 2 is the hash

            if ":" in manifest_hash:
                prefixed_hashes_found.append(
                    {"file": str(pointer_file), "pipeline": pointer_file.stem, "manifest_hash": manifest_hash}
                )

    if prefixed_hashes_found:
        error_msg = "Found latest pointer with algorithm prefix:\n"
        for finding in prefixed_hashes_found:
            error_msg += f"  {finding['file']} - pipeline={finding['pipeline']}, hash={finding['manifest_hash']}\n"

        pytest.fail(error_msg)


def test_hash_normalization_helper_exists():
    """Ensure normalize_manifest_hash helper function is available."""
    from osiris.core.fs_paths import normalize_manifest_hash

    # Test basic functionality
    assert normalize_manifest_hash("sha256:abc123") == "abc123"
    assert normalize_manifest_hash("abc123") == "abc123"
    assert normalize_manifest_hash("sha256abc123") == "abc123"
    assert normalize_manifest_hash("") == ""
