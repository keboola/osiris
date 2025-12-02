"""Tests for filesystem CSV extractor component."""

import logging

import duckdb
import pandas as pd
import pytest

# Import will be available when driver is created
# from osiris.drivers.filesystem_csv_extractor_driver import FilesystemCsvExtractorDriver


logger = logging.getLogger(__name__)


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def sample_csv(tmp_path):
    """Create basic CSV with headers."""
    csv_file = tmp_path / "test.csv"
    csv_file.write_text("id,name,value\n1,Alice,100\n2,Bob,200\n3,Charlie,300\n")
    return csv_file


@pytest.fixture
def sample_csv_dates(tmp_path):
    """Create CSV with date columns."""
    csv_file = tmp_path / "dates.csv"
    csv_file.write_text("id,date,amount\n1,2025-01-01,100\n2,2025-01-02,200\n3,2025-01-03,300\n")
    return csv_file


@pytest.fixture
def sample_tsv(tmp_path):
    """Create TSV file."""
    tsv_file = tmp_path / "test.tsv"
    tsv_file.write_text("id\tname\tvalue\n1\tAlice\t100\n2\tBob\t200\n")
    return tsv_file


@pytest.fixture
def sample_csv_no_header(tmp_path):
    """Create CSV without headers."""
    csv_file = tmp_path / "no_header.csv"
    csv_file.write_text("1,Alice,100\n2,Bob,200\n3,Charlie,300\n")
    return csv_file


@pytest.fixture
def sample_csv_with_nulls(tmp_path):
    """Create CSV with NULL values."""
    csv_file = tmp_path / "nulls.csv"
    csv_file.write_text("id,name,value\n1,Alice,100\n2,,200\n3,Charlie,\n4,David,NULL\n")
    return csv_file


@pytest.fixture
def sample_csv_utf8(tmp_path):
    """Create CSV with UTF-8 characters."""
    csv_file = tmp_path / "utf8.csv"
    csv_file.write_text("id,name,city\n1,José,São Paulo\n2,Müller,München\n3,王芳,北京\n", encoding="utf-8")
    return csv_file


@pytest.fixture
def csv_directory(tmp_path):
    """Create directory with multiple CSV files."""
    csv_dir = tmp_path / "csvs"
    csv_dir.mkdir()
    (csv_dir / "file1.csv").write_text("a,b\n1,2\n3,4\n")
    (csv_dir / "file2.csv").write_text("c,d\n5,6\n7,8\n")
    (csv_dir / "file3.csv").write_text("e,f\n9,10\n")
    return csv_dir


@pytest.fixture
def sample_csv_malformed(tmp_path):
    """Create malformed CSV with inconsistent columns."""
    csv_file = tmp_path / "malformed.csv"
    csv_file.write_text("a,b,c\n1,2,3\n4,5\n6,7,8,9\n")
    return csv_file


@pytest.fixture
def mock_ctx(tmp_path):
    """Mock execution context with base_path and DuckDB connection."""
    import duckdb

    class MockCtx:
        def __init__(self):
            self.base_path = tmp_path
            self.metrics = []
            self.events = []
            self._db_connection = None
            self._db_path = tmp_path / "test_pipeline.duckdb"

        def get_db_connection(self):
            """Get or create DuckDB connection."""
            if self._db_connection is None:
                self._db_connection = duckdb.connect(str(self._db_path))
            return self._db_connection

        def log_metric(self, name, value, tags=None):
            self.metrics.append({"name": name, "value": value, "tags": tags})
            logger.debug(f"Metric logged: {name}={value} (tags={tags})")

        def log_event(self, event_type, data=None):
            self.events.append({"type": event_type, "data": data})
            logger.debug(f"Event logged: {event_type} (data={data})")

        def cleanup(self):
            """Close DuckDB connection and clean up."""
            if self._db_connection is not None:
                self._db_connection.close()
                self._db_connection = None

    ctx = MockCtx()
    yield ctx
    ctx.cleanup()


# ============================================================================
# Helper Functions
# ============================================================================


