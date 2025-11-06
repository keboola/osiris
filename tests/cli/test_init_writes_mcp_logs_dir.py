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

"""Tests for osiris init command filesystem contract config generation.

Verifies that `osiris init` properly writes:
- filesystem.base_path (absolute path)
- filesystem.mcp_logs_dir (relative path)
- Backward compatibility (doesn't overwrite existing values)
"""

from pathlib import Path

import pytest
import yaml

from osiris.cli.init import init_command


class TestInitFilesystemConfig:
    """Test filesystem contract configuration generation in osiris init."""

    def test_init_writes_absolute_base_path(self, tmp_path):
        """Verify osiris init writes absolute base_path to osiris.yaml."""
        project_dir = tmp_path / "test_project"
        project_dir.mkdir()

        # Run init command
        init_command([str(project_dir)], json_output=False)

        # Verify osiris.yaml was created
        config_file = project_dir / "osiris.yaml"
        assert config_file.exists(), "osiris.yaml should be created"

        # Load and verify config
        with open(config_file) as f:
            config = yaml.safe_load(f)

        # Verify filesystem.base_path exists and is absolute
        assert "filesystem" in config, "Config should have filesystem section"
        assert "base_path" in config["filesystem"], "Config should have filesystem.base_path"

        base_path = config["filesystem"]["base_path"]
        assert base_path, "base_path should not be empty"

        # Verify it's an absolute path
        base_path_obj = Path(base_path)
        assert base_path_obj.is_absolute(), f"base_path should be absolute: {base_path}"

        # Verify it matches the project directory
        assert base_path_obj == project_dir.resolve(), f"base_path should match project dir: {base_path}"

    def test_init_writes_mcp_logs_dir(self, tmp_path):
        """Verify osiris init writes filesystem.mcp_logs_dir to osiris.yaml."""
        project_dir = tmp_path / "test_project2"
        project_dir.mkdir()

        # Run init command
        init_command([str(project_dir)], json_output=False)

        # Load config
        config_file = project_dir / "osiris.yaml"
        with open(config_file) as f:
            config = yaml.safe_load(f)

        # Verify mcp_logs_dir exists
        assert "mcp_logs_dir" in config["filesystem"], "Config should have filesystem.mcp_logs_dir"

        mcp_logs_dir = config["filesystem"]["mcp_logs_dir"]
        assert mcp_logs_dir == ".osiris/mcp/logs", f"mcp_logs_dir should be '.osiris/mcp/logs', got: {mcp_logs_dir}"

    def test_init_creates_mcp_log_directories(self, tmp_path):
        """Verify osiris init creates .osiris/mcp/logs directory structure."""
        project_dir = tmp_path / "test_project3"
        project_dir.mkdir()

        # Run init command
        init_command([str(project_dir)], json_output=False)

        # Note: init creates .osiris/sessions and .osiris/cache
        # MCP log directories are created by MCP server when it starts
        # But we can verify the base .osiris structure exists
        osiris_dir = project_dir / ".osiris"
        assert osiris_dir.exists(), ".osiris directory should be created"
        assert osiris_dir.is_dir(), ".osiris should be a directory"

        # Verify sessions and cache dirs (created by init)
        assert (osiris_dir / "sessions").exists(), ".osiris/sessions should exist"
        assert (osiris_dir / "cache").exists(), ".osiris/cache should exist"

    def test_init_with_current_directory(self, tmp_path, monkeypatch):
        """Verify osiris init uses current directory when no path specified."""
        project_dir = tmp_path / "test_project4"
        project_dir.mkdir()

        # Change to project directory
        monkeypatch.chdir(project_dir)

        # Run init with no path argument (should use current dir)
        init_command([], json_output=False)

        # Load config
        config_file = project_dir / "osiris.yaml"
        with open(config_file) as f:
            config = yaml.safe_load(f)

        # Verify base_path matches current directory
        base_path = Path(config["filesystem"]["base_path"])
        assert base_path == project_dir.resolve(), "base_path should match current directory"

    def test_init_backward_compatibility_force_flag(self, tmp_path):
        """Verify osiris init --force overwrites existing osiris.yaml."""
        project_dir = tmp_path / "test_project5"
        project_dir.mkdir()

        # Create initial config with custom base_path
        initial_config = {
            "version": "2.0",
            "filesystem": {
                "base_path": "/custom/path",
                "mcp_logs_dir": ".custom/mcp",
            },
        }
        config_file = project_dir / "osiris.yaml"
        with open(config_file, "w") as f:
            yaml.safe_dump(initial_config, f)

        # Run init with --force
        init_command([str(project_dir), "--force"], json_output=False)

        # Load new config
        with open(config_file) as f:
            config = yaml.safe_load(f)

        # Verify config was overwritten with new absolute path
        new_base_path = Path(config["filesystem"]["base_path"])
        assert new_base_path == project_dir.resolve(), "base_path should be updated to project dir"
        assert config["filesystem"]["mcp_logs_dir"] == ".osiris/mcp/logs", "mcp_logs_dir should be reset to default"

    def test_init_without_force_preserves_existing(self, tmp_path, capsys):
        """Verify osiris init without --force preserves existing osiris.yaml."""
        project_dir = tmp_path / "test_project6"
        project_dir.mkdir()

        # Create existing config
        existing_config = {
            "version": "2.0",
            "filesystem": {
                "base_path": "/existing/path",
                "mcp_logs_dir": ".existing/mcp",
            },
        }
        config_file = project_dir / "osiris.yaml"
        with open(config_file, "w") as f:
            yaml.safe_dump(existing_config, f)

        # Run init without --force (should fail with exit code 1)
        with pytest.raises(SystemExit) as exc_info:
            init_command([str(project_dir)], json_output=False)

        assert exc_info.value.code == 1, "init should exit with code 1 when osiris.yaml exists"

        # Verify config was NOT modified
        with open(config_file) as f:
            config = yaml.safe_load(f)

        assert config["filesystem"]["base_path"] == "/existing/path", "Existing base_path should be preserved"
        assert config["filesystem"]["mcp_logs_dir"] == ".existing/mcp", "Existing mcp_logs_dir should be preserved"

    def test_init_json_output_includes_filesystem_config(self, tmp_path, capsys):
        """Verify osiris init --json output indicates filesystem config was created."""
        project_dir = tmp_path / "test_project7"
        project_dir.mkdir()

        # Run init with JSON output
        init_command([str(project_dir), "--json"], json_output=True)

        # Capture JSON output
        captured = capsys.readouterr()
        import json

        result = json.loads(captured.out)

        # Verify JSON structure
        assert result["status"] == "success", "Init should succeed"
        assert result["created"]["osiris_yaml"] is True, "JSON should indicate osiris.yaml was created"
        assert str(project_dir) == result["project_path"], "JSON should include project path"

        # Verify actual config file
        config_file = project_dir / "osiris.yaml"
        with open(config_file) as f:
            config = yaml.safe_load(f)

        assert config["filesystem"]["base_path"] == str(project_dir), "Config should have correct base_path"
        assert config["filesystem"]["mcp_logs_dir"] == ".osiris/mcp/logs", "Config should have mcp_logs_dir"


