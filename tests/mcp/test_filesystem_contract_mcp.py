"""
Test filesystem contract compliance for MCP server.

Verifies that MCP server respects the filesystem contract defined in ADR-0028
and uses config-driven paths instead of hardcoded directories.
"""

import os
from pathlib import Path
from unittest.mock import patch

from osiris.mcp.config import MCPConfig, MCPFilesystemConfig


class TestFilesystemContractCompliance:
    """Test MCP filesystem contract compliance."""

    def test_mcp_config_reads_from_osiris_yaml(self, tmp_path):
        """Test that MCPConfig reads filesystem config from osiris.yaml."""
        # Create test config
        config_file = tmp_path / "osiris.yaml"
        config_file.write_text(
            f"""
version: '2.0'
filesystem:
  base_path: "{tmp_path}"
  mcp_logs_dir: ".osiris/mcp/logs"
"""
        )

        # Load filesystem config
        fs_config = MCPFilesystemConfig.from_config(str(config_file))

        # Verify paths
        assert fs_config.base_path == tmp_path
        assert fs_config.mcp_logs_dir == tmp_path / ".osiris/mcp/logs"

        # Create MCP config with filesystem config
        mcp_config = MCPConfig(fs_config=fs_config)

        # Verify MCP config uses filesystem config paths
        assert mcp_config.audit_dir == tmp_path / ".osiris/mcp/logs/audit"
        assert mcp_config.telemetry_dir == tmp_path / ".osiris/mcp/logs/telemetry"
        assert mcp_config.cache_dir == tmp_path / ".osiris/mcp/logs/cache"

    def test_mcp_logs_write_to_correct_location(self, tmp_path):
        """Test that MCP logs are written to configured location."""
        # Create config
        config_file = tmp_path / "osiris.yaml"
        config_file.write_text(
            f"""
version: '2.0'
filesystem:
  base_path: "{tmp_path}"
  mcp_logs_dir: ".osiris/mcp/logs"
"""
        )

        fs_config = MCPFilesystemConfig.from_config(str(config_file))
        mcp_config = MCPConfig(fs_config=fs_config)

        # Verify directories are created
        assert mcp_config.fs_config.mcp_logs_dir.exists()
        assert (mcp_config.fs_config.mcp_logs_dir / "audit").exists()
        assert (mcp_config.fs_config.mcp_logs_dir / "telemetry").exists()
        assert (mcp_config.fs_config.mcp_logs_dir / "cache").exists()

    def test_no_hardcoded_home_directories(self, tmp_path):
        """Test that MCP config doesn't use hardcoded home directories."""
        from osiris.mcp.config import MCPConfig

        # Create config with explicit paths using tmp_path
        test_base = tmp_path / "test_base"
        test_base.mkdir()

        fs_config = MCPFilesystemConfig()
        fs_config.base_path = test_base
        fs_config.mcp_logs_dir = test_base / ".osiris/mcp/logs"

        config = MCPConfig(fs_config=fs_config)

        # Verify no paths use Path.home()
        assert not str(config.audit_dir).startswith(str(Path.home()))
        assert not str(config.telemetry_dir).startswith(str(Path.home()))
        assert not str(config.cache_dir).startswith(str(Path.home()))
        assert not str(config.memory_dir).startswith(str(Path.home()))

        # All paths should be under base_path
        assert str(config.audit_dir).startswith(str(test_base))
        assert str(config.telemetry_dir).startswith(str(test_base))
        assert str(config.cache_dir).startswith(str(test_base))

    def test_config_precedence_yaml_over_env(self, tmp_path):
        """Test that osiris.yaml takes precedence over environment variables."""
        config_file = tmp_path / "osiris.yaml"
        config_file.write_text(
            f"""
version: '2.0'
filesystem:
  base_path: "{tmp_path}/from_config"
  mcp_logs_dir: ".osiris/mcp/logs"
"""
        )

        env_backup = os.environ.copy()
        try:
            # Set environment variable
            os.environ["OSIRIS_HOME"] = str(tmp_path / "from_env")

            # Load config
            fs_config = MCPFilesystemConfig.from_config(str(config_file))

            # Should use config file, not environment
            assert str(fs_config.base_path) == str(tmp_path / "from_config")
            assert "from_env" not in str(fs_config.base_path)

        finally:
            os.environ.clear()
            os.environ.update(env_backup)

    def test_empty_base_path_uses_config_directory(self, tmp_path):
        """Test that empty base_path uses config file's directory."""
        config_file = tmp_path / "osiris.yaml"
        config_file.write_text(
            """
version: '2.0'
filesystem:
  base_path: ""
  mcp_logs_dir: ".osiris/mcp/logs"
"""
        )

        fs_config = MCPFilesystemConfig.from_config(str(config_file))

        # Should use config file's parent directory
        assert fs_config.base_path == tmp_path

    def test_mcp_logs_dir_relative_to_base_path(self, tmp_path):
        """Test that mcp_logs_dir is resolved relative to base_path."""
        config_file = tmp_path / "osiris.yaml"
        config_file.write_text(
            f"""
version: '2.0'
filesystem:
  base_path: "{tmp_path}"
  mcp_logs_dir: "custom/mcp/logs"
"""
        )

        fs_config = MCPFilesystemConfig.from_config(str(config_file))

        # mcp_logs_dir should be relative to base_path
        assert fs_config.mcp_logs_dir == tmp_path / "custom/mcp/logs"

    def test_ensure_directories_creates_structure(self, tmp_path):
        """Test that ensure_directories creates all required subdirectories."""
        fs_config = MCPFilesystemConfig()
        fs_config.base_path = tmp_path
        fs_config.mcp_logs_dir = tmp_path / ".osiris/mcp/logs"

        # Before calling ensure_directories
        assert not fs_config.mcp_logs_dir.exists()

        # Call ensure_directories
        fs_config.ensure_directories()

        # Verify structure is created
        assert fs_config.mcp_logs_dir.exists()
        assert (fs_config.mcp_logs_dir / "audit").exists()
        assert (fs_config.mcp_logs_dir / "telemetry").exists()
        assert (fs_config.mcp_logs_dir / "cache").exists()

    def test_mcp_config_integration(self, tmp_path):
        """Test full integration of MCPConfig with filesystem contract."""
        # Create realistic config
        config_file = tmp_path / "osiris.yaml"
        config_file.write_text(
            f"""
version: '2.0'
filesystem:
  base_path: "{tmp_path}"
  mcp_logs_dir: ".osiris/mcp/logs"
  sessions_dir: ".osiris/sessions"
  cache_dir: ".osiris/cache"
  index_dir: ".osiris/index"
"""
        )

        # Load configs
        fs_config = MCPFilesystemConfig.from_config(str(config_file))
        mcp_config = MCPConfig(fs_config=fs_config)

        # Verify all paths are under base_path
        assert str(mcp_config.audit_dir).startswith(str(tmp_path))
        assert str(mcp_config.telemetry_dir).startswith(str(tmp_path))
        assert str(mcp_config.cache_dir).startswith(str(tmp_path))
        assert str(mcp_config.memory_dir).startswith(str(tmp_path))

        # Verify specific paths
        assert mcp_config.audit_dir == tmp_path / ".osiris/mcp/logs/audit"
        assert mcp_config.telemetry_dir == tmp_path / ".osiris/mcp/logs/telemetry"
        assert mcp_config.cache_dir == tmp_path / ".osiris/mcp/logs/cache"

        # Verify directories exist
        assert mcp_config.audit_dir.exists()
        assert mcp_config.telemetry_dir.exists()
        assert mcp_config.cache_dir.exists()


