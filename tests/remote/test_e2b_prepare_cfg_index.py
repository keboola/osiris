"""Tests for E2B adapter cfg_index handling and payload building."""

import json
import tarfile
import tempfile
from pathlib import Path

import pytest
import yaml

from osiris.core.execution_adapter import ExecutionContext
from osiris.remote.e2b_adapter import E2BAdapter
from osiris.remote.e2b_pack import PayloadBuilder, RunConfig


class TestE2BPrepareCfgIndex:
    """Test E2B adapter prepare phase with cfg_index."""

    def test_e2b_prepare_builds_cfg_index(self):
        """Test that E2BAdapter.prepare() returns PreparedRun with non-empty cfg_index."""
        adapter = E2BAdapter()

        # Create a manifest with cfg references
        manifest = {
            "pipeline": {"id": "test-pipeline", "name": "test"},
            "steps": [
                {
                    "id": "extract-data",
                    "driver": "mysql.extractor",
                    "cfg_path": "cfg/extract-data.json",
                    "needs": [],
                },
                {
                    "id": "write-output",
                    "driver": "filesystem.csv_writer",
                    "cfg_path": "cfg/write-output.json",
                    "needs": ["extract-data"],
                },
            ],
            "metadata": {"fingerprint": "test-123"},
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            context = ExecutionContext("test_session", Path(temp_dir))

            # Prepare the run
            prepared = adapter.prepare(manifest, context)

            # Verify cfg_index was built
            assert prepared.cfg_index is not None
            assert len(prepared.cfg_index) == 2
            assert "cfg/extract-data.json" in prepared.cfg_index
            assert "cfg/write-output.json" in prepared.cfg_index

            # Verify cfg_index content
            extract_cfg = prepared.cfg_index["cfg/extract-data.json"]
            assert extract_cfg["id"] == "extract-data"
            assert extract_cfg["driver"] == "mysql.extractor"

            write_cfg = prepared.cfg_index["cfg/write-output.json"]
            assert write_cfg["id"] == "write-output"
            assert write_cfg["driver"] == "filesystem.csv_writer"

    def test_e2b_payload_contains_cfg_files(self):
        """Test that E2B payload tgz contains exactly the cfg files from cfg_index."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Create a compile directory structure with cfg files
            compile_dir = temp_path / "compile_test"
            compiled_dir = compile_dir / "compiled"
            cfg_dir = compiled_dir / "cfg"
            cfg_dir.mkdir(parents=True)

            # Create actual cfg files
            cfg1 = cfg_dir / "extract-data.json"
            cfg1.write_text(json.dumps({"query": "SELECT * FROM users"}))

            cfg2 = cfg_dir / "write-output.json"
            cfg2.write_text(json.dumps({"path": "./output.csv"}))

            # Create manifest
            manifest_data = {
                "pipeline": {"id": "test-pipeline"},
                "steps": [
                    {"id": "extract", "cfg_path": "cfg/extract-data.json"},
                    {"id": "write", "cfg_path": "cfg/write-output.json"},
                ],
            }

            manifest_path = compiled_dir / "manifest.yaml"
            with open(manifest_path, "w") as f:
                yaml.dump(manifest_data, f)

            # Build payload
            build_dir = temp_path / "build"
            build_dir.mkdir()

            builder = PayloadBuilder(compile_dir, build_dir)
            run_config = RunConfig()

            # Build with source cfg directory
            payload_path = builder.build(manifest_path, run_config, source_cfg_dir=cfg_dir)

            # Verify payload contains cfg files
            assert payload_path.exists()

            with tarfile.open(payload_path, "r:gz") as tar:
                members = tar.getnames()

                # Check cfg files are present
                assert "cfg/extract-data.json" in members
                assert "cfg/write-output.json" in members

                # Extract and verify content
                cfg1_member = tar.getmember("cfg/extract-data.json")
                cfg1_content = tar.extractfile(cfg1_member).read()
                assert json.loads(cfg1_content) == {"query": "SELECT * FROM users"}

                cfg2_member = tar.getmember("cfg/write-output.json")
                cfg2_content = tar.extractfile(cfg2_member).read()
                assert json.loads(cfg2_content) == {"path": "./output.csv"}

    def test_e2b_payload_missing_cfg_error(self):
        """Test that missing cfg files produce actionable error."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Create compile dir WITHOUT cfg files
            compile_dir = temp_path / "compile_test"
            compiled_dir = compile_dir / "compiled"
            compiled_dir.mkdir(parents=True)

            # Create manifest referencing non-existent cfg
            manifest_data = {
                "pipeline": {"id": "test-pipeline"},
                "steps": [
                    {"id": "extract", "cfg_path": "cfg/missing.json"},
                ],
            }

            manifest_path = compiled_dir / "manifest.yaml"
            with open(manifest_path, "w") as f:
                yaml.dump(manifest_data, f)

            # Try to build payload
            build_dir = temp_path / "build"
            build_dir.mkdir()

            builder = PayloadBuilder(compile_dir, build_dir)
            run_config = RunConfig()

            # Should raise with actionable error
            with pytest.raises(ValueError) as exc_info:
                builder.build(manifest_path, run_config)

            error_msg = str(exc_info.value)
            assert "Missing cfg files" in error_msg
            assert "cfg/missing.json" in error_msg
            assert (
                "E2B payload must include cfg/*" in error_msg
                or "ensure compilation created cfg files" in error_msg
            )
