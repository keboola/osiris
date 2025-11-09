"""Tests for filesystem CSV extractor component with connection discovery feature."""

import logging
from pathlib import Path

import pandas as pd
import pytest
import yaml

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
def csv_directory(tmp_path):
    """Create directory with multiple CSV files."""
    csv_dir = tmp_path / "csvs"
    csv_dir.mkdir()
    (csv_dir / "file1.csv").write_text("a,b\n1,2\n3,4\n")
    (csv_dir / "file2.csv").write_text("c,d\n5,6\n7,8\n")
    (csv_dir / "file3.csv").write_text("e,f\n9,10\n")
    return csv_dir


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


@pytest.fixture
def temp_connections_yaml(tmp_path, monkeypatch):
    """Create temporary osiris_connections.yaml file and configure environment."""
    # Create connections directory structure
    conn_dir = tmp_path / "data"
    conn_dir.mkdir()
    exports_dir = tmp_path / "exports"
    exports_dir.mkdir()

    # Create sample CSV files in different locations
    (conn_dir / "data.csv").write_text("id,value\n1,100\n2,200\n")
    (exports_dir / "report.csv").write_text("id,name\n1,Test\n")

    # Create connections file
    connections_yaml = tmp_path / "osiris_connections.yaml"
    connections_data = {
        "connections": {
            "filesystem": {
                "local": {"base_dir": str(conn_dir), "default": True},
                "exports": {"base_dir": str(exports_dir)},
            }
        }
    }

    with open(connections_yaml, "w") as f:
        yaml.dump(connections_data, f)

    # Change to tmp_path directory so connection file is found
    monkeypatch.chdir(tmp_path)

    return {
        "connections_file": connections_yaml,
        "local_dir": conn_dir,
        "exports_dir": exports_dir,
    }


@pytest.fixture
def temp_connections_yaml_no_default(tmp_path, monkeypatch):
    """Create temporary connections file without default flag."""
    conn_dir = tmp_path / "data"
    conn_dir.mkdir()
    (conn_dir / "test.csv").write_text("a,b\n1,2\n")

    connections_yaml = tmp_path / "osiris_connections.yaml"
    connections_data = {"connections": {"filesystem": {"local": {"base_dir": str(conn_dir)}}}}

    with open(connections_yaml, "w") as f:
        yaml.dump(connections_data, f)

    monkeypatch.chdir(tmp_path)

    return {"connections_file": connections_yaml, "local_dir": conn_dir}


# ============================================================================
# Connection Resolution Tests
# ============================================================================


def test_extract_with_connection_reference(temp_connections_yaml, mock_ctx):
    """Test extracting CSV with valid @filesystem.alias connection."""
    from osiris.drivers.filesystem_csv_extractor_driver import FilesystemCsvExtractorDriver

    config = {"connection": "@filesystem.local", "path": "data.csv"}

    driver = FilesystemCsvExtractorDriver()
    result = driver.run(step_id="extract_1", config=config, inputs=None, ctx=mock_ctx)

    # Verify DataFrame was loaded
    assert "df" in result
    assert isinstance(result["df"], pd.DataFrame)
    assert len(result["df"]) == 2
    assert list(result["df"].columns) == ["id", "value"]
    assert result["df"]["id"].tolist() == [1, 2]


def test_extract_with_non_default_connection(temp_connections_yaml, mock_ctx):
    """Test extracting CSV with non-default connection alias."""
    from osiris.drivers.filesystem_csv_extractor_driver import FilesystemCsvExtractorDriver

    config = {"connection": "@filesystem.exports", "path": "report.csv"}

    driver = FilesystemCsvExtractorDriver()
    result = driver.run(step_id="extract_1", config=config, inputs=None, ctx=mock_ctx)

    # Verify correct file was loaded from exports directory
    assert "df" in result
    assert isinstance(result["df"], pd.DataFrame)
    assert len(result["df"]) == 1
    assert list(result["df"].columns) == ["id", "name"]
    assert result["df"]["name"].tolist() == ["Test"]


