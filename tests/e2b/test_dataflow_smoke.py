"""E2B dataflow smoke test - tests end-to-end DataFrame flow."""

import json
import os

import pytest

from osiris.core.adapter_factory import get_execution_adapter


@pytest.mark.skipif(not os.environ.get("E2B_API_KEY"), reason="E2B_API_KEY not set")
class TestE2BDataflow:
    """Test E2B dataflow with real sandbox."""

    def test_extractor_to_processor_to_writer(self, tmp_path):
        """Test pipeline: MySQL extractor → DuckDB processor → CSV writer."""
        # Create a simple pipeline that tests DataFrame flow
        pipeline_yaml = tmp_path / "test_pipeline.yaml"
        pipeline_yaml.write_text(
            """
oml_version: 0.1.0
name: test-dataflow
steps:
  - id: extract-test-data
    component: mysql.extractor
    config:
      connection: "@mysql.db_movies"
      query: |
        SELECT movie_id, title, release_year
        FROM movies
        LIMIT 20

  - id: process-data
    component: duckdb.processor
    needs: [extract-test-data]
    config:
      query: |
        SELECT
          release_year,
          COUNT(*) as movie_count
        FROM input_df
        GROUP BY release_year
        ORDER BY release_year DESC

  - id: write-results
    component: filesystem.csv_writer
    needs: [process-data]
    config:
      path: output/year_stats.csv
"""
        )

        # Compile the pipeline
        from osiris.core.compiler_v0 import CompilerV0

        compiler = CompilerV0()
        compile_result = compiler.compile(str(pipeline_yaml), output_dir=str(tmp_path / "compiled"))

        assert compile_result["success"]
        manifest_path = compile_result["manifest_path"]

        # Load the manifest
        from osiris.core.utils import load_manifest

        manifest = load_manifest(manifest_path)

        # Create execution context
        from osiris.core.execution_adapter import ExecutionContext

        context = ExecutionContext(session_id=f"test_dataflow_{os.getpid()}", artifacts_dir=tmp_path / "artifacts")

        # Get E2B adapter
        adapter = get_execution_adapter("e2b", {"verbose": True})

        # Prepare and execute
        plan = {"manifest": manifest}
        prepared = adapter.prepare(plan, context)

        # Execute the pipeline
        result = adapter.execute(prepared, context)

        # Verify execution success
        assert result["success"]
        assert result["steps_executed"] == 3
        assert result["total_rows"] > 0

        # Load and check events
        events_file = context.session_dir / "events.jsonl"
        assert events_file.exists()

        events = []
        with open(events_file) as f:
            for line in f:
                events.append(json.loads(line))

        # Check for key events
        event_names = {e.get("event") for e in events}

        # Should have import and driver events from prepare
        assert "import_selfcheck_ok" in event_names
        assert "drivers_registered" in event_names

        # Should have step events
        assert "step_start" in event_names
        assert "step_complete" in event_names

        # Should have inputs_resolved for processor and writer
        input_events = [e for e in events if e.get("event") == "inputs_resolved"]
        assert len(input_events) >= 2  # processor and writer

        # Check processor got input from extractor
        processor_inputs = [e for e in input_events if e.get("step_id") == "process-data"]
        assert len(processor_inputs) == 1
        assert processor_inputs[0]["from_step"] == "extract-test-data"
        assert processor_inputs[0]["rows"] > 0

        # Check writer got input from processor
        writer_inputs = [e for e in input_events if e.get("step_id") == "write-results"]
        assert len(writer_inputs) == 1
        assert writer_inputs[0]["from_step"] == "process-data"

        # Check rows_out metrics
        metrics_file = context.session_dir / "metrics.jsonl"
        assert metrics_file.exists()

        metrics = []
        with open(metrics_file) as f:
            for line in f:
                metrics.append(json.loads(line))

        rows_out_metrics = [m for m in metrics if m.get("metric") == "rows_out"]
        assert len(rows_out_metrics) >= 2  # extractor and processor produce DataFrames

        # Check run_card has DataFrame tracking
        run_card_path = context.artifacts_dir / "_system" / "run_card.json"
        if run_card_path.exists():
            with open(run_card_path) as f:
                run_card = json.load(f)

            assert "steps" in run_card
            for step_info in run_card["steps"]:
                # Check DataFrame tracking fields
                assert "has_df_in_memory" in step_info
                assert "spill_used" in step_info
                if step_info["spill_used"]:
                    assert "spill_paths" in step_info

        # Cleanup is handled by adapter
        adapter.cleanup(context)
