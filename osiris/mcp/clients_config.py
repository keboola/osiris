"""
Claude Desktop client configuration builder.

Generates MCP client configuration snippets for Claude Desktop with proper
shell wrapper for shell environment and resolved absolute paths.

Platform-aware: Uses /bin/bash on Unix, cmd.exe on Windows.

This module is a pure function with no side effects and no secret access.
"""

import platform
import shlex


def build_claude_clients_snippet(base_path: str, venv_python: str) -> dict:
    """
    Build Claude Desktop configuration snippet with platform-aware shell.

    Args:
        base_path: Absolute path to repository root
        venv_python: Absolute path to Python executable in venv

    Returns:
        dict: Claude Desktop config in mcpServers format with:
            - command: Platform-specific shell (/bin/bash or cmd.exe)
            - args: Shell wrapper with proper flags for environment
            - transport: stdio
            - env: OSIRIS_HOME and PYTHONPATH

    Platform Detection:
        - Unix/Linux/macOS: /bin/bash with -lc flags
        - Windows: cmd.exe with /c flag

    Example:
        >>> config = build_claude_clients_snippet(
        ...     base_path="/Users/me/osiris",
        ...     venv_python="/Users/me/osiris/.venv/bin/python"
        ... )
        >>> config["mcpServers"]["osiris"]["command"]
        '/bin/bash'  # or 'cmd.exe' on Windows
        >>> config["mcpServers"]["osiris"]["transport"]["type"]
        'stdio'
    """
    # Resolve OSIRIS_HOME: base_path directly (not base_path/testing_env)
    osiris_home = base_path

    # Platform detection for shell command
    is_windows = platform.system() == "Windows"

    if is_windows:
        # Windows: Use cmd.exe with /c flag and /d for directory change
        command = "cmd.exe"
        shell_command = f"cd /d {shlex.quote(base_path)} && {shlex.quote(venv_python)} -m osiris.cli.mcp_entrypoint"
        args = ["/c", shell_command]
    else:
        # Unix/Linux/macOS: Use /bin/bash with -lc flags
        command = "/bin/bash"
        shell_command = f"cd {shlex.quote(base_path)} && exec {shlex.quote(venv_python)} -m osiris.cli.mcp_entrypoint"
        args = ["-lc", shell_command]

    # Build config snippet with platform-aware shell wrapper
    # Use shlex.quote() to safely handle paths with spaces or special characters
    # (common on macOS/Windows: /Users/My Projects/osiris, C:\Program Files\python.exe)
    return {
        "mcpServers": {
            "osiris": {
                "command": command,
                "args": args,
                "transport": {"type": "stdio"},
                "env": {"OSIRIS_HOME": osiris_home, "PYTHONPATH": base_path},
            }
        }
    }