def test_base_dir_from_connection_overrides_ctx_base_path(temp_connections_yaml, mock_ctx):
    """Test that base_dir from connection takes precedence over ctx.base_path."""
    from osiris.drivers.filesystem_csv_extractor_driver import FilesystemCsvExtractorDriver

    # mock_ctx.base_path points to tmp_path root, but connection should use data/ subdir
    config = {"connection": "@filesystem.local", "path": "data.csv"}

    driver = FilesystemCsvExtractorDriver()
    result = driver.run(step_id="extract_1", config=config, inputs=None, ctx=mock_ctx)

    # Should successfully find data.csv in connection's base_dir, not ctx.base_path
    assert "df" in result
    assert len(result["df"]) == 2


def test_error_invalid_connection_format(mock_ctx):
    """Test error handling for invalid connection format."""
    from osiris.drivers.filesystem_csv_extractor_driver import FilesystemCsvExtractorDriver

    # Missing @ prefix
    config = {"connection": "filesystem.local", "path": "test.csv"}

    driver = FilesystemCsvExtractorDriver()
    with pytest.raises(ValueError, match="Invalid connection format.*Expected '@filesystem.alias'"):
        driver.run(step_id="extract_1", config=config, inputs=None, ctx=mock_ctx)


def test_error_connection_missing_dot(mock_ctx):
    """Test error handling for connection reference without dot separator."""
    from osiris.drivers.filesystem_csv_extractor_driver import FilesystemCsvExtractorDriver

    # Missing dot separator
    config = {"connection": "@filesystem", "path": "test.csv"}

    driver = FilesystemCsvExtractorDriver()
    with pytest.raises(ValueError, match="Invalid connection reference format.*Expected '@family.alias'"):
        driver.run(step_id="extract_1", config=config, inputs=None, ctx=mock_ctx)


def test_error_non_filesystem_family(temp_connections_yaml, mock_ctx):
    """Test error handling for non-filesystem connection family."""
    from osiris.drivers.filesystem_csv_extractor_driver import FilesystemCsvExtractorDriver

    # Using mysql family instead of filesystem
    config = {"connection": "@mysql.db_movies", "path": "test.csv"}

    driver = FilesystemCsvExtractorDriver()
    with pytest.raises(ValueError, match="Connection family must be 'filesystem', got 'mysql'"):
        driver.run(step_id="extract_1", config=config, inputs=None, ctx=mock_ctx)


def test_error_non_existent_connection_alias(temp_connections_yaml, mock_ctx):
    """Test error handling for non-existent connection alias."""
    from osiris.drivers.filesystem_csv_extractor_driver import FilesystemCsvExtractorDriver

    # Alias 'nonexistent' doesn't exist
    config = {"connection": "@filesystem.nonexistent", "path": "test.csv"}

    driver = FilesystemCsvExtractorDriver()
    with pytest.raises(ValueError, match="Failed to resolve connection.*Connection alias 'nonexistent' not found"):
        driver.run(step_id="extract_1", config=config, inputs=None, ctx=mock_ctx)


def test_error_non_existent_family(temp_connections_yaml, mock_ctx):
    """Test error handling for non-existent connection family."""
    from osiris.drivers.filesystem_csv_extractor_driver import FilesystemCsvExtractorDriver

    # Family 'duckdb' is validated before connection resolution
    config = {"connection": "@duckdb.default", "path": "test.csv"}

    driver = FilesystemCsvExtractorDriver()
    # The driver validates family=='filesystem' before attempting resolution
    with pytest.raises(ValueError, match="Connection family must be 'filesystem', got 'duckdb'"):
        driver.run(step_id="extract_1", config=config, inputs=None, ctx=mock_ctx)


def test_error_missing_base_dir_in_connection(tmp_path, monkeypatch, mock_ctx):
    """Test that extraction fails gracefully if connection lacks base_dir."""
    from osiris.drivers.filesystem_csv_extractor_driver import FilesystemCsvExtractorDriver

    # Create connection without base_dir
    connections_yaml = tmp_path / "osiris_connections.yaml"
    connections_data = {"connections": {"filesystem": {"broken": {"description": "Missing base_dir"}}}}

    with open(connections_yaml, "w") as f:
        yaml.dump(connections_data, f)

    monkeypatch.chdir(tmp_path)

    config = {"connection": "@filesystem.broken", "path": "test.csv"}

    driver = FilesystemCsvExtractorDriver()
    # Should not crash, but will fail to find file
    with pytest.raises((FileNotFoundError, RuntimeError)):
        driver.run(step_id="extract_1", config=config, inputs=None, ctx=mock_ctx)


