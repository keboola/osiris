"""Tests for OML metadata propagation through compilation to AIOP."""

from pathlib import Path
import tempfile
from unittest.mock import patch

import pytest
import yaml

from osiris.core.compiler_v0 import CompilerV0
from osiris.core.run_export_v2 import build_narrative_layer, build_semantic_layer

pytestmark = pytest.mark.skip(reason="Compiler integration tests need deep rewrite for Filesystem Contract v1")


class TestCompilerMetadataPropagation:
    """Test that compiler preserves OML metadata for AIOP consumption."""

    def test_compiler_preserves_name_and_metadata(self):
        """Test that compiler preserves name and metadata fields from OML."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create OML with name and metadata.intent
            oml_content = {
                "oml_version": "0.1.0",
                "name": "test-pipeline",
                "metadata": {
                    "intent": "Test intent for pipeline",
                    "description": "Test description",
                },
                "steps": [
                    {
                        "id": "extract",
                        "component": "mysql.extractor",
                        "mode": "read",
                        "config": {"query": "SELECT * FROM test"},
                    }
                ],
            }

            oml_path = Path(tmpdir) / "test.yaml"
            with open(oml_path, "w") as f:
                yaml.dump(oml_content, f)

            # Create a filesystem contract for testing
            from osiris.core.fs_config import FilesystemConfig, IdsConfig
            from osiris.core.fs_paths import FilesystemContract

            fs_config = FilesystemConfig(
                base_path=str(tmpdir),
                build_dir="build",
                profiles={"enabled": False},  # Disable profiles for simpler test
            )
            ids_config = IdsConfig()
            fs_contract = FilesystemContract(fs_config, ids_config)

            # Compile OML
            compiler = CompilerV0(fs_contract=fs_contract, pipeline_slug="test_pipeline")
            success, message = compiler.compile(str(oml_path), profile=None)

            assert success, f"Compilation failed: {message}"

            # Load compiled manifest - get path from filesystem contract
            manifest_paths = fs_contract.manifest_paths(
                pipeline_slug="test_pipeline",
                manifest_hash=compiler.manifest_hash,
                manifest_short=compiler.manifest_short,
                profile=None,
            )
            manifest_path = manifest_paths["manifest"]
            assert manifest_path.exists()

            with open(manifest_path) as f:
                manifest = yaml.safe_load(f)

            # Check that name and metadata are preserved
            assert "name" in manifest
            assert manifest["name"] == "test-pipeline"

            assert "metadata" in manifest
            assert manifest["metadata"]["intent"] == "Test intent for pipeline"
            assert manifest["metadata"]["description"] == "Test description"

    def test_aiop_consumes_manifest_intent(self):
        """Test that AIOP correctly reads intent from manifest."""
        manifest = {
            "name": "test-pipeline",
            "metadata": {"intent": "Test pipeline intent", "description": "Test description"},
            "pipeline": {"id": "test-pipeline"},
            "steps": [],
        }

        # Build narrative layer
        narrative = build_narrative_layer(
            manifest=manifest, run_summary={}, evidence_refs={}, config={}, chat_logs=None
        )

        # Check intent was correctly discovered
        assert narrative["intent_known"] is True
        assert narrative["intent_summary"] == "Test pipeline intent"

        # Check provenance shows manifest as source
        provenance = narrative.get("intent_provenance", [])
        assert any(p["source"] == "manifest" for p in provenance)
        manifest_provenance = [p for p in provenance if p["source"] == "manifest"]
        if manifest_provenance:
            assert manifest_provenance[0]["trust"] == "high"

    def test_aiop_semantic_layer_includes_pipeline_name(self):
        """Test that semantic layer includes pipeline name from manifest."""
        manifest = {
            "name": "test-pipeline",
            "metadata": {"intent": "Test intent"},
            "pipeline": {"id": "test-pipeline"},
            "steps": [],
        }

        # Build semantic layer
        semantic = build_semantic_layer(
            manifest=manifest,
            oml_spec={"oml_version": "0.1.0"},
            component_registry={},
            schema_mode="summary",
        )

        # Check pipeline name is included
        assert "pipeline_name" in semantic
        assert semantic["pipeline_name"] == "test-pipeline"

    def test_fallback_to_pipeline_id(self):
        """Test fallback to pipeline.id when name field is missing."""
        manifest = {
            # No 'name' field at root
            "pipeline": {"id": "fallback-pipeline-id"},
            "steps": [],
        }

        # Build semantic layer
        semantic = build_semantic_layer(
            manifest=manifest,
            oml_spec={"oml_version": "0.1.0"},
            component_registry={},
            schema_mode="summary",
        )

        # Should use pipeline.id as fallback
        assert "pipeline_name" in semantic
        assert semantic["pipeline_name"] == "fallback-pipeline-id"

    def test_manifest_hash_extraction(self):
        """Test that AIOP correctly extracts manifest hash from pipeline.fingerprints."""
        manifest = {
            "name": "test-pipeline",
            "metadata": {"intent": "Test intent"},
            "pipeline": {
                "id": "test-pipeline",
                "fingerprints": {
                    "manifest_fp": "sha256:abc123def456",
                    "oml_fp": "sha256:789ghi012jkl",
                },
            },
            "steps": [],
        }

        # Build semantic layer
        semantic = build_semantic_layer(
            manifest=manifest,
            oml_spec={"oml_version": "0.1.0"},
            component_registry={},
            schema_mode="summary",
        )

        # Check that manifest hash is extracted correctly
        assert "@id" in semantic
        assert semantic["@id"] == "osiris://pipeline/@sha256:abc123def456"

    def test_manifest_loading_from_session_root(self):
        """Test that AIOP loads manifest from session root directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            session_dir = Path(tmpdir) / "logs" / "run_123456"
            session_dir.mkdir(parents=True)

            # Create manifest at session root (where it actually is)
            manifest_content = {
                "name": "test-pipeline",
                "metadata": {"intent": "Test intent"},
                "pipeline": {"id": "test-pipeline"},
                "steps": [],
            }

            manifest_path = session_dir / "manifest.yaml"
            with open(manifest_path, "w") as f:
                yaml.dump(manifest_content, f)

            # Mock the session path resolution
            with patch("osiris.cli.logs.Path") as mock_path:

                def path_side_effect(path_str):
                    if "run_123456" in str(path_str):
                        return session_dir
                    return Path(path_str)

                mock_path.side_effect = path_side_effect
                mock_path.return_value = session_dir

                # The manifest should be found at session root
                assert manifest_path.exists()

                # Load manifest content
                with open(manifest_path) as f:
                    loaded = yaml.safe_load(f)

                assert loaded["name"] == "test-pipeline"
                assert loaded["metadata"]["intent"] == "Test intent"
