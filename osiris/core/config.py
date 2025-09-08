# # Copyright (c) 2025 Osiris Project
# #
# # Licensed under the Apache License, Version 2.0 (the "License");
# # you may not use this file except in compliance with the License.
# # You may obtain a copy of the License at
# #
# #     http://www.apache.org/licenses/LICENSE-2.0
# #
# # Unless required by applicable law or agreed to in writing, software
# # distributed under the License is distributed on an "AS IS" BASIS,
# # WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# # See the License for the specific language governing permissions and
# # limitations under the License.

"""Configuration management for Osiris v2."""

import os
import re
from pathlib import Path
from typing import Any, Dict, Optional

import yaml


def load_config(config_path: str = ".osiris.yaml") -> Dict[str, Any]:
    """Load configuration from YAML file.

    Args:
        config_path: Path to configuration file

    Returns:
        Configuration dictionary

    Raises:
        FileNotFoundError: If config file doesn't exist
        yaml.YAMLError: If config file is invalid
    """
    config_file = Path(config_path)

    if not config_file.exists():
        raise FileNotFoundError(f"Configuration file '{config_path}' not found")

    with open(config_file) as f:
        config = yaml.safe_load(f)

    return config or {}


def create_sample_config(config_path: str = "osiris.yaml") -> None:
    """Create a sample configuration file.

    Args:
        config_path: Path where to create the config file
    """
    config_file = Path(config_path)

    if config_file.exists():
        backup_path = f"{config_path}.backup"
        config_file.rename(backup_path)

    # Write config with comments (yaml.dump strips comments, so write manually)
    with open(config_file, "w") as f:
        f.write(
            """version: '2.0'

# ============================================================================
# LOGGING CONFIGURATION
# Enhanced session logging with structured events and metrics (M0-Validation-4)
# ============================================================================
logging:
  logs_dir: ./logs      # Session logs directory (per-session directories created here)
  level: INFO           # Log verbosity for .log files: DEBUG, INFO, WARNING, ERROR, CRITICAL

  # IMPORTANT: Events and log levels are INDEPENDENT systems:
  # - 'level' controls what goes into osiris.log (Python logging messages)
  # - 'events' controls what goes into events.jsonl (structured events)
  # Events are ALWAYS logged regardless of level setting - they use separate filtering below.

  events:               # Event types to log (structured JSONL format)
    # Use "*" to log ALL events (recommended), or specify individual events below:
    #
    # Session Lifecycle:
    #   run_start         - Session begins (command starts)
    #   run_end           - Session completes successfully
    #   run_error         - Session fails with error
    #
    # Chat & Conversation:
    #   chat_start        - Chat session begins
    #   chat_end          - Chat session ends
    #   user_message      - User sends a message
    #   assistant_response - AI responds to user
    #   chat_interrupted  - Chat stopped by Ctrl+C
    #
    # Chat Modes:
    #   sql_mode_start           - Direct SQL mode begins
    #   single_message_start     - One-shot message mode
    #   interactive_mode_start   - Interactive conversation mode
    #
    # Database Discovery:
    #   discovery_start   - Schema discovery begins
    #   discovery_end     - Schema discovery completes
    #   cache_hit         - Found cached discovery data
    #   cache_miss        - No cached data, discovering fresh
    #   cache_lookup      - Checking cache for discovery data
    #   cache_error       - Cache access failed
    #
    # Validation & Config:
    #   validate_start    - Configuration validation begins
    #   validate_complete - Configuration validation done
    #   validate_error    - Configuration validation failed
    #
    # Response Quality:
    #   sql_response             - SQL mode generated response
    #   single_message_response  - Single message got response
    #   single_message_empty_response - Single message got no response
    #   sql_error               - SQL mode encountered error
    #   single_message_error    - Single message mode failed
    #   chat_error              - General chat error occurred
    #
    # Examples:
    #   - "*"                          # Log ALL events (recommended)
    #   - ["run_start", "run_end"]     # Only session lifecycle
    #   - ["user_message", "assistant_response"]  # Only conversation
    #
    # NOTE: Events are filtered HERE, not by 'level' above. Even with level: ERROR,
    # validate_start events will still be logged if included in this list.
    - "*"
  metrics:
    enabled: true       # Enable performance metrics collection
    retention_hours: 168   # Keep metrics for 7 days (168 hours)
  retention: 7d         # Session retention policy (7d = 7 days, supports: 1d, 30d, 6m, 1y)
  env_overrides:        # Environment variables that can override these settings
    OSIRIS_LOG_LEVEL: level
    OSIRIS_LOGS_DIR: logs_dir
  cli_flags:            # CLI flags that can override these settings (highest precedence)
    --log-level: level
    --logs-dir: logs_dir

# ============================================================================
# OUTPUT CONFIGURATION
# Where generated pipeline results are saved
# ============================================================================
output:
  format: csv           # Output format: csv, parquet, json
  directory: output/    # Directory for pipeline outputs
  filename_template: pipeline_{session_id}_{timestamp}

# ============================================================================
# SESSION MANAGEMENT
# Osiris automatically manages conversation sessions and discovery cache
# ============================================================================
sessions:
  directory: .osiris_sessions/  # Where session data is stored
  cleanup_days: 30              # Auto-delete sessions older than N days (background cleanup)
  cache_ttl: 3600               # Cache database discovery for N seconds (avoids re-scanning)

# ============================================================================
# DATABASE DISCOVERY SETTINGS
# Controls how Osiris explores your database schema and samples data
# ============================================================================
discovery:
  sample_size: 10       # Number of sample rows to fetch per table for AI context
  parallel_tables: 5    # Max tables to discover simultaneously (performance tuning)
  timeout_seconds: 30   # Discovery timeout per table (prevents hanging)

# ============================================================================
# LLM (AI) CONFIGURATION
# Controls the AI behavior - API keys go in .env file, not here
# ============================================================================
llm:
  provider: openai      # Primary LLM: openai, claude, gemini

  # OpenAI models (active by default)
  model: gpt-5-mini           # Primary OpenAI model
  fallback_model: gpt-5       # Fallback OpenAI model

  # For Claude (uncomment below and comment OpenAI models above):
  # provider: claude
  # model: claude-sonnet-4-20250514       # Primary Claude model
  # fallback_model: claude-opus-4-1-20250805  # Fallback Claude model

  # For Gemini (uncomment below and comment other models above):
  # provider: gemini
  # model: gemini-2.5-flash               # Primary Gemini model
  # fallback_model: gemini-2.5-pro        # Fallback Gemini model

  temperature: 0.1      # Low temperature = deterministic SQL generation
  max_tokens: 2000      # Maximum response length from AI
  timeout_seconds: 30   # API request timeout
  fallback_enabled: true   # Use backup models if primary fails

# ============================================================================
# PIPELINE SAFETY & VALIDATION
# Security settings to prevent dangerous operations
# ============================================================================
pipeline:
  validation_required: true   # Always require human approval before execution
  auto_execute: false         # Never auto-execute without user confirmation
  max_sql_length: 10000       # Reject extremely long SQL queries
  dangerous_keywords:         # Block destructive operations
  - DROP
  - DELETE
  - TRUNCATE
  - ALTER

# ============================================================================
# VALIDATION CONFIGURATION
# Configuration validation modes and output formats (M0-Validation-4)
# ============================================================================
validate:
  mode: warn            # Validation mode: strict, warn, off
  json: false           # Output validation results in JSON format
  show_effective: true  # Show effective configuration values and their sources

# ============================================================================
# VALIDATION RETRY CONFIGURATION
# Pipeline validation retry settings (M1b.3 per ADR-0013)
# ============================================================================
validation:
  retry:
    max_attempts: 2           # Maximum retry attempts (0-5, 0 = strict mode)
    include_history_in_hitl: true  # Show retry history in HITL prompts
    history_limit: 3          # Max attempts to show in HITL history
    diff_format: patch        # Diff format: "patch" or "summary"
"""
        )


