"""
Tests for osiris.mcp.clients_config module.

Verifies that build_claude_clients_snippet produces the correct JSON structure
for Claude Desktop configuration with platform-aware shell wrapper, transport, and paths.
"""

from unittest.mock import patch

from osiris.mcp.clients_config import build_claude_clients_snippet


class TestBuildClaudeClientsSnippet:
    """Test suite for build_claude_clients_snippet function."""

    def test_absolute_base_path(self):
        """Test with absolute base_path produces correct structure."""
        config = build_claude_clients_snippet(
            base_path="/Users/me/osiris", venv_python="/Users/me/osiris/.venv/bin/python"
        )

        # Verify top-level structure
        assert "mcpServers" in config
        assert "osiris" in config["mcpServers"]

        server_config = config["mcpServers"]["osiris"]

        # Verify command is bash
        assert server_config["command"] == "/bin/bash"

        # Verify args contain bash wrapper with absolute paths
        assert server_config["args"] == [
            "-lc",
            "cd /Users/me/osiris && exec /Users/me/osiris/.venv/bin/python -m osiris.cli.mcp_entrypoint",
        ]

        # Verify transport
        assert server_config["transport"] == {"type": "stdio"}

        # Verify environment variables
        assert server_config["env"]["OSIRIS_HOME"] == "/Users/me/osiris"
        assert server_config["env"]["PYTHONPATH"] == "/Users/me/osiris"

    def test_venv_python_path_with_spaces(self):
        """Test that paths with spaces are safely quoted with shlex.quote()."""
        config = build_claude_clients_snippet(
            base_path="/Users/me/my project/osiris", venv_python="/Users/me/my project/osiris/.venv/bin/python"
        )

        server_config = config["mcpServers"]["osiris"]

        # Verify paths with spaces are properly quoted using shlex.quote()
        # This prevents shell injection and handles spaces correctly
        expected_args = [
            "-lc",
            "cd '/Users/me/my project/osiris' && exec '/Users/me/my project/osiris/.venv/bin/python' -m osiris.cli.mcp_entrypoint",
        ]
        assert server_config["args"] == expected_args

        # Verify env vars also have paths with spaces
        assert server_config["env"]["OSIRIS_HOME"] == "/Users/me/my project/osiris"
        assert server_config["env"]["PYTHONPATH"] == "/Users/me/my project/osiris"

    def test_transport_is_stdio(self):
        """Test that transport type is always stdio."""
        config = build_claude_clients_snippet(base_path="/any/path", venv_python="/any/path/.venv/bin/python")

        server_config = config["mcpServers"]["osiris"]
        assert server_config["transport"]["type"] == "stdio"
        assert "type" in server_config["transport"]
        assert len(server_config["transport"]) == 1  # Only 'type' field

    def test_command_is_bash(self):
        """Test that command is always /bin/bash."""
        config = build_claude_clients_snippet(base_path="/any/path", venv_python="/any/path/.venv/bin/python")

        server_config = config["mcpServers"]["osiris"]
        assert server_config["command"] == "/bin/bash"

    def test_bash_args_structure(self):
        """Test that bash args follow correct structure: [-lc, '<command>']."""
        config = build_claude_clients_snippet(
            base_path="/home/user/osiris", venv_python="/home/user/osiris/.venv/bin/python"
        )

        server_config = config["mcpServers"]["osiris"]
        args = server_config["args"]

        # Verify args is a list with 2 elements
        assert isinstance(args, list)
        assert len(args) == 2

        # First arg is bash flags
        assert args[0] == "-lc"

        # Second arg is the command string
        assert isinstance(args[1], str)
        assert args[1].startswith("cd ")
        assert " && exec " in args[1]
        assert args[1].endswith("-m osiris.cli.mcp_entrypoint")

    def test_osiris_home_is_base_path(self):
        """Test that OSIRIS_HOME is set to base_path directly."""
        base_path = "/opt/osiris"
        config = build_claude_clients_snippet(base_path=base_path, venv_python="/opt/osiris/.venv/bin/python")

        server_config = config["mcpServers"]["osiris"]
        assert server_config["env"]["OSIRIS_HOME"] == base_path

    def test_pythonpath_is_base_path(self):
        """Test that PYTHONPATH is set to base_path."""
        base_path = "/var/lib/osiris"
        config = build_claude_clients_snippet(base_path=base_path, venv_python="/var/lib/osiris/.venv/bin/python")

        server_config = config["mcpServers"]["osiris"]
        assert server_config["env"]["PYTHONPATH"] == base_path

    def test_pure_function_no_side_effects(self):
        """Test that function is pure - same inputs produce same outputs."""
        config1 = build_claude_clients_snippet(base_path="/Users/test", venv_python="/Users/test/.venv/bin/python")

        config2 = build_claude_clients_snippet(base_path="/Users/test", venv_python="/Users/test/.venv/bin/python")

        # Both calls should produce identical results
        assert config1 == config2

    def test_json_serializable(self):
        """Test that returned dict is JSON serializable."""
        import json

        config = build_claude_clients_snippet(
            base_path="/Users/me/osiris", venv_python="/Users/me/osiris/.venv/bin/python"
        )

        # Should not raise exception
        json_str = json.dumps(config, indent=2)
        assert isinstance(json_str, str)
        assert len(json_str) > 0

        # Should be able to parse back
        parsed = json.loads(json_str)
        assert parsed == config

    def test_minimal_env_vars(self):
        """Test that only required env vars are set (OSIRIS_HOME, PYTHONPATH)."""
        config = build_claude_clients_snippet(base_path="/home/osiris", venv_python="/home/osiris/.venv/bin/python")

        server_config = config["mcpServers"]["osiris"]
        env_vars = server_config["env"]

        # Should have exactly these 2 env vars
        assert set(env_vars.keys()) == {"OSIRIS_HOME", "PYTHONPATH"}

    def test_different_venv_python_paths(self):
        """Test with various venv Python path styles."""
        test_cases = [
            # Standard .venv
            ("/home/user/osiris", "/home/user/osiris/.venv/bin/python"),
            # Custom venv name
            ("/home/user/osiris", "/home/user/osiris/venv/bin/python"),
            # System Python (no venv)
            ("/home/user/osiris", "/usr/bin/python3"),
            # Conda env
            ("/home/user/osiris", "/opt/conda/envs/osiris/bin/python"),
        ]

        for base_path, venv_python in test_cases:
            config = build_claude_clients_snippet(base_path=base_path, venv_python=venv_python)

            server_config = config["mcpServers"]["osiris"]

            # Verify venv_python appears in args
            assert venv_python in server_config["args"][1]

            # Verify structure remains consistent
            assert server_config["command"] == "/bin/bash"
            assert server_config["transport"]["type"] == "stdio"
            assert server_config["env"]["PYTHONPATH"] == base_path

    def test_exec_prefix_in_bash_command(self):
        """Test that exec is used in bash command for proper signal handling."""
        config = build_claude_clients_snippet(
            base_path="/Users/me/osiris", venv_python="/Users/me/osiris/.venv/bin/python"
        )

        server_config = config["mcpServers"]["osiris"]
        bash_command = server_config["args"][1]

        # Should use 'exec' to replace shell process
        assert "exec " in bash_command
        assert bash_command.count("exec ") == 1  # Only one exec


