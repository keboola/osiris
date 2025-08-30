"""Comprehensive test for all Osiris commands with --json and --help support."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


class TestAllCommandsJSON:
    """Test that all commands support --json and --help flags properly."""

    @pytest.fixture
    def osiris_path(self):
        """Get the path to osiris.py."""
        return Path(__file__).parent.parent.parent / "osiris.py"

    def run_command(self, osiris_path, *args):
        """Run an osiris command and return stdout."""
        result = subprocess.run(
            [sys.executable, str(osiris_path)] + list(args),
            capture_output=True,
            text=True,
            cwd=osiris_path.parent,
        )
        return result.stdout, result.stderr, result.returncode

    def test_discover_all_commands(self, osiris_path):
        """Discover all available commands from main help."""
        # First, test that main help works
        stdout, stderr, code = self.run_command(osiris_path, "--help")
        assert "Commands" in stdout
        assert "init" in stdout
        assert "validate" in stdout
        assert "chat" in stdout
        assert "run" in stdout
        assert "dump-prompts" in stdout

        # Test main help with JSON (should show error since no command)
        stdout, stderr, code = self.run_command(osiris_path, "--json", "--help")
        if stdout.strip():  # Only parse if there's output
            data = json.loads(stdout)
            assert "available_commands" in data or "error" in data

    def test_init_command_help(self, osiris_path):
        """Test init command help with and without JSON."""
        # Test regular help
        stdout, stderr, code = self.run_command(osiris_path, "init", "--help")
        assert "osiris init" in stdout.lower()
        assert "--json" in stdout
        assert "--help" in stdout

        # Test JSON help
        stdout, stderr, code = self.run_command(osiris_path, "init", "--help", "--json")
        data = json.loads(stdout)
        assert data["command"] == "init"
        assert "options" in data
        assert "--json" in data["options"]
        assert "--help" in data["options"]

        # Test with global --json flag
        stdout, stderr, code = self.run_command(osiris_path, "--json", "init", "--help")
        data = json.loads(stdout)
        assert data["command"] == "init"

    def test_validate_command_help(self, osiris_path):
        """Test validate command help with and without JSON."""
        # Test regular help
        stdout, stderr, code = self.run_command(osiris_path, "validate", "--help")
        assert "osiris validate" in stdout.lower()
        assert "--json" in stdout
        assert "--config" in stdout

        # Test JSON help
        stdout, stderr, code = self.run_command(osiris_path, "validate", "--help", "--json")
        data = json.loads(stdout)
        assert data["command"] == "validate"
        assert "options" in data
        assert "--json" in data["options"]
        assert "--config FILE" in data["options"]

        # Test with global --json flag
        stdout, stderr, code = self.run_command(osiris_path, "--json", "validate", "--help")
        data = json.loads(stdout)
        assert data["command"] == "validate"

    def test_chat_command_help(self, osiris_path):
        """Test chat command help with and without JSON."""
        # Test regular help
        stdout, stderr, code = self.run_command(osiris_path, "chat", "--help")
        assert "conversational" in stdout.lower()
        assert "--json" in stdout
        assert "--session-id" in stdout

        # Test JSON help
        stdout, stderr, code = self.run_command(osiris_path, "chat", "--help", "--json")
        data = json.loads(stdout)
        assert data["command"] == "chat"
        assert "options" in data
        assert "--json" in data["options"]
        assert "--session-id, -s" in data["options"]

    def test_run_command_help(self, osiris_path):
        """Test run command help with and without JSON."""
        # Test regular help
        stdout, stderr, code = self.run_command(osiris_path, "run", "--help")
        assert "osiris run" in stdout.lower()
        assert "--json" in stdout
        assert "--dry-run" in stdout

        # Test JSON help
        stdout, stderr, code = self.run_command(osiris_path, "run", "--help", "--json")
        data = json.loads(stdout)
        assert data["command"] == "run"
        assert "options" in data
        assert "--json" in data["options"]
        assert "--dry-run" in data["options"]

        # Test with global --json flag
        stdout, stderr, code = self.run_command(osiris_path, "--json", "run", "--help")
        data = json.loads(stdout)
        assert data["command"] == "run"

    def test_dump_prompts_command_help(self, osiris_path):
        """Test dump-prompts command help with and without JSON."""
        # Test regular help
        stdout, stderr, code = self.run_command(osiris_path, "dump-prompts", "--help")
        assert "dump-prompts" in stdout.lower() or "export" in stdout.lower()
        assert "--json" in stdout
        assert "--export" in stdout

        # Test JSON help
        stdout, stderr, code = self.run_command(osiris_path, "dump-prompts", "--help", "--json")
        data = json.loads(stdout)
        assert data["command"] == "dump-prompts"
        assert "options" in data
        assert "--json" in data["options"]
        assert "--export" in data["options"]

        # Test with global --json flag
        stdout, stderr, code = self.run_command(osiris_path, "--json", "dump-prompts", "--help")
        data = json.loads(stdout)
        assert data["command"] == "dump-prompts"

    def test_all_commands_have_json_in_help(self, osiris_path):
        """Verify that all commands list --json in their help output."""
        commands = ["init", "validate", "chat", "run", "dump-prompts"]

        for cmd in commands:
            # Test that regular help mentions --json
            stdout, stderr, code = self.run_command(osiris_path, cmd, "--help")
            assert "--json" in stdout, f"Command '{cmd}' help doesn't mention --json option"

            # Test that JSON help works
            stdout, stderr, code = self.run_command(osiris_path, cmd, "--help", "--json")
            try:
                data = json.loads(stdout)
                assert (
                    data["command"] == cmd
                    if cmd != "dump-prompts"
                    else data["command"] == "dump-prompts"
                )
                assert "options" in data
                assert "--json" in data["options"]
            except json.JSONDecodeError:
                pytest.fail(f"Command '{cmd} --help --json' didn't return valid JSON: {stdout}")

    def test_json_output_consistency(self, osiris_path):
        """Test that JSON output has consistent structure across commands."""
        commands = ["init", "validate", "chat", "run", "dump-prompts"]

        for cmd in commands:
            stdout, stderr, code = self.run_command(osiris_path, cmd, "--help", "--json")
            data = json.loads(stdout)

            # All commands should have these fields
            assert "command" in data, f"'{cmd}' JSON help missing 'command' field"
            assert "description" in data, f"'{cmd}' JSON help missing 'description' field"
            assert "usage" in data, f"'{cmd}' JSON help missing 'usage' field"
            assert "options" in data, f"'{cmd}' JSON help missing 'options' field"

            # Options should be a dict
            assert isinstance(data["options"], dict), f"'{cmd}' options should be a dict"

            # Should have examples or similar
            assert any(
                key in data for key in ["examples", "workflow", "discovery_examples"]
            ), f"'{cmd}' JSON help should have examples or workflow"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
