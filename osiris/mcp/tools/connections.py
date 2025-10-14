"""
MCP tools for connection management.
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from osiris.mcp.errors import OsirisError, ErrorFamily

logger = logging.getLogger(__name__)


class ConnectionsTools:
    """Tools for managing database connections."""

    def __init__(self):
        """Initialize connections tools."""
        self._connections_cache = None

    def _load_connections(self) -> Dict[str, Dict[str, Any]]:
        """Load connections from osiris_connections.yaml."""
        if self._connections_cache is not None:
            return self._connections_cache

        try:
            from osiris.core.config import load_connections_yaml

            connections = load_connections_yaml()
            self._connections_cache = connections
            return connections

        except Exception as e:
            logger.error(f"Failed to load connections: {e}")
            return {}

    async def list(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """
        List all configured database connections.

        Args:
            args: Tool arguments (none required)

        Returns:
            Dictionary with connection information
        """
        try:
            connections = self._load_connections()

            # Format connections for response
            formatted = []
            for family, family_connections in connections.items():
                for alias, config in family_connections.items():
                    # Sanitize connection info (remove passwords)
                    safe_config = self._sanitize_config(config)

                    formatted.append({
                        "family": family,
                        "alias": alias,
                        "reference": f"@{family}.{alias}",
                        "config": safe_config
                    })

            return {
                "connections": formatted,
                "count": len(formatted),
                "status": "success"
            }

        except Exception as e:
            logger.error(f"Error listing connections: {e}")
            raise OsirisError(
                ErrorFamily.SEMANTIC,
                f"Failed to list connections: {str(e)}",
                path=["connections"],
                suggest="Check osiris_connections.yaml file"
            )

    async def doctor(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """
        Diagnose connection issues.

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
                suggest="Provide a connection reference like @mysql.default"
            )

        try:
            from osiris.core.config import parse_connection_ref, resolve_connection

            # Parse connection reference
            if not connection_id.startswith("@"):
                connection_id = f"@{connection_id}"

            family, alias = parse_connection_ref(connection_id)

            # Try to resolve the connection
            diagnostics = []

            # Check if connection exists in config
            connections = self._load_connections()
            if family not in connections:
                diagnostics.append({
                    "check": "family_exists",
                    "status": "failed",
                    "message": f"Connection family '{family}' not found",
                    "severity": "error"
                })
            elif alias and alias not in connections[family]:
                diagnostics.append({
                    "check": "alias_exists",
                    "status": "failed",
                    "message": f"Connection alias '{alias}' not found in family '{family}'",
                    "severity": "error"
                })
            else:
                diagnostics.append({
                    "check": "config_exists",
                    "status": "passed",
                    "message": "Connection configuration found"
                })

                # Try to resolve the connection (check env vars)
                try:
                    resolved = resolve_connection(family, alias)
                    diagnostics.append({
                        "check": "resolution",
                        "status": "passed",
                        "message": "Connection resolved successfully"
                    })

                    # Check for required fields based on family
                    required_fields = self._get_required_fields(family)
                    for field in required_fields:
                        if field in resolved and resolved[field]:
                            diagnostics.append({
                                "check": f"field_{field}",
                                "status": "passed",
                                "message": f"Required field '{field}' is set"
                            })
                        else:
                            diagnostics.append({
                                "check": f"field_{field}",
                                "status": "failed",
                                "message": f"Required field '{field}' is missing or empty",
                                "severity": "error"
                            })

                except Exception as e:
                    diagnostics.append({
                        "check": "resolution",
                        "status": "failed",
                        "message": f"Failed to resolve connection: {str(e)}",
                        "severity": "error"
                    })

            # Determine overall health
            has_error = any(d.get("severity") == "error" for d in diagnostics)
            health = "unhealthy" if has_error else "healthy"

            return {
                "connection_id": connection_id,
                "family": family,
                "alias": alias,
                "health": health,
                "diagnostics": diagnostics,
                "status": "success"
            }

        except Exception as e:
            logger.error(f"Error diagnosing connection: {e}")
            raise OsirisError(
                ErrorFamily.SEMANTIC,
                f"Failed to diagnose connection: {str(e)}",
                path=["connection_id"],
                suggest="Check the connection reference format"
            )

    def _sanitize_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Sanitize configuration by removing sensitive fields."""
        sanitized = {}
        sensitive_keys = ["password", "secret", "token", "api_key", "private_key"]

        for key, value in config.items():
            if any(sensitive in key.lower() for sensitive in sensitive_keys):
                # Check if it's an environment variable reference
                if isinstance(value, str) and value.startswith("${"):
                    sanitized[key] = value  # Keep env var reference
                else:
                    sanitized[key] = "***"
            elif isinstance(value, dict):
                sanitized[key] = self._sanitize_config(value)
            else:
                sanitized[key] = value

        return sanitized

    def _get_required_fields(self, family: str) -> List[str]:
        """Get required fields for a connection family."""
        required_by_family = {
            "mysql": ["host", "database", "username", "password"],
            "postgresql": ["host", "database", "username", "password"],
            "supabase": ["url", "key"],
            "duckdb": ["database"],
            "filesystem": ["path"]
        }

        return required_by_family.get(family, [])