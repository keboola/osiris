"""
MCP tools for connection management - CLI-first adapter.

This module delegates all operations to CLI subcommands, ensuring
that secrets are never accessed directly from the MCP process.
"""

import logging
from typing import Any

from osiris.mcp.cli_bridge import run_cli_json
from osiris.mcp.errors import ErrorFamily, OsirisError

logger = logging.getLogger(__name__)


class ConnectionsTools:
    """Tools for managing database connections via CLI delegation."""

    def __init__(self):
        """Initialize connections tools."""
        # No caching - delegate everything to CLI
        pass

    async def list(self, args: dict[str, Any]) -> dict[str, Any]:
        """
        List all configured database connections via CLI delegation.

        Args:
            args: Tool arguments (none required)

        Returns:
            Dictionary with connection information
        """
        try:
            # Delegate to CLI: osiris mcp connections list --json
            result = await run_cli_json(["mcp", "connections", "list"])

            # CLI already returns the correct format
            return result

        except OsirisError:
            # Re-raise OsirisError as-is
            raise
        except Exception as e:
            logger.error(f"Error listing connections: {e}")
            raise OsirisError(
                ErrorFamily.SEMANTIC,
                f"Failed to list connections: {str(e)}",
                path=["connections"],
                suggest="Check CLI bridge and osiris_connections.yaml file",
            )

    async def doctor(self, args: dict[str, Any]) -> dict[str, Any]:
        """
        Diagnose connection issues via CLI delegation.

        Args:
            args: Tool arguments with connection_id

        Returns:
            Dictionary with diagnostic information
        """
        connection_id = args.get("connection_id")
        if not connection_id:
            raise OsirisError(
                ErrorFamily.SCHEMA,
                "connection_id is required",
                path=["connection_id"],
                suggest="Provide a connection reference like @mysql.default",
            )

        try:
            # Ensure connection_id has @ prefix
            if not connection_id.startswith("@"):
                connection_id = f"@{connection_id}"

            # Delegate to CLI: osiris mcp connections doctor --connection-id @mysql.default --json
            result = await run_cli_json(["mcp", "connections", "doctor", "--connection-id", connection_id])

            # CLI already returns the correct format
            return result

        except OsirisError:
            # Re-raise OsirisError as-is
            raise
        except Exception as e:
            logger.error(f"Error diagnosing connection: {e}")
            raise OsirisError(
                ErrorFamily.SEMANTIC,
                f"Failed to diagnose connection: {str(e)}",
                path=["connection_id"],
                suggest="Check the connection reference format and CLI bridge",
            )
