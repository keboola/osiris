"""Unit tests for filesystem CSV writer driver."""

from pathlib import Path

import duckdb
import pandas as pd
import pytest

from osiris.drivers.filesystem_csv_writer_driver import FilesystemCsvWriterDriver


class MockContext:
    """Mock context for testing with DuckDB connection."""

    def __init__(self, tmpdir):
        self.base_path = Path(tmpdir)
        self._db_connection = None
        self.metrics = {}

    def get_db_connection(self):
        """Get or create DuckDB connection."""
        if self._db_connection is None:
            db_path = self.base_path / "pipeline_data.duckdb"
            self._db_connection = duckdb.connect(str(db_path))
        return self._db_connection

    def log_metric(self, name: str, value):
        """Log a metric."""
        self.metrics[name] = value


class TestFilesystemCsvWriterDriver:
    """Test filesystem CSV writer driver."""

    def test_run_success(self, tmp_path):
        """Test successful CSV writing."""
        # Setup context with DuckDB
        mock_ctx = MockContext(tmp_path)
        con = mock_ctx.get_db_connection()

        # Create test data in DuckDB
        con.execute("CREATE TABLE test_data (name TEXT, age INT, city TEXT)")
        con.execute(
            "INSERT INTO test_data VALUES " "('Alice', 30, 'NYC'), " "('Bob', 25, 'LA'), " "('Charlie', 35, 'Chicago')"
        )

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
                "newline": "lf",
            },
            inputs={"table": "test_data"},
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
        assert mock_ctx.metrics["rows_written"] == 3

    def test_run_missing_table_input(self, tmp_path):
        """Test error when table input is missing."""
        mock_ctx = MockContext(tmp_path)
        driver = FilesystemCsvWriterDriver()

        with pytest.raises(ValueError, match="requires 'table' in inputs"):
            driver.run(step_id="test-write", config={"path": str(tmp_path / "output.csv")}, inputs={}, ctx=mock_ctx)

    def test_run_no_inputs(self, tmp_path):
        """Test error when inputs is None."""
        mock_ctx = MockContext(tmp_path)
        driver = FilesystemCsvWriterDriver()

        with pytest.raises(ValueError, match="requires 'table' in inputs"):
            driver.run(step_id="test-write", config={"path": str(tmp_path / "output.csv")}, inputs=None, ctx=mock_ctx)

    def test_run_missing_path(self, tmp_path):
        """Test error when path is missing."""
        mock_ctx = MockContext(tmp_path)
        con = mock_ctx.get_db_connection()
        con.execute("CREATE TABLE test_data (col INT)")
        con.execute("INSERT INTO test_data VALUES (1), (2), (3)")

        driver = FilesystemCsvWriterDriver()

        with pytest.raises(ValueError, match="'path' is required"):
            driver.run(step_id="test-write", config={}, inputs={"table": "test_data"}, ctx=mock_ctx)

    def test_run_custom_delimiter(self, tmp_path):
        """Test writing with custom delimiter."""
        mock_ctx = MockContext(tmp_path)
        con = mock_ctx.get_db_connection()
        con.execute("CREATE TABLE test_data (a INT, b INT)")
        con.execute("INSERT INTO test_data VALUES (1, 3), (2, 4)")

        output_file = tmp_path / "output.tsv"

        driver = FilesystemCsvWriterDriver()
        driver.run(
            step_id="test-write",
            config={"path": str(output_file), "delimiter": "\t"},
            inputs={"table": "test_data"},
            ctx=mock_ctx,
        )

        # Read file and verify delimiter
        with open(output_file) as f:
            content = f.read()
            assert "\t" in content
            assert "," not in content

    def test_run_no_header(self, tmp_path):
        """Test writing without header."""
        mock_ctx = MockContext(tmp_path)
        con = mock_ctx.get_db_connection()
        con.execute("CREATE TABLE test_data (a INT, b INT)")
        con.execute("INSERT INTO test_data VALUES (1, 3), (2, 4)")

        output_file = tmp_path / "output.csv"

        driver = FilesystemCsvWriterDriver()
        driver.run(
            step_id="test-write",
            config={"path": str(output_file), "header": False},
            inputs={"table": "test_data"},
            ctx=mock_ctx,
        )

        # Read file and verify no header
        with open(output_file) as f:
            lines = f.readlines()
            # First line should be data, not headers
            assert lines[0].strip() == "1,3"

    def test_run_creates_parent_directory(self, tmp_path):
        """Test that parent directories are created."""
        mock_ctx = MockContext(tmp_path)
        con = mock_ctx.get_db_connection()
        con.execute("CREATE TABLE test_data (col INT)")
        con.execute("INSERT INTO test_data VALUES (1), (2)")

        # Path with non-existent parent
        output_file = tmp_path / "nested" / "dir" / "output.csv"

        driver = FilesystemCsvWriterDriver()
        driver.run(step_id="test-write", config={"path": str(output_file)}, inputs={"table": "test_data"}, ctx=mock_ctx)

        # Verify file and parent dirs exist
        assert output_file.exists()
        assert output_file.parent.exists()

    def test_run_relative_path(self, tmp_path, monkeypatch):
        """Test writing to relative path."""
        mock_ctx = MockContext(tmp_path)
        con = mock_ctx.get_db_connection()
        con.execute("CREATE TABLE test_data (col INT)")
        con.execute("INSERT INTO test_data VALUES (1), (2)")

        # Change to temp directory
        monkeypatch.chdir(tmp_path)

        driver = FilesystemCsvWriterDriver()
        driver.run(
            step_id="test-write",
            config={"path": "relative/output.csv"},
            inputs={"table": "test_data"},
            ctx=mock_ctx,
        )

        # Verify file exists at expected location
        expected_file = tmp_path / "relative" / "output.csv"
        assert expected_file.exists()

    def test_run_empty_table(self, tmp_path):
        """Test writing empty table."""
        mock_ctx = MockContext(tmp_path)
        con = mock_ctx.get_db_connection()
        con.execute("CREATE TABLE test_data (col INT)")
        # Don't insert any data

        output_file = tmp_path / "empty.csv"

        driver = FilesystemCsvWriterDriver()
        result = driver.run(
            step_id="test-write", config={"path": str(output_file)}, inputs={"table": "test_data"}, ctx=mock_ctx
        )

        # Verify file exists but is essentially empty (just header)
        assert output_file.exists()
        assert result == {}
        assert mock_ctx.metrics["rows_written"] == 0

    def test_nonexistent_table_error(self, tmp_path):
        """Test error when table does not exist."""
        mock_ctx = MockContext(tmp_path)
        driver = FilesystemCsvWriterDriver()

        output_file = tmp_path / "output.csv"

        with pytest.raises(ValueError, match="Table.*does not exist"):
            driver.run(
                step_id="test-write",
                config={"path": str(output_file)},
                inputs={"table": "nonexistent_table"},
                ctx=mock_ctx,
            )