class TestPlatformAwareShell:
    """Test suite for platform-specific shell command generation."""

    @patch("osiris.mcp.clients_config.platform.system")
    def test_unix_uses_bash_with_lc_flags(self, mock_system):
        """Test that Unix/Linux/macOS uses /bin/bash with -lc flags."""
        mock_system.return_value = "Linux"

        config = build_claude_clients_snippet(
            base_path="/home/user/osiris", venv_python="/home/user/osiris/.venv/bin/python"
        )

        server_config = config["mcpServers"]["osiris"]

        # Verify Unix shell
        assert server_config["command"] == "/bin/bash"

        # Verify Unix args structure
        assert len(server_config["args"]) == 2
        assert server_config["args"][0] == "-lc"

        # Verify Unix command uses 'exec' and 'cd' (not 'cd /d')
        bash_command = server_config["args"][1]
        assert bash_command.startswith("cd ")
        assert " && exec " in bash_command
        assert "cd /d" not in bash_command  # Windows-specific flag should not appear

    @patch("osiris.mcp.clients_config.platform.system")
    def test_macos_uses_bash_with_lc_flags(self, mock_system):
        """Test that macOS uses /bin/bash with -lc flags."""
        mock_system.return_value = "Darwin"

        config = build_claude_clients_snippet(
            base_path="/Users/me/osiris", venv_python="/Users/me/osiris/.venv/bin/python"
        )

        server_config = config["mcpServers"]["osiris"]

        # Verify macOS shell
        assert server_config["command"] == "/bin/bash"

        # Verify macOS args structure
        assert len(server_config["args"]) == 2
        assert server_config["args"][0] == "-lc"

        # Verify macOS command uses 'exec'
        bash_command = server_config["args"][1]
        assert " && exec " in bash_command

    @patch("osiris.mcp.clients_config.platform.system")
    def test_windows_uses_cmd_with_c_flag(self, mock_system):
        """Test that Windows uses cmd.exe with /c flag."""
        mock_system.return_value = "Windows"

        config = build_claude_clients_snippet(
            base_path="C:\\Users\\me\\osiris", venv_python="C:\\Users\\me\\osiris\\.venv\\Scripts\\python.exe"
        )

        server_config = config["mcpServers"]["osiris"]

        # Verify Windows shell
        assert server_config["command"] == "cmd.exe"

        # Verify Windows args structure
        assert len(server_config["args"]) == 2
        assert server_config["args"][0] == "/c"

        # Verify Windows command uses 'cd /d' (not 'cd' or 'exec')
        cmd_command = server_config["args"][1]
        assert cmd_command.startswith("cd /d ")
        assert " && " in cmd_command
        assert "exec " not in cmd_command  # Windows doesn't use exec

    @patch("osiris.mcp.clients_config.platform.system")
    def test_windows_paths_with_spaces(self, mock_system):
        """Test that Windows paths with spaces are properly quoted."""
        mock_system.return_value = "Windows"

        config = build_claude_clients_snippet(
            base_path="C:\\Program Files\\osiris", venv_python="C:\\Program Files\\osiris\\.venv\\Scripts\\python.exe"
        )

        server_config = config["mcpServers"]["osiris"]

        # Verify Windows shell
        assert server_config["command"] == "cmd.exe"

        # Verify paths with spaces are quoted
        cmd_command = server_config["args"][1]
        assert "'" in cmd_command or '"' in cmd_command  # Should contain quotes

        # Verify base_path appears in command
        assert "C:\\Program Files\\osiris" in cmd_command or "'C:\\Program Files\\osiris'" in cmd_command

    @patch("osiris.mcp.clients_config.platform.system")
    def test_windows_env_vars_unchanged(self, mock_system):
        """Test that Windows uses same OSIRIS_HOME and PYTHONPATH as Unix."""
        mock_system.return_value = "Windows"

        base_path = "C:\\Users\\me\\osiris"
        config = build_claude_clients_snippet(
            base_path=base_path, venv_python="C:\\Users\\me\\osiris\\.venv\\Scripts\\python.exe"
        )

        server_config = config["mcpServers"]["osiris"]

        # Verify env vars are consistent across platforms
        assert server_config["env"]["OSIRIS_HOME"] == base_path
        assert server_config["env"]["PYTHONPATH"] == base_path

    @patch("osiris.mcp.clients_config.platform.system")
    def test_unix_and_windows_transport_consistent(self, mock_system):
        """Test that transport is 'stdio' on all platforms."""
        for platform_name in ["Linux", "Darwin", "Windows"]:
            mock_system.return_value = platform_name

            config = build_claude_clients_snippet(base_path="/any/path", venv_python="/any/path/python")

            server_config = config["mcpServers"]["osiris"]
            assert server_config["transport"]["type"] == "stdio"

    @patch("osiris.mcp.clients_config.platform.system")
    def test_platform_detection_called_once_per_call(self, mock_system):
        """Test that platform.system() is called during config generation."""
        mock_system.return_value = "Linux"

        build_claude_clients_snippet(base_path="/home/user/osiris", venv_python="/home/user/osiris/.venv/bin/python")

        # Verify platform detection was called
        assert mock_system.call_count > 0

    @patch("osiris.mcp.clients_config.platform.system")
    def test_windows_cd_flag_is_d_not_default(self, mock_system):
        """Test that Windows uses 'cd /d' for drive-aware directory change."""
        mock_system.return_value = "Windows"

        config = build_claude_clients_snippet(
            base_path="D:\\projects\\osiris", venv_python="D:\\projects\\osiris\\.venv\\Scripts\\python.exe"
        )

        server_config = config["mcpServers"]["osiris"]
        cmd_command = server_config["args"][1]

        # Verify 'cd /d' is used (allows changing drives on Windows)
        assert cmd_command.startswith("cd /d ")

    @patch("osiris.mcp.clients_config.platform.system")
    def test_unix_no_exec_on_windows(self, mock_system):
        """Test that 'exec' is used on Unix but not on Windows."""
        # Test Unix
        mock_system.return_value = "Linux"
        unix_config = build_claude_clients_snippet(base_path="/home/user/osiris", venv_python="/usr/bin/python3")
        unix_command = unix_config["mcpServers"]["osiris"]["args"][1]
        assert "exec " in unix_command

        # Test Windows
        mock_system.return_value = "Windows"
        win_config = build_claude_clients_snippet(
            base_path="C:\\Users\\me\\osiris", venv_python="C:\\Python39\\python.exe"
        )
        win_command = win_config["mcpServers"]["osiris"]["args"][1]
        assert "exec " not in win_command
