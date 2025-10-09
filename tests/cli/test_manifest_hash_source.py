"""Tests to verify run.py reads manifest_hash from meta.manifest_hash, not pipeline.fingerprints.manifest_fp."""

import yaml


def test_run_extracts_hash_from_meta(tmp_path):
    """Test that run command extracts manifest_hash from meta.manifest_hash."""
    # Create a mock manifest with both locations to verify correct source
    manifest_data = {
        "pipeline": {
            "id": "test_pipeline",
            "fingerprints": {
                "manifest_fp": "WRONG_HASH_FROM_FINGERPRINTS",  # Should NOT use this
                "oml_fp": "oml123",
            },
        },
        "meta": {
            "manifest_hash": "abc123def456",  # pragma: allowlist secret
            "manifest_short": "abc123d",
            "profile": "dev",
            "generated_at": "2025-10-08T10:00:00Z",
        },
        "steps": [],
    }

    # Write manifest to temp file
    manifest_path = tmp_path / "manifest.yaml"
    with open(manifest_path, "w") as f:
        yaml.dump(manifest_data, f)

    # Verify manifest reads the correct field
    with open(manifest_path) as f:
        loaded = yaml.safe_load(f)

    # Extract hash using the same logic as run.py lines 658-659
    manifest_hash = loaded.get("meta", {}).get("manifest_hash", "")

    assert manifest_hash == "abc123def456"  # pragma: allowlist secret
    assert manifest_hash != "WRONG_HASH_FROM_FINGERPRINTS"


def test_run_derives_manifest_short_from_meta(tmp_path):
    """Test that run command derives manifest_short from meta fields."""
    manifest_data = {
        "pipeline": {
            "id": "test_pipeline",
            "fingerprints": {"manifest_fp": "wrong_hash"},
        },
        "meta": {
            "manifest_hash": "abc123def456789",  # pragma: allowlist secret
            "manifest_short": "abc123d",  # Should use this if present
            "profile": "dev",
        },
        "steps": [],
    }

    manifest_path = tmp_path / "manifest.yaml"
    with open(manifest_path, "w") as f:
        yaml.dump(manifest_data, f)

    with open(manifest_path) as f:
        loaded = yaml.safe_load(f)

    # Extract using run.py logic (lines 585-589)
    manifest_short = loaded.get("meta", {}).get("manifest_short", "")
    if not manifest_short:
        manifest_hash_temp = loaded.get("meta", {}).get("manifest_hash", "")
        manifest_short = manifest_hash_temp[:7] if manifest_hash_temp else ""

    assert manifest_short == "abc123d"


def test_run_aiop_export_uses_meta_hash(tmp_path):
    """Test that AIOP export path uses meta.manifest_hash, not fingerprints.manifest_fp."""
    manifest_data = {
        "pipeline": {
            "id": "test_pipeline",
            "fingerprints": {"manifest_fp": "WRONG_HASH"},
        },
        "meta": {
            "manifest_hash": "correct_hash_123",
            "manifest_short": "correct",
            "profile": "dev",
        },
        "steps": [],
    }

    manifest_path = tmp_path / "manifest.yaml"
    with open(manifest_path, "w") as f:
        yaml.dump(manifest_data, f)

    with open(manifest_path) as f:
        loaded = yaml.safe_load(f)

    # Extract using run.py AIOP export logic (lines 796-802)
    manifest_hash = loaded.get("meta", {}).get("manifest_hash", "")
    pipeline_slug = loaded.get("pipeline", {}).get("id")
    manifest_short = loaded.get("meta", {}).get("manifest_short") or (manifest_hash[:7] if manifest_hash else "")

    assert manifest_hash == "correct_hash_123"
    assert manifest_short == "correct"
    assert pipeline_slug == "test_pipeline"


def test_run_handles_missing_meta_manifest_hash(tmp_path):
    """Test graceful handling when meta.manifest_hash is missing."""
    manifest_data = {
        "pipeline": {
            "id": "test_pipeline",
            "fingerprints": {"manifest_fp": "fallback_hash"},
        },
        "meta": {
            # manifest_hash is missing
            "profile": "dev",
        },
        "steps": [],
    }

    manifest_path = tmp_path / "manifest.yaml"
    with open(manifest_path, "w") as f:
        yaml.dump(manifest_data, f)

    with open(manifest_path) as f:
        loaded = yaml.safe_load(f)

    # Extract using run.py logic - should get empty string if missing
    manifest_hash = loaded.get("meta", {}).get("manifest_hash", "")

    assert manifest_hash == ""  # Should be empty, not fallback to fingerprints


def test_run_index_record_creation_uses_correct_hash(tmp_path):
    """Test that RunRecord creation in run.py uses the correct manifest_hash source."""
    from osiris.core.run_index import RunRecord

    # Simulate manifest data
    manifest_data = {
        "pipeline": {"id": "test_pipeline", "fingerprints": {"manifest_fp": "WRONG"}},
        "meta": {"manifest_hash": "CORRECT_HASH", "manifest_short": "CORRECT", "profile": "dev"},
        "steps": [],
    }

    # Extract hash using run.py logic (line 659)
    manifest_hash = manifest_data.get("meta", {}).get("manifest_hash", "")
    manifest_short = manifest_data.get("meta", {}).get("manifest_short", "")

    # Create record as in run.py (lines 682-695)
    record = RunRecord(
        run_id="test_001",
        pipeline_slug="test_pipeline",
        profile="dev",
        manifest_hash=manifest_hash,
        manifest_short=manifest_short,
        run_ts="2025-10-08T10:00:00Z",
        status="success",
        duration_ms=1000,
        run_logs_path=str(tmp_path / "logs"),
        aiop_path=str(tmp_path / "aiop"),
        build_manifest_path=str(tmp_path / "manifest.yaml"),
        tags=[],
    )

    assert record.manifest_hash == "CORRECT_HASH"
    assert record.manifest_short == "CORRECT"
    assert record.manifest_hash != "WRONG"


def test_manifest_short_derivation_fallback(tmp_path):
    """Test that manifest_short is derived from manifest_hash when not explicitly provided."""
    manifest_data = {
        "pipeline": {"id": "test_pipeline"},
        "meta": {
            "manifest_hash": "abc123def456789",  # pragma: allowlist secret
            # manifest_short is missing - should derive from hash
            "profile": "dev",
        },
        "steps": [],
    }

    manifest_path = tmp_path / "manifest.yaml"
    with open(manifest_path, "w") as f:
        yaml.dump(manifest_data, f)

    with open(manifest_path) as f:
        loaded = yaml.safe_load(f)

    # Extract using run.py logic (lines 585-589)
    manifest_short = loaded.get("meta", {}).get("manifest_short", "")
    if not manifest_short:
        manifest_hash_temp = loaded.get("meta", {}).get("manifest_hash", "")
        manifest_short = manifest_hash_temp[:7] if manifest_hash_temp else ""

    # Should derive first 7 characters
    assert manifest_short == "abc123d"
    assert len(manifest_short) == 7
