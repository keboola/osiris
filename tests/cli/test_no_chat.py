"""
Tests to ensure chat command remains deprecated.
"""

import json
import subprocess
import sys


def test_chat_command_deprecated():
    """Test that chat command returns deprecation error."""
    result = subprocess.run([sys.executable, "osiris.py", "chat"], check=False, capture_output=True, text=True)

    # Should exit with error
    assert result.returncode == 1

    # Should show deprecation message
    assert "deprecated" in result.stdout.lower()
    assert "osiris v0.5.0" in result.stdout.lower()


def test_chat_command_deprecated_json():
    """Test that chat command returns deprecation error in JSON format."""
    result = subprocess.run([sys.executable, "osiris.py", "chat", "--json"], check=False, capture_output=True, text=True)

    # Should exit with error
    assert result.returncode == 1

    # Should return JSON error
    output = json.loads(result.stdout)
    assert output["error"] == "deprecated"
    assert "chat command deprecated" in output["message"]
    assert "migration" in output


def test_help_no_chat():
    """Test that help output does not mention chat command."""
    result = subprocess.run([sys.executable, "osiris.py", "--help"], check=False, capture_output=True, text=True)

    # Should succeed
    assert result.returncode == 0

    # Should not mention chat in commands list
    # Allow "MCP" but not standalone "chat"
    lines = result.stdout.split("\n")
    for line in lines:
        # Skip lines that are about MCP
        if "MCP" in line or "Model Context Protocol" in line:
            continue
        # Check that 'chat' doesn't appear as a standalone command
        if "chat" in line.lower():
            # This should only be in historical context or MCP-related
            assert (
                "deprecated" in line.lower() or "migration" in line.lower()
            ), f"Found unexpected 'chat' reference: {line}"


def test_help_json_no_chat():
    """Test that JSON help output does not list chat as available command."""
    result = subprocess.run([sys.executable, "osiris.py", "--help", "--json"], check=False, capture_output=True, text=True)

    # Should succeed
    assert result.returncode == 0

    # Parse JSON and check commands list
    output = json.loads(result.stdout)
    assert "chat" not in output.get("commands", [])
