"""Unit tests for cfg materialization in execution adapters.

Tests that cfg files are properly materialized from compile to run sessions.
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from osiris.core.execution_adapter import ExecutionContext
from osiris.runtime.local_adapter import LocalAdapter


class TestLocalCfgMaterialization:
    """Test cfg materialization in LocalAdapter."""

    def test_cfg_materialization_local(self):
        """Test that LocalAdapter materializes cfg files to run session."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir)

            # Create a fake compile session with cfg files
            compile_dir = base_dir / "compile_123"
            compiled_dir = compile_dir / "compiled"
            cfg_dir = compiled_dir / "cfg"
            cfg_dir.mkdir(parents=True)

            # Create sample cfg files
            cfg_files = {
                "cfg/extract-data.json": {"query": "SELECT * FROM users"},
                "cfg/write-output.json": {"path": "output.csv"},
            }

            for cfg_path, cfg_content in cfg_files.items():
                cfg_file = compiled_dir / cfg_path
                cfg_file.parent.mkdir(parents=True, exist_ok=True)
                with open(cfg_file, "w") as f:
                    json.dump(cfg_content, f)

            # Create manifest with cfg references
            manifest = {
                "meta": {"generated_at": "2025-01-01T00:00:00Z"},
                "pipeline": {"id": "test-pipeline"},
                "steps": [
                    {
                        "id": "extract",
                        "cfg_path": "cfg/extract-data.json",
                        "driver": "test.extractor",
                    },
                    {"id": "write", "cfg_path": "cfg/write-output.json", "driver": "test.writer"},
                ],
                "metadata": {"source_manifest_path": str(compiled_dir / "manifest.yaml")},
            }

            # Create execution context
            context = ExecutionContext("run_456", base_dir)

            # The actual run_dir is created by ExecutionContext
            run_dir = context.logs_dir  # This will be base_dir / "logs" / "run_456"
            run_dir.mkdir(parents=True, exist_ok=True)

            # Execute prepare phase
            adapter = LocalAdapter()
            prepared = adapter.prepare(manifest, context)

            # Mock execute to trigger cfg materialization
            with patch("osiris.runtime.local_adapter.RunnerV0") as MockRunner:
                mock_runner = MagicMock()
                mock_runner.run.return_value = True
                MockRunner.return_value = mock_runner

                try:
                    adapter.execute(prepared, context)
                except Exception as e:
                    # Cfg materialization should happen before runner execution
                    # So we can ignore runner-related errors
                    print(f"Expected error after materialization: {e}")

            # Verify cfg files were materialized
            run_cfg_dir = run_dir / "cfg"
            assert run_cfg_dir.exists()

            for cfg_name in ["extract-data.json", "write-output.json"]:
                cfg_file = run_cfg_dir / cfg_name
                assert cfg_file.exists(), f"Expected {cfg_file} to be materialized"

                # Verify content matches
                with open(cfg_file) as f:
                    materialized = json.load(f)
                    original_path = f"cfg/{cfg_name}"
                    assert materialized == cfg_files[original_path]

    def test_cfg_materialization_missing_cfg_error(self):
        """Test that missing cfg files raise a friendly error."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir)

            # Create compile dir WITHOUT cfg files
            compile_dir = base_dir / "compile_123"
            compiled_dir = compile_dir / "compiled"
            compiled_dir.mkdir(parents=True)

            # Create manifest referencing non-existent cfg
            manifest = {
                "meta": {"generated_at": "2025-01-01T00:00:00Z"},
                "pipeline": {"id": "test-pipeline"},
                "steps": [
                    {"id": "extract", "cfg_path": "cfg/missing.json", "driver": "test.extractor"},
                ],
                "metadata": {"source_manifest_path": str(compiled_dir / "manifest.yaml")},
            }

            # Create execution context
            context = ExecutionContext("run_456", base_dir)
            run_dir = context.logs_dir
            run_dir.mkdir(parents=True, exist_ok=True)

            # Execute prepare phase
            adapter = LocalAdapter()
            prepared = adapter.prepare(manifest, context)

            # Attempt execute - should fail with helpful message
            from osiris.core.execution_adapter import ExecuteError

            with pytest.raises(ExecuteError) as exc_info:
                adapter.execute(prepared, context)

            error_msg = str(exc_info.value)
            assert "Missing configuration files required by manifest" in error_msg
            assert "cfg/missing.json" in error_msg
            assert "PreparedRun cfg_index" in error_msg

    def test_cfg_materialization_no_source_error(self):
        """Test that missing source location raises appropriate error."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir)

            # Create manifest WITHOUT source_manifest_path
            manifest = {
                "meta": {"generated_at": "2025-01-01T00:00:00Z"},
                "pipeline": {"id": "test-pipeline"},
                "steps": [
                    {"id": "extract", "cfg_path": "cfg/extract.json", "driver": "test.extractor"},
                ],
                # No metadata with source path
            }

            # Create execution context
            context = ExecutionContext("run_456", base_dir)
            run_dir = context.logs_dir
            run_dir.mkdir(parents=True, exist_ok=True)

            # Execute prepare phase
            adapter = LocalAdapter()
            prepared = adapter.prepare(manifest, context)

            # Mock that no compile dirs exist
            with patch("osiris.runtime.local_adapter.Path.glob") as mock_glob:
                mock_glob.return_value = []

                # Attempt execute - should fail with helpful message
                from osiris.core.execution_adapter import ExecuteError

                with pytest.raises(ExecuteError) as exc_info:
                    adapter.execute(prepared, context)

                error_msg = str(exc_info.value)
                assert "Cannot find source location for cfg files" in error_msg
                assert "Ensure compilation was successful" in error_msg


