"""
Tests for osiris.mcp.clients_config module.

Verifies that build_claude_clients_snippet produces the correct JSON structure
for Claude Desktop configuration with direct Python invocation using --base-path parameter.
"""

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

        # Verify command is the Python path
        assert server_config["command"] == "/Users/me/osiris/.venv/bin/python"

        # Verify args use --base-path parameter
        assert server_config["args"] == ["-m", "osiris.cli.mcp_entrypoint", "--base-path", "/Users/me/osiris"]

        # Verify transport
        assert server_config["transport"] == {"type": "stdio"}

        # Verify NO env vars
        assert "env" not in server_config

    def test_venv_python_path_with_spaces(self):
        """Test that paths with spaces work correctly without shell quoting."""
        config = build_claude_clients_snippet(
            base_path="/Users/me/my project/osiris", venv_python="/Users/me/my project/osiris/.venv/bin/python"
        )

        server_config = config["mcpServers"]["osiris"]

        # Verify command path with spaces (no quoting needed for direct Python invocation)
        assert server_config["command"] == "/Users/me/my project/osiris/.venv/bin/python"

        # Verify args with spaces in base_path (no quoting needed)
        assert server_config["args"] == [
            "-m",
            "osiris.cli.mcp_entrypoint",
            "--base-path",
            "/Users/me/my project/osiris",
        ]

        # Verify NO env vars
        assert "env" not in server_config

    def test_transport_is_stdio(self):
        """Test that transport type is always stdio."""
        config = build_claude_clients_snippet(base_path="/any/path", venv_python="/any/path/.venv/bin/python")

        server_config = config["mcpServers"]["osiris"]
        assert server_config["transport"]["type"] == "stdio"
        assert "type" in server_config["transport"]
        assert len(server_config["transport"]) == 1  # Only 'type' field

    def test_command_is_python(self):
        """Test that command is the venv_python path."""
        config = build_claude_clients_snippet(base_path="/any/path", venv_python="/any/path/.venv/bin/python")

        server_config = config["mcpServers"]["osiris"]
        assert server_config["command"] == "/any/path/.venv/bin/python"

    def test_args_structure(self):
        """Test that args follow correct structure: ['-m', 'osiris.cli.mcp_entrypoint', '--base-path', <path>]."""
        config = build_claude_clients_snippet(
            base_path="/home/user/osiris", venv_python="/home/user/osiris/.venv/bin/python"
        )

        server_config = config["mcpServers"]["osiris"]
        args = server_config["args"]

        # Verify args is a list with 4 elements
        assert isinstance(args, list)
        assert len(args) == 4

        # First arg is -m flag
        assert args[0] == "-m"

        # Second arg is module path
        assert args[1] == "osiris.cli.mcp_entrypoint"

        # Third arg is --base-path flag
        assert args[2] == "--base-path"

        # Fourth arg is the base path
        assert args[3] == "/home/user/osiris"

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

    def test_no_env_vars(self):
        """Test that no environment variables are set in the configuration."""
        config = build_claude_clients_snippet(base_path="/home/osiris", venv_python="/home/osiris/.venv/bin/python")

        server_config = config["mcpServers"]["osiris"]

        # Should have no env key at all
        assert "env" not in server_config

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

            # Verify command is the venv_python path
            assert server_config["command"] == venv_python

            # Verify args structure
            assert server_config["args"] == ["-m", "osiris.cli.mcp_entrypoint", "--base-path", base_path]

            # Verify transport remains consistent
            assert server_config["transport"]["type"] == "stdio"

            # Verify no env vars
            assert "env" not in server_config

    def test_base_path_parameter_position(self):
        """Test that --base-path parameter is correctly positioned in args."""
        config = build_claude_clients_snippet(
            base_path="/Users/me/osiris", venv_python="/Users/me/osiris/.venv/bin/python"
        )

        server_config = config["mcpServers"]["osiris"]
        args = server_config["args"]

        # Find --base-path flag
        base_path_index = args.index("--base-path")

        # Next element should be the actual path
        assert args[base_path_index + 1] == "/Users/me/osiris"

    def test_minimal_config_structure(self):
        """Test that config contains only required fields (command, args, transport)."""
        config = build_claude_clients_snippet(
            base_path="/Users/me/osiris", venv_python="/Users/me/osiris/.venv/bin/python"
        )

        server_config = config["mcpServers"]["osiris"]

        # Should have exactly these 3 keys
        assert set(server_config.keys()) == {"command", "args", "transport"}
