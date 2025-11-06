"""Unit tests for filesystem CSV writer driver."""

from unittest.mock import MagicMock

import pandas as pd
import pytest

from osiris.drivers.filesystem_csv_writer_driver import FilesystemCsvWriterDriver


class TestFilesystemCsvWriterDriver:
    """Test filesystem CSV writer driver."""

    def test_run_success(self, tmp_path):
        """Test successful CSV writing."""
        # Create test DataFrame
        test_df = pd.DataFrame(
            {
                "name": ["Alice", "Bob", "Charlie"],
                "age": [30, 25, 35],
                "city": ["NYC", "LA", "Chicago"],
            }
        )

        # Setup context with metrics logging
        mock_ctx = MagicMock()

        # Output path
        output_file = tmp_path / "output.csv"

        # Create driver and run
        driver = FilesystemCsvWriterDriver()
        result = driver.run(
            step_id="test-write",
            config={
                "path": str(output_file),
                "delimiter": ",",
                "header": True,
                "encoding": "utf-8",
                "newline": "\n",
            },
            inputs={"df_upstream": test_df},
            ctx=mock_ctx,
        )

        # Verify result
        assert result == {}

        # Verify file exists
        assert output_file.exists()

        # Read and verify content
        written_df = pd.read_csv(output_file)
        assert len(written_df) == 3
        # Columns should be sorted lexicographically
        assert list(written_df.columns) == ["age", "city", "name"]

        # Verify data integrity
        assert written_df["name"].tolist() == ["Alice", "Bob", "Charlie"]
        assert written_df["age"].tolist() == [30, 25, 35]
        assert written_df["city"].tolist() == ["NYC", "LA", "Chicago"]

        # Verify metrics logged
        mock_ctx.log_metric.assert_called_once_with("rows_written", 3)

    def test_run_missing_df_input(self, tmp_path):
        """Test error when DataFrame input is missing."""
        driver = FilesystemCsvWriterDriver()

        with pytest.raises(ValueError, match="requires inputs with DataFrame"):
            driver.run(step_id="test-write", config={"path": str(tmp_path / "output.csv")}, inputs={})

    def test_run_no_inputs(self, tmp_path):
        """Test error when inputs is None."""
        driver = FilesystemCsvWriterDriver()

        with pytest.raises(ValueError, match="requires inputs with DataFrame"):
            driver.run(step_id="test-write", config={"path": str(tmp_path / "output.csv")}, inputs=None)

    def test_run_missing_path(self):
        """Test error when path is missing."""
        driver = FilesystemCsvWriterDriver()
        test_df = pd.DataFrame({"col": [1, 2, 3]})

        with pytest.raises(ValueError, match="'path' is required"):
            driver.run(step_id="test-write", config={}, inputs={"df_upstream": test_df})

    def test_run_custom_delimiter(self, tmp_path):
        """Test writing with custom delimiter."""
        test_df = pd.DataFrame({"a": [1, 2], "b": [3, 4]})

        output_file = tmp_path / "output.tsv"

        driver = FilesystemCsvWriterDriver()
        driver.run(
            step_id="test-write",
            config={"path": str(output_file), "delimiter": "\t"},
            inputs={"df_upstream": test_df},
        )

        # Read file and verify delimiter
        with open(output_file) as f:
            content = f.read()
            assert "\t" in content
            assert "," not in content

    def test_run_no_header(self, tmp_path):
        """Test writing without header."""
        test_df = pd.DataFrame({"a": [1, 2], "b": [3, 4]})

        output_file = tmp_path / "output.csv"

        driver = FilesystemCsvWriterDriver()
        driver.run(
            step_id="test-write",
            config={"path": str(output_file), "header": False},
            inputs={"df_upstream": test_df},
        )

        # Read file and verify no header
        with open(output_file) as f:
            lines = f.readlines()
            # First line should be data, not headers
            assert lines[0].strip() == "1,3"

    def test_run_creates_parent_directory(self, tmp_path):
        """Test that parent directories are created."""
        test_df = pd.DataFrame({"col": [1, 2]})

        # Path with non-existent parent
        output_file = tmp_path / "nested" / "dir" / "output.csv"

        driver = FilesystemCsvWriterDriver()
        driver.run(step_id="test-write", config={"path": str(output_file)}, inputs={"df_upstream": test_df})

        # Verify file and parent dirs exist
        assert output_file.exists()
        assert output_file.parent.exists()

    def test_run_relative_path(self, tmp_path, monkeypatch):
        """Test writing to relative path."""
        # Change to temp directory
        monkeypatch.chdir(tmp_path)

        test_df = pd.DataFrame({"col": [1, 2]})

        driver = FilesystemCsvWriterDriver()
        driver.run(step_id="test-write", config={"path": "relative/output.csv"}, inputs={"df_upstream": test_df})

        # Verify file exists at expected location
        expected_file = tmp_path / "relative" / "output.csv"
        assert expected_file.exists()

    def test_run_empty_dataframe(self, tmp_path):
        """Test writing empty DataFrame."""
        test_df = pd.DataFrame()

        output_file = tmp_path / "empty.csv"

        driver = FilesystemCsvWriterDriver()
        result = driver.run(step_id="test-write", config={"path": str(output_file)}, inputs={"df_upstream": test_df})

        # Verify file exists but is essentially empty
        assert output_file.exists()
        assert result == {}
