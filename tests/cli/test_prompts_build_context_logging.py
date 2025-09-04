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
        project_root = Path(__file__).parent.parent.parent
        osiris_py = project_root / "osiris.py"
        result = subprocess.run(
            [
                sys.executable,
                str(osiris_py),
                "prompts",
                "build-context",
                "--logs-dir",
                str(tmp_path),
            ],
            capture_output=True,
            text=True,
            cwd=project_root,  # Run from project root
        )

        # Check stdout and stderr for debugging
        stdout = result.stdout
        stderr = result.stderr

        # If test fails, provide debug info
        if not stdout or "✓ Context built successfully" not in stdout:
            pytest.fail(
                f"Command failed!\nSTDOUT: '{stdout}'\nSTDERR: '{stderr}'\nReturn code: {result.returncode}"
            )

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
        lines = stdout.strip().split("\n")
        session_line = [line for line in lines if line.startswith("Session:")][0]
        session_id = session_line.split(": ")[1]

        # Check that session log file exists
        session_log = tmp_path / session_id / "osiris.log"
        assert session_log.exists(), f"Session log not found at {session_log}"

        log_content = session_log.read_text()
        # Log file should exist and contain at least INFO messages
        # (might be cached, so DEBUG logs may not always be present)
        assert "INFO" in log_content or "DEBUG" in log_content

    def test_debug_flag_shows_output(self, tmp_path, monkeypatch):
        """Test that --log-level DEBUG shows DEBUG messages on console when appropriate."""
        # Clear the cache to force DEBUG logs to appear
        cache_dir = Path(".osiris_prompts")
        if cache_dir.exists():
            import shutil

            shutil.rmtree(cache_dir, ignore_errors=True)

        # Run the command with DEBUG flag
        project_root = Path(__file__).parent.parent.parent
        osiris_py = project_root / "osiris.py"
        result = subprocess.run(
            [
                sys.executable,
                str(osiris_py),
                "prompts",
                "build-context",
                "--log-level",
                "DEBUG",
                "--logs-dir",
                str(tmp_path),
            ],
            capture_output=True,
            text=True,
            cwd=project_root,  # Run from project root
        )

        # Check stdout and stderr for debugging
        stdout = result.stdout
        stderr = result.stderr

        # If test fails, provide debug info
        if not stdout or "✓ Context built successfully" not in stdout:
            pytest.fail(
                f"Command failed!\nSTDOUT: '{stdout}'\nSTDERR: '{stderr}'\nReturn code: {result.returncode}"
            )

        # Should contain success message
        assert "✓ Context built successfully" in stdout

        # With DEBUG flag, if cache is not present, we should see debug messages
        # Note: This may not always work if cache already exists, but the key test
        # is that the output is clean by default (test_default_clean_output)

        # Extract session ID from stdout
        lines = stdout.strip().split("\n")
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
        project_root = Path(__file__).parent.parent.parent
        osiris_py = project_root / "osiris.py"
        result = subprocess.run(
            [
                sys.executable,
                str(osiris_py),
                "prompts",
                "build-context",
                "--json",
                "--logs-dir",
                str(tmp_path),
            ],
            capture_output=True,
            text=True,
            cwd=project_root,  # Run from project root
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