def get_table_data(ctx, table_name, order_by=None):
    """Helper to fetch data from DuckDB table as DataFrame.

    Args:
        ctx: Mock context with get_db_connection()
        table_name: Name of table to query
        order_by: Optional column name to order by

    Returns:
        DataFrame with table data
    """
    conn = ctx.get_db_connection()
    query = f"SELECT * FROM {table_name}"
    if order_by:
        query += f" ORDER BY {order_by}"
    return conn.execute(query).fetchdf()


# ============================================================================
# Basic Extraction Tests
# ============================================================================


def test_basic_extraction(sample_csv, mock_ctx):
    """Test basic CSV extraction."""
    from osiris.drivers.filesystem_csv_extractor_driver import FilesystemCsvExtractorDriver

    config = {"path": str(sample_csv)}

    driver = FilesystemCsvExtractorDriver()
    result = driver.run(step_id="extract_1", config=config, inputs=None, ctx=mock_ctx)

    # Verify return format (new DuckDB streaming interface)
    assert "table" in result
    assert "rows" in result
    assert result["table"] == "extract_1"
    assert result["rows"] == 3

    # Verify data in DuckDB
    df = get_table_data(mock_ctx, "extract_1", order_by="id")
    assert len(df) == 3
    assert list(df.columns) == ["id", "name", "value"]
    assert df["id"].tolist() == [1, 2, 3]
    assert df["name"].tolist() == ["Alice", "Bob", "Charlie"]
    assert df["value"].tolist() == [100, 200, 300]


def test_extraction_returns_table_and_rows(sample_csv, mock_ctx):
    """Test that extraction returns table name and row count."""
    from osiris.drivers.filesystem_csv_extractor_driver import FilesystemCsvExtractorDriver

    config = {"path": str(sample_csv)}

    driver = FilesystemCsvExtractorDriver()
    result = driver.run(step_id="extract_1", config=config, inputs=None, ctx=mock_ctx)

    # Verify return structure (new DuckDB streaming interface)
    assert isinstance(result, dict)
    assert "table" in result
    assert "rows" in result
    assert result["table"] == "extract_1"
    assert result["rows"] == 3


def test_rows_read_metric_emitted(sample_csv, mock_ctx):
    """Test that rows_read metric is logged."""
    from osiris.drivers.filesystem_csv_extractor_driver import FilesystemCsvExtractorDriver

    config = {"path": str(sample_csv)}

    driver = FilesystemCsvExtractorDriver()
    driver.run(step_id="extract_1", config=config, inputs=None, ctx=mock_ctx)

    # Verify metric was logged
    metrics = [m for m in mock_ctx.metrics if m["name"] == "rows_read"]
    assert len(metrics) == 1
    assert metrics[0]["value"] == 3


# ============================================================================
# Column Selection Tests
# ============================================================================


def test_column_selection(sample_csv, mock_ctx):
    """Test extracting specific columns."""
    from osiris.drivers.filesystem_csv_extractor_driver import FilesystemCsvExtractorDriver

    config = {"path": str(sample_csv), "columns": ["id", "name"]}

    driver = FilesystemCsvExtractorDriver()
    result = driver.run(step_id="extract_1", config=config, inputs=None, ctx=mock_ctx)

    assert result["rows"] == 3
    df = get_table_data(mock_ctx, "extract_1")
    assert list(df.columns) == ["id", "name"]
    assert "value" not in df.columns


def test_column_order_preserved(sample_csv, mock_ctx):
    """Test that column order is preserved."""
    from osiris.drivers.filesystem_csv_extractor_driver import FilesystemCsvExtractorDriver

    config = {"path": str(sample_csv), "columns": ["value", "id"]}

    driver = FilesystemCsvExtractorDriver()
    result = driver.run(step_id="extract_1", config=config, inputs=None, ctx=mock_ctx)

    df = get_table_data(mock_ctx, "extract_1")
    assert list(df.columns) == ["value", "id"]


# ============================================================================
# CSV Options Tests
# ============================================================================