class TestE2BCfgMaterialization:
    """Test cfg inclusion in E2B payloads."""

    def test_e2b_payload_includes_cfg(self):
        """Test that E2B payload builder includes cfg files."""
        from osiris.remote.e2b_pack import PayloadBuilder

        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir)

            # Create compile session with cfg
            compile_dir = base_dir / "compile_123"
            compiled_dir = compile_dir / "compiled"
            cfg_dir = compiled_dir / "cfg"
            cfg_dir.mkdir(parents=True)

            # Create cfg files
            cfg_file = cfg_dir / "extract.json"
            with open(cfg_file, "w") as f:
                json.dump({"query": "SELECT 1"}, f)

            # Create manifest
            manifest = {
                "pipeline": {"id": "test"},
                "steps": [
                    {"id": "extract", "cfg_path": "cfg/extract.json"},
                ],
            }

            manifest_path = compiled_dir / "manifest.yaml"
            with open(manifest_path, "w") as f:
                yaml.dump(manifest, f)

            # Build payload
            build_dir = base_dir / "build"
            builder = PayloadBuilder(compile_dir, build_dir)

            from osiris.remote.e2b_pack import RunConfig

            run_config = RunConfig()

            payload_path = builder.build(manifest_path, run_config)

            # Verify payload was created
            assert payload_path.exists()

            # Extract and check contents
            import tarfile

            with tarfile.open(payload_path, "r:gz") as tar:
                members = tar.getnames()

                # Check cfg file is included
                assert "cfg/extract.json" in members

                # Extract and verify content
                cfg_member = tar.getmember("cfg/extract.json")
                cfg_content = tar.extractfile(cfg_member).read()
                cfg_data = json.loads(cfg_content)
                assert cfg_data["query"] == "SELECT 1"

    def test_e2b_payload_missing_cfg_error(self):
        """Test that missing cfg files fail payload build with clear error."""
        from osiris.remote.e2b_pack import PayloadBuilder

        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir)

            # Create compile dir WITHOUT cfg file
            compile_dir = base_dir / "compile_123"
            compiled_dir = compile_dir / "compiled"
            compiled_dir.mkdir(parents=True)

            # Create manifest referencing non-existent cfg
            manifest = {
                "pipeline": {"id": "test"},
                "steps": [
                    {"id": "extract", "cfg_path": "cfg/missing.json"},
                ],
            }

            manifest_path = compiled_dir / "manifest.yaml"
            with open(manifest_path, "w") as f:
                yaml.dump(manifest, f)

            # Attempt to build payload
            build_dir = base_dir / "build"
            builder = PayloadBuilder(compile_dir, build_dir)

            from osiris.remote.e2b_pack import RunConfig

            run_config = RunConfig()

            # Should fail with clear error
            with pytest.raises(ValueError) as exc_info:
                builder.build(manifest_path, run_config)

            error_msg = str(exc_info.value)
            assert "Missing cfg files referenced by manifest" in error_msg
            assert "cfg/missing.json" in error_msg
