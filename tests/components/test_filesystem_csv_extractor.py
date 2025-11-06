"""Tests for filesystem CSV extractor component."""

import logging

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
    """Mock execution context with base_path."""

    class MockCtx:
        def __init__(self):
            self.base_path = tmp_path
            self.metrics = []
            self.events = []

        def log_metric(self, name, value, tags=None):
            self.metrics.append({"name": name, "value": value, "tags": tags})
            logger.debug(f"Metric logged: {name}={value} (tags={tags})")

        def log_event(self, event_type, data=None):
            self.events.append({"type": event_type, "data": data})
            logger.debug(f"Event logged: {event_type} (data={data})")

    return MockCtx()


# ============================================================================
# Basic Extraction Tests
# ============================================================================


@pytest.mark.skip(reason="Driver not yet implemented")
def test_basic_extraction(sample_csv, mock_ctx):
    """Test basic CSV extraction."""
    from osiris.drivers.filesystem_csv_extractor_driver import FilesystemCsvExtractorDriver

    config = {"path": str(sample_csv)}

    driver = FilesystemCsvExtractorDriver()
    result = driver.run(step_id="extract_1", config=config, inputs=None, ctx=mock_ctx)

    # Verify return format
    assert "df" in result
    assert isinstance(result["df"], pd.DataFrame)

    # Verify data
    df = result["df"]
    assert len(df) == 3
    assert list(df.columns) == ["id", "name", "value"]
    assert df["id"].tolist() == [1, 2, 3]
    assert df["name"].tolist() == ["Alice", "Bob", "Charlie"]
    assert df["value"].tolist() == [100, 200, 300]


@pytest.mark.skip(reason="Driver not yet implemented")
def test_extraction_returns_dataframe_in_df_key(sample_csv, mock_ctx):
    """Test that extraction returns DataFrame in 'df' key."""
    from osiris.drivers.filesystem_csv_extractor_driver import FilesystemCsvExtractorDriver

    config = {"path": str(sample_csv)}

    driver = FilesystemCsvExtractorDriver()
    result = driver.run(step_id="extract_1", config=config, inputs=None, ctx=mock_ctx)

    # Verify return structure
    assert isinstance(result, dict)
    assert "df" in result
    assert isinstance(result["df"], pd.DataFrame)


@pytest.mark.skip(reason="Driver not yet implemented")
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


@pytest.mark.skip(reason="Driver not yet implemented")
def test_column_selection(sample_csv, mock_ctx):
    """Test extracting specific columns."""
    from osiris.drivers.filesystem_csv_extractor_driver import FilesystemCsvExtractorDriver

    config = {"path": str(sample_csv), "columns": ["id", "name"]}

    driver = FilesystemCsvExtractorDriver()
    result = driver.run(step_id="extract_1", config=config, inputs=None, ctx=mock_ctx)

    df = result["df"]
    assert list(df.columns) == ["id", "name"]
    assert "value" not in df.columns


@pytest.mark.skip(reason="Driver not yet implemented")
def test_column_order_preserved(sample_csv, mock_ctx):
    """Test that column order is preserved."""
    from osiris.drivers.filesystem_csv_extractor_driver import FilesystemCsvExtractorDriver

    config = {"path": str(sample_csv), "columns": ["value", "id"]}

    driver = FilesystemCsvExtractorDriver()
    result = driver.run(step_id="extract_1", config=config, inputs=None, ctx=mock_ctx)

    df = result["df"]
    assert list(df.columns) == ["value", "id"]


# ============================================================================
# CSV Options Tests
# ============================================================================


@pytest.mark.skip(reason="Driver not yet implemented")
def test_delimiter_tsv(sample_tsv, mock_ctx):
    """Test reading TSV with custom delimiter."""
    from osiris.drivers.filesystem_csv_extractor_driver import FilesystemCsvExtractorDriver

    config = {"path": str(sample_tsv), "delimiter": "\t"}

    driver = FilesystemCsvExtractorDriver()
    result = driver.run(step_id="extract_1", config=config, inputs=None, ctx=mock_ctx)

    df = result["df"]
    assert len(df) == 2
    assert list(df.columns) == ["id", "name", "value"]


