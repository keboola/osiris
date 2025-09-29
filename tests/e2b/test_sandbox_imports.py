"""Test E2B sandbox import verification.

This test verifies that critical modules are properly imported in the E2B sandbox.
"""

import os
import tempfile

import pytest

# Skip all tests if E2B_API_KEY not available
pytestmark = pytest.mark.skipif(not os.environ.get("E2B_API_KEY"), reason="E2B_API_KEY not set - skipping E2B tests")


@pytest.fixture
def minimal_pipeline():
    """Create a minimal pipeline for testing."""
    return {
        "oml_version": "0.1.0",
        "name": "test_imports",
        "steps": [
            {
                "id": "write_test",
                "component": "filesystem.csv_writer",
                "mode": "write",
                "config": {"path": "test.csv", "format": {"header": True}},
            }
        ],
    }


def test_e2b_import_selfcheck(minimal_pipeline, tmp_path):
    """Test that import self-check works in E2B sandbox."""
    from osiris.cli.main import compile_pipeline

    # Write minimal pipeline to file
    pipeline_file = tmp_path / "test_pipeline.yaml"
    import yaml

    with open(pipeline_file, "w") as f:
        yaml.dump(minimal_pipeline, f)

    # Compile the pipeline
    result = compile_pipeline(str(pipeline_file), output_dir=str(tmp_path))
    assert result is not None, "Compilation failed"

    compiled_manifest = tmp_path / "compiled" / "manifest.yaml"
    assert compiled_manifest.exists(), "Manifest not created"

    # Run with E2B but without credentials (dry run with install deps)
    # This should still initialize the sandbox and run import checks
    with tempfile.TemporaryDirectory():
        try:
            # Mock a simple DataFrame for the writer
            import pandas as pd

            pd.DataFrame({"col1": [1, 2], "col2": ["a", "b"]})

            # Run the pipeline in E2B mode
            from osiris.core.runner_v0 import Runner

            runner = Runner()

            # Set up E2B config
            e2b_config = {
                "target": "e2b",
                "install_deps": True,
                "dry_run": False,  # We want actual execution to see the import check
                "timeout": 60,
            }

            # Run and capture events
            events = []
            original_log_event = None

            if hasattr(runner, "session_context"):
                original_log_event = runner.session_context.log_event

                def capture_event(name, **kwargs):
                    events.append({"name": name, "data": kwargs})
                    if original_log_event:
                        original_log_event(name, **kwargs)

                runner.session_context.log_event = capture_event

            # Run the pipeline (may fail on actual execution, but we care about import check)
            try:
                runner.run(str(compiled_manifest), output_dir=str(tmp_path / "output"), **e2b_config)
            except Exception:
                # Execution might fail due to missing data, but import check should have run
                pass

            # Check that import_selfcheck_ok event was emitted
            import_check_events = [e for e in events if e["name"] in ["import_selfcheck_ok", "import_selfcheck_failed"]]

            # Also check for drivers_registered event after prepare
            [e for e in events if e["name"] == "drivers_registered"]
            assert len(import_check_events) > 0, f"No import check events found. Events: {events}"

            # Verify it was successful
            assert any(
                e["name"] == "import_selfcheck_ok" for e in import_check_events
            ), f"Import check failed: {import_check_events}"

            # Check that expected modules were imported
            success_event = next(e for e in import_check_events if e["name"] == "import_selfcheck_ok")
            imported_modules = success_event["data"].get("modules", [])
            assert "osiris" in imported_modules
            assert "osiris.components" in imported_modules
            assert "osiris.components.registry" in imported_modules

        except ImportError as e:
            pytest.skip(f"E2B SDK not available: {e}")


def test_e2b_drivers_registered(minimal_pipeline, tmp_path):
    """Test that drivers are properly registered in E2B sandbox."""
    from osiris.cli.main import compile_pipeline

    # Write minimal pipeline to file
    pipeline_file = tmp_path / "test_pipeline.yaml"
    import yaml

    with open(pipeline_file, "w") as f:
        yaml.dump(minimal_pipeline, f)

    # Compile the pipeline
    result = compile_pipeline(str(pipeline_file), output_dir=str(tmp_path))
    assert result is not None, "Compilation failed"

    compiled_manifest = tmp_path / "compiled" / "manifest.yaml"
    assert compiled_manifest.exists(), "Manifest not created"

    # Run with E2B
    with tempfile.TemporaryDirectory():
        try:
            from osiris.core.runner_v0 import Runner

            runner = Runner()

            # Set up E2B config
            e2b_config = {"target": "e2b", "install_deps": True, "dry_run": False, "timeout": 60}

            # Run and capture events
            events = []
            original_log_event = None

            if hasattr(runner, "session_context"):
                original_log_event = runner.session_context.log_event

                def capture_event(name, **kwargs):
                    events.append({"name": name, "data": kwargs})
                    if original_log_event:
                        original_log_event(name, **kwargs)

                runner.session_context.log_event = capture_event

            # Run the pipeline
            try:
                runner.run(str(compiled_manifest), output_dir=str(tmp_path / "output"), **e2b_config)
            except Exception:
                # Execution might fail, but we care about driver registration
                pass

            # Check that drivers_registered event was emitted
            driver_events = [e for e in events if e["name"] == "drivers_registered"]
            assert len(driver_events) > 0, f"No drivers_registered event found. Events: {events}"

            # Verify at least one driver was registered
            registered_drivers = driver_events[0]["data"].get("drivers", [])
            assert len(registered_drivers) > 0, "No drivers were registered"

            # Check that filesystem.csv_writer is among registered drivers
            assert (
                "filesystem.csv_writer" in registered_drivers
                or "osiris.drivers.filesystem_csv_writer_driver:FilesystemCsvWriterDriver" in str(registered_drivers)
            ), f"Expected driver not found. Registered: {registered_drivers}"

        except ImportError as e:
            pytest.skip(f"E2B SDK not available: {e}")
