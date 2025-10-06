"""Test component spec packaging for E2B upload simulation.

This test simulates the E2B upload process locally and verifies that
components can be imported and specs can be loaded.
No E2B_API_KEY required - this tests packaging logic only.
"""

import shutil
import sys
from pathlib import Path

import pytest
import yaml


def test_component_spec_packaging_locally(tmp_path):
    """Test that component specs can be packaged and loaded locally."""
    # Find the project root
    project_root = Path(__file__).parent.parent.parent

    # Create a simulated E2B sandbox directory structure
    sandbox_dir = tmp_path / "sandbox"
    sandbox_dir.mkdir()

    # Simulate what E2B uploader does
    osiris_dir = sandbox_dir / "osiris"
    osiris_dir.mkdir()

    # Copy osiris core modules
    core_modules = [
        "core/driver.py",
        "core/execution_adapter.py",
        "core/session_logging.py",
        "core/redaction.py",
        "components/__init__.py",
        "components/registry.py",
        "components/error_mapper.py",
    ]

    for module_path in core_modules:
        src_path = project_root / "osiris" / module_path
        if src_path.exists():
            dst_path = osiris_dir / module_path
            dst_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(src_path, dst_path)

    # Create __init__.py files
    (osiris_dir / "__init__.py").write_text("# Osiris package\n")
    (osiris_dir / "core" / "__init__.py").write_text("# Core package\n")
    (osiris_dir / "components" / "__init__.py").write_text("# Components package\n")

    # Copy component spec files
    components_src_dir = project_root / "components"
    components_dst_dir = sandbox_dir / "components"

    if components_src_dir.exists():
        for component_dir in components_src_dir.iterdir():
            if component_dir.is_dir():
                spec_file = component_dir / "spec.yaml"
                if spec_file.exists():
                    dst_component_dir = components_dst_dir / component_dir.name
                    dst_component_dir.mkdir(parents=True, exist_ok=True)
                    shutil.copy(spec_file, dst_component_dir / "spec.yaml")

    # Add sandbox to Python path (simulating E2B PYTHONPATH)
    original_path = sys.path.copy()
    try:
        sys.path.insert(0, str(sandbox_dir))

        # Try to import the modules
        import importlib

        import_success = True
        import_errors = []

        # Test critical imports
        critical_modules = ["osiris", "osiris.components", "osiris.components.registry", "osiris.core.driver"]

        for module_name in critical_modules:
            try:
                # Remove from sys.modules if already imported
                if module_name in sys.modules:
                    del sys.modules[module_name]
                # Try to import
                importlib.import_module(module_name)
            except ImportError as e:
                import_success = False
                import_errors.append((module_name, str(e)))

        assert import_success, f"Failed to import modules: {import_errors}"

        # Test that ComponentRegistry can load specs
        from osiris.components.registry import ComponentRegistry

        registry = ComponentRegistry()

        # Override the component base path to use our sandbox
        getattr(registry, "_base_path", None)
        registry._base_path = components_dst_dir

        specs = registry.load_specs()
        assert len(specs) > 0, "No component specs loaded"

        # Verify some expected components
        expected_components = ["filesystem.csv_writer", "mysql.extractor", "duckdb.processor"]

        for component_name in expected_components:
            assert component_name in specs, f"Component {component_name} not found in specs"
            spec = specs[component_name]
            assert "modes" in spec, f"No modes field in {component_name} spec"
            # Driver path is in x-runtime.driver
            if "x-runtime" in spec:
                assert "driver" in spec["x-runtime"], f"No driver in x-runtime for {component_name}"

        # Test that DriverRegistry can use the specs
        from osiris.core.driver import DriverRegistry

        driver_registry = DriverRegistry()

        # Populate from specs (without actual import verification)
        summary = driver_registry.populate_from_component_specs(specs, verify_import=False, strict=False)

        assert len(summary.registered) > 0, f"No drivers registered. Errors: {summary.errors}"

    finally:
        # Restore original Python path
        sys.path = original_path
        # Clean up imported modules
        for module_name in list(sys.modules.keys()):
            if module_name.startswith("osiris"):
                del sys.modules[module_name]


