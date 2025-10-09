"""Integration test for MySQL to CSV pipeline."""

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
import yaml

from osiris.core.compiler_v0 import CompilerV0
from osiris.core.runner_v0 import RunnerV0

pytestmark = pytest.mark.skip(reason="Integration tests need rewrite for FilesystemContract v1 API")


class TestMySQLToCSVRun:
    """Test end-to-end MySQL to CSV pipeline execution."""

    @patch("osiris.drivers.mysql_extractor_driver.sa.create_engine")
    @patch("osiris.drivers.mysql_extractor_driver.pd.read_sql_query")
    def test_mysql_to_csv_pipeline(self, mock_read_sql, mock_create_engine, tmp_path):
        """Test complete pipeline from MySQL extraction to CSV writing."""
        # Setup mock MySQL data
        mock_engine = MagicMock()
        mock_create_engine.return_value = mock_engine

        # Mock different tables with data
        def read_sql_side_effect(query, engine):
            if "actors" in query.lower():
                return pd.DataFrame(
                    {
                        "id": [1, 2, 3],
                        "name": ["Tom Hanks", "Morgan Freeman", "Meryl Streep"],
                        "birth_year": [1956, 1937, 1949],
                    }
                )
            elif "directors" in query.lower():
                return pd.DataFrame(
                    {
                        "id": [1, 2],
                        "name": ["Steven Spielberg", "Christopher Nolan"],
                        "birth_year": [1946, 1970],
                    }
                )
            else:
                return pd.DataFrame()

        mock_read_sql.side_effect = read_sql_side_effect

        # Create simple OML
        oml = {
            "oml_version": "0.1.0",
            "name": "test-mysql-to-csv",
            "steps": [
                {
                    "id": "extract-actors",
                    "component": "mysql.extractor",
                    "mode": "read",
                    "config": {"connection": "@mysql.test", "query": "SELECT * FROM actors"},
                },
                {
                    "id": "write-actors",
                    "component": "filesystem.csv_writer",
                    "mode": "write",
                    "needs": ["extract-actors"],
                    "config": {"path": "output/actors.csv"},
                },
                {
                    "id": "extract-directors",
                    "component": "mysql.extractor",
                    "mode": "read",
                    "needs": [],  # Explicit empty needs for parallel execution
                    "config": {"connection": "@mysql.test", "query": "SELECT * FROM directors"},
                },
                {
                    "id": "write-directors",
                    "component": "filesystem.csv_writer",
                    "mode": "write",
                    "needs": ["extract-directors"],
                    "config": {"path": "output/directors.csv"},
                },
            ],
        }

        # Write OML file
        oml_path = tmp_path / "pipeline.yaml"
        with open(oml_path, "w") as f:
            yaml.dump(oml, f)

        # Create connection config
        connections = {
            "connections": {
                "mysql": {
                    "test": {
                        "host": "localhost",
                        "port": 3306,
                        "database": "test_db",
                        "user": "test_user",
                        "password": "${MYSQL_PASSWORD}",
                    }
                }
            }
        }

        conn_path = tmp_path / "osiris_connections.yaml"
        with open(conn_path, "w") as f:
            yaml.dump(connections, f)

        # Compile the pipeline
        compile_dir = tmp_path / "compiled"
        compiler = CompilerV0(output_dir=str(compile_dir))

        # Mock connection resolution for compilation
        with patch("osiris.core.config.resolve_connection") as mock_resolve:
            mock_resolve.return_value = {
                "host": "localhost",
                "port": 3306,
                "database": "test_db",
                "user": "test_user",
                "password": "test_pass",  # pragma: allowlist secret
            }

            # Set environment for password
            with patch.dict("os.environ", {"MYSQL_PASSWORD": "test_pass"}):  # pragma: allowlist secret
                success, message = compiler.compile(oml_path=str(oml_path), cli_params={})

        assert success, f"Compilation failed: {message}"

        # Verify manifest was created
        manifest_path = compile_dir / "manifest.yaml"
        assert manifest_path.exists()

        # Load and verify manifest structure
        with open(manifest_path) as f:
            manifest = yaml.safe_load(f)

        assert len(manifest["steps"]) == 4

        # Verify extract steps have no dependencies (explicit DAG structure)
        extract_actors = next(s for s in manifest["steps"] if s["id"] == "extract-actors")
        assert extract_actors["needs"] == []

        extract_directors = next(s for s in manifest["steps"] if s["id"] == "extract-directors")
        assert extract_directors["needs"] == []

        # Verify write steps depend only on their extracts
        write_actors = next(s for s in manifest["steps"] if s["id"] == "write-actors")
        assert write_actors["needs"] == ["extract-actors"]

        write_directors = next(s for s in manifest["steps"] if s["id"] == "write-directors")
        assert write_directors["needs"] == ["extract-directors"]

        # Run the pipeline
        run_dir = tmp_path / "run_output"
        runner = RunnerV0(str(manifest_path), output_dir=str(run_dir))

        # Mock connection resolution for runtime
        with patch("osiris.core.config.resolve_connection") as mock_resolve:
            mock_resolve.return_value = {
                "host": "localhost",
                "port": 3306,
                "database": "test_db",
                "user": "test_user",
                "password": "test_pass",  # pragma: allowlist secret
            }

            # Also set environment for password
            with patch.dict("os.environ", {"MYSQL_PASSWORD": "test_pass"}):  # pragma: allowlist secret
                # Change to temp dir for relative paths
                import os

                original_cwd = os.getcwd()
                try:
                    os.chdir(tmp_path)
                    success = runner.run()
                finally:
                    os.chdir(original_cwd)

        assert success, "Pipeline execution failed"

        # Verify CSV files were created
        actors_csv = tmp_path / "output" / "actors.csv"
        assert actors_csv.exists()

        directors_csv = tmp_path / "output" / "directors.csv"
        assert directors_csv.exists()

        # Verify CSV content
        actors_df = pd.read_csv(actors_csv)
        assert len(actors_df) == 3
        assert "name" in actors_df.columns
        assert "Tom Hanks" in actors_df["name"].values

        directors_df = pd.read_csv(directors_csv)
        assert len(directors_df) == 2
        assert "Christopher Nolan" in directors_df["name"].values

        # Verify columns are sorted lexicographically
        assert list(actors_df.columns) == sorted(actors_df.columns)
        assert list(directors_df.columns) == sorted(directors_df.columns)
