"""Tests for runner config cleaning (meta key stripping)."""

import json
from unittest.mock import MagicMock, patch

import yaml

from osiris.core.runner_v0 import RunnerV0


def test_runner_strips_meta_keys(tmp_path):
    """Test that runner strips component and connection keys before passing to driver."""
    # Create a manifest
    manifest_path = tmp_path / "manifest.yaml"
    manifest = {
        "pipeline": {"id": "test", "version": "0.1.0"},
        "steps": [
            {
                "id": "test_step",
                "driver": "test.driver",
                "cfg_path": "cfg/test_step.json",
                "needs": [],
            }
        ],
        "meta": {"oml_version": "0.1.0", "profile": "default"},
    }
    with open(manifest_path, "w") as f:
        yaml.dump(manifest, f)

    # Create config with meta keys
    cfg_dir = tmp_path / "cfg"
    cfg_dir.mkdir()
    config_path = cfg_dir / "test_step.json"
    config = {
        "component": "test.driver",  # Meta key
        "connection": "@test.main",  # Meta key
        "table": "test_table",  # Driver config
        "mode": "write",  # Driver config
    }
    with open(config_path, "w") as f:
        json.dump(config, f)

    # Mock the driver registry
    mock_driver = MagicMock()
    mock_driver.run.return_value = {}

    with patch("osiris.core.runner_v0.ComponentRegistry"):
        runner = RunnerV0(str(manifest_path), str(tmp_path / "output"))
        runner.driver_registry = MagicMock()
        runner.driver_registry.get.return_value = mock_driver

        # Mock connection resolution
        with patch("osiris.core.runner_v0.resolve_connection") as mock_resolve:
            mock_resolve.return_value = {"url": "http://test", "key": "test_key"}

            # Run the pipeline
            runner.run()

            # Check that driver was called
            mock_driver.run.assert_called_once()

            # Get the config passed to driver
            call_args = mock_driver.run.call_args
            driver_config = call_args.kwargs["config"]

            # Verify meta keys were stripped
            assert "component" not in driver_config
            assert "connection" not in driver_config

            # Verify driver config keys remain
            assert driver_config["table"] == "test_table"
            assert driver_config["mode"] == "write"

            # Verify resolved_connection was added
            assert "resolved_connection" in driver_config
            assert driver_config["resolved_connection"]["url"] == "http://test"


def test_cleaned_config_artifact_saved(tmp_path):
    """Test that cleaned config is saved as artifact without secrets."""
    # Create a manifest
    manifest_path = tmp_path / "manifest.yaml"
    manifest = {
        "pipeline": {"id": "test", "version": "0.1.0"},
        "steps": [
            {
                "id": "test_step",
                "driver": "test.driver",
                "cfg_path": "cfg/test_step.json",
                "needs": [],
            }
        ],
        "meta": {"oml_version": "0.1.0", "profile": "default"},
    }
    with open(manifest_path, "w") as f:
        yaml.dump(manifest, f)

    # Create config
    cfg_dir = tmp_path / "cfg"
    cfg_dir.mkdir()
    config_path = cfg_dir / "test_step.json"
    config = {"component": "test.driver", "connection": "@test.main", "table": "test_table"}
    with open(config_path, "w") as f:
        json.dump(config, f)

    # Mock the driver
    mock_driver = MagicMock()
    mock_driver.run.return_value = {}

    output_dir = tmp_path / "output"

    with patch("osiris.core.runner_v0.ComponentRegistry"):
        runner = RunnerV0(str(manifest_path), str(output_dir))
        runner.driver_registry = MagicMock()
        runner.driver_registry.get.return_value = mock_driver

        # Mock connection resolution with secret
        with patch("osiris.core.runner_v0.resolve_connection") as mock_resolve:
            mock_resolve.return_value = {
                "url": "http://test",
                "key": "secret_key_123",  # pragma: allowlist secret
                "password": "secret_pass",  # pragma: allowlist secret
            }

            # Run the pipeline
            runner.run()

            # Check cleaned config artifact was saved
            cleaned_config_path = output_dir / "test_step" / "cleaned_config.json"
            assert cleaned_config_path.exists()

            # Load and verify cleaned config
            with open(cleaned_config_path) as f:
                saved_config = json.load(f)

            # Meta keys should be absent
            assert "component" not in saved_config
            assert "connection" not in saved_config

            # Driver config should be present
            assert saved_config["table"] == "test_table"

            # Secrets should be masked
            assert saved_config["resolved_connection"]["key"] == "***MASKED***"
            assert saved_config["resolved_connection"]["password"] == "***MASKED***"
            assert saved_config["resolved_connection"]["url"] == "http://test"  # Non-secret


