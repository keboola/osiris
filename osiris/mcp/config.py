"""
Configuration module for Osiris MCP server.

Centralizes configuration and tunable parameters with filesystem contract support.
"""

import logging
import os
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


class MCPFilesystemConfig:
    """
    Filesystem configuration for MCP server.

    Resolution order:
    1. osiris.yaml (filesystem.base_path, filesystem.mcp_logs_dir)
    2. Environment variables (OSIRIS_HOME, OSIRIS_MCP_LOGS_DIR)
    3. Default fallbacks
    """

    @classmethod
    def from_config(cls, config_path: str = "osiris.yaml") -> "MCPFilesystemConfig":
        """
        Load filesystem configuration from osiris.yaml.

        Args:
            config_path: Path to osiris.yaml (default: "osiris.yaml")

        Returns:
            MCPFilesystemConfig instance with resolved paths
        """
        instance = cls()

        # Try to load from osiris.yaml
        config_file = Path(config_path)
        if config_file.exists():
            try:
                with open(config_file) as f:
                    config = yaml.safe_load(f)

                if config and "filesystem" in config:
                    fs_config = config["filesystem"]

                    # Get base_path from config
                    base_path_str = fs_config.get("base_path", "")
                    if base_path_str:
                        instance.base_path = Path(base_path_str).resolve()
                    else:
                        # Empty string means use config file's directory
                        instance.base_path = config_file.parent.resolve()

                    # Get mcp_logs_dir from config (relative to base_path)
                    mcp_logs_dir = fs_config.get("mcp_logs_dir", ".osiris/mcp/logs")
                    instance.mcp_logs_dir = instance.base_path / mcp_logs_dir

                    logger.info(f"MCP filesystem config loaded from {config_path}")
                    logger.info(f"  base_path: {instance.base_path}")
                    logger.info(f"  mcp_logs_dir: {instance.mcp_logs_dir}")

                    return instance

            except Exception as e:
                logger.warning(f"Failed to load osiris.yaml: {e}")

        # Fall back to environment variables (with warning)
        osiris_home = os.environ.get("OSIRIS_HOME", "").strip()
        if osiris_home:
            logger.warning("Using OSIRIS_HOME from environment (config preferred)")
            instance.base_path = Path(osiris_home).resolve()
        else:
            # Ultimate fallback: current working directory
            instance.base_path = Path.cwd().resolve()
            logger.warning(f"No config found, using CWD as base_path: {instance.base_path}")

        # Check for MCP logs dir override
        mcp_logs_env = os.environ.get("OSIRIS_MCP_LOGS_DIR", "").strip()
        if mcp_logs_env:
            logger.warning("Using OSIRIS_MCP_LOGS_DIR from environment (config preferred)")
            instance.mcp_logs_dir = Path(mcp_logs_env).resolve()
        else:
            instance.mcp_logs_dir = instance.base_path / ".osiris" / "mcp" / "logs"

        return instance

    def __init__(self):
        """Initialize with default values."""
        self.base_path = Path.cwd().resolve()
        self.mcp_logs_dir = self.base_path / ".osiris" / "mcp" / "logs"

    def ensure_directories(self):
        """Create necessary directories if they don't exist."""
        self.mcp_logs_dir.mkdir(parents=True, exist_ok=True)
        (self.mcp_logs_dir / "audit").mkdir(exist_ok=True)
        (self.mcp_logs_dir / "telemetry").mkdir(exist_ok=True)
        (self.mcp_logs_dir / "cache").mkdir(exist_ok=True)


class MCPConfig:
    """Configuration for MCP server."""

    # Protocol configuration
    PROTOCOL_VERSION = "2024-11-05"  # MCP protocol spec version
    SERVER_VERSION = "0.5.4"  # Osiris server version
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

    def __init__(self, fs_config: MCPFilesystemConfig | None = None):
        """
        Initialize configuration with defaults and environment overrides.

        Args:
            fs_config: Filesystem configuration (if None, will load from osiris.yaml)
        """
        # Load filesystem configuration
        if fs_config is None:
            fs_config = MCPFilesystemConfig.from_config()
        self.fs_config = fs_config

        # Payload limit (can be overridden by environment)
        self.payload_limit_mb = int(os.environ.get("OSIRIS_MCP_PAYLOAD_LIMIT_MB", self.DEFAULT_PAYLOAD_LIMIT_MB))

        # Validate payload limit
        if self.payload_limit_mb < self.MIN_PAYLOAD_LIMIT_MB:
            self.payload_limit_mb = self.MIN_PAYLOAD_LIMIT_MB
        elif self.payload_limit_mb > self.MAX_PAYLOAD_LIMIT_MB:
            self.payload_limit_mb = self.MAX_PAYLOAD_LIMIT_MB

        # Convert to bytes
        self.payload_limit_bytes = self.payload_limit_mb * 1024 * 1024

        # Timeouts
        self.handshake_timeout = float(os.environ.get("OSIRIS_MCP_HANDSHAKE_TIMEOUT", self.DEFAULT_HANDSHAKE_TIMEOUT))
        self.tool_timeout = float(os.environ.get("OSIRIS_MCP_TOOL_TIMEOUT", self.DEFAULT_TOOL_TIMEOUT))
        self.resource_timeout = float(os.environ.get("OSIRIS_MCP_RESOURCE_TIMEOUT", self.DEFAULT_RESOURCE_TIMEOUT))

        # Cache configuration
        self.discovery_cache_ttl_hours = int(
            os.environ.get("OSIRIS_MCP_CACHE_TTL_HOURS", self.DEFAULT_DISCOVERY_CACHE_TTL_HOURS)
        )

        # Memory retention
        self.memory_retention_days = int(
            os.environ.get("OSIRIS_MCP_MEMORY_RETENTION_DAYS", self.DEFAULT_MEMORY_RETENTION_DAYS)
        )

        # Telemetry
        self.telemetry_enabled = os.environ.get(
            "OSIRIS_MCP_TELEMETRY_ENABLED", str(self.TELEMETRY_ENABLED_DEFAULT)
        ).lower() in ("true", "1", "yes", "on")

        # Directories - use filesystem config
        self.cache_dir = fs_config.mcp_logs_dir / "cache"
        self.memory_dir = fs_config.mcp_logs_dir / "memory"
        self.audit_dir = fs_config.mcp_logs_dir / "audit"
        self.telemetry_dir = fs_config.mcp_logs_dir / "telemetry"

        # Data and state directories (relative to module)
        self.data_dir = self.DEFAULT_DATA_DIR
        self.state_dir = self.DEFAULT_STATE_DIR

        # Ensure directories exist
        fs_config.ensure_directories()

    def to_dict(self) -> dict[str, Any]:
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
                "telemetry": str(self.telemetry_dir),
            },
        }

    @classmethod
    def get_default(cls) -> "MCPConfig":
        """Get default configuration instance."""
        return cls()


# Global configuration instance
_config: MCPConfig | None = None


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
