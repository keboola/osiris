"""Integration test for compile and run with filesystem.csv_writer."""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import yaml

from osiris.core.compiler_v0 import CompilerV0
from osiris.core.runner_v0 import RunnerV0


class TestCompileRunCSVWriter:
    """Test compile and run pipeline with filesystem.csv_writer."""

    def test_compile_csv_writer_pipeline(self):
        """Test compiling a pipeline with filesystem.csv_writer."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create OML file
            oml = {
                "oml_version": "0.1.0",
                "name": "test-csv-writer",
                "steps": [
                    {
                        "id": "extract-data",
                        "component": "mysql.extractor",
                        "mode": "read",
                        "config": {
                            "connection": "@mysql.test_db",
                            "query": "SELECT * FROM test_table",
                        },
                    },
                    {
                        "id": "write-csv",
                        "component": "filesystem.csv_writer",
                        "mode": "write",
                        "needs": ["extract-data"],
                        "config": {
                            "path": f"{tmpdir}/output.csv",
                            "delimiter": ",",
                            "header": True,
                            "encoding": "utf-8",
                            "newline": "lf",
                        },
                    },
                ],
            }

            oml_path = Path(tmpdir) / "pipeline.yaml"
            with open(oml_path, "w") as f:
                yaml.dump(oml, f)

            # Compile the pipeline
            compiler = CompilerV0(output_dir=f"{tmpdir}/compiled")
            success, message = compiler.compile(str(oml_path))

            assert success, f"Compilation failed: {message}"

            # Check manifest
            manifest_path = Path(tmpdir) / "compiled" / "manifest.yaml"
            assert manifest_path.exists()

            with open(manifest_path) as f:
                manifest = yaml.safe_load(f)

            # Verify steps
            assert len(manifest["steps"]) == 2
            assert manifest["steps"][0]["driver"] == "mysql.extractor"
            assert manifest["steps"][1]["driver"] == "filesystem.csv_writer"

            # Check configs
            extract_config_path = Path(tmpdir) / "compiled" / "cfg" / "extract-data.json"
            write_config_path = Path(tmpdir) / "compiled" / "cfg" / "write-csv.json"

            assert extract_config_path.exists()
            assert write_config_path.exists()

            with open(write_config_path) as f:
                write_config = json.load(f)

            assert write_config["component"] == "filesystem.csv_writer"
            assert write_config["path"] == f"{tmpdir}/output.csv"
            assert write_config["delimiter"] == ","
            assert write_config["header"] is True

    @patch("osiris.core.config.resolve_connection")
    def test_run_csv_writer_pipeline(self, mock_resolve_connection):
        """Test running a pipeline with filesystem.csv_writer."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Mock connection resolution
            mock_resolve_connection.return_value = {
                "host": "localhost",
                "database": "test_db",
                "user": "test_user",
                "password": "test_pass",  # pragma: allowlist secret
            }

            # Create test data
            test_data = pd.DataFrame(
                {"id": [1, 2, 3], "name": ["Alice", "Bob", "Charlie"], "age": [30, 25, 35]}
            )

            # Create manifest
            manifest = {
                "pipeline": {"id": "test-csv-writer", "version": "0.1.0", "fingerprints": {}},
                "steps": [
                    {
                        "id": "extract-data",
                        "driver": "mysql.extractor",
                        "cfg_path": "cfg/extract-data.json",
                        "needs": [],
                    },
                    {
                        "id": "write-csv",
                        "driver": "filesystem.csv_writer",
                        "cfg_path": "cfg/write-csv.json",
                        "needs": ["extract-data"],
                    },
                ],
                "meta": {"oml_version": "0.1.0", "profile": "default", "run_id": "test_run"},
            }

            # Create config files
            cfg_dir = Path(tmpdir) / "cfg"
            cfg_dir.mkdir()

            extract_config = {
                "component": "mysql.extractor",
                "mode": "read",
                "connection": "@mysql.test_db",
                "query": "SELECT * FROM test_table",
            }

            write_config = {
                "component": "filesystem.csv_writer",
                "mode": "write",
                "path": f"{tmpdir}/output.csv",
                "delimiter": ",",
                "header": True,
                "encoding": "utf-8",
                "newline": "lf",
            }

            with open(cfg_dir / "extract-data.json", "w") as f:
                json.dump(extract_config, f)

            with open(cfg_dir / "write-csv.json", "w") as f:
                json.dump(write_config, f)

            # Mock MySQL extractor to return test data
            with patch("osiris.connectors.mysql.extractor.MySQLExtractor") as mock_mysql:
                mock_extractor = MagicMock()
                mock_extractor.extract.return_value = test_data
                mock_mysql.return_value = mock_extractor

                # Save manifest
                manifest_path = Path(tmpdir) / "manifest.yaml"
                with open(manifest_path, "w") as f:
                    yaml.dump(manifest, f)

                # Run the pipeline
                runner = RunnerV0(str(manifest_path))
                runner.manifest_dir = Path(tmpdir)
                result = runner.run(manifest)

                # Check results
                assert result["status"] == "success"
                assert len(result["steps"]) == 2

                # Verify CSV file was created
                csv_path = Path(tmpdir) / "output.csv"
                assert csv_path.exists()

                # Read and verify CSV contents
                written_df = pd.read_csv(csv_path)
                assert len(written_df) == 3
                assert list(written_df.columns) == ["age", "id", "name"]  # Lexicographic order
                assert written_df["name"].tolist() == ["Alice", "Bob", "Charlie"]

    def test_csv_writer_error_handling(self):
        """Test error handling when CSV writer fails."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create manifest with invalid path
            manifest = {
                "pipeline": {"id": "test-error", "version": "0.1.0", "fingerprints": {}},
                "steps": [
                    {
                        "id": "write-csv",
                        "driver": "filesystem.csv_writer",
                        "cfg_path": "cfg/write-csv.json",
                        "needs": [],
                    }
                ],
                "meta": {"oml_version": "0.1.0", "profile": "default", "run_id": "test_run"},
            }

            # Create config with non-existent parent directory
            cfg_dir = Path(tmpdir) / "cfg"
            cfg_dir.mkdir()

            write_config = {
                "component": "filesystem.csv_writer",
                "mode": "write",
                "path": "/invalid/path/that/does/not/exist/output.csv",
                "create_dirs": False,  # Don't create parent dirs
            }

            with open(cfg_dir / "write-csv.json", "w") as f:
                json.dump(write_config, f)

            # Save manifest
            manifest_path = Path(tmpdir) / "manifest.yaml"
            with open(manifest_path, "w") as f:
                yaml.dump(manifest, f)

            # Run should handle the error gracefully
            runner = RunnerV0(str(manifest_path))
            runner.manifest_dir = Path(tmpdir)

            # Mock step data to provide input
            runner.step_data = {"write-csv": [{"test": "data"}]}

            result = runner.run(manifest)

            # Should fail but not crash
            assert result["status"] == "failed"
            assert "write-csv" in result["steps"]
            assert result["steps"]["write-csv"]["status"] == "failed"
