"""
Tests for osiris.mcp.clients_config module.

Verifies that build_claude_clients_snippet produces the correct JSON structure
for Claude Desktop configuration with proper bash wrapper, transport, and paths.
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
        assert server_config["env"]["OSIRIS_HOME"] == "/Users/me/osiris/testing_env"
        assert server_config["env"]["PYTHONPATH"] == "/Users/me/osiris"

    def test_venv_python_path_with_spaces(self):
        """Test that paths with spaces are handled correctly in bash args."""
        config = build_claude_clients_snippet(
            base_path="/Users/me/my project/osiris", venv_python="/Users/me/my project/osiris/.venv/bin/python"
        )

        server_config = config["mcpServers"]["osiris"]

        # Verify paths with spaces are included in args (bash -lc will handle quoting)
        expected_args = [
            "-lc",
            "cd /Users/me/my project/osiris && exec /Users/me/my project/osiris/.venv/bin/python -m osiris.cli.mcp_entrypoint",
        ]
        assert server_config["args"] == expected_args

        # Verify env vars also have paths with spaces
        assert server_config["env"]["OSIRIS_HOME"] == "/Users/me/my project/osiris/testing_env"
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

    def test_osiris_home_is_base_path_plus_testing_env(self):
        """Test that OSIRIS_HOME is always base_path/testing_env."""
        base_path = "/opt/osiris"
        config = build_claude_clients_snippet(base_path=base_path, venv_python="/opt/osiris/.venv/bin/python")

        server_config = config["mcpServers"]["osiris"]
        assert server_config["env"]["OSIRIS_HOME"] == f"{base_path}/testing_env"

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