def test_delimiter_tsv(sample_tsv, mock_ctx):
    """Test reading TSV with custom delimiter."""
    from osiris.drivers.filesystem_csv_extractor_driver import FilesystemCsvExtractorDriver

    config = {"path": str(sample_tsv), "delimiter": "\t"}

    driver = FilesystemCsvExtractorDriver()
    result = driver.run(step_id="extract_1", config=config, inputs=None, ctx=mock_ctx)

    df = get_table_data(mock_ctx, result["table"])
    assert len(df) == 2
    assert list(df.columns) == ["id", "name", "value"]


def test_encoding_utf8(sample_csv_utf8, mock_ctx):
    """Test reading UTF-8 encoded file."""
    from osiris.drivers.filesystem_csv_extractor_driver import FilesystemCsvExtractorDriver

    config = {"path": str(sample_csv_utf8), "encoding": "utf-8"}

    driver = FilesystemCsvExtractorDriver()
    result = driver.run(step_id="extract_1", config=config, inputs=None, ctx=mock_ctx)

    df = get_table_data(mock_ctx, result["table"])
    assert df["name"].tolist() == ["José", "Müller", "王芳"]
    assert df["city"].tolist() == ["São Paulo", "München", "北京"]


def test_no_header(sample_csv_no_header, mock_ctx):
    """Test reading CSV without headers."""
    from osiris.drivers.filesystem_csv_extractor_driver import FilesystemCsvExtractorDriver

    config = {"path": str(sample_csv_no_header), "header": None}

    driver = FilesystemCsvExtractorDriver()
    result = driver.run(step_id="extract_1", config=config, inputs=None, ctx=mock_ctx)

    df = get_table_data(mock_ctx, result["table"])
    assert len(df) == 3
    # Default column names should be integers (0, 1, 2)
    assert 0 in df.columns
    assert 1 in df.columns
    assert 2 in df.columns


def test_skip_rows(sample_csv, mock_ctx):
    """Test skipping first N rows."""
    from osiris.drivers.filesystem_csv_extractor_driver import FilesystemCsvExtractorDriver

    config = {"path": str(sample_csv), "skip_rows": 1}

    driver = FilesystemCsvExtractorDriver()
    result = driver.run(step_id="extract_1", config=config, inputs=None, ctx=mock_ctx)

    df = get_table_data(mock_ctx, result["table"])
    # First data row becomes header, so we should have 2 rows
    assert len(df) == 2
    # Values from second and third data rows
    assert df["1"].tolist() == [2, 3]


def test_limit_rows(sample_csv, mock_ctx):
    """Test reading only N rows."""
    from osiris.drivers.filesystem_csv_extractor_driver import FilesystemCsvExtractorDriver

    config = {"path": str(sample_csv), "limit": 2}

    driver = FilesystemCsvExtractorDriver()
    result = driver.run(step_id="extract_1", config=config, inputs=None, ctx=mock_ctx)

    df = get_table_data(mock_ctx, result["table"])
    assert len(df) == 2
    assert df["id"].tolist() == [1, 2]


# ============================================================================
# Advanced Features Tests
# ============================================================================


def test_parse_dates(sample_csv_dates, mock_ctx):
    """Test parsing date columns."""
    from osiris.drivers.filesystem_csv_extractor_driver import FilesystemCsvExtractorDriver

    config = {"path": str(sample_csv_dates), "parse_dates": ["date"]}

    driver = FilesystemCsvExtractorDriver()
    result = driver.run(step_id="extract_1", config=config, inputs=None, ctx=mock_ctx)

    df = get_table_data(mock_ctx, result["table"])
    assert pd.api.types.is_datetime64_any_dtype(df["date"])


def test_dtype_specification(tmp_path, mock_ctx):
    """Test custom dtype specification."""
    from osiris.drivers.filesystem_csv_extractor_driver import FilesystemCsvExtractorDriver

    csv_file = tmp_path / "dtypes.csv"
    csv_file.write_text("id,code,amount\n1,001,100.50\n2,002,200.75\n")

    config = {"path": str(csv_file), "dtype": {"id": int, "code": str, "amount": float}}

    driver = FilesystemCsvExtractorDriver()
    result = driver.run(step_id="extract_1", config=config, inputs=None, ctx=mock_ctx)

    df = get_table_data(mock_ctx, result["table"])
    assert df["id"].dtype == int
    assert df["code"].dtype == object  # string
    assert df["amount"].dtype == float
    assert df["code"].tolist() == ["001", "002"]  # Leading zeros preserved


