"""
Configuration module for Osiris MCP server.

Centralizes configuration and tunable parameters.
"""

import os
from pathlib import Path
from typing import Any, Dict, Optional


class MCPConfig:
    """Configuration for MCP server."""

    # Protocol configuration
    PROTOCOL_VERSION = "0.5"
    SERVER_VERSION = "0.5.0"
    SERVER_NAME = "osiris-mcp-server"

    # Payload limits
    DEFAULT_PAYLOAD_LIMIT_MB = 16
    MIN_PAYLOAD_LIMIT_MB = 1
    MAX_PAYLOAD_LIMIT_MB = 100

    # Timeouts (in seconds)
    DEFAULT_HANDSHAKE_TIMEOUT = 2.0
    DEFAULT_TOOL_TIMEOUT = 30.0
    DEFAULT_RESOURCE_TIMEOUT = 10.0

    # Cache configuration
    DEFAULT_DISCOVERY_CACHE_TTL_HOURS = 24
    MAX_CACHE_SIZE_MB = 500

    # Memory configuration
    DEFAULT_MEMORY_RETENTION_DAYS = 365
    MAX_MEMORY_RETENTION_DAYS = 730

    # Telemetry configuration
    TELEMETRY_ENABLED_DEFAULT = True
    TELEMETRY_BATCH_SIZE = 100
    TELEMETRY_FLUSH_INTERVAL_SECONDS = 60

    # Directory paths
    DEFAULT_DATA_DIR = Path(__file__).parent / "data"
    DEFAULT_STATE_DIR = Path(__file__).parent / "state"
    DEFAULT_CACHE_DIR = Path.home() / ".osiris_cache" / "mcp"
    DEFAULT_MEMORY_DIR = Path.home() / ".osiris_memory" / "mcp"
    DEFAULT_AUDIT_DIR = Path.home() / ".osiris_audit"
    DEFAULT_TELEMETRY_DIR = Path.home() / ".osiris_telemetry"

    def __init__(self):
        """Initialize configuration with defaults and environment overrides."""
        # Payload limit (can be overridden by environment)
        self.payload_limit_mb = int(
            os.environ.get(
                "OSIRIS_MCP_PAYLOAD_LIMIT_MB",
                self.DEFAULT_PAYLOAD_LIMIT_MB
            )
        )

        # Validate payload limit
        if self.payload_limit_mb < self.MIN_PAYLOAD_LIMIT_MB:
            self.payload_limit_mb = self.MIN_PAYLOAD_LIMIT_MB
        elif self.payload_limit_mb > self.MAX_PAYLOAD_LIMIT_MB:
            self.payload_limit_mb = self.MAX_PAYLOAD_LIMIT_MB

        # Convert to bytes
        self.payload_limit_bytes = self.payload_limit_mb * 1024 * 1024

        # Timeouts
        self.handshake_timeout = float(
            os.environ.get(
                "OSIRIS_MCP_HANDSHAKE_TIMEOUT",
                self.DEFAULT_HANDSHAKE_TIMEOUT
            )
        )
        self.tool_timeout = float(
            os.environ.get(
                "OSIRIS_MCP_TOOL_TIMEOUT",
                self.DEFAULT_TOOL_TIMEOUT
            )
        )
        self.resource_timeout = float(
            os.environ.get(
                "OSIRIS_MCP_RESOURCE_TIMEOUT",
                self.DEFAULT_RESOURCE_TIMEOUT
            )
        )

        # Cache configuration
        self.discovery_cache_ttl_hours = int(
            os.environ.get(
                "OSIRIS_MCP_CACHE_TTL_HOURS",
                self.DEFAULT_DISCOVERY_CACHE_TTL_HOURS
            )
        )

        # Memory retention
        self.memory_retention_days = int(
            os.environ.get(
                "OSIRIS_MCP_MEMORY_RETENTION_DAYS",
                self.DEFAULT_MEMORY_RETENTION_DAYS
            )
        )

        # Telemetry
        self.telemetry_enabled = os.environ.get(
            "OSIRIS_MCP_TELEMETRY_ENABLED",
            str(self.TELEMETRY_ENABLED_DEFAULT)
        ).lower() in ("true", "1", "yes", "on")

        # Directories (can be overridden by OSIRIS_HOME)
        osiris_home = os.environ.get("OSIRIS_HOME")
        if osiris_home:
            base_path = Path(osiris_home)
            self.cache_dir = base_path / "cache" / "mcp"
            self.memory_dir = base_path / "memory" / "mcp"
            self.audit_dir = base_path / "audit"
            self.telemetry_dir = base_path / "telemetry"
        else:
            self.cache_dir = self.DEFAULT_CACHE_DIR
            self.memory_dir = self.DEFAULT_MEMORY_DIR
            self.audit_dir = self.DEFAULT_AUDIT_DIR
            self.telemetry_dir = self.DEFAULT_TELEMETRY_DIR

        # Data and state directories (relative to module)
        self.data_dir = self.DEFAULT_DATA_DIR
        self.state_dir = self.DEFAULT_STATE_DIR

    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary."""
        return {
            "protocol_version": self.PROTOCOL_VERSION,
            "server_version": self.SERVER_VERSION,
            "server_name": self.SERVER_NAME,
            "payload_limit_mb": self.payload_limit_mb,
            "payload_limit_bytes": self.payload_limit_bytes,
            "handshake_timeout": self.handshake_timeout,
            "tool_timeout": self.tool_timeout,
            "resource_timeout": self.resource_timeout,
            "discovery_cache_ttl_hours": self.discovery_cache_ttl_hours,
            "memory_retention_days": self.memory_retention_days,
            "telemetry_enabled": self.telemetry_enabled,
            "directories": {
                "data": str(self.data_dir),
                "state": str(self.state_dir),
                "cache": str(self.cache_dir),
                "memory": str(self.memory_dir),
                "audit": str(self.audit_dir),
                "telemetry": str(self.telemetry_dir)
            }
        }

    @classmethod
    def get_default(cls) -> "MCPConfig":
        """Get default configuration instance."""
        return cls()


# Global configuration instance
_config: Optional[MCPConfig] = None


def get_config() -> MCPConfig:
    """Get the global configuration instance."""
    global _config
    if _config is None:
        _config = MCPConfig()
    return _config


def init_config() -> MCPConfig:
    """Initialize and return global configuration."""
    global _config
    _config = MCPConfig()
    return _config