"""
MCP tools for AIOP artifact management - CLI-first adapter.

This module provides read-only access to AIOP artifacts via CLI delegation.
All operations delegate to existing CLI commands, ensuring no AIOP logic is
reimplemented in the MCP layer.
"""

import logging
import time
from typing import Any

from osiris.mcp import cli_bridge
from osiris.mcp.errors import ErrorFamily, OsirisError
from osiris.mcp.metrics_helper import add_metrics

logger = logging.getLogger(__name__)


class AIOPTools:
    """Tools for reading AIOP artifacts via CLI delegation."""

    def __init__(self, audit_logger=None):
        """Initialize AIOP tools."""
        # No caching - delegate everything to CLI
        self.audit = audit_logger

    async def list(self, args: dict[str, Any]) -> dict[str, Any]:
        """
        List AIOP runs via CLI delegation.

        Args:
            args: Tool arguments (optional: pipeline, profile)

        Returns:
            Dictionary with list of AIOP runs and metadata
        """
        start_time = time.time()
        correlation_id = self.audit.make_correlation_id() if self.audit else "unknown"

        try:
            # Build CLI command: osiris mcp aiop list --json
            cli_args = ["mcp", "aiop", "list"]

            # Add optional filters
            if args.get("pipeline"):
                cli_args.extend(["--pipeline", args["pipeline"]])
            if args.get("profile"):
                cli_args.extend(["--profile", args["profile"]])

            # Delegate to CLI (returns wrapped list with metadata)
            cli_response = await cli_bridge.run_cli_json(cli_args)

            # Extract data from wrapped response (CLI bridge wraps arrays in {"data": ...})
            runs = cli_response.get("data", []) if isinstance(cli_response, dict) else []

            # Wrap list in dict for MCP protocol compliance
            response = {"runs": runs, "count": len(runs)}

            # Add metrics to response
            return add_metrics(response, correlation_id, start_time, args)

        except OsirisError:
            # Re-raise OsirisError as-is
            raise
        except Exception as e:
            logger.error(f"Error listing AIOP runs: {e}")
            raise OsirisError(
                ErrorFamily.SEMANTIC,
                f"Failed to list AIOP runs: {str(e)}",
                path=["aiop", "list"],
                suggest="Check AIOP index and filesystem configuration",
            ) from e

    async def show(self, args: dict[str, Any]) -> dict[str, Any]:
        """
        Show AIOP summary for a specific run via CLI delegation.

        Args:
            args: Tool arguments with run_id (required)

        Returns:
            Dictionary with AIOP summary (core.json + run_card)
        """
        start_time = time.time()
        correlation_id = self.audit.make_correlation_id() if self.audit else "unknown"

        run_id = args.get("run_id")
        if not run_id:
            raise OsirisError(
                ErrorFamily.SCHEMA,
                "run_id is required",
                path=["run_id"],
                suggest="Provide a run ID from aiop_list results",
            )

        try:
            # Delegate to CLI: osiris mcp aiop show --run <run_id> --json
            result = await cli_bridge.run_cli_json(["mcp", "aiop", "show", "--run", run_id])

            # Add metrics to response
            return add_metrics(result, correlation_id, start_time, args)

        except OsirisError:
            # Re-raise OsirisError as-is
            raise
        except Exception as e:
            logger.error(f"Error showing AIOP run: {e}")
            raise OsirisError(
                ErrorFamily.SEMANTIC,
                f"Failed to show AIOP run: {str(e)}",
                path=["aiop", "show"],
                suggest="Check run ID format and AIOP artifact existence",
            ) from e