def test_na_values(sample_csv_with_nulls, mock_ctx):
    """Test custom NA values."""
    from osiris.drivers.filesystem_csv_extractor_driver import FilesystemCsvExtractorDriver

    config = {"path": str(sample_csv_with_nulls), "na_values": ["NULL"]}

    driver = FilesystemCsvExtractorDriver()
    result = driver.run(step_id="extract_1", config=config, inputs=None, ctx=mock_ctx)

    df = get_table_data(mock_ctx, result["table"])
    # Check that empty strings and "NULL" are treated as NaN
    assert pd.isna(df.loc[1, "name"])  # Empty string
    assert pd.isna(df.loc[2, "value"])  # Empty value
    assert pd.isna(df.loc[3, "value"])  # NULL string


# ============================================================================
# Path Resolution Tests
# ============================================================================


def test_absolute_path(sample_csv, mock_ctx):
    """Test that absolute paths work correctly."""
    from osiris.drivers.filesystem_csv_extractor_driver import FilesystemCsvExtractorDriver

    config = {"path": str(sample_csv.absolute())}

    driver = FilesystemCsvExtractorDriver()
    result = driver.run(step_id="extract_1", config=config, inputs=None, ctx=mock_ctx)

    assert "table" in result and "rows" in result
    assert result["rows"] == 3


def test_relative_path(tmp_path, mock_ctx):
    """Test that relative paths resolve to ctx.base_path."""
    from osiris.drivers.filesystem_csv_extractor_driver import FilesystemCsvExtractorDriver

    # Create CSV in base_path
    csv_file = tmp_path / "data.csv"
    csv_file.write_text("a,b\n1,2\n")

    # Use relative path
    config = {"path": "data.csv"}

    driver = FilesystemCsvExtractorDriver()
    result = driver.run(step_id="extract_1", config=config, inputs=None, ctx=mock_ctx)

    assert "table" in result and "rows" in result
    assert result["rows"] == 1


def test_path_resolution_without_ctx(sample_csv):
    """Test that driver requires ctx with get_db_connection()."""
    from osiris.drivers.filesystem_csv_extractor_driver import FilesystemCsvExtractorDriver

    config = {"path": str(sample_csv.absolute())}

    driver = FilesystemCsvExtractorDriver()
    # Driver now requires ctx with get_db_connection() method
    with pytest.raises(RuntimeError, match="Context must provide get_db_connection"):
        driver.run(step_id="extract_1", config=config, inputs=None, ctx=None)


# ============================================================================
# Discovery Mode Tests
# ============================================================================


def test_discovery_lists_csv_files(csv_directory, mock_ctx):
    """Test discovery mode lists CSV files."""
    from osiris.drivers.filesystem_csv_extractor_driver import FilesystemCsvExtractorDriver

    config = {"path": str(csv_directory), "discovery": True}

    driver = FilesystemCsvExtractorDriver()
    result = driver.run(step_id="extract_1", config=config, inputs=None, ctx=mock_ctx)

    # Should return list of files instead of DataFrame
    assert "files" in result
    files = result["files"]
    assert len(files) == 3
    assert all(f["name"].endswith(".csv") for f in files)


def test_discovery_sorted_output(csv_directory, mock_ctx):
    """Test discovery returns files in deterministic order."""
    from osiris.drivers.filesystem_csv_extractor_driver import FilesystemCsvExtractorDriver

    config = {"path": str(csv_directory), "discovery": True}

    driver = FilesystemCsvExtractorDriver()
    result = driver.run(step_id="extract_1", config=config, inputs=None, ctx=mock_ctx)

    files = result["files"]
    # Files should be sorted
    file_names = [f["name"] for f in files]
    assert file_names == sorted(file_names)