def test_component_spec_format(tmp_path):
    """Test that component spec files have the correct format."""
    project_root = Path(__file__).parent.parent.parent
    components_dir = project_root / "components"

    if not components_dir.exists():
        pytest.skip("Components directory not found")

    spec_count = 0
    for component_dir in components_dir.iterdir():
        if component_dir.is_dir():
            spec_file = component_dir / "spec.yaml"
            if spec_file.exists():
                spec_count += 1

                # Load and validate spec
                with open(spec_file) as f:
                    spec = yaml.safe_load(f)

                # Check required fields - new format has these at top level
                assert "name" in spec, f"Missing 'name' in {spec_file}"
                assert "modes" in spec, f"Missing 'modes' in {spec_file}"

                # Check for driver in x-runtime (if present)
                if "x-runtime" in spec:
                    assert "driver" in spec["x-runtime"], f"Missing 'driver' in x-runtime for {spec_file}"
                    driver = spec["x-runtime"]["driver"]
                    assert "." in driver, f"Invalid driver format in {spec_file}: {driver}"
                    # Split using rsplit to handle class name
                    parts = driver.rsplit(".", 1)
                    if len(parts) == 2:
                        module_path, class_name = parts
                        assert module_path.startswith("osiris."), f"Driver should be in osiris package: {driver}"

                # Verify modes are valid
                valid_modes = {"extract", "transform", "write", "read", "discover"}
                modes = spec["modes"]
                assert isinstance(modes, list), f"Modes should be a list in {spec_file}"
                for mode in modes:
                    assert mode in valid_modes, f"Invalid mode '{mode}' in {spec_file}"

    assert spec_count > 0, "No component spec files found"


def test_simulated_e2b_upload(tmp_path):
    """Simulate the complete E2B upload process and verify functionality."""
    project_root = Path(__file__).parent.parent.parent

    # Create sandbox directory
    sandbox_dir = tmp_path / "e2b_sandbox"
    sandbox_dir.mkdir()
    home_user = sandbox_dir / "home" / "user"
    home_user.mkdir(parents=True)

    # Simulate directory creation (as done in e2b_transparent_proxy)
    dirs_to_create = ["osiris/core", "osiris/remote", "osiris/drivers", "osiris/components", "components"]

    for dir_path in dirs_to_create:
        (home_user / dir_path).mkdir(parents=True, exist_ok=True)

    # Copy required modules (simulating upload)
    osiris_src = project_root / "osiris"
    osiris_dst = home_user / "osiris"

    # Core modules to copy
    modules_to_copy = [
        "core/driver.py",
        "core/execution_adapter.py",
        "core/session_logging.py",
        "core/redaction.py",
        "components/__init__.py",
        "components/registry.py",
        "components/error_mapper.py",
    ]

    for module_path in modules_to_copy:
        src_file = osiris_src / module_path
        if src_file.exists():
            dst_file = osiris_dst / module_path
            dst_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(src_file, dst_file)

    # Create __init__.py files
    init_paths = [
        osiris_dst / "__init__.py",
        osiris_dst / "core" / "__init__.py",
        osiris_dst / "remote" / "__init__.py",
        osiris_dst / "drivers" / "__init__.py",
        osiris_dst / "components" / "__init__.py",
    ]

    for init_path in init_paths:
        init_path.write_text("# Package init\n")

    # Copy driver files
    drivers_src = osiris_src / "drivers"
    drivers_dst = osiris_dst / "drivers"
    if drivers_src.exists():
        for driver_file in drivers_src.glob("*.py"):
            if driver_file.name != "__init__.py":
                shutil.copy(driver_file, drivers_dst / driver_file.name)

    # Copy component spec files
    components_src = project_root / "components"
    components_dst = home_user / "components"

    if components_src.exists():
        for component_dir in components_src.iterdir():
            if component_dir.is_dir():
                spec_file = component_dir / "spec.yaml"
                if spec_file.exists():
                    dst_dir = components_dst / component_dir.name
                    dst_dir.mkdir(exist_ok=True)
                    shutil.copy(spec_file, dst_dir / "spec.yaml")

    # Verify the structure
    assert (home_user / "osiris" / "__init__.py").exists()
    assert (home_user / "osiris" / "components" / "registry.py").exists()
    assert (home_user / "osiris" / "core" / "driver.py").exists()

    # Count spec files
    spec_files = list((home_user / "components").glob("*/spec.yaml"))
    assert len(spec_files) > 0, "No component spec files copied"

    # Add to Python path and test imports
    original_path = sys.path.copy()
    try:
        sys.path.insert(0, str(home_user))

        # Clean existing imports
        for module_name in list(sys.modules.keys()):
            if module_name.startswith("osiris"):
                del sys.modules[module_name]

        # Test imports work
        import importlib

        modules_to_test = ["osiris", "osiris.components", "osiris.components.registry", "osiris.core.driver"]

        for module_name in modules_to_test:
            try:
                importlib.import_module(module_name)
            except ImportError as e:
                pytest.fail(f"Failed to import {module_name}: {e}")

        # Verify ComponentRegistry works
        from osiris.components.registry import ComponentRegistry

        registry = ComponentRegistry()
        # Point to our sandbox components
        registry._base_path = components_dst
        specs = registry.load_specs()

        assert len(specs) > 0, "ComponentRegistry failed to load specs"

    finally:
        # Restore Python path
        sys.path = original_path
        # Clean up modules
        for module_name in list(sys.modules.keys()):
            if module_name.startswith("osiris"):
                del sys.modules[module_name]
