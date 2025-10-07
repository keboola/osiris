# Copyright (c) 2025 Osiris Project
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Filesystem Contract v1 - Typed configuration models (ADR-0028)."""

from dataclasses import dataclass, field
import os
from pathlib import Path
from typing import Any

import yaml

from osiris.core.config import ConfigError


@dataclass
class ProfilesConfig:
    """Profile configuration for multi-environment support."""

    enabled: bool = True
    values: list[str] = field(default_factory=lambda: ["dev", "staging", "prod", "ml", "finance", "incident_debug"])
    default: str = "dev"

    def validate(self) -> None:
        """Validate profiles configuration.

        Raises:
            ConfigError: If configuration is invalid
        """
        if self.enabled:
            if not self.values:
                raise ConfigError("profiles.values must contain at least one profile when profiles are enabled")
            if self.default not in self.values:
                raise ConfigError(
                    f"profiles.default '{self.default}' must be one of profiles.values: {', '.join(self.values)}"
                )


@dataclass
class NamingConfig:
    """Naming templates configuration."""

    manifest_dir: str = "{pipeline_slug}/{manifest_short}-{manifest_hash}"
    run_dir: str = "{pipeline_slug}/{run_ts}_{run_id}-{manifest_short}"
    aiop_run_dir: str = "{run_id}"
    run_ts_format: str = "iso_basic_z"
    manifest_short_len: int = 7

    def validate(self) -> None:
        """Validate naming configuration.

        Raises:
            ConfigError: If configuration is invalid
        """
        if not (3 <= self.manifest_short_len <= 16):
            raise ConfigError(f"naming.manifest_short_len must be between 3 and 16, got {self.manifest_short_len}")


@dataclass
class ArtifactsConfig:
    """Build artifacts configuration."""

    manifest: bool = True
    plan: bool = True
    fingerprints: bool = True
    run_summary: bool = True
    cfg: bool = True
    save_events_tail: int = 0

    def validate(self) -> None:
        """Validate artifacts configuration.

        Raises:
            ConfigError: If configuration is invalid
        """
        if self.save_events_tail < 0:
            raise ConfigError(f"artifacts.save_events_tail must be >= 0, got {self.save_events_tail}")


@dataclass
class RetentionConfig:
    """Retention policy configuration."""

    run_logs_days: int = 7
    aiop_keep_runs_per_pipeline: int = 200
    annex_keep_days: int = 14

    def validate(self) -> None:
        """Validate retention configuration.

        Raises:
            ConfigError: If configuration is invalid
        """
        if self.run_logs_days < 0:
            raise ConfigError(f"retention.run_logs_days must be >= 0, got {self.run_logs_days}")
        if self.aiop_keep_runs_per_pipeline < 0:
            raise ConfigError(
                f"retention.aiop_keep_runs_per_pipeline must be >= 0, got {self.aiop_keep_runs_per_pipeline}"
            )
        if self.annex_keep_days < 0:
            raise ConfigError(f"retention.annex_keep_days must be >= 0, got {self.annex_keep_days}")


@dataclass
class OutputsConfig:
    """Output configuration for pipeline data exports."""

    directory: str = "output"
    format: str = "csv"

    def validate(self) -> None:
        """Validate outputs configuration.

        Raises:
            ConfigError: If configuration is invalid
        """
        if not self.directory:
            raise ConfigError("outputs.directory cannot be empty")
        if not self.format:
            raise ConfigError("outputs.format cannot be empty")


@dataclass
class IdsConfig:
    """ID generation configuration."""

    run_id_format: str | list[str] = "iso_ulid"
    manifest_hash_algo: str = "sha256_slug"

    SUPPORTED_RUN_ID_FORMATS = {"incremental", "ulid", "iso_ulid", "uuidv4", "snowflake"}

    def validate(self) -> None:
        """Validate IDs configuration.

        Raises:
            ConfigError: If configuration is invalid
        """
        # Normalize to list for validation
        formats = [self.run_id_format] if isinstance(self.run_id_format, str) else self.run_id_format

        if not formats:
            raise ConfigError("ids.run_id_format cannot be empty")

        for fmt in formats:
            if fmt not in self.SUPPORTED_RUN_ID_FORMATS:
                supported = ", ".join(sorted(self.SUPPORTED_RUN_ID_FORMATS))
                raise ConfigError(f"Unsupported run_id_format token '{fmt}'. Supported: {supported}")


@dataclass
class FilesystemConfig:
    """Filesystem Contract v1 configuration."""

    # Base paths
    base_path: str = ""
    pipelines_dir: str = "pipelines"
    build_dir: str = "build"
    aiop_dir: str = "aiop"
    run_logs_dir: str = "run_logs"
    sessions_dir: str = ".osiris/sessions"
    cache_dir: str = ".osiris/cache"
    index_dir: str = ".osiris/index"

    # Sub-configurations
    profiles: ProfilesConfig = field(default_factory=ProfilesConfig)
    naming: NamingConfig = field(default_factory=NamingConfig)
    artifacts: ArtifactsConfig = field(default_factory=ArtifactsConfig)
    retention: RetentionConfig = field(default_factory=RetentionConfig)
    outputs: OutputsConfig = field(default_factory=OutputsConfig)

    def __post_init__(self) -> None:
        """Normalize paths after initialization."""
        # Ensure sub-configs are dataclass instances
        if isinstance(self.profiles, dict):
            self.profiles = ProfilesConfig(**self.profiles)
        if isinstance(self.naming, dict):
            self.naming = NamingConfig(**self.naming)
        if isinstance(self.artifacts, dict):
            self.artifacts = ArtifactsConfig(**self.artifacts)
        if isinstance(self.retention, dict):
            self.retention = RetentionConfig(**self.retention)
        if isinstance(self.outputs, dict):
            self.outputs = OutputsConfig(**self.outputs)

        # Normalize base_path
        if self.base_path:
            self.base_path = os.path.expanduser(self.base_path)
            self.base_path = os.path.abspath(self.base_path)

    def validate(self) -> None:
        """Validate filesystem configuration.

        Raises:
            ConfigError: If configuration is invalid
        """
        self.profiles.validate()
        self.naming.validate()
        self.artifacts.validate()
        self.retention.validate()
        self.outputs.validate()

    def resolve_path(self, relative_path: str) -> Path:
        """Resolve a relative path against base_path.

        Args:
            relative_path: Path relative to filesystem root

        Returns:
            Absolute path resolved against base_path
        """
        if self.base_path:
            return Path(self.base_path) / relative_path
        return Path.cwd() / relative_path


def load_osiris_config(config_path: str = "osiris.yaml") -> tuple[FilesystemConfig, IdsConfig, dict[str, Any]]:
    """Load and parse Osiris configuration with filesystem contract support.

    Precedence: Environment > YAML > defaults

    Args:
        config_path: Path to osiris.yaml configuration file

    Returns:
        Tuple of (FilesystemConfig, IdsConfig, raw_config_dict)

    Raises:
        ConfigError: If configuration is invalid
    """
    import logging

    logger = logging.getLogger(__name__)

    # Load raw YAML
    raw_config = _load_raw_yaml(config_path)

    # Apply environment overrides
    raw_config = _apply_env_overrides(raw_config)

    # Extract filesystem config
    fs_dict = raw_config.get("filesystem", {})

    # Legacy compatibility: migrate output.* to filesystem.outputs.*
    outputs_dict = {}
    if "outputs" in fs_dict:
        outputs_dict = fs_dict["outputs"]
    elif "output" in raw_config:
        # Legacy top-level output.* detected
        legacy_output = raw_config["output"]
        if isinstance(legacy_output, dict):
            if "directory" in legacy_output or "format" in legacy_output:
                logger.warning(
                    "Legacy output.* configuration detected. Please migrate to filesystem.outputs.* "
                    "(see docs/samples/osiris.filesystem.yaml). Legacy format will be removed in future versions."
                )
                outputs_dict = {
                    "directory": legacy_output.get("directory", "output"),
                    "format": legacy_output.get("format", "csv"),
                }

    fs_config = FilesystemConfig(
        base_path=fs_dict.get("base_path", ""),
        pipelines_dir=fs_dict.get("pipelines_dir", "pipelines"),
        build_dir=fs_dict.get("build_dir", "build"),
        aiop_dir=fs_dict.get("aiop_dir", "aiop"),
        run_logs_dir=fs_dict.get("run_logs_dir", "run_logs"),
        sessions_dir=fs_dict.get("sessions_dir", ".osiris/sessions"),
        cache_dir=fs_dict.get("cache_dir", ".osiris/cache"),
        index_dir=fs_dict.get("index_dir", ".osiris/index"),
        profiles=ProfilesConfig(**fs_dict.get("profiles", {})) if "profiles" in fs_dict else ProfilesConfig(),
        naming=NamingConfig(**fs_dict.get("naming", {})) if "naming" in fs_dict else NamingConfig(),
        artifacts=ArtifactsConfig(**fs_dict.get("artifacts", {})) if "artifacts" in fs_dict else ArtifactsConfig(),
        retention=RetentionConfig(**fs_dict.get("retention", {})) if "retention" in fs_dict else RetentionConfig(),
        outputs=OutputsConfig(**outputs_dict) if outputs_dict else OutputsConfig(),
    )

    # Extract IDs config
    ids_dict = raw_config.get("ids", {})
    ids_config = IdsConfig(
        run_id_format=ids_dict.get("run_id_format", "iso_ulid"),
        manifest_hash_algo=ids_dict.get("manifest_hash_algo", "sha256_slug"),
    )

    # Validate configs
    fs_config.validate()
    ids_config.validate()

    return fs_config, ids_config, raw_config


def _load_raw_yaml(config_path: str) -> dict[str, Any]:
    """Load raw YAML configuration.

    Args:
        config_path: Path to configuration file

    Returns:
        Raw configuration dictionary
    """
    config_file = Path(config_path)

    if not config_file.exists():
        # Return defaults if no config file
        return {}

    with open(config_file) as f:
        config = yaml.safe_load(f)

    return config or {}


def _apply_env_overrides(config: dict[str, Any]) -> dict[str, Any]:
    """Apply environment variable overrides to configuration.

    Supported environment variables:
    - OSIRIS_PROFILE: Override default profile
    - OSIRIS_FILESYSTEM_BASE: Override filesystem.base_path
    - OSIRIS_RUN_ID_FORMAT: Override ids.run_id_format
    - OSIRIS_RETENTION_RUN_LOGS_DAYS: Override filesystem.retention.run_logs_days

    Args:
        config: Base configuration dictionary

    Returns:
        Configuration with environment overrides applied
    """
    # Profile override
    if "OSIRIS_PROFILE" in os.environ:
        config.setdefault("filesystem", {}).setdefault("profiles", {})["default"] = os.environ["OSIRIS_PROFILE"]

    # Base path override
    if "OSIRIS_FILESYSTEM_BASE" in os.environ:
        config.setdefault("filesystem", {})["base_path"] = os.environ["OSIRIS_FILESYSTEM_BASE"]

    # Run ID format override
    if "OSIRIS_RUN_ID_FORMAT" in os.environ:
        run_id_format = os.environ["OSIRIS_RUN_ID_FORMAT"]
        # Parse comma-separated list
        if "," in run_id_format:
            run_id_format = [fmt.strip() for fmt in run_id_format.split(",")]
        config.setdefault("ids", {})["run_id_format"] = run_id_format

    # Retention override
    if "OSIRIS_RETENTION_RUN_LOGS_DAYS" in os.environ:
        try:
            days = int(os.environ["OSIRIS_RETENTION_RUN_LOGS_DAYS"])
            config.setdefault("filesystem", {}).setdefault("retention", {})["run_logs_days"] = days
        except ValueError:
            pass  # Ignore invalid values

    return config
