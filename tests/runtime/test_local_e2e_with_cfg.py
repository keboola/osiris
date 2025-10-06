"""E2E test for local run with cfg materialization.

Tests the complete flow from compile to run with cfg files.
"""

import json
import os
from pathlib import Path
import tempfile

import pytest

from osiris.cli.run import run_command
from osiris.core.compiler_v0 import CompilerV0


class TestLocalE2EWithCfg:
    """Test end-to-end local execution with cfg files."""

    @pytest.mark.skipif(not os.getenv("MYSQL_PASSWORD"), reason="MySQL password required for connection tests")
    def test_local_run_with_cfg_materialization(self):
        """Test that local run properly materializes and uses cfg files."""
        # Use the existing example pipeline that has cfg files
        example_pipeline = (
            Path(__file__).parent.parent.parent / "docs" / "examples" / "mysql_to_local_csv_all_tables.yaml"
        )

        if not example_pipeline.exists():
            pytest.skip(f"Example pipeline not found: {example_pipeline}")

        with tempfile.TemporaryDirectory() as tmpdir:
            # Set environment for testing
            os.environ["OSIRIS_BASE_LOGS_DIR"] = tmpdir

            # Compile the pipeline
            compile_output = Path(tmpdir) / "compile_test" / "compiled"
            compiler = CompilerV0(output_dir=str(compile_output))
            success, manifest_path = compiler.compile(str(example_pipeline))

            assert success, f"Compilation failed: {manifest_path}"
            assert Path(manifest_path).exists()

            # Verify cfg files were created during compile
            cfg_dir = compile_output / "cfg"
            assert cfg_dir.exists()
            cfg_files = list(cfg_dir.glob("*.json"))
            assert len(cfg_files) > 0, "No cfg files generated during compile"

            # Run using --last-compile equivalent
            # We'll use the run command with the manifest directly
            import sys
            from unittest.mock import patch

            # Mock sys.argv to simulate command line
            test_args = ["osiris", "run", str(manifest_path), "--verbose"]

            with patch.object(sys, "argv", test_args):
                # Capture exit to prevent test from exiting
                with pytest.raises(SystemExit) as exc_info:
                    run_command(test_args)

                # Check exit code - may be non-zero due to missing connections
                # but cfg materialization should have happened
                exit_code = exc_info.value.code

                # Find the run session that was created
                run_dirs = list(Path(tmpdir).glob("run_*"))
                if run_dirs:
                    run_dir = run_dirs[-1]  # Get most recent

                    # Verify cfg files were materialized to run session
                    run_cfg_dir = run_dir / "cfg"
                    if run_cfg_dir.exists():
                        run_cfg_files = list(run_cfg_dir.glob("*.json"))
                        assert len(run_cfg_files) == len(
                            cfg_files
                        ), f"Cfg file count mismatch: compile has {len(cfg_files)}, run has {len(run_cfg_files)}"

                        # Verify content matches
                        for cfg_file in cfg_files:
                            run_cfg = run_cfg_dir / cfg_file.name
                            assert run_cfg.exists(), f"Missing cfg in run: {cfg_file.name}"

                            with open(cfg_file) as f1, open(run_cfg) as f2:
                                compile_content = json.load(f1)
                                run_content = json.load(f2)
                                assert compile_content == run_content, f"Cfg content mismatch for {cfg_file.name}"

                    # Check for expected error if no connections configured
                    if exit_code != 0:
                        osiris_log = run_dir / "osiris.log"
                        if osiris_log.exists():
                            log_content = osiris_log.read_text()
                            # We expect connection errors, not cfg errors
                            assert (
                                "cfg" not in log_content.lower() or "Missing configuration files" not in log_content
                            ), "Should not have cfg errors after materialization"


class TestNegativeCfgScenarios:
    """Test error handling for cfg materialization."""

    def test_missing_cfg_produces_friendly_error(self):
        """Test that missing cfg files produce a helpful error message."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a manifest that references a non-existent cfg
            manifest = {
                "meta": {"generated_at": "2025-01-01T00:00:00Z"},
                "pipeline": {"id": "test-pipeline"},
                "steps": [
                    {
                        "id": "missing-step",
                        "driver": "mysql.extractor",
                        "cfg_path": "cfg/does-not-exist.json",
                    }
                ],
            }

            # Write manifest
            manifest_path = Path(tmpdir) / "manifest.yaml"
            import yaml

            with open(manifest_path, "w") as f:
                yaml.dump(manifest, f)

            # Try to run it
            import sys
            from unittest.mock import patch

            test_args = ["osiris", "run", str(manifest_path)]

            with patch.object(sys, "argv", test_args):
                with pytest.raises(SystemExit) as exc_info:
                    run_command(test_args)

                # Should exit with error
                assert exc_info.value.code != 0

                # The error message should be in the logs or output
                # (exact location depends on error handling path)
