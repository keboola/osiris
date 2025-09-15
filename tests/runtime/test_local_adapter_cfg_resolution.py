"""Tests for LocalAdapter cfg resolution and preflight validation logic."""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from osiris.core.execution_adapter import ExecuteError, ExecutionContext, PreparedRun
from osiris.runtime.local_adapter import LocalAdapter


class TestLocalAdapterCfgResolution:
    """Test LocalAdapter cfg file resolution with different scenarios."""

    def setup_method(self):
        """Set up test environment."""
        self.adapter = LocalAdapter()

    def create_test_manifest(self, tmp_path: Path, steps_count: int = 2) -> dict:
        """Create a test manifest with cfg file references."""
        manifest = {
            "metadata": {"fingerprint": "test123"},
            "pipeline": {"name": "test-pipeline", "id": "test-id"},
            "steps": [],
        }

        for i in range(steps_count):
            manifest["steps"].append(
                {"id": f"step-{i}", "cfg_path": f"cfg/step-{i}.json", "driver": "test.driver"}
            )

        return manifest

    def create_test_cfg_files(self, base_path: Path, count: int = 2) -> dict:
        """Create test cfg files and return cfg_index."""
        cfg_dir = base_path / "cfg"
        cfg_dir.mkdir(parents=True, exist_ok=True)

        cfg_index = {}
        for i in range(count):
            cfg_path = f"cfg/step-{i}.json"
            cfg_file = cfg_dir / f"step-{i}.json"
            cfg_content = {
                "component": "test.extractor",
                "connection": f"@mysql.test_{i}",
                "query": f"SELECT * FROM table_{i}",
            }
            cfg_file.write_text(json.dumps(cfg_content, indent=2))
            cfg_index[cfg_path] = cfg_content

        return cfg_index

    def create_test_connections_file(self, base_path: Path):
        """Create test osiris_connections.yaml file."""
        connections = {
            "connections": {
                "mysql": {
                    "test_0": {
                        "host": "localhost",
                        "password": "${MYSQL_PASSWORD}",
                        "database": "test",
                    },
                    "test_1": {
                        "host": "localhost",
                        "password": "${MYSQL_PASSWORD}",
                        "database": "test",
                    },
                }
            }
        }
        connections_file = base_path / "osiris_connections.yaml"
        with open(connections_file, "w") as f:
            yaml.dump(connections, f)

    def test_manifest_relative_cfg_resolution_success(self):
        """Test successful cfg resolution with --manifest execution."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)

            # Setup: manifest with compiled_root pointing to tmp_path
            manifest = self.create_test_manifest(tmp_path)
            self.create_test_cfg_files(tmp_path)

            # Create context
            context = ExecutionContext(session_id="test_session", base_path=tmp_path)

            # Set compiled_root to enable manifest-relative resolution
            # First prepare to set internal state
            manifest["metadata"]["source_manifest_path"] = str(
                tmp_path / "compiled" / "manifest.yaml"
            )
            prepared = self.adapter.prepare(manifest, context)

            # This should not raise an exception
            self.adapter._preflight_validate_cfg_files(prepared, context)

    def test_preflight_validation_missing_cfg_files(self):
        """Test preflight validation fails with missing cfg files."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)

            # Setup: manifest but NO cfg files created
            manifest = self.create_test_manifest(tmp_path)
            cfg_index = {
                "cfg/step-0.json": {"component": "test.extractor"},
                "cfg/step-1.json": {"component": "test.extractor"},
            }

            # Create context
            context = ExecutionContext(session_id="test_session", base_path=tmp_path)

            # Prepare run with missing cfg files
            manifest = self.create_test_manifest(tmp_path)
            prepared = PreparedRun(
                plan=manifest,
                resolved_connections={},
                cfg_index=cfg_index,
                io_layout={
                    "logs_dir": str(context.logs_dir),
                    "artifacts_dir": str(context.artifacts_dir),
                    "manifest_path": str(context.logs_dir / "manifest.yaml"),
                },
                run_params={"verbose": False},
                constraints={},
                metadata={},
                compiled_root=str(tmp_path),
            )

            # Set the internal state manually
            self.adapter._cfg_paths_to_materialize = set(cfg_index.keys())

            # This should raise ExecuteError due to missing cfg files
            with pytest.raises(ExecuteError) as exc_info:
                self.adapter._preflight_validate_cfg_files(prepared, context)

                # Check error message contains expected content
                assert "Missing required cfg files" in str(exc_info.value)
                assert "cfg/step-0.json" in str(exc_info.value)
                assert "cfg/step-1.json" in str(exc_info.value)

    def test_connection_resolution_with_env_vars(self):
        """Test connection descriptor extraction finds env vars."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)

            # Setup connections file and cfg files
            self.create_test_connections_file(tmp_path)
            cfg_index = self.create_test_cfg_files(tmp_path)

            with patch("os.getcwd", return_value=str(tmp_path)):
                # Test connection resolution
                resolved = self.adapter._extract_connection_descriptors(cfg_index)

                # Should find connections for both steps
                assert "@mysql.test_0" in resolved
                assert "@mysql.test_1" in resolved

                # Should contain env var placeholders
                assert resolved["@mysql.test_0"]["password"] == "${MYSQL_PASSWORD}"
                assert resolved["@mysql.test_1"]["password"] == "${MYSQL_PASSWORD}"

    def test_fallback_to_osiris_compiled_root_env(self):
        """Test cfg resolution falls back to OSIRIS_COMPILED_ROOT environment variable."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)

            # Setup cfg files
            cfg_index = self.create_test_cfg_files(tmp_path)

            # Create context
            base_path = Path(tmp_dir) / "other_location"
            context = ExecutionContext(session_id="test_session", base_path=base_path)

            with patch.object(self.adapter, "_cfg_paths_to_materialize", set(cfg_index.keys())):
                # PreparedRun without compiled_root (simulating --last-compile)
                prepared = PreparedRun(
                    plan={},
                    resolved_connections={},
                    cfg_index=cfg_index,
                    io_layout={
                        "logs_dir": str(context.logs_dir),
                        "artifacts_dir": str(context.artifacts_dir),
                        "manifest_path": str(context.logs_dir / "manifest.yaml"),
                    },
                    run_params={"verbose": False},
                    constraints={},
                    metadata={},
                    compiled_root=None,
                )

                # Set OSIRIS_COMPILED_ROOT environment variable
                with patch.dict("os.environ", {"OSIRIS_COMPILED_ROOT": str(tmp_path)}):
                    # Should not raise exception due to env var fallback
                    self.adapter._preflight_validate_cfg_files(prepared, context)

    def test_no_cfg_files_required_skip_validation(self):
        """Test preflight validation is skipped when no cfg files are needed."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)

            # Create context
            context = ExecutionContext(session_id="test_session", base_path=tmp_path)

            with patch.object(self.adapter, "_cfg_paths_to_materialize", set()):  # Empty set
                prepared = PreparedRun(
                    plan={},
                    resolved_connections={},
                    cfg_index={},  # No cfg files
                    io_layout={
                        "logs_dir": str(context.logs_dir),
                        "artifacts_dir": str(context.artifacts_dir),
                        "manifest_path": str(context.logs_dir / "manifest.yaml"),
                    },
                    run_params={"verbose": False},
                    constraints={},
                    metadata={},
                    compiled_root=str(tmp_path),
                )

                # Should complete without error (no cfg files to validate)
                self.adapter._preflight_validate_cfg_files(prepared, context)


class TestLocalAdapterIntegration:
    """Integration tests for LocalAdapter prepare method."""

    def test_prepare_sets_compiled_root_from_source_manifest_path(self):
        """Test that prepare() correctly sets compiled_root from source_manifest_path."""
        adapter = LocalAdapter()

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            manifest_path = tmp_path / "compiled" / "manifest.yaml"
            manifest_path.parent.mkdir(parents=True)

            # Create mock context
            context = ExecutionContext(session_id="test_session", base_path=tmp_path)

            # Plan with source_manifest_path metadata
            plan = {
                "metadata": {"source_manifest_path": str(manifest_path)},
                "pipeline": {"name": "test", "id": "test"},
                "steps": [],
            }

            prepared = adapter.prepare(plan, context)

            # compiled_root should be set to the parent of the manifest
            assert prepared.compiled_root == str(tmp_path / "compiled")
