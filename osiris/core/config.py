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
# ============================================================================
logging:
  level: INFO           # DEBUG, INFO, WARNING, ERROR, CRITICAL
  file: osiris.log      # Log file path (null for console-only)
  format: '%(asctime)s - %(name)s - [%(session_id)s] - %(levelname)s - %(message)s'

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
