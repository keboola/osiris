"""
Claude Desktop client configuration builder.

Generates MCP client configuration snippets for Claude Desktop with portable
command-line invocation using --base-path parameter.

This allows multiple MCP servers to coexist without environment variable conflicts.

This module is a pure function with no side effects and no secret access.
"""


def build_claude_clients_snippet(base_path: str, venv_python: str) -> dict:
    """
    Build Claude Desktop configuration snippet with portable command.

    Args:
        base_path: Absolute path to OSIRIS_HOME (project directory with osiris.yaml)
        venv_python: Absolute path to Python executable in venv

    Returns:
        dict: Claude Desktop config in mcpServers format with:
            - command: Python executable
            - args: Module invocation with --base-path parameter
            - transport: stdio
            - NO environment variables (path passed as parameter)

    Example:
        >>> config = build_claude_clients_snippet(
        ...     base_path="/Users/me/my-project",
        ...     venv_python="/Users/me/my-project/.venv/bin/python"
        ... )
        >>> config["mcpServers"]["osiris"]["command"]
        '/Users/me/my-project/.venv/bin/python'
        >>> config["mcpServers"]["osiris"]["args"]
        ['-m', 'osiris.cli.mcp_entrypoint', '--base-path', '/Users/me/my-project']
    """
    # Build portable config with --base-path parameter
    # This allows multiple MCP servers to coexist without environment variable conflicts
    return {
        "mcpServers": {
            "osiris": {
                "command": venv_python,
                "args": ["-m", "osiris.cli.mcp_entrypoint", "--base-path", base_path],
                "transport": {"type": "stdio"},
            }
        }
    }