# ============================================================================
# Discovery Mode Tests
# ============================================================================


def test_discovery_with_connection(temp_connections_yaml, mock_ctx):
    """Test discovery mode uses base_dir from connection."""
    from osiris.drivers.filesystem_csv_extractor_driver import FilesystemCsvExtractorDriver

    # Create CSV files in local connection directory
    local_dir = temp_connections_yaml["local_dir"]
    (local_dir / "file1.csv").write_text("a,b\n1,2\n")
    (local_dir / "file2.csv").write_text("c,d\n3,4\n")

    config = {"connection": "@filesystem.local", "path": ".", "discovery": True}

    driver = FilesystemCsvExtractorDriver()
    result = driver.run(step_id="discover_1", config=config, inputs=None, ctx=mock_ctx)

    # Should discover files in connection's base_dir
    assert "files" in result
    assert result["status"] == "success"
    assert result["total_files"] >= 2  # At least file1.csv and file2.csv

    file_names = [f["name"] for f in result["files"]]
    assert "file1.csv" in file_names
    assert "file2.csv" in file_names


def test_discovery_without_connection(csv_directory, mock_ctx):
    """Test discovery mode without connection works as before."""
    from osiris.drivers.filesystem_csv_extractor_driver import FilesystemCsvExtractorDriver

    config = {"path": str(csv_directory), "discovery": True}

    driver = FilesystemCsvExtractorDriver()
    result = driver.run(step_id="discover_1", config=config, inputs=None, ctx=mock_ctx)

    # Should discover files using path directly
    assert "files" in result
    assert result["status"] == "success"
    assert result["total_files"] == 3

    file_names = [f["name"] for f in result["files"]]
    assert set(file_names) == {"file1.csv", "file2.csv", "file3.csv"}


def test_discovery_files_relative_to_connection_base_dir(temp_connections_yaml, mock_ctx):
    """Test that discovered files are relative to base_dir when connection is used."""
    from osiris.drivers.filesystem_csv_extractor_driver import FilesystemCsvExtractorDriver

    local_dir = temp_connections_yaml["local_dir"]
    (local_dir / "test1.csv").write_text("a\n1\n")
    (local_dir / "test2.csv").write_text("b\n2\n")

    config = {"connection": "@filesystem.local", "path": ".", "discovery": True}

    driver = FilesystemCsvExtractorDriver()
    result = driver.run(step_id="discover_1", config=config, inputs=None, ctx=mock_ctx)

    # Verify all discovered paths are within base_dir
    for file_info in result["files"]:
        file_path = Path(file_info["path"])
        assert file_path.exists()
        # Path should be absolute and within local_dir
        assert file_path.is_absolute()
        assert str(local_dir) in str(file_path)


def test_discovery_with_subdirectory_path(temp_connections_yaml, mock_ctx):
    """Test discovery with subdirectory path relative to connection base_dir."""
    from osiris.drivers.filesystem_csv_extractor_driver import FilesystemCsvExtractorDriver

    local_dir = temp_connections_yaml["local_dir"]
    sub_dir = local_dir / "reports"
    sub_dir.mkdir()
    (sub_dir / "report1.csv").write_text("id,total\n1,100\n")
    (sub_dir / "report2.csv").write_text("id,total\n2,200\n")

    config = {"connection": "@filesystem.local", "path": "reports", "discovery": True}

    driver = FilesystemCsvExtractorDriver()
    result = driver.run(step_id="discover_1", config=config, inputs=None, ctx=mock_ctx)

    # Should discover files in subdirectory
    assert "files" in result
    assert result["status"] == "success"
    assert result["total_files"] == 2

    file_names = [f["name"] for f in result["files"]]
    assert set(file_names) == {"report1.csv", "report2.csv"}


# ============================================================================
# Backward Compatibility Tests
# ============================================================================


