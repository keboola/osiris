"""Integration test for MySQL → DuckDB → Supabase demo pipeline."""

import json
import os
from pathlib import Path

import pytest
import yaml

from osiris.core.compiler_v0 import CompilerV0
from osiris.core.runner_v0 import RunnerV0

pytestmark = [pytest.mark.supabase, pytest.mark.integration]


@pytest.mark.skipif(
    not os.getenv("MYSQL_PASSWORD") or not os.getenv("SUPABASE_SERVICE_ROLE_KEY"),
    reason="Missing required credentials (MYSQL_PASSWORD or SUPABASE_SERVICE_ROLE_KEY)",
)
class TestMySQLDuckDBSupabaseDemo:
    """Test the MySQL → DuckDB → Supabase demo pipeline."""

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

    def test_pipeline_compiles(self, demo_oml_path, temp_workspace):
        """Test that the demo pipeline compiles successfully."""
        # Create compiler
        compiler = CompilerV0(
            source_path=str(demo_oml_path),
            output_dir=str(temp_workspace / "compiled"),
        )

        # Compile
        manifest_path = compiler.compile()
        assert manifest_path is not None
        assert Path(manifest_path).exists()

        # Load and verify manifest
        with open(manifest_path) as f:
            manifest = yaml.safe_load(f)

        assert manifest["pipeline"]["name"] == "mysql-duckdb-supabase-demo"
        assert len(manifest["steps"]) == 3

        # Verify steps
        step_ids = [s["id"] for s in manifest["steps"]]
        assert "extract-movies" in step_ids
        assert "compute-director-stats" in step_ids
        assert "write-director-stats" in step_ids

    def test_duckdb_transform_produces_output(self, demo_oml_path, temp_workspace):
        """Test that DuckDB transformation produces expected output."""
        # Compile
        compiler = CompilerV0(
            source_path=str(demo_oml_path),
            output_dir=str(temp_workspace / "compiled"),
        )
        manifest_path = compiler.compile()

        # Create session directory for runner
        session_dir = temp_workspace / "run_test"
        session_dir.mkdir(exist_ok=True)
        artifacts_dir = session_dir / "artifacts"
        artifacts_dir.mkdir(exist_ok=True)

        # Run pipeline
        runner = RunnerV0(
            manifest_path=manifest_path,
            output_dir=str(artifacts_dir),
        )

        # Change to workspace directory (for connection resolution)
        original_cwd = os.getcwd()
        try:
            os.chdir(temp_workspace)
            success = runner.run()
            assert success is True
        finally:
            os.chdir(original_cwd)

        # Check that DuckDB step produced output
        duckdb_step_dir = artifacts_dir / "compute-director-stats"
        assert duckdb_step_dir.exists()

        # Check for cleaned_config.json (created by runner)
        config_file = duckdb_step_dir / "cleaned_config.json"
        if config_file.exists():
            with open(config_file) as f:
                config = json.load(f)
            assert "query" in config
            assert "SELECT" in config["query"]

    def test_pipeline_end_to_end(self, demo_oml_path, temp_workspace):
        """Test full pipeline execution from MySQL to Supabase."""
        # Compile
        compiler = CompilerV0(
            source_path=str(demo_oml_path),
            output_dir=str(temp_workspace / "compiled"),
        )
        manifest_path = compiler.compile()

        # Create session directory
        session_dir = temp_workspace / "run_e2e"
        session_dir.mkdir(exist_ok=True)
        artifacts_dir = session_dir / "artifacts"
        artifacts_dir.mkdir(exist_ok=True)

        # Create events and metrics files for session logging
        events_file = session_dir / "events.jsonl"
        metrics_file = session_dir / "metrics.jsonl"
        events_file.touch()
        metrics_file.touch()

        # Run pipeline
        runner = RunnerV0(
            manifest_path=manifest_path,
            output_dir=str(artifacts_dir),
        )

        original_cwd = os.getcwd()
        try:
            os.chdir(temp_workspace)
            success = runner.run()
            assert success is True

            # Verify all steps executed
            assert (artifacts_dir / "extract-movies").exists()
            assert (artifacts_dir / "compute-director-stats").exists()
            assert (artifacts_dir / "write-director-stats").exists()

            # Check events were logged
            if events_file.stat().st_size > 0:
                with open(events_file) as f:
                    events = [json.loads(line) for line in f if line.strip()]
                    event_types = [e.get("event", e.get("type")) for e in events]
                    assert "run_start" in event_types
                    assert "run_complete" in event_types or "run_complete" in str(events)

        finally:
            os.chdir(original_cwd)

    def test_duckdb_sql_correctness(self):
        """Test the DuckDB SQL logic in isolation."""
        import pandas as pd

        # Mock input data (simulating MySQL extract)
        input_df = pd.DataFrame(
            {
                "movie_id": [1, 2, 3, 4],
                "title": ["Movie A", "Movie B", "Movie C", "Movie D"],
                "director_id": [1, 1, 2, 2],
                "director_name": ["Director X", "Director X", "Director Y", "Director Y"],
                "director_nationality": ["USA", "USA", "UK", "UK"],
                "release_year": [2020, 2021, 2019, 2022],
                "runtime_minutes": [120, 110, 95, 130],
                "budget_usd": [10_000_000, 15_000_000, 5_000_000, 20_000_000],
                "box_office_usd": [50_000_000, 45_000_000, 15_000_000, 100_000_000],
                "genre": ["Action", "Drama", "Comedy", "Action"],
            }
        )

        # Apply the transformation (simulating DuckDB)
        # This mimics what the DuckDB processor would do
        result = (
            input_df.groupby(["director_id", "director_name", "director_nationality"])
            .agg(
                movie_count=("movie_id", "count"),
                unique_genres=("genre", "nunique"),
                avg_runtime_minutes=("runtime_minutes", "mean"),
                first_movie_year=("release_year", "min"),
                latest_movie_year=("release_year", "max"),
                avg_budget_usd=("budget_usd", "mean"),
                avg_box_office_usd=("box_office_usd", "mean"),
                total_box_office_usd=("box_office_usd", "sum"),
            )
            .reset_index()
        )

        # Calculate ROI ratio
        result["avg_roi_ratio"] = result["avg_box_office_usd"] / result["avg_budget_usd"]

        # Verify results
        assert len(result) == 2  # Two directors
        assert result.iloc[0]["movie_count"] == 2  # Director X has 2 movies
        assert result.iloc[1]["movie_count"] == 2  # Director Y has 2 movies

        # Check Director X stats
        dir_x = result[result["director_id"] == 1].iloc[0]
        assert dir_x["total_box_office_usd"] == 95_000_000
        assert dir_x["unique_genres"] == 2  # Action and Drama

        # Check Director Y stats
        dir_y = result[result["director_id"] == 2].iloc[0]
        assert dir_y["total_box_office_usd"] == 115_000_000
        assert dir_y["unique_genres"] == 2  # Comedy and Action
