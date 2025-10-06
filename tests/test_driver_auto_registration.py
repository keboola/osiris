"""Tests for driver auto-registration from component specs."""

import importlib
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from osiris.core.runner_v0 import RunnerV0


def test_driver_registry_registers_from_specs(tmp_path):
    """Test that drivers are registered from component specs."""
    # Create a temporary component with x-runtime.driver
    component_dir = tmp_path / "test.component"
    component_dir.mkdir()

    spec = {
        "name": "test.component",
        "version": "1.0.0",
        "modes": ["extract"],
        "capabilities": {},
        "configSchema": {"type": "object"},
        "x-runtime": {"driver": "osiris.drivers.mysql_extractor_driver.MySQLExtractorDriver"},
    }

    with open(component_dir / "spec.yaml", "w") as f:
        yaml.dump(spec, f)

    # Create a manifest to test with
    manifest_path = tmp_path / "manifest.yaml"
    manifest = {
        "pipeline": {"id": "test", "version": "0.1.0"},
        "steps": [],
        "meta": {"oml_version": "0.1.0"},
    }
    with open(manifest_path, "w") as f:
        yaml.dump(manifest, f)

    # Reload runner module to ensure patch targets current instance
    import osiris.core.runner_v0 as runner_module

    importlib.reload(runner_module)

    # Mock the component registry to return our test spec
    with patch("osiris.core.runner_v0.ComponentRegistry") as MockRegistry:
        mock_registry = MagicMock()
        mock_registry.load_specs.return_value = {"test.component": spec}
        MockRegistry.return_value = mock_registry

        # Create runner which should auto-register drivers
        runner = runner_module.RunnerV0(str(manifest_path), str(tmp_path / "output"))

        # Verify registry was called
        mock_registry.load_specs.assert_called_once()

        # Check that driver is registered
        drivers = runner.driver_registry.list_drivers()
        assert "test.component" in drivers


def test_driver_registration_handles_import_errors(tmp_path, caplog):
    """Test that driver registration handles import errors gracefully."""
    import logging

    # Create a component with invalid driver path
    component_dir = tmp_path / "bad.component"
    component_dir.mkdir()

    spec = {
        "name": "bad.component",
        "version": "1.0.0",
        "modes": ["extract"],
        "capabilities": {},
        "configSchema": {"type": "object"},
        "x-runtime": {"driver": "nonexistent.module.NonExistentDriver"},
    }

    with open(component_dir / "spec.yaml", "w") as f:
        yaml.dump(spec, f)

    # Create a manifest
    manifest_path = tmp_path / "manifest.yaml"
    manifest = {
        "pipeline": {"id": "test", "version": "0.1.0"},
        "steps": [],
        "meta": {"oml_version": "0.1.0"},
    }
    with open(manifest_path, "w") as f:
        yaml.dump(manifest, f)

    # Reload runner module to ensure patch targets current instance
    import osiris.core.runner_v0 as runner_module

    importlib.reload(runner_module)

    # Mock the component registry to return our bad spec
    with patch("osiris.core.runner_v0.ComponentRegistry") as MockRegistry:
        mock_registry = MagicMock()
        mock_registry.load_specs.return_value = {"bad.component": spec}
        MockRegistry.return_value = mock_registry

        # Create runner - should log error but not crash
        with caplog.at_level(logging.DEBUG):
            runner = runner_module.RunnerV0(str(manifest_path), str(tmp_path / "output"))

        # Driver should be registered (factory function created)
        drivers = runner.driver_registry.list_drivers()
        assert "bad.component" in drivers

        # But trying to instantiate it should fail
        with pytest.raises(ModuleNotFoundError):
            runner.driver_registry.get("bad.component")


def test_components_without_driver_are_skipped(tmp_path):
    """Test that components without x-runtime.driver are skipped."""
    # Create a component without x-runtime.driver
    component_dir = tmp_path / "no_driver.component"
    component_dir.mkdir()

    spec = {
        "name": "no_driver.component",
        "version": "1.0.0",
        "modes": ["transform"],
        "capabilities": {},
        "configSchema": {"type": "object"},
        # No x-runtime section
    }

    with open(component_dir / "spec.yaml", "w") as f:
        yaml.dump(spec, f)

    # Create a manifest
    manifest_path = tmp_path / "manifest.yaml"
    manifest = {
        "pipeline": {"id": "test", "version": "0.1.0"},
        "steps": [],
        "meta": {"oml_version": "0.1.0"},
    }
    with open(manifest_path, "w") as f:
        yaml.dump(manifest, f)

    # Mock the component registry
    with patch("osiris.core.runner_v0.ComponentRegistry") as MockRegistry:
        mock_registry = MagicMock()
        mock_registry.load_specs.return_value = {"no_driver.component": spec}
        MockRegistry.return_value = mock_registry

        # Create runner
        runner = RunnerV0(str(manifest_path), str(tmp_path / "output"))

        # Component should not be registered
        drivers = runner.driver_registry.list_drivers()
        assert "no_driver.component" not in drivers


def test_actual_drivers_are_registered(tmp_path):
    """Test that actual drivers (mysql, csv, supabase) are registered."""
    # Create a dummy manifest
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        manifest = {
            "pipeline": {"id": "test", "version": "0.1.0"},
            "steps": [],
            "meta": {"oml_version": "0.1.0"},
        }
        yaml.dump(manifest, f)
        manifest_path = f.name

    try:
        # Create runner with actual component registry
        runner = RunnerV0(manifest_path, str(tmp_path / "output"))

        # Check that expected drivers are registered
        drivers = runner.driver_registry.list_drivers()

        # These should be registered if specs have x-runtime.driver
        expected_drivers = ["mysql.extractor", "filesystem.csv_writer", "supabase.writer"]

        for driver in expected_drivers:
            assert driver in drivers, f"Expected driver {driver} not registered"

    finally:
        Path(manifest_path).unlink()


def test_driver_factory_creates_instances(tmp_path):
    """Test that driver factories create proper instances."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        manifest = {
            "pipeline": {"id": "test", "version": "0.1.0"},
            "steps": [],
            "meta": {"oml_version": "0.1.0"},
        }
        yaml.dump(manifest, f)
        manifest_path = f.name

    try:
        # Create runner
        runner = RunnerV0(manifest_path, str(tmp_path / "output"))

        # Get a driver instance
        if "mysql.extractor" in runner.driver_registry.list_drivers():
            driver = runner.driver_registry.get("mysql.extractor")

            # Check it has the required method
            assert hasattr(driver, "run")
            assert callable(driver.run)

    finally:
        Path(manifest_path).unlink()
