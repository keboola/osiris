"""Tests for filesystem CSV writer component."""

import csv
from pathlib import Path
import tempfile

from osiris.connectors.filesystem.writer import FilesystemCSVWriter


class TestFilesystemCSVWriter:
    """Test filesystem CSV writer functionality."""

    def test_basic_csv_write(self):
        """Test basic CSV writing with headers."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = {"path": f"{tmpdir}/output.csv", "delimiter": ",", "header": True}

            data = [
                {"name": "Alice", "age": 30, "city": "NYC"},
                {"name": "Bob", "age": 25, "city": "LA"},
            ]

            writer = FilesystemCSVWriter(config)
            result = writer.write(data)

            assert result["rows_written"] == 2
            assert Path(result["path"]).exists()

            # Verify file contents
            with open(result["path"], encoding="utf-8") as f:
                reader = csv.DictReader(f)
                rows = list(reader)
                assert len(rows) == 2
                assert rows[0]["name"] == "Alice"
                assert rows[1]["name"] == "Bob"
                # Check deterministic column order (lexicographic)
                assert list(rows[0].keys()) == ["age", "city", "name"]

    def test_csv_without_headers(self):
        """Test CSV writing without headers."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = {"path": f"{tmpdir}/output.csv", "header": False}

            data = [
                {"col1": "a", "col2": "b"},
                {"col1": "c", "col2": "d"},
            ]

            writer = FilesystemCSVWriter(config)
            result = writer.write(data)

            assert result["rows_written"] == 2

            # Verify no header in file
            with open(result["path"]) as f:
                lines = f.readlines()
                assert len(lines) == 2
                assert "col1" not in lines[0]
                assert "col2" not in lines[0]

    def test_custom_delimiter(self):
        """Test CSV with custom delimiter (TSV)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = {"path": f"{tmpdir}/output.tsv", "delimiter": "\t", "header": True}

            data = [
                {"field1": "value1", "field2": "value2"},
            ]

            writer = FilesystemCSVWriter(config)
            result = writer.write(data)

            with open(result["path"]) as f:
                content = f.read()
                assert "\t" in content
                assert "," not in content

    def test_utf8_encoding(self):
        """Test UTF-8 encoding with special characters."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = {"path": f"{tmpdir}/output.csv", "encoding": "utf-8", "header": True}

            data = [
                {"name": "José", "text": "Hello 世界 🌍"},
                {"name": "Müller", "text": "Café ☕"},
            ]

            writer = FilesystemCSVWriter(config)
            result = writer.write(data)

            # Verify UTF-8 content
            with open(result["path"], encoding="utf-8") as f:
                content = f.read()
                assert "José" in content
                assert "世界" in content
                assert "Müller" in content
                assert "☕" in content

    def test_newline_normalization(self):
        """Test LF newline normalization."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = {"path": f"{tmpdir}/output.csv", "newline": "lf", "header": True}

            data = [
                {"col": "line1"},
                {"col": "line2"},
            ]

            writer = FilesystemCSVWriter(config)
            result = writer.write(data)

            # Read as binary to check newlines
            with open(result["path"], "rb") as f:
                content = f.read()
                # Should only have \n, not \r\n
                assert b"\r\n" not in content
                assert b"\n" in content

    def test_deterministic_column_order(self):
        """Test that columns are always in lexicographic order."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = {"path": f"{tmpdir}/output.csv", "header": True}

            # Provide columns in random order
            data = [
                {"zebra": 1, "apple": 2, "mango": 3},
                {"mango": 6, "apple": 5, "zebra": 4},
            ]

            writer = FilesystemCSVWriter(config)
            result = writer.write(data)

            with open(result["path"]) as f:
                header = f.readline().strip()
                # Columns should be alphabetically sorted
                assert header == "apple,mango,zebra"

    def test_create_parent_directories(self):
        """Test automatic parent directory creation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            nested_path = f"{tmpdir}/level1/level2/level3/output.csv"
            config = {"path": nested_path, "create_dirs": True}

            data = [{"col": "value"}]

            writer = FilesystemCSVWriter(config)
            result = writer.write(data)

            assert Path(result["path"]).exists()
            assert Path(result["path"]).parent.exists()

    def test_missing_columns_handled(self):
        """Test handling of rows with missing columns."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = {"path": f"{tmpdir}/output.csv", "header": True}

            data = [
                {"a": 1, "b": 2, "c": 3},
                {"a": 4, "b": 5},  # Missing 'c'
                {"a": 6, "c": 7},  # Missing 'b'
            ]

            writer = FilesystemCSVWriter(config)
            result = writer.write(data)

            assert result["rows_written"] == 3

            with open(result["path"]) as f:
                reader = csv.DictReader(f)
                rows = list(reader)
                assert rows[1]["c"] == ""  # Missing value should be empty
                assert rows[2]["b"] == ""  # Missing value should be empty

    def test_empty_data(self):
        """Test writing empty dataset."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = {"path": f"{tmpdir}/output.csv", "header": True}

            data = []

            writer = FilesystemCSVWriter(config)
            result = writer.write(data)

            assert result["rows_written"] == 0
            assert Path(result["path"]).exists()

            # File should be empty or just have headers
            with open(result["path"]) as f:
                content = f.read()
                assert content == ""

    def test_chunked_writing(self):
        """Test that chunked writing works correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = {
                "path": f"{tmpdir}/output.csv",
                "header": True,
                "chunk_size": 2,  # Small chunk for testing
            }

            # Create more rows than chunk size
            data = [{"id": i, "value": f"val{i}"} for i in range(10)]

            writer = FilesystemCSVWriter(config)
            result = writer.write(data)

            assert result["rows_written"] == 10

            with open(result["path"]) as f:
                reader = csv.DictReader(f)
                rows = list(reader)
                assert len(rows) == 10
                assert rows[0]["id"] == "0"
                assert rows[9]["id"] == "9"
