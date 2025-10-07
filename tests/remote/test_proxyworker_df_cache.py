"""Test ProxyWorker DataFrame caching and spilling."""

import json
import os
from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd
import pytest

from osiris.remote.proxy_worker import ProxyWorker
from osiris.remote.rpc_protocol import ExecStepCommand


class MockExtractorDriver:
    """Mock extractor that returns a DataFrame."""

    def run(self, step_id, config, inputs, ctx):
        df = pd.DataFrame({"id": range(1, 15), "value": [f"val_{i}" for i in range(1, 15)]})
        return {"df": df}


class MockProcessorDriver:
    """Mock processor that expects a DataFrame input."""

    def run(self, step_id, config, inputs, ctx):
        if not inputs or "df" not in inputs:
            raise ValueError(f"Step {step_id}: Processor requires 'df' input")

        input_df = inputs["df"]
        if not isinstance(input_df, pd.DataFrame):
            raise ValueError(f"Step {step_id}: Expected DataFrame, got {type(input_df)}")

        # Transform - keep first 10 rows
        result_df = input_df.head(10)
        return {"df": result_df}


@pytest.fixture
def temp_session_dir(tmp_path):
    """Create a temporary session directory."""
    session_dir = tmp_path / "test_session"
    session_dir.mkdir(parents=True, exist_ok=True)

    # Create cfg directory with mock configs
    cfg_dir = session_dir / "cfg"
    cfg_dir.mkdir(exist_ok=True)

    (cfg_dir / "extract-data.json").write_text(
        json.dumps({"component": "mock.extractor", "query": "SELECT * FROM test"})
    )

    (cfg_dir / "process-data.json").write_text(
        json.dumps({"component": "mock.processor", "query": "SELECT * FROM input_df LIMIT 10"})
    )

    return session_dir


@pytest.fixture
def mock_driver_registry():
    """Create a mock driver registry."""
    registry = MagicMock()
    registry.get.side_effect = lambda name: {
        "mock.extractor": MockExtractorDriver(),
        "mock.processor": MockProcessorDriver(),
    }.get(name)
    return registry


def test_dataframe_in_memory_cache(temp_session_dir, mock_driver_registry):
    """Test that DataFrames are cached in memory by default."""
    worker = ProxyWorker()
    worker.session_dir = temp_session_dir
    worker.driver_registry = mock_driver_registry
    worker.manifest = {
        "steps": [
            {"id": "extract-data", "driver": "mock.extractor"},
            {"id": "process-data", "driver": "mock.processor"},
        ]
    }

    # Collect events and metrics
    events = []
    metrics = []

    def capture_event(name, **kwargs):
        events.append({"event": name, **kwargs})

    def capture_metric(name, value, **kwargs):
        metrics.append({"metric": name, "value": value, **kwargs})

    worker.send_event = capture_event
    worker.send_metric = capture_metric

    # Execute extractor step
    extract_cmd = ExecStepCommand(
        step_id="extract-data", driver="mock.extractor", cfg_path="cfg/extract-data.json", inputs=None
    )

    extract_resp = worker.handle_exec_step(extract_cmd)

    # Verify extractor results
    assert extract_resp.status == "complete"
    assert extract_resp.rows_processed == 14

    # Check that DataFrame is in memory cache
    assert "extract-data" in worker.step_outputs
    output = worker.step_outputs["extract-data"]
    assert "df" in output
    assert isinstance(output["df"], pd.DataFrame)
    assert len(output["df"]) == 14
    assert output.get("spilled") is False

    # Check metrics
    rows_out_metrics = [m for m in metrics if m["metric"] == "rows_out"]
    assert len(rows_out_metrics) == 1
    assert rows_out_metrics[0]["value"] == 14

    # Execute processor step with input from extractor
    process_cmd = ExecStepCommand(
        step_id="process-data",
        driver="mock.processor",
        cfg_path="cfg/process-data.json",
        inputs={"df": {"from_step": "extract-data", "key": "df"}},
    )

    process_resp = worker.handle_exec_step(process_cmd)

    # Verify processor results
    assert process_resp.status == "complete"
    assert process_resp.rows_processed == 10

    # Check inputs_resolved event
    input_events = [e for e in events if e["event"] == "inputs_resolved"]
    assert len(input_events) == 1
    assert input_events[0]["from_step"] == "extract-data"
    assert input_events[0]["rows"] == 14
    assert input_events[0]["from_memory"] is True


