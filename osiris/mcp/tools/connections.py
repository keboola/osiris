"""
MCP tools for connection management - CLI-first adapter.

This module delegates all operations to CLI subcommands, ensuring
that secrets are never accessed directly from the MCP process.
"""

import logging
import time
from typing import Any

from osiris.mcp.cli_bridge import run_cli_json
from osiris.mcp.errors import ErrorFamily, OsirisError
from osiris.mcp.metrics_helper import add_metrics

logger = logging.getLogger(__name__)


class ConnectionsTools:
    """Tools for managing database connections via CLI delegation."""

    def __init__(self, audit_logger=None):
        """Initialize connections tools."""
        # No caching - delegate everything to CLI
        self.audit = audit_logger

    async def list(self, args: dict[str, Any]) -> dict[str, Any]:
        """
        List all configured database connections via CLI delegation.

        Args:
            args: Tool arguments (none required)

        Returns:
            Dictionary with connection information
        """
        start_time = time.time()
        correlation_id = self.audit.make_correlation_id() if self.audit else "unknown"

        try:
            # Delegate to CLI: osiris mcp connections list --json
            result = await run_cli_json(["mcp", "connections", "list"])

            # Add metrics to response
            return add_metrics(result, correlation_id, start_time, args)

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
            ) from e

    async def doctor(self, args: dict[str, Any]) -> dict[str, Any]:
        """
        Diagnose connection issues via CLI delegation.

        Args:
            args: Tool arguments with connection_id

        Returns:
            Dictionary with diagnostic information
        """
        start_time = time.time()
        correlation_id = self.audit.make_correlation_id() if self.audit else "unknown"

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

            # Add metrics to response
            return add_metrics(result, correlation_id, start_time, args)

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
            ) from e
