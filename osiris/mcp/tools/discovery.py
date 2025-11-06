"""
MCP tools for database discovery operations - CLI-first adapter.

This module delegates all operations to CLI subcommands, ensuring
that secrets are never accessed directly from the MCP process.
"""

import logging
import time
from typing import Any

from osiris.mcp import cli_bridge
from osiris.mcp.cache import DiscoveryCache
from osiris.mcp.errors import ErrorFamily, OsirisError
from osiris.mcp.metrics_helper import add_metrics

logger = logging.getLogger(__name__)


class DiscoveryTools:
    """Tools for database discovery operations via CLI delegation."""

    def __init__(self, cache: DiscoveryCache | None = None, audit_logger=None):
        """Initialize discovery tools."""
        self.cache = cache or DiscoveryCache()
        self.audit = audit_logger

    async def request(self, args: dict[str, Any]) -> dict[str, Any]:
        """
        Perform database schema discovery via CLI delegation.

        Args:
            args: Tool arguments including connection, component, samples, idempotency_key

        Returns:
            Dictionary with discovery results
        """
        start_time = time.time()
        correlation_id = self.audit.make_correlation_id() if self.audit else "unknown"

        connection = args.get("connection")
        component = args.get("component")
        samples = args.get("samples", 0)
        idempotency_key = args.get("idempotency_key")

        # Validate required fields
        if not connection:
            raise OsirisError(
                ErrorFamily.SCHEMA,
                "connection is required",
                path=["connection"],
                suggest="Provide a connection reference like @mysql.default",
            )

        if not component:
            raise OsirisError(
                ErrorFamily.SCHEMA,
                "component is required",
                path=["component"],
                suggest="Provide a component ID like mysql.extractor",
            )

        try:
            # Check cache first (optional optimization)
            if idempotency_key:
                cached_result = await self.cache.get(connection, component, samples, idempotency_key)

                if cached_result:
                    logger.info(f"Discovery cache hit for {connection}/{component}")
                    result = {
                        "discovery_id": cached_result.get("discovery_id"),
                        "cached": True,
                        "artifacts": self._get_artifact_uris(cached_result.get("discovery_id")),
                        "status": "success",
                    }
                    return add_metrics(result, correlation_id, start_time, args)

            # Delegate to CLI: osiris mcp discovery run --connection-id @mysql.default --samples 10
            # Note: component is derived from connection family in CLI, not passed explicitly
            cli_args = [
                "mcp",
                "discovery",
                "run",
                "--connection-id",
                connection,
                "--samples",
                str(samples),
            ]

            result = await cli_bridge.run_cli_json(cli_args)

            # Cache the result if idempotency_key provided
            if idempotency_key and result.get("discovery_id"):
                await self.cache.set(connection, component, samples, result, idempotency_key)

            # Add metrics and return
            return add_metrics(result, correlation_id, start_time, args)

        except OsirisError:
            # Re-raise OsirisError as-is
            raise
        except Exception as e:
            logger.error(f"Discovery failed: {e}")
            raise OsirisError(
                ErrorFamily.DISCOVERY,
                f"Discovery failed: {str(e)}",
                path=["discovery"],
                suggest="Check connection, component configuration, and CLI bridge",
            ) from e

    def _get_artifact_uris(self, discovery_id: str) -> dict[str, str]:
        """Get URIs for discovery artifacts."""
        return {
            "overview": self.cache.get_discovery_uri(discovery_id, "overview"),
            "tables": self.cache.get_discovery_uri(discovery_id, "tables"),
            "samples": self.cache.get_discovery_uri(discovery_id, "samples"),
        }