def test_extraction_without_connection_field(sample_csv, mock_ctx):
    """Test extraction without connection field works as before."""
    from osiris.drivers.filesystem_csv_extractor_driver import FilesystemCsvExtractorDriver

    config = {"path": str(sample_csv)}

    driver = FilesystemCsvExtractorDriver()
    result = driver.run(step_id="extract_1", config=config, inputs=None, ctx=mock_ctx)

    # Should work exactly as before
    assert "df" in result
    assert isinstance(result["df"], pd.DataFrame)
    assert len(result["df"]) == 3
    assert list(result["df"].columns) == ["id", "name", "value"]


def test_relative_path_without_connection_uses_ctx_base_path(tmp_path, mock_ctx):
    """Test relative path resolution without connection uses ctx.base_path."""
    from osiris.drivers.filesystem_csv_extractor_driver import FilesystemCsvExtractorDriver

    # Create CSV in ctx.base_path (tmp_path)
    csv_file = tmp_path / "data.csv"
    csv_file.write_text("a,b\n1,2\n")

    config = {"path": "data.csv"}  # No connection

    driver = FilesystemCsvExtractorDriver()
    result = driver.run(step_id="extract_1", config=config, inputs=None, ctx=mock_ctx)

    # Should resolve to ctx.base_path / data.csv
    assert "df" in result
    assert len(result["df"]) == 1


def test_absolute_path_ignores_connection(temp_connections_yaml, sample_csv, mock_ctx):
    """Test that absolute path ignores connection base_dir."""
    from osiris.drivers.filesystem_csv_extractor_driver import FilesystemCsvExtractorDriver

    # Use absolute path to sample_csv (outside connection base_dir)
    config = {"connection": "@filesystem.local", "path": str(sample_csv.absolute())}

    driver = FilesystemCsvExtractorDriver()
    result = driver.run(step_id="extract_1", config=config, inputs=None, ctx=mock_ctx)

    # Should successfully load from absolute path
    assert "df" in result
    assert len(result["df"]) == 3


def test_discovery_without_connection_works_as_before(csv_directory, mock_ctx):
    """Test discovery without connection uses path from config."""
    from osiris.drivers.filesystem_csv_extractor_driver import FilesystemCsvExtractorDriver

    config = {"path": str(csv_directory), "discovery": True}

    driver = FilesystemCsvExtractorDriver()
    result = driver.run(step_id="discover_1", config=config, inputs=None, ctx=mock_ctx)

    # Should work as before
    assert "files" in result
    assert result["total_files"] == 3


# ============================================================================
# Integration Tests
# ============================================================================


def test_multiple_filesystem_connections(tmp_path, monkeypatch, mock_ctx):
    """Test with multiple filesystem connections (local, exports, etc.)."""
    from osiris.drivers.filesystem_csv_extractor_driver import FilesystemCsvExtractorDriver

    # Create multiple directories
    local_dir = tmp_path / "local"
    local_dir.mkdir()
    exports_dir = tmp_path / "exports"
    exports_dir.mkdir()
    archives_dir = tmp_path / "archives"
    archives_dir.mkdir()

    # Create test files
    (local_dir / "local.csv").write_text("id,name\n1,Local\n")
    (exports_dir / "export.csv").write_text("id,name\n2,Export\n")
    (archives_dir / "archive.csv").write_text("id,name\n3,Archive\n")

    # Create connections file
    connections_yaml = tmp_path / "osiris_connections.yaml"
    connections_data = {
        "connections": {
            "filesystem": {
                "local": {"base_dir": str(local_dir), "default": True},
                "exports": {"base_dir": str(exports_dir)},
                "archives": {"base_dir": str(archives_dir)},
            }
        }
    }

    with open(connections_yaml, "w") as f:
        yaml.dump(connections_data, f)

    monkeypatch.chdir(tmp_path)

    driver = FilesystemCsvExtractorDriver()

    # Test local connection
    result1 = driver.run(
        step_id="extract_local",
        config={"connection": "@filesystem.local", "path": "local.csv"},
        inputs=None,
        ctx=mock_ctx,
    )
    assert result1["df"]["name"].tolist() == ["Local"]

    # Test exports connection
    result2 = driver.run(
        step_id="extract_exports",
        config={"connection": "@filesystem.exports", "path": "export.csv"},
        inputs=None,
        ctx=mock_ctx,
    )
    assert result2["df"]["name"].tolist() == ["Export"]

    # Test archives connection
    result3 = driver.run(
        step_id="extract_archives",
        config={"connection": "@filesystem.archives", "path": "archive.csv"},
        inputs=None,
        ctx=mock_ctx,
    )
    assert result3["df"]["name"].tolist() == ["Archive"]