@pytest.mark.skip(reason="Driver not yet implemented")
def test_encoding_utf8(sample_csv_utf8, mock_ctx):
    """Test reading UTF-8 encoded file."""
    from osiris.drivers.filesystem_csv_extractor_driver import FilesystemCsvExtractorDriver

    config = {"path": str(sample_csv_utf8), "encoding": "utf-8"}

    driver = FilesystemCsvExtractorDriver()
    result = driver.run(step_id="extract_1", config=config, inputs=None, ctx=mock_ctx)

    df = result["df"]
    assert df["name"].tolist() == ["José", "Müller", "王芳"]
    assert df["city"].tolist() == ["São Paulo", "München", "北京"]


@pytest.mark.skip(reason="Driver not yet implemented")
def test_no_header(sample_csv_no_header, mock_ctx):
    """Test reading CSV without headers."""
    from osiris.drivers.filesystem_csv_extractor_driver import FilesystemCsvExtractorDriver

    config = {"path": str(sample_csv_no_header), "header": None}

    driver = FilesystemCsvExtractorDriver()
    result = driver.run(step_id="extract_1", config=config, inputs=None, ctx=mock_ctx)

    df = result["df"]
    assert len(df) == 3
    # Default column names should be integers (0, 1, 2)
    assert 0 in df.columns
    assert 1 in df.columns
    assert 2 in df.columns


@pytest.mark.skip(reason="Driver not yet implemented")
def test_skip_rows(sample_csv, mock_ctx):
    """Test skipping first N rows."""
    from osiris.drivers.filesystem_csv_extractor_driver import FilesystemCsvExtractorDriver

    config = {"path": str(sample_csv), "skiprows": 1}

    driver = FilesystemCsvExtractorDriver()
    result = driver.run(step_id="extract_1", config=config, inputs=None, ctx=mock_ctx)

    df = result["df"]
    # First data row becomes header, so we should have 2 rows
    assert len(df) == 2
    # Values from second and third data rows
    assert df["1"].tolist() == [2, 3]


@pytest.mark.skip(reason="Driver not yet implemented")
def test_limit_rows(sample_csv, mock_ctx):
    """Test reading only N rows."""
    from osiris.drivers.filesystem_csv_extractor_driver import FilesystemCsvExtractorDriver

    config = {"path": str(sample_csv), "nrows": 2}

    driver = FilesystemCsvExtractorDriver()
    result = driver.run(step_id="extract_1", config=config, inputs=None, ctx=mock_ctx)

    df = result["df"]
    assert len(df) == 2
    assert df["id"].tolist() == [1, 2]


# ============================================================================
# Advanced Features Tests
# ============================================================================


@pytest.mark.skip(reason="Driver not yet implemented")
def test_parse_dates(sample_csv_dates, mock_ctx):
    """Test parsing date columns."""
    from osiris.drivers.filesystem_csv_extractor_driver import FilesystemCsvExtractorDriver

    config = {"path": str(sample_csv_dates), "parse_dates": ["date"]}

    driver = FilesystemCsvExtractorDriver()
    result = driver.run(step_id="extract_1", config=config, inputs=None, ctx=mock_ctx)

    df = result["df"]
    assert pd.api.types.is_datetime64_any_dtype(df["date"])


@pytest.mark.skip(reason="Driver not yet implemented")
def test_dtype_specification(tmp_path, mock_ctx):
    """Test custom dtype specification."""
    from osiris.drivers.filesystem_csv_extractor_driver import FilesystemCsvExtractorDriver

    csv_file = tmp_path / "dtypes.csv"
    csv_file.write_text("id,code,amount\n1,001,100.50\n2,002,200.75\n")

    config = {"path": str(csv_file), "dtype": {"id": int, "code": str, "amount": float}}

    driver = FilesystemCsvExtractorDriver()
    result = driver.run(step_id="extract_1", config=config, inputs=None, ctx=mock_ctx)

    df = result["df"]
    assert df["id"].dtype == int
    assert df["code"].dtype == object  # string
    assert df["amount"].dtype == float
    assert df["code"].tolist() == ["001", "002"]  # Leading zeros preserved


@pytest.mark.skip(reason="Driver not yet implemented")
def test_na_values(sample_csv_with_nulls, mock_ctx):
    """Test custom NA values."""
    from osiris.drivers.filesystem_csv_extractor_driver import FilesystemCsvExtractorDriver

    config = {"path": str(sample_csv_with_nulls), "na_values": ["NULL"]}

    driver = FilesystemCsvExtractorDriver()
    result = driver.run(step_id="extract_1", config=config, inputs=None, ctx=mock_ctx)

    df = result["df"]
    # Check that empty strings and "NULL" are treated as NaN
    assert pd.isna(df.loc[1, "name"])  # Empty string
    assert pd.isna(df.loc[2, "value"])  # Empty value
    assert pd.isna(df.loc[3, "value"])  # NULL string


