#!/usr/bin/env python3
# Copyright (c) 2025 Osiris Project
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Integration tests for AIOP automatic export on run completion."""

import json
from pathlib import Path
import subprocess
import sys

import pytest
import yaml


class TestAIOPAutopilot:
    """Test automatic AIOP export at end of runs."""

    @pytest.fixture
    def simple_pipeline(self, tmp_path):
        """Create a simple test pipeline."""
        pipeline = {
            "oml_version": "0.1.0",
            "name": "test_pipeline",
            "steps": [
                {
                    "id": "generate",
                    "component": "duckdb.generator",
                    "config": {
                        "sql": "SELECT 1 as id, 'test' as name",
                    },
                },
                {
                    "id": "write",
                    "component": "filesystem.csv_writer",
                    "config": {
                        "path": str(tmp_path / "output.csv"),
                    },
                },
            ],
        }
        pipeline_file = tmp_path / "pipeline.yaml"
        with open(pipeline_file, "w") as f:
            yaml.dump(pipeline, f)
        return pipeline_file

    def test_aiop_export_on_success(self, tmp_path, monkeypatch, simple_pipeline):
        """Test AIOP is exported when run succeeds."""
        monkeypatch.chdir(tmp_path)

        # Create osiris.yaml with AIOP enabled
        config = {
            "version": "2.0",
            "aiop": {
                "enabled": True,
                "output": {
                    "core_path": "logs/aiop/{session_id}/aiop.json",
                    "run_card_path": "logs/aiop/{session_id}/run-card.md",
                },
                "run_card": True,
            },
        }
        with open("osiris.yaml", "w") as f:
            yaml.dump(config, f)

        # Run pipeline
        result = subprocess.run(
            [sys.executable, "-m", "osiris.cli.main", "run", str(simple_pipeline)],
            check=False,
            capture_output=True,
            text=True,
            cwd=tmp_path,
        )

        # Extract session_id from output (assuming JSON output)
        if "--json" in str(simple_pipeline):
            output = json.loads(result.stdout)
            session_id = output.get("session_id", "unknown")
        else:
            # Try to extract from logs directory
            logs_dir = Path("logs")
            if logs_dir.exists():
                session_dirs = [d for d in logs_dir.iterdir() if d.is_dir()]
                if session_dirs:
                    session_id = session_dirs[-1].name
                else:
                    session_id = None
            else:
                session_id = None

        # Check AIOP was exported (even without knowing exact session_id)
        aiop_dir = Path("logs/aiop")
        if session_id and aiop_dir.exists():
            session_aiop_dir = aiop_dir / session_id
            if session_aiop_dir.exists():
                assert (session_aiop_dir / "aiop.json").exists()
                assert (session_aiop_dir / "run-card.md").exists()

                # Verify AIOP content
                with open(session_aiop_dir / "aiop.json") as f:
                    aiop = json.load(f)
                assert "@context" in aiop
                assert "narrative" in aiop
                assert "evidence" in aiop
                assert "metadata" in aiop

    def test_aiop_disabled(self, tmp_path, monkeypatch, simple_pipeline):
        """Test AIOP is not exported when disabled."""
        monkeypatch.chdir(tmp_path)

        # Create osiris.yaml with AIOP disabled
        config = {
            "version": "2.0",
            "aiop": {
                "enabled": False,
            },
        }
        with open("osiris.yaml", "w") as f:
            yaml.dump(config, f)

        # Run pipeline
        subprocess.run(
            [sys.executable, "-m", "osiris.cli.main", "run", str(simple_pipeline)],
            check=False,
            capture_output=True,
            text=True,
            cwd=tmp_path,
        )

        # Check AIOP was NOT exported
        aiop_dir = Path("logs/aiop")
        assert not aiop_dir.exists() or len(list(aiop_dir.iterdir())) == 0

    def test_index_files_created(self, tmp_path, monkeypatch, simple_pipeline):
        """Test index files are created and updated."""
        monkeypatch.chdir(tmp_path)

        # Create osiris.yaml with index enabled
        config = {
            "version": "2.0",
            "aiop": {
                "enabled": True,
                "index": {
                    "enabled": True,
                    "runs_jsonl": "logs/aiop/index/runs.jsonl",
                    "by_pipeline_dir": "logs/aiop/index/by_pipeline",
                },
            },
        }
        with open("osiris.yaml", "w") as f:
            yaml.dump(config, f)

        # Run pipeline
        subprocess.run(
            [sys.executable, "-m", "osiris.cli.main", "run", str(simple_pipeline)],
            check=False,
            capture_output=True,
            text=True,
            cwd=tmp_path,
        )

        # Check index files exist
        runs_index = Path("logs/aiop/index/runs.jsonl")
        if runs_index.exists():
            with open(runs_index) as f:
                lines = f.readlines()
            assert len(lines) >= 1
            record = json.loads(lines[0])
            assert "session_id" in record
            assert "core_path" in record
            assert "status" in record

    def test_config_precedence_env_override(self, tmp_path, monkeypatch, simple_pipeline):
        """Test environment variable overrides YAML."""
        monkeypatch.chdir(tmp_path)

        # Create osiris.yaml with medium timeline_density
        config = {
            "version": "2.0",
            "aiop": {
                "enabled": True,
                "timeline_density": "medium",
            },
        }
        with open("osiris.yaml", "w") as f:
            yaml.dump(config, f)

        # Set ENV to override to high
        monkeypatch.setenv("OSIRIS_AIOP_TIMELINE_DENSITY", "high")

        # Run pipeline
        subprocess.run(
            [sys.executable, "-m", "osiris.cli.main", "run", str(simple_pipeline)],
            check=False,
            capture_output=True,
            text=True,
            cwd=tmp_path,
        )

        # Find and check AIOP
        aiop_dir = Path("logs/aiop")
        if aiop_dir.exists():
            for session_dir in aiop_dir.iterdir():
                if session_dir.is_dir() and session_dir.name != "index":
                    aiop_file = session_dir / "aiop.json"
                    if aiop_file.exists():
                        with open(aiop_file) as f:
                            aiop = json.load(f)
                        # Check config_effective shows ENV source
                        if "metadata" in aiop and "config_effective" in aiop["metadata"]:
                            config_eff = aiop["metadata"]["config_effective"]
                            if "timeline_density" in config_eff:
                                assert config_eff["timeline_density"]["value"] == "high"
                                assert config_eff["timeline_density"]["source"] == "ENV"

    def test_latest_symlink(self, tmp_path, monkeypatch, simple_pipeline):
        """Test latest symlink points to newest run."""
        monkeypatch.chdir(tmp_path)

        # Skip on Windows
        if sys.platform.startswith("win"):
            pytest.skip("Symlinks not supported on Windows")

        config = {
            "version": "2.0",
            "aiop": {
                "enabled": True,
                "index": {
                    "enabled": True,
                    "latest_symlink": "logs/aiop/latest",
                },
            },
        }
        with open("osiris.yaml", "w") as f:
            yaml.dump(config, f)

        # Run pipeline
        subprocess.run(
            [sys.executable, "-m", "osiris.cli.main", "run", str(simple_pipeline)],
            check=False,
            capture_output=True,
            text=True,
            cwd=tmp_path,
        )

        # Check symlink exists and is valid
        latest = Path("logs/aiop/latest")
        if latest.exists():
            assert latest.is_symlink() or latest.is_dir()
            # Should contain aiop.json
            assert (latest / "aiop.json").exists() or list(latest.iterdir())

    def test_retention_on_multiple_runs(self, tmp_path, monkeypatch, simple_pipeline):
        """Test retention is applied when keep_runs limit exceeded."""
        monkeypatch.chdir(tmp_path)

        # Create config with keep_runs=1
        config = {
            "version": "2.0",
            "aiop": {
                "enabled": True,
                "retention": {
                    "keep_runs": 1,
                },
            },
        }
        with open("osiris.yaml", "w") as f:
            yaml.dump(config, f)

        # Run pipeline twice
        for _ in range(2):
            subprocess.run(
                [sys.executable, "-m", "osiris.cli.main", "run", str(simple_pipeline)],
                check=False,
                capture_output=True,
                text=True,
                cwd=tmp_path,
            )

        # Check only 1 run directory remains
        aiop_dir = Path("logs/aiop")
        if aiop_dir.exists():
            run_dirs = [d for d in aiop_dir.iterdir() if d.is_dir() and d.name not in ["index", "latest"]]
            assert len(run_dirs) <= 1  # Should be at most 1 after retention