class ConfigManager:
    """Configuration manager for loading and managing Osiris configuration."""

    def __init__(self, config_path: Optional[str] = None):
        """Initialize configuration manager.

        Args:
            config_path: Path to configuration file (defaults to osiris.yaml)
        """
        self.config_path = config_path or "osiris.yaml"
        self._config = None

    def load_config(self) -> Dict[str, Any]:
        """Load configuration from file.

        Returns:
            Configuration dictionary
        """
        if self._config is None:
            try:
                self._config = load_config(self.config_path)
            except FileNotFoundError:
                # Return default configuration if file doesn't exist
                self._config = self._get_default_config()

        return self._config

    def _get_default_config(self) -> Dict[str, Any]:
        """Get default configuration when no config file exists."""
        return {
            "version": "2.0",
            # Logging Configuration
            "logging": {
                "level": "INFO",
                "file": None,  # Console-only logging by default
                "format": "%(asctime)s - %(name)s - [%(session_id)s] - %(levelname)s - %(message)s",
            },
            # Output Configuration
            "output": {
                "format": "csv",
                "directory": "output/",
                "filename_template": "pipeline_{session_id}_{timestamp}",
            },
            # Session Management
            "sessions": {"directory": ".osiris_sessions/", "cleanup_days": 30, "cache_ttl": 3600},
            # Discovery Settings
            "discovery": {"sample_size": 10, "parallel_tables": 5, "timeout_seconds": 30},
            # LLM Configuration (non-sensitive)
            "llm": {
                "provider": "openai",
                "temperature": 0.1,
                "max_tokens": 2000,
                "timeout_seconds": 30,
                "fallback_enabled": True,
            },
            # Pipeline Generation Settings
            "pipeline": {
                "validation_required": True,
                "auto_execute": False,
                "max_sql_length": 10000,
                "dangerous_keywords": ["DROP", "DELETE", "TRUNCATE", "ALTER"],
            },
        }