def test_dataframe_force_spill(temp_session_dir, mock_driver_registry):
    """Test that DataFrames are spilled to disk when E2B_FORCE_SPILL is set."""
    # Set force spill environment variable
    os.environ["E2B_FORCE_SPILL"] = "1"

    try:
        worker = ProxyWorker()
        worker.session_dir = temp_session_dir
        worker.driver_registry = mock_driver_registry
        worker.artifacts_root = temp_session_dir / "artifacts"
        worker.manifest = {
            "steps": [
                {"id": "extract-data", "driver": "mock.extractor"},
                {"id": "process-data", "driver": "mock.processor"},
            ]
        }

        # Collect events
        events = []

        def capture_event(name, **kwargs):
            events.append({"event": name, **kwargs})

        worker.send_event = capture_event
        worker.send_metric = lambda *args, **kwargs: None

        # Execute extractor step
        extract_cmd = ExecStepCommand(
            step_id="extract-data", driver="mock.extractor", cfg_path="cfg/extract-data.json", inputs=None
        )

        extract_resp = worker.handle_exec_step(extract_cmd)

        # Verify extractor results
        assert extract_resp.status == "complete"
        assert extract_resp.rows_processed == 14

        # Check that DataFrame is NOT in memory cache but spilled
        assert "extract-data" in worker.step_outputs
        output = worker.step_outputs["extract-data"]
        assert "df" not in output  # DataFrame removed from memory
        assert output.get("spilled") is True
        assert "df_path" in output
        assert "schema_path" in output

        # Verify parquet file exists
        parquet_path = Path(output["df_path"])
        assert parquet_path.exists()

        # Verify schema file exists
        schema_path = Path(output["schema_path"])
        assert schema_path.exists()

        # Check artifact events
        artifact_events = [e for e in events if e["event"] == "artifact_created"]
        parquet_events = [e for e in artifact_events if e.get("artifact_type") == "parquet"]
        schema_events = [e for e in artifact_events if e.get("artifact_type") == "schema"]
        assert len(parquet_events) == 1
        assert len(schema_events) == 1

        # Execute processor step - should load from spill
        process_cmd = ExecStepCommand(
            step_id="process-data",
            driver="mock.processor",
            cfg_path="cfg/process-data.json",
            inputs={"df": {"from_step": "extract-data", "key": "df"}},
        )

        process_resp = worker.handle_exec_step(process_cmd)

        # Verify processor results
        assert process_resp.status == "complete"
        assert process_resp.rows_processed == 10

        # Check inputs_resolved event shows loading from spill
        input_events = [e for e in events if e["event"] == "inputs_resolved"]
        assert len(input_events) == 1
        assert input_events[0]["from_step"] == "extract-data"
        assert input_events[0]["rows"] == 14
        assert input_events[0].get("from_spill") is True

    finally:
        # Clean up environment variable
        del os.environ["E2B_FORCE_SPILL"]


def test_dataframe_missing_input_error(temp_session_dir, mock_driver_registry):
    """Test clear error when DataFrame input is not found."""
    worker = ProxyWorker()
    worker.session_dir = temp_session_dir
    worker.driver_registry = mock_driver_registry
    worker.manifest = {"steps": [{"id": "process-data", "driver": "mock.processor"}]}

    worker.send_event = lambda *args, **kwargs: None
    worker.send_metric = lambda *args, **kwargs: None

    # Try to execute processor without upstream data
    process_cmd = ExecStepCommand(
        step_id="process-data",
        driver="mock.processor",
        cfg_path="cfg/process-data.json",
        inputs={"df": {"from_step": "missing-step", "key": "df"}},
    )

    # Should return error response with clear message
    response = worker.handle_exec_step(process_cmd)

    assert response.error is not None
    assert "Processor requires 'df' input" in response.error
    assert response.error_type == "ValueError"
