"""E2B smoke test for MySQL → DuckDB → Supabase pipeline."""

import json
import os
from pathlib import Path

import pytest

from osiris.core.compiler_v0 import CompilerV0
from osiris.core.runner_v0 import RunnerV0


@pytest.mark.e2b
@pytest.mark.skipif(not os.getenv("E2B_API_KEY"), reason="E2B_API_KEY not set")
@pytest.mark.skipif(
    not os.getenv("MYSQL_PASSWORD") or not os.getenv("SUPABASE_SERVICE_ROLE_KEY"),
    reason="Missing required credentials (MYSQL_PASSWORD or SUPABASE_SERVICE_ROLE_KEY)",
)
class TestDuckDBPipelineE2B:
    """Test MySQL → DuckDB → Supabase pipeline in E2B sandbox."""

    @pytest.fixture
    def demo_oml_path(self):
        """Path to the demo OML file."""
        return Path(__file__).parent.parent.parent / "docs/examples/mysql_duckdb_supabase_demo.yaml"

    @pytest.fixture
    def temp_workspace(self, tmp_path):
        """Create a temporary workspace with connections."""
        # Copy osiris_connections.yaml from testing_env
        connections_src = Path(__file__).parent.parent.parent / "testing_env/osiris_connections.yaml"
        if connections_src.exists():
            connections_dst = tmp_path / "osiris_connections.yaml"
            connections_dst.write_text(connections_src.read_text())

        return tmp_path

    def test_duckdb_pipeline_e2b(self, demo_oml_path, temp_workspace):
        """Test that DuckDB pipeline runs successfully in E2B."""
        # Compile
        compiler = CompilerV0(
            source_path=str(demo_oml_path),
            output_dir=str(temp_workspace / "compiled"),
        )
        manifest_path = compiler.compile()
        assert manifest_path is not None

        # Create session directory
        session_dir = temp_workspace / "run_e2b_test"
        session_dir.mkdir(exist_ok=True)
        artifacts_dir = session_dir / "artifacts"
        artifacts_dir.mkdir(exist_ok=True)

        # Run in E2B
        runner = RunnerV0(
            manifest_path=manifest_path,
            output_dir=str(artifacts_dir),
            target="e2b",  # Force E2B execution
        )

        original_cwd = os.getcwd()
        try:
            os.chdir(temp_workspace)
            success = runner.run()
            assert success is True, "Pipeline failed to execute in E2B"

            # Check metrics to verify DuckDB transformation
            metrics_file = artifacts_dir.parent / "metrics.jsonl"
            if metrics_file.exists():
                with open(metrics_file) as f:
                    metrics = [json.loads(line) for line in f if line.strip()]

                # Look for DuckDB step metrics
                duckdb_metrics = [
                    m
                    for m in metrics
                    if m.get("step_id") == "compute-director-stats" and m.get("metric") == "rows_written"
                ]

                assert len(duckdb_metrics) > 0, "No DuckDB metrics found"
                rows_out = duckdb_metrics[0].get("value", 0)
                assert rows_out > 0, "DuckDB produced 0 rows, expected > 0"

                # Look for Supabase writer metrics
                supabase_metrics = [
                    m
                    for m in metrics
                    if m.get("step_id") == "write-director-stats" and m.get("metric") == "rows_written"
                ]

                assert len(supabase_metrics) > 0, "No Supabase metrics found"
                rows_written = supabase_metrics[0].get("value", 0)
                assert rows_written > 0, "Supabase writer wrote 0 rows, expected > 0"

                print(
                    f"✅ E2B smoke test passed: DuckDB transformed {rows_out} rows, Supabase wrote {rows_written} rows"
                )

        finally:
            os.chdir(original_cwd)

    def test_duckdb_driver_registered_e2b(self, demo_oml_path, temp_workspace):
        """Test that DuckDB driver is registered in E2B ProxyWorker."""
        # Compile
        compiler = CompilerV0(
            source_path=str(demo_oml_path),
            output_dir=str(temp_workspace / "compiled"),
        )
        manifest_path = compiler.compile()

        # Create session directory
        session_dir = temp_workspace / "run_registration_test"
        session_dir.mkdir(exist_ok=True)
        artifacts_dir = session_dir / "artifacts"
        artifacts_dir.mkdir(exist_ok=True)
        events_file = session_dir / "events.jsonl"
        events_file.touch()

        # Run in E2B
        runner = RunnerV0(
            manifest_path=manifest_path,
            output_dir=str(artifacts_dir),
            target="e2b",
        )

        original_cwd = os.getcwd()
        try:
            os.chdir(temp_workspace)
            runner.run()

            # Check events for driver registration
            with open(events_file) as f:
                events = [json.loads(line) for line in f if line.strip()]

            # Look for driver registration events
            driver_events = [
                e for e in events if e.get("event") == "driver_registered" and e.get("driver") == "duckdb.processor"
            ]

            assert len(driver_events) > 0, "DuckDB driver was not registered in E2B ProxyWorker"
            print("✅ DuckDB driver successfully registered in E2B")

        finally:
            os.chdir(original_cwd)