# ============================================================================
# Path Resolution Tests
# ============================================================================


@pytest.mark.skip(reason="Driver not yet implemented")
def test_absolute_path(sample_csv, mock_ctx):
    """Test that absolute paths work correctly."""
    from osiris.drivers.filesystem_csv_extractor_driver import FilesystemCsvExtractorDriver

    config = {"path": str(sample_csv.absolute())}

    driver = FilesystemCsvExtractorDriver()
    result = driver.run(step_id="extract_1", config=config, inputs=None, ctx=mock_ctx)

    assert "df" in result
    assert len(result["df"]) == 3


@pytest.mark.skip(reason="Driver not yet implemented")
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

    assert "df" in result
    assert len(result["df"]) == 1


@pytest.mark.skip(reason="Driver not yet implemented")
def test_path_resolution_without_ctx(sample_csv):
    """Test path resolution fallback to cwd when ctx not provided."""
    from osiris.drivers.filesystem_csv_extractor_driver import FilesystemCsvExtractorDriver

    config = {"path": str(sample_csv.absolute())}

    driver = FilesystemCsvExtractorDriver()
    result = driver.run(step_id="extract_1", config=config, inputs=None, ctx=None)

    assert "df" in result
    assert len(result["df"]) == 3


# ============================================================================
# Discovery Mode Tests
# ============================================================================


@pytest.mark.skip(reason="Driver not yet implemented")
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
    assert all(f.endswith(".csv") for f in files)


@pytest.mark.skip(reason="Driver not yet implemented")
def test_discovery_sorted_output(csv_directory, mock_ctx):
    """Test discovery returns files in deterministic order."""
    from osiris.drivers.filesystem_csv_extractor_driver import FilesystemCsvExtractorDriver

    config = {"path": str(csv_directory), "discovery": True}

    driver = FilesystemCsvExtractorDriver()
    result = driver.run(step_id="extract_1", config=config, inputs=None, ctx=mock_ctx)

    files = result["files"]
    # Files should be sorted
    assert files == sorted(files)


# ============================================================================
# Doctor/Health Check Tests
# ============================================================================


@pytest.mark.skip(reason="Driver not yet implemented")
def test_doctor_healthy(sample_csv):
    """Test doctor health check passes for valid file."""
    from osiris.drivers.filesystem_csv_extractor_driver import FilesystemCsvExtractorDriver

    config = {"path": str(sample_csv)}

    driver = FilesystemCsvExtractorDriver()
    result = driver.doctor(config)

    assert result["status"] == "healthy"
    assert "file_exists" in result["checks"]


@pytest.mark.skip(reason="Driver not yet implemented")
def test_doctor_file_not_found(tmp_path):
    """Test doctor health check fails for missing file."""
    from osiris.drivers.filesystem_csv_extractor_driver import FilesystemCsvExtractorDriver

    config = {"path": str(tmp_path / "nonexistent.csv")}

    driver = FilesystemCsvExtractorDriver()
    result = driver.doctor(config)

    assert result["status"] == "unhealthy"
    assert "file_exists" in result["checks"]


@pytest.mark.skip(reason="Driver not yet implemented")
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


@pytest.mark.skip(reason="Driver not yet implemented")
def test_missing_path_config(mock_ctx):
    """Test error when path is missing from config."""
    from osiris.drivers.filesystem_csv_extractor_driver import FilesystemCsvExtractorDriver

    config = {}

    driver = FilesystemCsvExtractorDriver()
    with pytest.raises(ValueError, match="'path' is required"):
        driver.run(step_id="extract_1", config=config, inputs=None, ctx=mock_ctx)


@pytest.mark.skip(reason="Driver not yet implemented")
def test_file_not_found_error(tmp_path, mock_ctx):
    """Test error when file does not exist."""
    from osiris.drivers.filesystem_csv_extractor_driver import FilesystemCsvExtractorDriver

    config = {"path": str(tmp_path / "nonexistent.csv")}

    driver = FilesystemCsvExtractorDriver()
    with pytest.raises((FileNotFoundError, RuntimeError)):
        driver.run(step_id="extract_1", config=config, inputs=None, ctx=mock_ctx)


