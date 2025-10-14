"""
MCP tools for database discovery operations.
"""

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from osiris.mcp.cache import DiscoveryCache
from osiris.mcp.errors import OsirisError, ErrorFamily

logger = logging.getLogger(__name__)


class DiscoveryTools:
    """Tools for database discovery operations."""

    def __init__(self, cache: Optional[DiscoveryCache] = None):
        """Initialize discovery tools."""
        self.cache = cache or DiscoveryCache()

    async def request(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """
        Perform database schema discovery with optional sampling.

        Args:
            args: Tool arguments including connection_id, component_id, samples, idempotency_key

        Returns:
            Dictionary with discovery results
        """
        connection_id = args.get("connection_id")
        component_id = args.get("component_id")
        samples = args.get("samples", 0)
        idempotency_key = args.get("idempotency_key")

        # Validate required fields
        if not connection_id:
            raise OsirisError(
                ErrorFamily.SCHEMA,
                "connection_id is required",
                path=["connection_id"],
                suggest="Provide a connection reference like @mysql.default"
            )

        if not component_id:
            raise OsirisError(
                ErrorFamily.SCHEMA,
                "component_id is required",
                path=["component_id"],
                suggest="Provide a component ID like mysql.extractor"
            )

        try:
            # Check cache first
            cached_result = await self.cache.get(
                connection_id, component_id, samples, idempotency_key
            )

            if cached_result:
                logger.info(f"Discovery cache hit for {connection_id}/{component_id}")
                return {
                    "discovery_id": cached_result.get("discovery_id"),
                    "cached": True,
                    "status": "success",
                    "artifacts": self._get_artifact_uris(cached_result.get("discovery_id"))
                }

            # Perform actual discovery
            logger.info(f"Performing discovery for {connection_id}/{component_id}")
            discovery_result = await self._perform_discovery(
                connection_id, component_id, samples
            )

            # Cache the result
            discovery_id = await self.cache.set(
                connection_id,
                component_id,
                samples,
                discovery_result,
                idempotency_key
            )

            return {
                "discovery_id": discovery_id,
                "cached": False,
                "status": "success",
                "artifacts": self._get_artifact_uris(discovery_id),
                "summary": discovery_result.get("summary", {})
            }

        except OsirisError:
            raise
        except Exception as e:
            logger.error(f"Discovery failed: {e}")
            raise OsirisError(
                ErrorFamily.DISCOVERY,
                f"Discovery failed: {str(e)}",
                path=["discovery"],
                suggest="Check connection and component configuration"
            )

    async def _perform_discovery(
        self,
        connection_id: str,
        component_id: str,
        samples: int
    ) -> Dict[str, Any]:
        """
        Perform actual database discovery.

        Args:
            connection_id: Connection reference
            component_id: Component ID
            samples: Number of samples to fetch

        Returns:
            Discovery results
        """
        try:
            from osiris.core.config import parse_connection_ref, resolve_connection
            from osiris.core.driver import DriverRegistry

            # Parse and resolve connection
            family, alias = parse_connection_ref(connection_id)
            connection = resolve_connection(family, alias)

            # Get the driver
            registry = DriverRegistry()
            driver = registry.get(component_id)

            # Perform discovery based on component type
            if "extractor" in component_id:
                return await self._discover_extractor(driver, connection, samples)
            else:
                # For non-extractor components, return basic info
                return {
                    "component_id": component_id,
                    "connection_id": connection_id,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "summary": {
                        "type": "component",
                        "name": component_id
                    }
                }

        except Exception as e:
            logger.error(f"Discovery execution failed: {e}")
            raise

    async def _discover_extractor(
        self,
        driver: Any,
        connection: Dict[str, Any],
        samples: int
    ) -> Dict[str, Any]:
        """
        Discover database schema for an extractor.

        Args:
            driver: Driver instance
            connection: Resolved connection config
            samples: Number of samples to fetch

        Returns:
            Discovery results with tables and samples
        """
        # This would normally interact with the actual driver
        # For now, return a placeholder structure
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "database": connection.get("database", "unknown"),
            "tables": [],  # Would be populated by actual discovery
            "samples": {},  # Would contain sample data if requested
            "summary": {
                "tables_count": 0,
                "total_rows": 0,
                "database": connection.get("database", "unknown")
            }
        }

    def _get_artifact_uris(self, discovery_id: str) -> Dict[str, str]:
        """Get URIs for discovery artifacts."""
        return {
            "overview": self.cache.get_discovery_uri(discovery_id, "overview"),
            "tables": self.cache.get_discovery_uri(discovery_id, "tables"),
            "samples": self.cache.get_discovery_uri(discovery_id, "samples")
        }