def test_config_meta_stripped_event_logged(tmp_path):
    """Test that config_meta_stripped event is logged when meta keys are removed."""
    # Create a manifest
    manifest_path = tmp_path / "manifest.yaml"
    manifest = {
        "pipeline": {"id": "test", "version": "0.1.0"},
        "steps": [
            {
                "id": "test_step",
                "driver": "test.driver",
                "cfg_path": "cfg/test_step.json",
                "needs": [],
            }
        ],
        "meta": {"oml_version": "0.1.0", "profile": "default"},
    }
    with open(manifest_path, "w") as f:
        yaml.dump(manifest, f)

    # Create config with meta keys
    cfg_dir = tmp_path / "cfg"
    cfg_dir.mkdir()
    config_path = cfg_dir / "test_step.json"
    config = {"component": "test.driver", "connection": "@test.main", "table": "test_table"}
    with open(config_path, "w") as f:
        json.dump(config, f)

    # Mock the driver
    mock_driver = MagicMock()
    mock_driver.run.return_value = {}

    with patch("osiris.core.runner_v0.ComponentRegistry"), patch(
        "osiris.core.runner_v0.log_event"
    ) as mock_log_event:
        runner = RunnerV0(str(manifest_path), str(tmp_path / "output"))
        runner.driver_registry = MagicMock()
        runner.driver_registry.get.return_value = mock_driver

        with patch("osiris.core.runner_v0.resolve_connection") as mock_resolve:
            mock_resolve.return_value = {"url": "http://test", "key": "test"}

            # Run the pipeline
            runner.run()

            # Check that config_meta_stripped event was logged
            meta_stripped_calls = [
                call
                for call in mock_log_event.call_args_list
                if call[0][0] == "config_meta_stripped"
            ]

            assert len(meta_stripped_calls) == 1
            event_call = meta_stripped_calls[0]
            event_data = event_call[1]

            assert event_data["step_id"] == "test_step"
            assert event_data["keys_removed"] == ["component", "connection"]
            assert event_data["config_meta_stripped"] is True


def test_no_meta_keys_no_stripping(tmp_path):
    """Test that when config has no meta keys, nothing is stripped."""
    # Create a manifest
    manifest_path = tmp_path / "manifest.yaml"
    manifest = {
        "pipeline": {"id": "test", "version": "0.1.0"},
        "steps": [
            {
                "id": "test_step",
                "driver": "test.driver",
                "cfg_path": "cfg/test_step.json",
                "needs": [],
            }
        ],
        "meta": {"oml_version": "0.1.0", "profile": "default"},
    }
    with open(manifest_path, "w") as f:
        yaml.dump(manifest, f)

    # Create config WITHOUT meta keys
    cfg_dir = tmp_path / "cfg"
    cfg_dir.mkdir()
    config_path = cfg_dir / "test_step.json"
    config = {"table": "test_table", "mode": "write"}
    with open(config_path, "w") as f:
        json.dump(config, f)

    # Mock the driver
    mock_driver = MagicMock()
    mock_driver.run.return_value = {}

    with patch("osiris.core.runner_v0.ComponentRegistry"), patch(
        "osiris.core.runner_v0.log_event"
    ) as mock_log_event:
        runner = RunnerV0(str(manifest_path), str(tmp_path / "output"))
        runner.driver_registry = MagicMock()
        runner.driver_registry.get.return_value = mock_driver

        # No connection to resolve (DuckDB local case)
        with patch("osiris.core.runner_v0.resolve_connection") as mock_resolve:
            mock_resolve.return_value = None

            # Run the pipeline
            runner.run()

            # Check that NO config_meta_stripped event was logged
            meta_stripped_calls = [
                call
                for call in mock_log_event.call_args_list
                if call[0][0] == "config_meta_stripped"
            ]

            assert len(meta_stripped_calls) == 0  # No stripping event