def test_discovery_includes_column_types(tmp_path, mock_ctx):
    """Test discovery includes actual column data types."""
    from osiris.drivers.filesystem_csv_extractor_driver import FilesystemCsvExtractorDriver

    # Create CSV directory with typed data
    csv_dir = tmp_path / "typed_csvs"
    csv_dir.mkdir()

    # Create CSV with various data types
    actors_csv = csv_dir / "actors.csv"
    actors_csv.write_text("actor_id,birth_year,name,rating\n1,1990,Alice,8.5\n2,1985,Bob,7.2\n")

    config = {"path": str(csv_dir), "discovery": True}

    driver = FilesystemCsvExtractorDriver()
    result = driver.run(step_id="extract_1", config=config, inputs=None, ctx=mock_ctx)

    # Verify column_types are included
    assert "files" in result
    assert len(result["files"]) == 1

    file_info = result["files"][0]
    assert "column_types" in file_info, "Discovery should include column_types"

    # Verify actual types (not "unknown")
    types = file_info["column_types"]
    assert types["actor_id"] == "integer"
    assert types["birth_year"] == "integer"
    assert types["name"] == "string"
    assert types["rating"] == "float"


# ============================================================================
# Doctor/Health Check Tests
# ============================================================================


def test_doctor_healthy(sample_csv):
    """Test doctor health check passes for valid file."""
    from osiris.drivers.filesystem_csv_extractor_driver import FilesystemCsvExtractorDriver

    config = {"path": str(sample_csv)}

    driver = FilesystemCsvExtractorDriver()
    result = driver.doctor(config)

    assert result["status"] == "healthy"
    assert "file_exists" in result["checks"]


def test_doctor_file_not_found(tmp_path):
    """Test doctor health check fails for missing file."""
    from osiris.drivers.filesystem_csv_extractor_driver import FilesystemCsvExtractorDriver

    config = {"path": str(tmp_path / "nonexistent.csv")}

    driver = FilesystemCsvExtractorDriver()
    result = driver.doctor(config)

    assert result["status"] == "unhealthy"
    assert "file_exists" in result["checks"]


def test_doctor_not_a_file(tmp_path):
    """Test doctor health check fails for directory."""
    from osiris.drivers.filesystem_csv_extractor_driver import FilesystemCsvExtractorDriver

    config = {"path": str(tmp_path)}

    driver = FilesystemCsvExtractorDriver()
    result = driver.doctor(config)

    assert result["status"] == "unhealthy"
    assert "is_file" in result["checks"]


# ============================================================================
# Error Handling Tests
# ============================================================================


def test_missing_path_config(mock_ctx):
    """Test error when path is missing from config."""
    from osiris.drivers.filesystem_csv_extractor_driver import FilesystemCsvExtractorDriver

    config = {}

    driver = FilesystemCsvExtractorDriver()
    with pytest.raises(ValueError, match="'path' is required"):
        driver.run(step_id="extract_1", config=config, inputs=None, ctx=mock_ctx)


def test_file_not_found_error(tmp_path, mock_ctx):
    """Test error when file does not exist."""
    from osiris.drivers.filesystem_csv_extractor_driver import FilesystemCsvExtractorDriver

    config = {"path": str(tmp_path / "nonexistent.csv")}

    driver = FilesystemCsvExtractorDriver()
    with pytest.raises((FileNotFoundError, RuntimeError)):
        driver.run(step_id="extract_1", config=config, inputs=None, ctx=mock_ctx)


def test_invalid_csv_format(tmp_path, mock_ctx):
    """Test handling of file with invalid encoding."""
    from osiris.drivers.filesystem_csv_extractor_driver import FilesystemCsvExtractorDriver

    # Create file with invalid UTF-8 encoding
    invalid_file = tmp_path / "invalid.csv"
    invalid_file.write_bytes(b"id,name\n\xff\xfe\x00\x00")

    config = {"path": str(invalid_file), "encoding": "utf-8"}

    driver = FilesystemCsvExtractorDriver()
    with pytest.raises(RuntimeError, match="encoding error"):
        driver.run(step_id="extract_1", config=config, inputs=None, ctx=mock_ctx)