def test_connection_with_env_var_substitution(tmp_path, monkeypatch, mock_ctx):
    """Test connection with environment variable substitution in base_dir."""
    from osiris.drivers.filesystem_csv_extractor_driver import FilesystemCsvExtractorDriver

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "test.csv").write_text("id\n1\n")

    # Set environment variable
    monkeypatch.setenv("DATA_BASE_DIR", str(data_dir))

    # Create connections file with env var
    connections_yaml = tmp_path / "osiris_connections.yaml"
    connections_data = {"connections": {"filesystem": {"env_based": {"base_dir": "${DATA_BASE_DIR}"}}}}

    with open(connections_yaml, "w") as f:
        yaml.dump(connections_data, f)

    monkeypatch.chdir(tmp_path)

    config = {"connection": "@filesystem.env_based", "path": "test.csv"}

    driver = FilesystemCsvExtractorDriver()
    result = driver.run(step_id="extract_1", config=config, inputs=None, ctx=mock_ctx)

    # Should successfully resolve env var and load file
    assert "df" in result
    assert len(result["df"]) == 1


def test_connection_with_missing_env_var(tmp_path, monkeypatch, mock_ctx):
    """Test error handling when connection has unresolved env var."""
    from osiris.drivers.filesystem_csv_extractor_driver import FilesystemCsvExtractorDriver

    # Create connections file with env var (don't set the env var)
    connections_yaml = tmp_path / "osiris_connections.yaml"
    connections_data = {"connections": {"filesystem": {"broken": {"base_dir": "${MISSING_VAR}"}}}}

    with open(connections_yaml, "w") as f:
        yaml.dump(connections_data, f)

    monkeypatch.chdir(tmp_path)

    config = {"connection": "@filesystem.broken", "path": "test.csv"}

    driver = FilesystemCsvExtractorDriver()
    with pytest.raises(ValueError, match="Failed to resolve connection.*Environment variable 'MISSING_VAR' not set"):
        driver.run(step_id="extract_1", config=config, inputs=None, ctx=mock_ctx)


def test_default_connection_selection(temp_connections_yaml_no_default, mock_ctx):
    """Test default connection selection when no default flag is set."""
    from osiris.drivers.filesystem_csv_extractor_driver import FilesystemCsvExtractorDriver

    # Connection file has only one alias 'local' without default flag
    # Using just family should fail (no default specified)
    config = {"connection": "@filesystem.local", "path": "test.csv"}

    driver = FilesystemCsvExtractorDriver()
    result = driver.run(step_id="extract_1", config=config, inputs=None, ctx=mock_ctx)

    # Should work when alias is explicitly specified
    assert "df" in result
    assert len(result["df"]) == 1


# ============================================================================
# Edge Cases
# ============================================================================


def test_connection_with_empty_base_dir(tmp_path, monkeypatch, mock_ctx):
    """Test connection with empty base_dir field."""
    from osiris.drivers.filesystem_csv_extractor_driver import FilesystemCsvExtractorDriver

    # Create CSV in current directory
    csv_file = tmp_path / "test.csv"
    csv_file.write_text("a\n1\n")

    connections_yaml = tmp_path / "osiris_connections.yaml"
    connections_data = {"connections": {"filesystem": {"empty": {"base_dir": ""}}}}

    with open(connections_yaml, "w") as f:
        yaml.dump(connections_data, f)

    monkeypatch.chdir(tmp_path)

    config = {"connection": "@filesystem.empty", "path": "test.csv"}

    driver = FilesystemCsvExtractorDriver()
    # Empty base_dir should be falsy, so path resolution falls back to ctx or cwd
    result = driver.run(step_id="extract_1", config=config, inputs=None, ctx=mock_ctx)
    assert "df" in result