def load_connections_yaml(substitute_env: bool = True) -> Dict[str, Any]:
    """Load connections configuration with optional ${VAR} substitution from environment.

    Args:
        substitute_env: If True, substitute ${VAR} with environment values.
                       If False, return raw config with ${VAR} patterns intact.

    Searches for osiris_connections.yaml in:
    1. Current working directory
    2. Repository root (parent directories)

    Returns:
        Dict structure {family: {alias: {fields}}}
        Returns empty dict if no connections file found
    """
    # Search for connections file
    search_paths = [
        Path.cwd() / "osiris_connections.yaml",
        Path.cwd().parent / "osiris_connections.yaml",
        Path(__file__).parent.parent.parent
        / "osiris_connections.yaml",  # Repo root from osiris/core/
    ]

    connections_file = None
    for path in search_paths:
        if path.exists():
            connections_file = path
            break

    if not connections_file:
        return {}

    # Load YAML
    with open(connections_file) as f:
        data = yaml.safe_load(f) or {}

    if "connections" not in data:
        return {}

    connections = data["connections"]

    if not substitute_env:
        # Return raw config without substitution
        return connections

    # Perform environment variable substitution
    def substitute_env_vars(obj):
        """Recursively substitute ${VAR} with environment variable values."""
        if isinstance(obj, str):
            # Find all ${VAR} patterns
            pattern = r"\$\{([^}]+)\}"

            def replacer(match):
                var_name = match.group(1)
                value = os.environ.get(var_name)
                if value is None:
                    # Keep original if not found (will error later if required)
                    return match.group(0)
                return value

            return re.sub(pattern, replacer, obj)
        elif isinstance(obj, dict):
            return {k: substitute_env_vars(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [substitute_env_vars(item) for item in obj]
        else:
            return obj

    return substitute_env_vars(connections)


def resolve_connection(family: str, alias: Optional[str] = None) -> Dict[str, Any]:
    """Resolve connection by family and optional alias.

    Args:
        family: Connection family (e.g., "mysql", "supabase", "duckdb")
        alias: Optional alias name. Can be:
            - None: Apply default selection precedence
            - "@family.alias": Parse and resolve specific alias
            - "alias_name": Direct alias name

    Returns:
        Resolved dict with secrets substituted

    Raises:
        ValueError: If connection cannot be resolved
    """
    # Parse @family.alias format if provided
    if alias and alias.startswith("@"):
        # Parse @family.alias format
        parts = alias[1:].split(".", 1)
        if len(parts) == 2:
            parsed_family, parsed_alias = parts
            # Override family if specified in @ format
            if parsed_family:
                family = parsed_family
            alias = parsed_alias
        else:
            raise ValueError(
                f"Invalid connection reference format: {alias}. Expected @family.alias"
            )

    # Load connections
    connections = load_connections_yaml()

    # Check if family exists
    if family not in connections:
        available = list(connections.keys())
        if not available:
            raise ValueError(
                f"No connections configured. Create osiris_connections.yaml with {family} connections."
            )
        raise ValueError(
            f"Connection family '{family}' not found. Available families: {', '.join(available)}"
        )

    family_connections = connections[family]

    if not family_connections:
        raise ValueError(f"No connections defined for family '{family}'")

    # If specific alias requested, return it
    if alias:
        if alias not in family_connections:
            available_aliases = list(family_connections.keys())
            raise ValueError(
                f"Connection alias '{alias}' not found in family '{family}'. "
                f"Available aliases: {', '.join(available_aliases)}"
            )
        connection = family_connections[alias].copy()
        # Remove the 'default' flag if present (not needed in resolved connection)
        connection.pop("default", None)

        # Check for unresolved environment variables
        def check_unresolved_vars(obj, path=""):
            """Check for any remaining ${VAR} patterns."""
            if isinstance(obj, str):
                pattern = r"\$\{([^}]+)\}"
                matches = re.findall(pattern, obj)
                if matches:
                    for var in matches:
                        field_name = path.split(".")[-1] if path else "field"
                        raise ValueError(
                            f"Environment variable '{var}' not set for {field_name} in {family}.{alias}"
                        )
            elif isinstance(obj, dict):
                for k, v in obj.items():
                    new_path = f"{path}.{k}" if path else k
                    check_unresolved_vars(v, new_path)
            elif isinstance(obj, list):
                for i, item in enumerate(obj):
                    check_unresolved_vars(item, f"{path}[{i}]")

        check_unresolved_vars(connection)
        return connection

    # Apply default selection precedence

    # 1. Look for alias with default: true
    for alias_name, conn_data in family_connections.items():
        if conn_data.get("default") is True:
            connection = conn_data.copy()
            connection.pop("default", None)

            # Check for unresolved vars
            def check_unresolved_vars(obj, path="", current_alias=alias_name):
                if isinstance(obj, str):
                    pattern = r"\$\{([^}]+)\}"
                    matches = re.findall(pattern, obj)
                    if matches:
                        for var in matches:
                            field_name = path.split(".")[-1] if path else "field"
                            raise ValueError(
                                f"Environment variable '{var}' not set for {field_name} in {family}.{current_alias}"
                            )
                elif isinstance(obj, dict):
                    for k, v in obj.items():
                        new_path = f"{path}.{k}" if path else k
                        check_unresolved_vars(v, new_path, current_alias)
                elif isinstance(obj, list):
                    for i, item in enumerate(obj):
                        check_unresolved_vars(item, f"{path}[{i}]", current_alias)

            check_unresolved_vars(connection)
            return connection

    # 2. Look for alias named "default"
    if "default" in family_connections:
        connection = family_connections["default"].copy()
        connection.pop("default", None)

        # Check for unresolved vars
        def check_unresolved_vars(obj, path=""):
            if isinstance(obj, str):
                pattern = r"\$\{([^}]+)\}"
                matches = re.findall(pattern, obj)
                if matches:
                    for var in matches:
                        field_name = path.split(".")[-1] if path else "field"
                        raise ValueError(
                            f"Environment variable '{var}' not set for {field_name} in {family}.default"
                        )
            elif isinstance(obj, dict):
                for k, v in obj.items():
                    new_path = f"{path}.{k}" if path else k
                    check_unresolved_vars(v, new_path)
            elif isinstance(obj, list):
                for i, item in enumerate(obj):
                    check_unresolved_vars(item, f"{path}[{i}]")

        check_unresolved_vars(connection)
        return connection

    # 3. Error with available aliases
    available_aliases = list(family_connections.keys())
    raise ValueError(
        f"No default connection for family '{family}'. "
        f"Available aliases: {', '.join(available_aliases)}. "
        f"Either: 1) Set 'default: true' on an alias, 2) Name an alias 'default', "
        f"or 3) Specify an alias explicitly."
    )