@pytest.mark.skip(reason="Driver not yet implemented")
def test_invalid_csv_format(tmp_path, mock_ctx):
    """Test error handling for invalid CSV format."""
    from osiris.drivers.filesystem_csv_extractor_driver import FilesystemCsvExtractorDriver

    # Create invalid CSV (binary data)
    invalid_file = tmp_path / "invalid.csv"
    invalid_file.write_bytes(b"\x00\x01\x02\x03\x04")

    config = {"path": str(invalid_file)}

    driver = FilesystemCsvExtractorDriver()
    with pytest.raises(RuntimeError):
        driver.run(step_id="extract_1", config=config, inputs=None, ctx=mock_ctx)


@pytest.mark.skip(reason="Driver not yet implemented")
def test_malformed_csv_strict_mode(sample_csv_malformed, mock_ctx):
    """Test handling of malformed CSV with inconsistent columns."""
    from osiris.drivers.filesystem_csv_extractor_driver import FilesystemCsvExtractorDriver

    config = {"path": str(sample_csv_malformed), "on_bad_lines": "error"}

    driver = FilesystemCsvExtractorDriver()
    with pytest.raises(RuntimeError):
        driver.run(step_id="extract_1", config=config, inputs=None, ctx=mock_ctx)


@pytest.mark.skip(reason="Driver not yet implemented")
def test_malformed_csv_skip_mode(sample_csv_malformed, mock_ctx):
    """Test skipping malformed rows."""
    from osiris.drivers.filesystem_csv_extractor_driver import FilesystemCsvExtractorDriver

    config = {"path": str(sample_csv_malformed), "on_bad_lines": "skip"}

    driver = FilesystemCsvExtractorDriver()
    result = driver.run(step_id="extract_1", config=config, inputs=None, ctx=mock_ctx)

    df = result["df"]
    # Only the valid first row should be included
    assert len(df) == 1
    assert df["a"].tolist() == [1]


# ============================================================================
# Empty File Tests
# ============================================================================


@pytest.mark.skip(reason="Driver not yet implemented")
def test_empty_csv_file(tmp_path, mock_ctx):
    """Test reading empty CSV file."""
    from osiris.drivers.filesystem_csv_extractor_driver import FilesystemCsvExtractorDriver

    empty_file = tmp_path / "empty.csv"
    empty_file.write_text("")

    config = {"path": str(empty_file)}

    driver = FilesystemCsvExtractorDriver()
    result = driver.run(step_id="extract_1", config=config, inputs=None, ctx=mock_ctx)

    df = result["df"]
    assert len(df) == 0


@pytest.mark.skip(reason="Driver not yet implemented")
def test_csv_with_header_only(tmp_path, mock_ctx):
    """Test CSV with headers but no data."""
    from osiris.drivers.filesystem_csv_extractor_driver import FilesystemCsvExtractorDriver

    header_only = tmp_path / "header_only.csv"
    header_only.write_text("id,name,value\n")

    config = {"path": str(header_only)}

    driver = FilesystemCsvExtractorDriver()
    result = driver.run(step_id="extract_1", config=config, inputs=None, ctx=mock_ctx)

    df = result["df"]
    assert len(df) == 0
    assert list(df.columns) == ["id", "name", "value"]


# ============================================================================
# Large File Tests
# ============================================================================


@pytest.mark.skip(reason="Driver not yet implemented")
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

    df = result["df"]
    assert len(df) == 1000


# ============================================================================
# Comment Handling Tests
# ============================================================================


@pytest.mark.skip(reason="Driver not yet implemented")
def test_comment_lines(tmp_path, mock_ctx):
    """Test handling comment lines in CSV."""
    from osiris.drivers.filesystem_csv_extractor_driver import FilesystemCsvExtractorDriver

    csv_with_comments = tmp_path / "comments.csv"
    csv_with_comments.write_text("# This is a comment\nid,name\n# Another comment\n1,Alice\n2,Bob\n")

    config = {"path": str(csv_with_comments), "comment": "#"}

    driver = FilesystemCsvExtractorDriver()
    result = driver.run(step_id="extract_1", config=config, inputs=None, ctx=mock_ctx)

    df = result["df"]
    assert len(df) == 2
    assert df["id"].tolist() == [1, 2]