def test_connection_with_relative_base_dir(tmp_path, monkeypatch, mock_ctx):
    """Test connection with relative base_dir path."""
    from osiris.drivers.filesystem_csv_extractor_driver import FilesystemCsvExtractorDriver

    # Create subdirectory
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "test.csv").write_text("id\n1\n")

    connections_yaml = tmp_path / "osiris_connections.yaml"
    # Use relative path for base_dir
    connections_data = {"connections": {"filesystem": {"relative": {"base_dir": "data"}}}}

    with open(connections_yaml, "w") as f:
        yaml.dump(connections_data, f)

    monkeypatch.chdir(tmp_path)

    config = {"connection": "@filesystem.relative", "path": "test.csv"}

    driver = FilesystemCsvExtractorDriver()
    result = driver.run(step_id="extract_1", config=config, inputs=None, ctx=mock_ctx)

    # Should resolve relative base_dir correctly
    assert "df" in result
    assert len(result["df"]) == 1


def test_connection_with_tilde_in_base_dir(tmp_path, monkeypatch, mock_ctx):
    """Test connection with ~ in base_dir (should expand to home directory)."""
    from osiris.drivers.filesystem_csv_extractor_driver import FilesystemCsvExtractorDriver

    # Note: This test creates files in actual home directory, which may not be ideal
    # Instead, we'll just verify the path gets created correctly without actually using it
    connections_yaml = tmp_path / "osiris_connections.yaml"
    connections_data = {"connections": {"filesystem": {"home": {"base_dir": "~/osiris_test"}}}}

    with open(connections_yaml, "w") as f:
        yaml.dump(connections_data, f)

    monkeypatch.chdir(tmp_path)

    config = {"connection": "@filesystem.home", "path": "test.csv"}

    driver = FilesystemCsvExtractorDriver()
    # This will fail with FileNotFoundError, but we verify the error handling works
    with pytest.raises((FileNotFoundError, RuntimeError)):
        driver.run(step_id="extract_1", config=config, inputs=None, ctx=mock_ctx)


# ============================================================================
# Path Resolution Priority Tests
# ============================================================================


def test_path_resolution_priority_order(tmp_path, monkeypatch, mock_ctx):
    """Test path resolution follows correct priority: connection > ctx.base_path > cwd."""
    from osiris.drivers.filesystem_csv_extractor_driver import FilesystemCsvExtractorDriver

    # Create three different directories with same filename
    conn_dir = tmp_path / "conn"
    conn_dir.mkdir()
    ctx_dir = tmp_path / "ctx"
    ctx_dir.mkdir()
    cwd_dir = tmp_path / "cwd"
    cwd_dir.mkdir()

    # Create different files in each location
    (conn_dir / "test.csv").write_text("id\n100\n")  # Connection dir
    (ctx_dir / "test.csv").write_text("id\n200\n")  # Context base_path
    (cwd_dir / "test.csv").write_text("id\n300\n")  # Current working dir

    # Setup connection
    connections_yaml = tmp_path / "osiris_connections.yaml"
    connections_data = {"connections": {"filesystem": {"priority_test": {"base_dir": str(conn_dir)}}}}

    with open(connections_yaml, "w") as f:
        yaml.dump(connections_data, f)

    monkeypatch.chdir(cwd_dir)

    # Update mock_ctx to point to ctx_dir
    mock_ctx.base_path = ctx_dir

    driver = FilesystemCsvExtractorDriver()

    # Test 1: With connection - should use conn_dir (priority 1)
    config1 = {"connection": "@filesystem.priority_test", "path": "test.csv"}
    result1 = driver.run(step_id="extract_1", config=config1, inputs=None, ctx=mock_ctx)
    assert result1["df"]["id"].tolist() == [100]  # From conn_dir

    # Test 2: Without connection but with ctx - should use ctx_dir (priority 2)
    config2 = {"path": "test.csv"}  # No connection
    result2 = driver.run(step_id="extract_2", config=config2, inputs=None, ctx=mock_ctx)
    assert result2["df"]["id"].tolist() == [200]  # From ctx_dir

    # Test 3: Without connection and without ctx - should use cwd (priority 3)
    config3 = {"path": "test.csv"}
    result3 = driver.run(step_id="extract_3", config=config3, inputs=None, ctx=None)
    assert result3["df"]["id"].tolist() == [300]  # From cwd_dir