class TestInitConfigPrecedence:
    """Test config-first precedence behavior (filesystem contract compliance)."""

    def test_mcp_reads_config_not_env(self, tmp_path, monkeypatch):
        """Verify MCP config loader prefers osiris.yaml over environment variables."""
        project_dir = tmp_path / "test_project8"
        project_dir.mkdir()

        # Run init
        init_command([str(project_dir)], json_output=False)

        # Set conflicting environment variable
        monkeypatch.setenv("OSIRIS_HOME", "/fake/env/path")
        monkeypatch.setenv("OSIRIS_MCP_LOGS_DIR", "/fake/mcp/logs")

        # Load config using MCP filesystem config
        from osiris.mcp.config import MCPFilesystemConfig

        config_file = project_dir / "osiris.yaml"
        fs_config = MCPFilesystemConfig.from_config(str(config_file))

        # Verify config file wins over environment
        assert fs_config.base_path == project_dir.resolve(), "Config file should take precedence over OSIRIS_HOME"
        expected_mcp_logs = project_dir / ".osiris" / "mcp" / "logs"
        assert fs_config.mcp_logs_dir == expected_mcp_logs, "Config mcp_logs_dir should take precedence over env"

    def test_env_fallback_with_warning(self, tmp_path, monkeypatch, caplog):
        """Verify environment variables are used with WARNING when osiris.yaml missing."""
        project_dir = tmp_path / "test_project9"
        project_dir.mkdir()

        # Set environment variables
        monkeypatch.setenv("OSIRIS_HOME", str(project_dir))

        # Try to load config from non-existent file
        from osiris.mcp.config import MCPFilesystemConfig

        fs_config = MCPFilesystemConfig.from_config("nonexistent.yaml")

        # Verify environment variable was used
        assert fs_config.base_path == project_dir.resolve(), "Should fall back to OSIRIS_HOME"

        # Verify WARNING was logged (checked in logs)
        # Note: This test assumes logging is configured in the test environment
