"""Tests for filesystem configuration (ADR-0028)."""

import os
from pathlib import Path
import tempfile

import pytest
import yaml

from osiris.core.config import ConfigError
from osiris.core.fs_config import (
    ArtifactsConfig,
    FilesystemConfig,
    IdsConfig,
    NamingConfig,
    ProfilesConfig,
    RetentionConfig,
    load_osiris_config,
)


class TestProfilesConfig:
    """Test profiles configuration."""

    def test_default_profiles(self):
        """Test default profiles configuration."""
        config = ProfilesConfig()
        assert config.enabled is True
        assert "dev" in config.values
        assert config.default == "dev"

    def test_validate_success(self):
        """Test successful validation."""
        config = ProfilesConfig(enabled=True, values=["dev", "prod"], default="dev")
        config.validate()  # Should not raise

    def test_validate_empty_values(self):
        """Test validation fails with empty values."""
        config = ProfilesConfig(enabled=True, values=[], default="dev")
        with pytest.raises(ConfigError, match="at least one profile"):
            config.validate()

    def test_validate_invalid_default(self):
        """Test validation fails with invalid default."""
        config = ProfilesConfig(enabled=True, values=["dev", "prod"], default="staging")
        with pytest.raises(ConfigError, match="must be one of"):
            config.validate()


class TestNamingConfig:
    """Test naming configuration."""

    def test_default_naming(self):
        """Test default naming templates."""
        config = NamingConfig()
        assert "{pipeline_slug}" in config.manifest_dir
        assert "{run_id}" in config.run_dir
        assert config.manifest_short_len == 7

    def test_validate_manifest_short_len(self):
        """Test validation of manifest_short_len."""
        config = NamingConfig(manifest_short_len=2)
        with pytest.raises(ConfigError, match="between 3 and 16"):
            config.validate()

        config = NamingConfig(manifest_short_len=20)
        with pytest.raises(ConfigError, match="between 3 and 16"):
            config.validate()


class TestIdsConfig:
    """Test IDs configuration."""

    def test_default_ids(self):
        """Test default IDs configuration."""
        config = IdsConfig()
        assert config.run_id_format == "iso_ulid"
        assert config.manifest_hash_algo == "sha256_slug"

    def test_validate_single_format(self):
        """Test validation of single format."""
        config = IdsConfig(run_id_format="ulid")
        config.validate()  # Should not raise

    def test_validate_composite_format(self):
        """Test validation of composite format."""
        config = IdsConfig(run_id_format=["incremental", "ulid"])
        config.validate()  # Should not raise

    def test_validate_invalid_format(self):
        """Test validation fails with invalid format."""
        config = IdsConfig(run_id_format="invalid")
        with pytest.raises(ConfigError, match="Unsupported run_id_format"):
            config.validate()

    def test_validate_empty_format(self):
        """Test validation fails with empty format."""
        config = IdsConfig(run_id_format=[])
        with pytest.raises(ConfigError, match="cannot be empty"):
            config.validate()


class TestFilesystemConfig:
    """Test filesystem configuration."""

    def test_default_filesystem(self):
        """Test default filesystem configuration."""
        config = FilesystemConfig()
        assert config.pipelines_dir == "pipelines"
        assert config.build_dir == "build"
        assert config.aiop_dir == "aiop"
        assert config.run_logs_dir == "run_logs"

    def test_resolve_path_with_base(self):
        """Test path resolution with base_path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = FilesystemConfig(base_path=tmpdir)
            resolved = config.resolve_path("pipelines")
            assert str(resolved).startswith(tmpdir)
            assert resolved.name == "pipelines"

    def test_resolve_path_without_base(self):
        """Test path resolution without base_path."""
        config = FilesystemConfig()
        resolved = config.resolve_path("pipelines")
        assert resolved == Path.cwd() / "pipelines"


class TestLoadOsirisConfig:
    """Test configuration loading."""

    def test_load_default_config(self):
        """Test loading default configuration."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "osiris.yaml"
            # Create minimal config
            with open(config_path, "w") as f:
                yaml.dump({"version": "2.0"}, f)

            fs_config, ids_config, raw = load_osiris_config(str(config_path))

            assert isinstance(fs_config, FilesystemConfig)
            assert isinstance(ids_config, IdsConfig)
            assert fs_config.pipelines_dir == "pipelines"
            assert ids_config.run_id_format == "iso_ulid"

    def test_load_custom_config(self):
        """Test loading custom configuration."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "osiris.yaml"
            config_data = {
                "version": "2.0",
                "filesystem": {
                    "pipelines_dir": "custom_pipelines",
                    "profiles": {"enabled": False},
                },
                "ids": {"run_id_format": "uuidv4"},
            }
            with open(config_path, "w") as f:
                yaml.dump(config_data, f)

            fs_config, ids_config, raw = load_osiris_config(str(config_path))

            assert fs_config.pipelines_dir == "custom_pipelines"
            assert fs_config.profiles.enabled is False
            assert ids_config.run_id_format == "uuidv4"

    def test_env_override_profile(self):
        """Test environment variable override for profile."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "osiris.yaml"
            with open(config_path, "w") as f:
                yaml.dump({"version": "2.0"}, f)

            # Set environment override
            os.environ["OSIRIS_PROFILE"] = "prod"
            try:
                fs_config, _, _ = load_osiris_config(str(config_path))
                assert fs_config.profiles.default == "prod"
            finally:
                del os.environ["OSIRIS_PROFILE"]

    def test_env_override_run_id_format(self):
        """Test environment variable override for run_id_format."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "osiris.yaml"
            with open(config_path, "w") as f:
                yaml.dump({"version": "2.0"}, f)

            # Set environment override
            os.environ["OSIRIS_RUN_ID_FORMAT"] = "incremental,ulid"
            try:
                _, ids_config, _ = load_osiris_config(str(config_path))
                assert ids_config.run_id_format == ["incremental", "ulid"]
            finally:
                del os.environ["OSIRIS_RUN_ID_FORMAT"]

    def test_validation_error(self):
        """Test validation error is raised for invalid config."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "osiris.yaml"
            config_data = {
                "version": "2.0",
                "ids": {"run_id_format": "invalid_format"},
            }
            with open(config_path, "w") as f:
                yaml.dump(config_data, f)

            with pytest.raises(ConfigError):
                load_osiris_config(str(config_path))
