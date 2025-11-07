"""
Chat command deprecation handler for Osiris v0.5.0.

Per ADR-0036, the chat interface is deprecated in favor of MCP.
"""

import json

import osiris


def handle_chat_deprecation(json_output: bool = False) -> int:
    """
    Handle deprecated chat command with migration guidance.

    Args:
        json_output: If True, output JSON format error

    Returns:
        Exit code 1 (failure)
    """
    if json_output:
        error_response = {
            "error": "deprecated",
            "message": "chat command deprecated. Use 'osiris mcp' or Claude Desktop MCP integration",
            "migration": "docs/migration/chat-to-mcp.md",
        }
        print(json.dumps(error_response))
    else:
        print(f"Error: 'chat' command is deprecated in Osiris v{osiris.__version__}.")
        print("Use 'osiris mcp' (server) or Claude Desktop MCP integration.")
        print("See docs/migration/chat-to-mcp.md")

    return 1
