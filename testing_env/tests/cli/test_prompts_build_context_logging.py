"""Test logging behavior for prompts build-context command."""

import json
import subprocess
import sys
from pathlib import Path

import pytest


class TestPromptsLogging:
    """Test that prompts build-context has clean console output."""

    def test_default_clean_output(self, tmp_path):
        """Test that default run shows clean output without DEBUG messages."""
        # Run the command
        result = subprocess.run(
            [sys.executable, "osiris.py", "prompts", "build-context", "--logs-dir", str(tmp_path)],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent.parent,  # Run from project root
        )

        # Check stdout
        stdout = result.stdout
        
        # Should contain success message
        assert "✓ Context built successfully" in stdout
        assert "Components:" in stdout
        assert "Size:" in stdout
        assert "Estimated tokens:" in stdout
        assert "Output:" in stdout
        
        # Should NOT contain DEBUG messages
        assert "Loaded schema" not in stdout
        assert "Loaded component spec" not in stdout
        assert "DEBUG" not in stdout
        
        # Extract session ID from stdout
        lines = stdout.strip().split('\n')
        session_line = [line for line in lines if line.startswith("Session:")][0]
        session_id = session_line.split(": ")[1]
        
        # Check that session log file contains DEBUG entries
        session_log = tmp_path / session_id / "osiris.log"
        assert session_log.exists(), f"Session log not found at {session_log}"
        
        log_content = session_log.read_text()
        # Should contain DEBUG entries in log file
        assert "Loaded schema" in log_content or "Loaded component spec" in log_content
        assert "DEBUG" in log_content
    
    def test_debug_flag_shows_output(self, tmp_path):
        """Test that --log-level DEBUG shows DEBUG messages on console."""
        # Run the command with DEBUG flag
        result = subprocess.run(
            [
                sys.executable, 
                "osiris.py", 
                "prompts", 
                "build-context",
                "--log-level", 
                "DEBUG",
                "--logs-dir",
                str(tmp_path),
            ],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent.parent,  # Run from project root
        )
        
        # Check stdout
        stdout = result.stdout
        
        # Should contain success message
        assert "✓ Context built successfully" in stdout
        
        # SHOULD contain DEBUG messages this time
        assert "DEBUG" in stdout
        assert "Loaded schema" in stdout or "Loaded component spec" in stdout
        
        # Extract session ID from stdout
        lines = stdout.strip().split('\n')
        session_line = [line for line in lines if line.startswith("Session:")][0]
        session_id = session_line.split(": ")[1]
        
        # Check that session log file also contains DEBUG entries
        session_log = tmp_path / session_id / "osiris.log"
        assert session_log.exists(), f"Session log not found at {session_log}"
        
        log_content = session_log.read_text()
        # Should contain DEBUG entries in log file
        assert "DEBUG" in log_content
    
    def test_json_output_clean(self, tmp_path):
        """Test that JSON output mode is also clean."""
        # Run the command with JSON output
        result = subprocess.run(
            [
                sys.executable, 
                "osiris.py", 
                "prompts", 
                "build-context",
                "--json",
                "--logs-dir",
                str(tmp_path),
            ],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent.parent,  # Run from project root
        )
        
        # Check stdout - should be valid JSON
        stdout = result.stdout.strip()
        
        # Should NOT contain DEBUG messages
        assert "Loaded schema" not in stdout
        assert "Loaded component spec" not in stdout
        assert "DEBUG" not in stdout
        
        # Should be valid JSON
        try:
            data = json.loads(stdout)
            assert "success" in data
            assert data["success"] is True
            assert "components" in data
            assert "size_bytes" in data
            assert "token_estimate" in data
            assert "session_id" in data
        except json.JSONDecodeError:
            pytest.fail(f"Output is not valid JSON: {stdout}")