class TestConfigFallbacks:
    """Test fallback behavior when config is missing."""

    def test_fallback_to_env_variable(self, tmp_path):
        """Test fallback to OSIRIS_HOME when config is missing."""
        env_backup = os.environ.copy()
        try:
            os.environ["OSIRIS_HOME"] = str(tmp_path)

            # Load config with non-existent file
            fs_config = MCPFilesystemConfig.from_config("nonexistent.yaml")

            # Should fall back to OSIRIS_HOME
            assert fs_config.base_path == tmp_path

        finally:
            os.environ.clear()
            os.environ.update(env_backup)

    def test_ultimate_fallback_to_cwd(self, tmp_path):
        """Test ultimate fallback to current working directory."""
        env_backup = os.environ.copy()
        try:
            # Clear all relevant env vars
            for key in list(os.environ.keys()):
                if key.startswith("OSIRIS_"):
                    del os.environ[key]

            with patch("pathlib.Path.cwd", return_value=tmp_path):
                # Load config with non-existent file and no env vars
                fs_config = MCPFilesystemConfig.from_config("nonexistent.yaml")

                # Should fall back to CWD
                assert fs_config.base_path == tmp_path

        finally:
            os.environ.clear()
            os.environ.update(env_backup)

    def test_env_override_logs_warning(self, caplog, tmp_path):
        """Test that environment variable override logs a warning."""
        env_backup = os.environ.copy()
        try:
            os.environ["OSIRIS_MCP_LOGS_DIR"] = str(tmp_path / "override")

            # Load config
            fs_config = MCPFilesystemConfig.from_config("nonexistent.yaml")

            # Should log warning about environment override
            assert any("OSIRIS_MCP_LOGS_DIR" in record.message for record in caplog.records)
            assert any("environment" in record.message.lower() for record in caplog.records)

        finally:
            os.environ.clear()
            os.environ.update(env_backup)


class TestConfigValidation:
    """Test configuration validation and error handling."""

    def test_handles_malformed_yaml(self, tmp_path, caplog):
        """Test handling of malformed YAML file."""
        config_file = tmp_path / "osiris.yaml"
        config_file.write_text("invalid: yaml: content: [[[")

        # Should not crash, should fall back
        fs_config = MCPFilesystemConfig.from_config(str(config_file))

        # Should have fallen back to default/env
        assert fs_config.base_path is not None
        assert fs_config.mcp_logs_dir is not None

        # Should have logged warning
        assert any("Failed to load" in record.message for record in caplog.records)

    def test_handles_missing_filesystem_section(self, tmp_path):
        """Test handling of config without filesystem section."""
        config_file = tmp_path / "osiris.yaml"
        config_file.write_text(
            """
version: '2.0'
logging:
  level: INFO
"""
        )

        # Should not crash
        fs_config = MCPFilesystemConfig.from_config(str(config_file))

        # Should have defaults
        assert fs_config.base_path is not None
        assert fs_config.mcp_logs_dir is not None

    def test_to_dict_includes_filesystem_paths(self, tmp_path):
        """Test that MCPConfig.to_dict includes filesystem paths."""
        fs_config = MCPFilesystemConfig()
        fs_config.base_path = tmp_path
        fs_config.mcp_logs_dir = tmp_path / ".osiris/mcp/logs"

        mcp_config = MCPConfig(fs_config=fs_config)
        config_dict = mcp_config.to_dict()

        # Verify filesystem paths are included
        assert "directories" in config_dict
        assert "audit" in config_dict["directories"]
        assert "telemetry" in config_dict["directories"]
        assert "cache" in config_dict["directories"]

        # Verify paths are strings
        assert isinstance(config_dict["directories"]["audit"], str)
        assert tmp_path.name in config_dict["directories"]["audit"]
