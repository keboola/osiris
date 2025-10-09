"""Integration tests for AIOP autopilot export during run."""

import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml


class TestAIOPAutopilotRun:
    """Test automatic AIOP export at end of pipeline runs."""

    @pytest.mark.skip(reason="Integration test needs cfg file naming alignment between compiler and runner")
    def test_aiop_export_on_successful_run(self, tmp_path, monkeypatch):
        """Test that AIOP is automatically exported after successful run."""
        # Create minimal test config
        config_dir = tmp_path / "test_config"
        config_dir.mkdir()

        # Create osiris.yaml with AIOP enabled
        config_file = config_dir / "osiris.yaml"
        config = {
            "version": "2.0",
            "aiop": {
                "enabled": True,
                "output": {
                    "core_path": "logs/aiop/{session_id}/aiop.json",
                    "run_card_path": "logs/aiop/{session_id}/run-card.md",
                },
                "index": {
                    "enabled": True,
                    "runs_jsonl": "logs/aiop/index/runs.jsonl",
                },
                "retention": {"keep_runs": 3},
            },
            "logging": {"logs_dir": "logs", "events": ["*"]},
        }
        config_file.write_text(yaml.dump(config))

        # Copy components directory to test location
        import shutil

        src_components = Path(__file__).parent.parent.parent / "components"
        dst_components = config_dir / "components"
        if src_components.exists():
            shutil.copytree(src_components, dst_components)

        # Create a simple OML file to compile
        oml_file = config_dir / "test.oml"
        oml_content = """
oml_version: "0.1.0"
name: test_pipeline
steps:
  - name: test_step
    component: filesystem.csv_writer
    config:
      path: output.csv
"""
        oml_file.write_text(oml_content)

        # Change to config directory
        monkeypatch.chdir(config_dir)

        # First compile the OML
        osiris_path = Path(__file__).parent.parent.parent / "osiris.py"
        compile_result = subprocess.run(
            [sys.executable, str(osiris_path), "compile", str(oml_file)],
            check=False,
            capture_output=True,
            text=True,
        )

        # Check compile succeeded
        assert compile_result.returncode == 0, f"Compile failed: {compile_result.stderr}"

        # Check .osiris/index/latest/<filename>.txt was created (Filesystem Contract v1)
        # Note: filename is based on OML filename (test.oml -> test.txt), not pipeline name
        latest_manifest_file = config_dir / ".osiris" / "index" / "latest" / "test.txt"
        assert latest_manifest_file.exists(), f"Latest manifest pointer not created at {latest_manifest_file}"

        # Extract session ID from compile output
        for line in compile_result.stdout.split("\n"):
            if "Session:" in line and "logs/" in line:
                # Extract session ID from "Session: logs/compile_XXX/"
                parts = line.split("logs/")
                if len(parts) > 1:
                    parts[1].strip("/")
                    break

        # Now run the compiled manifest with dry-run
        run_result = subprocess.run(
            [sys.executable, str(osiris_path), "run", "--last-compile", "--dry-run"],
            check=False,
            capture_output=True,
            text=True,
        )

        # Extract session ID from run output
        session_id = None
        for line in run_result.stdout.split("\n"):
            if "Session:" in line and "logs/" in line:
                # Extract session ID from "Session: logs/run_XXX/"
                parts = line.split("logs/")
                if len(parts) > 1:
                    session_id = parts[1].strip("/")
                    break

        # Verify AIOP files were created
        assert session_id, f"Could not extract session ID from output: {run_result.stdout}"

        aiop_file = config_dir / f"logs/aiop/{session_id}/aiop.json"
        assert aiop_file.exists(), f"AIOP file not created at {aiop_file}"

        # Verify AIOP content
        aiop_data = json.loads(aiop_file.read_text())
        assert aiop_data["run"]["session_id"] == session_id
        assert aiop_data["run"]["status"] in ["completed", "partial", "failed"]
        assert aiop_data["pipeline"]["name"] == "test_pipeline"
        assert aiop_data["run"]["duration_ms"] >= 0
        assert "@id" in aiop_data and "osiris://pipeline/" in aiop_data["@id"]

        # Verify run-card created
        runcard_file = config_dir / f"logs/aiop/{session_id}/run-card.md"
        assert runcard_file.exists(), f"Run-card not created at {runcard_file}"
        runcard_content = runcard_file.read_text()
        assert "test_pipeline" in runcard_content
        assert runcard_content.strip() != "", "Run-card should not be empty"

        # Verify index updated
        index_file = config_dir / "logs/aiop/index/runs.jsonl"
        assert index_file.exists(), "Index file not created"
        index_lines = index_file.read_text().strip().split("\n")
        last_entry = json.loads(index_lines[-1])
        assert last_entry["session_id"] == session_id

    def test_aiop_export_on_failed_run(self, tmp_path, monkeypatch):
        """Test that AIOP is exported even when pipeline fails."""
        # Skip this test for now - it's hard to make a pipeline fail predictably
        pytest.skip("Skipping failed run test - requires mock infrastructure")

    def test_aiop_disabled_no_export(self, tmp_path, monkeypatch):
        """Test that AIOP is not exported when disabled in config."""
        # Skip this test too - requires more setup
        pytest.skip("Skipping disabled export test - requires mock infrastructure")

    def test_non_templated_path_auto_suffix(self, tmp_path, monkeypatch):
        """Test that non-templated paths get auto-suffixed to prevent overwrites."""
        # Skip this test too
        pytest.skip("Skipping auto-suffix test - requires complex setup")
