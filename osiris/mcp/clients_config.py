"""
Claude Desktop client configuration builder.

Generates MCP client configuration snippets for Claude Desktop with proper
bash wrapper for shell environment and resolved absolute paths.

This module is a pure function with no side effects and no secret access.
"""


def build_claude_clients_snippet(base_path: str, venv_python: str) -> dict:
    """
    Build Claude Desktop configuration snippet.

    Args:
        base_path: Absolute path to repository root
        venv_python: Absolute path to Python executable in venv

    Returns:
        dict: Claude Desktop config in mcpServers format with:
            - command: "/bin/bash"
            - args: bash wrapper with -lc for proper shell env
            - transport: stdio
            - env: OSIRIS_HOME and PYTHONPATH

    Example:
        >>> config = build_claude_clients_snippet(
        ...     base_path="/Users/me/osiris",
        ...     venv_python="/Users/me/osiris/.venv/bin/python"
        ... )
        >>> config["mcpServers"]["osiris"]["command"]
        '/bin/bash'
        >>> config["mcpServers"]["osiris"]["transport"]["type"]
        'stdio'
    """
    # Resolve OSIRIS_HOME: base_path/testing_env
    osiris_home = f"{base_path}/testing_env"

    # Build config snippet with bash wrapper
    return {
        "mcpServers": {
            "osiris": {
                "command": "/bin/bash",
                "args": [
                    "-lc",
                    f"cd {base_path} && exec {venv_python} -m osiris.cli.mcp_entrypoint"
                ],
                "transport": {
                    "type": "stdio"
                },
                "env": {
                    "OSIRIS_HOME": osiris_home,
                    "PYTHONPATH": base_path
                }
            }
        }
    }