def test_malformed_csv_strict_mode(sample_csv_malformed, mock_ctx):
    """Test handling of malformed CSV with inconsistent columns."""
    from osiris.drivers.filesystem_csv_extractor_driver import FilesystemCsvExtractorDriver

    config = {"path": str(sample_csv_malformed), "on_bad_lines": "error"}

    driver = FilesystemCsvExtractorDriver()
    with pytest.raises(RuntimeError):
        driver.run(step_id="extract_1", config=config, inputs=None, ctx=mock_ctx)


def test_malformed_csv_skip_mode(sample_csv_malformed, mock_ctx):
    """Test skipping malformed rows."""
    from osiris.drivers.filesystem_csv_extractor_driver import FilesystemCsvExtractorDriver

    config = {"path": str(sample_csv_malformed), "on_bad_lines": "skip"}

    driver = FilesystemCsvExtractorDriver()
    result = driver.run(step_id="extract_1", config=config, inputs=None, ctx=mock_ctx)

    df = get_table_data(mock_ctx, result["table"])
    # Pandas skips rows with MORE columns, fills NaN for rows with LESS
    assert len(df) == 2
    assert df["a"].tolist() == [1, 4]


# ============================================================================
# Empty File Tests
# ============================================================================


def test_empty_csv_file(tmp_path, mock_ctx):
    """Test reading empty CSV file."""
    from osiris.drivers.filesystem_csv_extractor_driver import FilesystemCsvExtractorDriver

    empty_file = tmp_path / "empty.csv"
    empty_file.write_text("")

    config = {"path": str(empty_file)}

    driver = FilesystemCsvExtractorDriver()
    result = driver.run(step_id="extract_1", config=config, inputs=None, ctx=mock_ctx)

    df = get_table_data(mock_ctx, result["table"])
    assert len(df) == 0


def test_csv_with_header_only(tmp_path, mock_ctx):
    """Test CSV with headers but no data."""
    from osiris.drivers.filesystem_csv_extractor_driver import FilesystemCsvExtractorDriver

    header_only = tmp_path / "header_only.csv"
    header_only.write_text("id,name,value\n")

    config = {"path": str(header_only)}

    driver = FilesystemCsvExtractorDriver()
    result = driver.run(step_id="extract_1", config=config, inputs=None, ctx=mock_ctx)

    df = get_table_data(mock_ctx, result["table"])
    assert len(df) == 0
    assert list(df.columns) == ["id", "name", "value"]


# ============================================================================
# Large File Tests
# ============================================================================


def test_chunked_reading(tmp_path, mock_ctx):
    """Test reading large file in chunks."""
    from osiris.drivers.filesystem_csv_extractor_driver import FilesystemCsvExtractorDriver

    # Create larger CSV
    large_csv = tmp_path / "large.csv"
    with open(large_csv, "w") as f:
        f.write("id,value\n")
        for i in range(1000):
            f.write(f"{i},{i * 10}\n")

    config = {"path": str(large_csv), "chunksize": 100}

    driver = FilesystemCsvExtractorDriver()
    result = driver.run(step_id="extract_1", config=config, inputs=None, ctx=mock_ctx)

    df = get_table_data(mock_ctx, result["table"])
    assert len(df) == 1000


# ============================================================================
# Comment Handling Tests
# ============================================================================


def test_comment_lines(tmp_path, mock_ctx):
    """Test handling comment lines in CSV."""
    from osiris.drivers.filesystem_csv_extractor_driver import FilesystemCsvExtractorDriver

    csv_with_comments = tmp_path / "comments.csv"
    csv_with_comments.write_text("# This is a comment\nid,name\n# Another comment\n1,Alice\n2,Bob\n")

    config = {"path": str(csv_with_comments), "comment": "#"}

    driver = FilesystemCsvExtractorDriver()
    result = driver.run(step_id="extract_1", config=config, inputs=None, ctx=mock_ctx)

    df = get_table_data(mock_ctx, result["table"])
    assert len(df) == 2
    assert df["id"].tolist() == [1, 2]
