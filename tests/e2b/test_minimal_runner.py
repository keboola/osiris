"""Test minimal E2B runner functionality.

This test verifies basic E2B execution with a simple CSV writer pipeline.
"""

import os

import pytest

# Skip all tests if E2B_API_KEY not available
pytestmark = pytest.mark.skipif(not os.environ.get("E2B_API_KEY"), reason="E2B_API_KEY not set - skipping E2B tests")


@pytest.fixture
def csv_writer_pipeline():
    """Create a minimal CSV writer pipeline."""
    return {
        "oml_version": "0.1.0",
        "name": "minimal_csv_test",
        "steps": [
            {
                "id": "generate_data",
                "component": "duckdb.processor",
                "mode": "transform",
                "config": {"query": "SELECT 1 as id, 'test' as name UNION SELECT 2, 'data'"},
            },
            {
                "id": "write_csv",
                "component": "filesystem.csv_writer",
                "mode": "write",
                "config": {"path": "output.csv", "format": {"header": True, "delimiter": ","}},
                "input": {"df": {"step": "generate_data", "output": "df"}},
            },
        ],
    }


def test_minimal_e2b_execution(csv_writer_pipeline, tmp_path):
    """Test basic E2B execution with CSV writer."""
    import yaml

    from osiris.cli.main import compile_pipeline

    # Write pipeline to file
    pipeline_file = tmp_path / "test_pipeline.yaml"
    with open(pipeline_file, "w") as f:
        yaml.dump(csv_writer_pipeline, f)

    # Compile the pipeline
    compile_result = compile_pipeline(str(pipeline_file), output_dir=str(tmp_path))
    assert compile_result is not None, "Compilation failed"

    compiled_manifest = tmp_path / "compiled" / "manifest.yaml"
    assert compiled_manifest.exists(), "Manifest not created"

    # Run with E2B
    try:
        from osiris.core.runner_v0 import Runner
        from osiris.core.session_logging import SessionContext

        runner = Runner()

        # Create session context for logging
        session_id = f"test_minimal_{os.getpid()}"
        session_dir = tmp_path / "session"
        session_dir.mkdir(exist_ok=True)

        session_context = SessionContext(session_id=session_id, base_path=session_dir, config={})

        # Capture events
        events = []
        metrics = []

        original_log_event = session_context.log_event
        original_log_metric = session_context.log_metric

        def capture_event(name, **kwargs):
            events.append({"name": name, "data": kwargs})
            original_log_event(name, **kwargs)

        def capture_metric(name, value):
            metrics.append({"name": name, "value": value})
            original_log_metric(name, value)

        session_context.log_event = capture_event
        session_context.log_metric = capture_metric

        # Set up E2B config
        e2b_config = {"target": "e2b", "install_deps": True, "timeout": 120, "session_context": session_context}

        # Run the pipeline
        result = runner.run(str(compiled_manifest), output_dir=str(tmp_path / "output"), **e2b_config)

        # Verify execution completed
        assert result is not None, "Execution returned None"

        # Check for successful events
        step_complete_events = [e for e in events if e["name"] == "step_complete"]
        assert len(step_complete_events) >= 2, f"Expected 2 step completions, got {len(step_complete_events)}"

        # Verify drivers were registered
        driver_events = [e for e in events if e["name"] == "drivers_registered"]
        assert len(driver_events) > 0, "No drivers_registered event"

        registered_drivers = driver_events[0]["data"].get("drivers", [])
        assert len(registered_drivers) > 0, "No drivers registered"

        # Check for known drivers
        driver_names_str = str(registered_drivers)
        assert (
            "csv_writer" in driver_names_str or "filesystem" in driver_names_str
        ), f"CSV writer not found in drivers: {registered_drivers}"
        assert (
            "duckdb" in driver_names_str or "processor" in driver_names_str
        ), f"DuckDB processor not found in drivers: {registered_drivers}"

        # Verify data flow metrics
        rows_metrics = [m for m in metrics if "rows" in m["name"]]
        assert len(rows_metrics) > 0, "No row metrics recorded"

        # Check that some rows were processed
        total_rows = sum(m["value"] for m in rows_metrics if m["value"] > 0)
        assert total_rows > 0, f"No rows processed. Metrics: {metrics}"

        # Verify import self-check passed
        import_check_events = [e for e in events if e["name"] in ["import_selfcheck_ok", "import_selfcheck_failed"]]
        assert len(import_check_events) > 0, "No import self-check event"
        assert import_check_events[0]["name"] == "import_selfcheck_ok", f"Import check failed: {import_check_events[0]}"

    except ImportError as e:
        pytest.skip(f"Required dependencies not available: {e}")
    except Exception as e:
        # Log detailed error information
        if "events" in locals():
            error_events = [e for e in events if "error" in e["name"].lower()]
            if error_events:
                pytest.fail(f"Execution failed with error events: {error_events}\nOriginal error: {e}")
        raise


def test_e2b_step_completion(csv_writer_pipeline, tmp_path):
    """Test that E2B properly reports step completion."""
    import yaml

    from osiris.cli.main import compile_pipeline

    # Write pipeline to file
    pipeline_file = tmp_path / "test_pipeline.yaml"
    with open(pipeline_file, "w") as f:
        yaml.dump(csv_writer_pipeline, f)

    # Compile the pipeline
    compile_result = compile_pipeline(str(pipeline_file), output_dir=str(tmp_path))
    assert compile_result is not None, "Compilation failed"

    compiled_manifest = tmp_path / "compiled" / "manifest.yaml"
    assert compiled_manifest.exists(), "Manifest not created"

    # Run with E2B
    try:
        from osiris.core.runner_v0 import Runner
        from osiris.core.session_logging import SessionContext

        runner = Runner()

        # Create session context
        session_id = f"test_steps_{os.getpid()}"
        session_dir = tmp_path / "session"
        session_dir.mkdir(exist_ok=True)

        session_context = SessionContext(session_id=session_id, base_path=session_dir, config={})

        # Capture events
        events = []

        original_log_event = session_context.log_event

        def capture_event(name, **kwargs):
            events.append({"name": name, "data": kwargs})
            original_log_event(name, **kwargs)

        session_context.log_event = capture_event

        # Run the pipeline
        e2b_config = {"target": "e2b", "install_deps": True, "timeout": 120, "session_context": session_context}

        runner.run(str(compiled_manifest), output_dir=str(tmp_path / "output"), **e2b_config)

        # Check step events
        step_events = [e for e in events if "step" in e["name"]]

        # Verify we have step_start and step_complete for each step
        step_starts = [e for e in step_events if e["name"] == "step_start"]
        step_completes = [e for e in step_events if e["name"] == "step_complete"]

        assert len(step_starts) == 2, f"Expected 2 step_start events, got {len(step_starts)}"
        assert len(step_completes) == 2, f"Expected 2 step_complete events, got {len(step_completes)}"

        # Verify step IDs match
        start_ids = {e["data"].get("step_id") for e in step_starts}
        complete_ids = {e["data"].get("step_id") for e in step_completes}

        assert "generate_data" in start_ids, "generate_data step not started"
        assert "generate_data" in complete_ids, "generate_data step not completed"
        assert "write_csv" in start_ids, "write_csv step not started"
        assert "write_csv" in complete_ids, "write_csv step not completed"

        # Verify completion statuses
        for complete_event in step_completes:
            assert (
                complete_event["data"].get("status") == "success"
            ), f"Step {complete_event['data'].get('step_id')} failed: {complete_event['data']}"

    except ImportError as e:
        pytest.skip(f"Required dependencies not available: {e}")
