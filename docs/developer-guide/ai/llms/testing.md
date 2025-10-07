# LLM Contract: Testing

**Purpose**: AI patterns for generating tests and test fixtures.

**Audience**: AI agents, LLMs generating test code

---

## Testing Framework

### TEST-001: pytest Framework

**Statement**: All tests MUST use pytest.

**Why**: Industry standard, rich fixture system, parametrization, plugins.

**Basic Test**:
```python
import pytest

def test_driver_run():
    """Test driver execution."""
    driver = MySQLExtractorDriver()
    result = driver.run(
        step_id="test_step",
        config={"query": "SELECT 1"},
        inputs={},
        ctx=None
    )
    assert "data" in result
```

---

### TEST-002: Test File Location

**Statement**: Tests MUST be in `tests/` directory, NOT in `testing_env/`.

**Structure**:
```
tests/
  core/
    test_compiler.py
    test_runner.py
  drivers/
    test_mysql_extractor.py
    test_csv_writer.py
  cli/
    test_main.py
    test_logs.py
```

---

## Test Naming

### TEST-003: Descriptive Names

**Statement**: Test names MUST describe what is being tested.

**Pattern**: `test_<what>_<when>_<expected>`

**Examples**:
```python
def test_driver_run_with_valid_config_returns_dataframe():
    """Test driver returns DataFrame with valid config."""
    pass

def test_connection_resolve_with_missing_alias_raises_error():
    """Test connection resolution raises error for missing alias."""
    pass

def test_discovery_output_is_deterministic():
    """Test discovery produces same output on multiple runs."""
    pass
```

---

### TEST-004: Test Organization

**Statement**: Group related tests in test classes.

**Implementation**:
```python
class TestMySQLExtractor:
    """Tests for MySQL extractor driver."""

    def test_run_with_valid_query(self):
        """Test extraction with valid SQL query."""
        pass

    def test_run_with_invalid_query_raises_error(self):
        """Test extraction with invalid query raises error."""
        pass

    def test_discover_returns_tables(self):
        """Test discovery returns list of tables."""
        pass

    def test_doctor_with_valid_connection_returns_ok(self):
        """Test healthcheck with valid connection."""
        pass
```

---

## Fixtures

### TEST-005: pytest Fixtures

**Statement**: Use pytest fixtures for shared test data.

**Implementation**:
```python
import pytest

@pytest.fixture
def sample_config():
    """Sample driver config."""
    return {
        "query": "SELECT * FROM users",
        "resolved_connection": {
            "host": "localhost",
            "port": 3306,
            "database": "testdb",
            "user": "test",
            "password": "test123"  # pragma: allowlist secret
        }
    }

@pytest.fixture
def sample_dataframe():
    """Sample pandas DataFrame."""
    return pd.DataFrame({
        "id": [1, 2, 3],
        "name": ["Alice", "Bob", "Charlie"]
    })

def test_driver_with_fixtures(sample_config, sample_dataframe):
    """Test driver using fixtures."""
    driver = MySQLExtractorDriver()
    result = driver.run(step_id="test", config=sample_config, inputs={}, ctx=None)
    assert len(result["data"]) == 3
```

---

### TEST-006: Temporary Files

**Statement**: Use pytest's `tmp_path` fixture for temporary files.

**Implementation**:
```python
def test_csv_writer_creates_file(tmp_path):
    """Test CSV writer creates output file."""
    output_file = tmp_path / "output.csv"

    driver = CSVWriterDriver()
    driver.run(
        step_id="write_csv",
        config={"output_path": str(output_file)},
        inputs={"extract": {"data": sample_df}},
        ctx=None
    )

    assert output_file.exists()
    assert output_file.stat().st_size > 0
```

---

### TEST-007: Fixture Scope

**Statement**: Use appropriate fixture scope for performance.

**Scopes**: `function` (default), `class`, `module`, `session`

**Implementation**:
```python
@pytest.fixture(scope="session")
def test_database():
    """Create test database once per session."""
    db = create_test_database()
    yield db
    db.close()

@pytest.fixture(scope="function")
def clean_database(test_database):
    """Clean database before each test."""
    test_database.truncate_all()
    yield test_database
```

---

## Mocking

### TEST-008: unittest.mock

**Statement**: Use `unittest.mock` for mocking external dependencies.

**Implementation**:
```python
from unittest.mock import MagicMock, patch

def test_driver_with_mock_client():
    """Test driver with mocked API client."""
    mock_client = MagicMock()
    mock_client.fetch_data.return_value = [
        {"id": 1, "name": "Alice"},
        {"id": 2, "name": "Bob"}
    ]

    driver = ShopifyExtractorDriver(client_factory=lambda conn: mock_client)
    result = driver.run(
        step_id="test",
        config={"resource": "customers"},
        inputs={},
        ctx=None
    )

    assert len(result["data"]) == 2
    mock_client.fetch_data.assert_called_once()
```

---

### TEST-009: Patch Decorator

**Statement**: Use `@patch` decorator for patching imports.

**Implementation**:
```python
from unittest.mock import patch

@patch("osiris.drivers.mysql.extractor.pymysql.connect")
def test_driver_connection(mock_connect):
    """Test driver creates connection."""
    mock_conn = MagicMock()
    mock_connect.return_value = mock_conn

    driver = MySQLExtractorDriver()
    driver.run(
        step_id="test",
        config={"query": "SELECT 1"},
        inputs={},
        ctx=None
    )

    mock_connect.assert_called_once()
```

---

### TEST-010: Context Manager Mocking

**Statement**: Mock context managers using `__enter__` and `__exit__`.

**Implementation**:
```python
def test_connection_context_manager():
    """Test connection is used as context manager."""
    mock_conn = MagicMock()
    mock_conn.__enter__.return_value = mock_conn
    mock_conn.__exit__.return_value = None

    with patch("pymysql.connect", return_value=mock_conn):
        driver = MySQLExtractorDriver()
        driver.run(step_id="test", config={"query": "SELECT 1"}, inputs={}, ctx=None)

    mock_conn.__enter__.assert_called_once()
    mock_conn.__exit__.assert_called_once()
```

---

## Parametrization

### TEST-011: pytest.mark.parametrize

**Statement**: Use parametrization to test multiple inputs.

**Implementation**:
```python
@pytest.mark.parametrize("resource,expected_count", [
    ("customers", 1000),
    ("orders", 5000),
    ("products", 500)
])
def test_extraction_row_counts(resource, expected_count):
    """Test extraction returns expected row counts."""
    driver = ShopifyExtractorDriver()
    result = driver.run(
        step_id="test",
        config={"resource": resource},
        inputs={},
        ctx=None
    )
    assert len(result["data"]) == expected_count
```

---

### TEST-012: Multiple Parameters

**Statement**: Parametrize multiple parameters for combinatorial testing.

**Implementation**:
```python
@pytest.mark.parametrize("limit,page_size", [
    (100, 10),
    (1000, 100),
    (10000, 500)
])
def test_pagination(limit, page_size):
    """Test pagination with different limits and page sizes."""
    driver = MySQLExtractorDriver()
    result = driver.run(
        step_id="test",
        config={"query": "SELECT * FROM users", "limit": limit, "page_size": page_size},
        inputs={},
        ctx=None
    )
    assert len(result["data"]) <= limit
```

---

## Assertions

### TEST-013: Specific Assertions

**Statement**: Use specific assertion methods for clarity.

**Examples**:
```python
# ✓ Correct: Specific assertions
assert result == expected
assert "key" in result
assert len(result) == 3
assert result is None
assert isinstance(result, pd.DataFrame)

# ❌ Wrong: Generic assertions
assert result  # Not specific
assert True  # Always passes
```

---

### TEST-014: pytest Assertions

**Statement**: Use pytest's assertion introspection for better error messages.

**Implementation**:
```python
def test_dataframe_columns():
    """Test DataFrame has expected columns."""
    df = extract_data()

    # pytest provides detailed failure messages
    assert "id" in df.columns
    assert "email" in df.columns
    assert len(df) > 0
```

---

### TEST-015: Custom Error Messages

**Statement**: Add custom messages to assertions for debugging.

**Implementation**:
```python
def test_extraction_count():
    """Test extraction returns expected row count."""
    result = extract_data()
    expected = 1000

    assert len(result["data"]) == expected, (
        f"Expected {expected} rows, got {len(result['data'])}"
    )
```

---

## Secret Handling

### TEST-016: pragma allowlist secret

**Statement**: Test secrets MUST include `# pragma: allowlist secret` comment.

**Implementation**:
```python
@pytest.fixture
def test_connection():
    """Test connection with dummy credentials."""
    return {
        "host": "localhost",
        "user": "test",
        "password": "test123"  # pragma: allowlist secret
    }

def test_connection_string():
    """Test connection string building."""
    dsn = build_dsn(
        host="localhost",
        user="test",
        password="dummy_password_for_testing"  # pragma: allowlist secret
    )
    assert "test" in dsn
```

---

### TEST-017: Never Commit Real Secrets

**Statement**: NEVER use real credentials in tests.

**Correct**:
```python
# ✓ Use dummy credentials
@pytest.fixture
def test_api_key():
    return "test_key_123"  # pragma: allowlist secret

# ✓ Use environment variables for integration tests
@pytest.fixture
def api_key():
    key = os.environ.get("TEST_API_KEY")
    if not key:
        pytest.skip("TEST_API_KEY not set")
    return key
```

**Wrong**:
```python
# ❌ Real credentials
@pytest.fixture
def api_key():
    return "sk_live_abc123xyz789"  # NEVER DO THIS
```

---

## Error Testing

### TEST-018: pytest.raises

**Statement**: Use `pytest.raises` to test exceptions.

**Implementation**:
```python
def test_invalid_query_raises_error():
    """Test invalid query raises ValueError."""
    driver = MySQLExtractorDriver()

    with pytest.raises(ValueError, match="Invalid SQL query"):
        driver.run(
            step_id="test",
            config={"query": "INVALID SQL"},
            inputs={},
            ctx=None
        )
```

---

### TEST-019: Exception Messages

**Statement**: Validate exception messages for clarity.

**Implementation**:
```python
def test_missing_connection_error_message():
    """Test missing connection provides clear error."""
    driver = MySQLExtractorDriver()

    with pytest.raises(ValueError) as exc_info:
        driver.run(
            step_id="test",
            config={"query": "SELECT 1"},  # No connection
            inputs={},
            ctx=None
        )

    assert "resolved_connection" in str(exc_info.value)
    assert "required" in str(exc_info.value)
```

---

## Integration Tests

### TEST-020: Skipping Tests

**Statement**: Skip integration tests when dependencies unavailable.

**Implementation**:
```python
@pytest.mark.skipif(
    not os.environ.get("MYSQL_PASSWORD"),
    reason="MYSQL_PASSWORD not set"
)
def test_mysql_integration():
    """Integration test with real MySQL database."""
    driver = MySQLExtractorDriver()
    result = driver.run(
        step_id="test",
        config={
            "query": "SELECT 1",
            "resolved_connection": {
                "host": "localhost",
                "user": "root",
                "password": os.environ["MYSQL_PASSWORD"]
            }
        },
        inputs={},
        ctx=None
    )
    assert len(result["data"]) == 1
```

---

### TEST-021: Test Markers

**Statement**: Use pytest markers to categorize tests.

**Implementation**:
```python
import pytest

@pytest.mark.unit
def test_driver_validation():
    """Unit test for driver validation."""
    pass

@pytest.mark.integration
@pytest.mark.skipif(not os.environ.get("E2B_API_KEY"), reason="E2B_API_KEY not set")
def test_e2b_execution():
    """Integration test with E2B."""
    pass

@pytest.mark.slow
def test_large_dataset_extraction():
    """Slow test for large dataset."""
    pass
```

**pytest.ini**:
```ini
[pytest]
markers =
    unit: Unit tests
    integration: Integration tests requiring external services
    slow: Slow tests (> 1s)
```

**Usage**:
```bash
pytest -m unit           # Run only unit tests
pytest -m "not slow"     # Skip slow tests
pytest -m integration    # Run only integration tests
```

---

## Cleanup

### TEST-022: Fixture Cleanup

**Statement**: Use fixture yield for cleanup.

**Implementation**:
```python
@pytest.fixture
def temp_database():
    """Create temporary database."""
    db = create_database("test_db")
    yield db
    # Cleanup after test
    db.drop()

def test_with_cleanup(temp_database):
    """Test that uses cleanup fixture."""
    temp_database.insert("users", {"id": 1, "name": "Alice"})
    assert temp_database.count("users") == 1
```

---

### TEST-023: Context Manager Cleanup

**Statement**: Use context managers for resource cleanup.

**Implementation**:
```python
def test_file_cleanup(tmp_path):
    """Test file is cleaned up after test."""
    output_file = tmp_path / "output.csv"

    with open(output_file, "w") as f:
        f.write("id,name\n1,Alice\n")

    assert output_file.exists()
    # File automatically closed
```

---

## Coverage

### TEST-024: Coverage Target

**Statement**: Aim for >80% test coverage for new code.

**Measurement**:
```bash
pytest --cov=osiris --cov-report=html
```

**HTML Report**: `htmlcov/index.html`

---

### TEST-025: Coverage Gaps

**Statement**: Identify and document coverage gaps.

**Implementation**:
```python
# If code path is hard to test, document why
def _internal_api_call(self):
    """Internal API call - tested via integration tests only."""
    pass  # pragma: no cover
```

---

## Determinism

### TEST-026: Deterministic Tests

**Statement**: Tests MUST be deterministic (same input → same output).

**Anti-Pattern**:
```python
# ❌ Non-deterministic: relies on current time
def test_timestamp():
    ts = generate_timestamp()
    assert ts == datetime.now().isoformat()  # Flaky!
```

**Correct Pattern**:
```python
# ✓ Deterministic: mock time
from unittest.mock import patch

@patch("datetime.datetime")
def test_timestamp(mock_datetime):
    mock_datetime.now.return_value = datetime(2025, 9, 30, 12, 0, 0)
    ts = generate_timestamp()
    assert ts == "2025-09-30T12:00:00.000Z"
```

---

### TEST-027: Isolation

**Statement**: Tests MUST be isolated (no shared state).

**Anti-Pattern**:
```python
# ❌ Shared state
counter = 0

def test_increment():
    global counter
    counter += 1
    assert counter == 1  # Fails if run after another test!
```

**Correct Pattern**:
```python
# ✓ Isolated state
def test_increment():
    counter = 0
    counter += 1
    assert counter == 1
```

---

## Performance

### TEST-028: Fast Tests

**Statement**: Unit tests SHOULD run in <1s.

**Guidelines**:
- Mock external dependencies
- Use small datasets
- Skip slow tests by default

**Implementation**:
```python
@pytest.mark.slow
def test_large_dataset():
    """Slow test - skip by default."""
    pass  # Takes >5s
```

---

### TEST-029: Parallel Execution

**Statement**: Tests SHOULD be parallelizable.

**Why**: Faster CI/CD pipeline.

**Usage**:
```bash
pytest -n auto  # pytest-xdist plugin
```

**Requirements**:
- Tests must be isolated
- No shared file system state
- No shared database state

---

## Documentation

### TEST-030: Docstrings

**Statement**: Test functions SHOULD have docstrings.

**Implementation**:
```python
def test_driver_with_pagination():
    """
    Test driver correctly paginates large result sets.

    This test verifies that the driver:
    1. Fetches data in chunks
    2. Combines chunks into single DataFrame
    3. Emits correct metrics
    """
    pass
```

---

## Common Test Patterns

### Driver Test Template
```python
class TestMyExtractorDriver:
    """Tests for MyExtractor driver."""

    @pytest.fixture
    def driver(self):
        """Create driver instance."""
        return MyExtractorDriver()

    @pytest.fixture
    def config(self):
        """Sample config."""
        return {
            "query": "SELECT * FROM users",
            "resolved_connection": {
                "host": "localhost",
                "password": "test123"  # pragma: allowlist secret
            }
        }

    def test_run_with_valid_config(self, driver, config):
        """Test driver execution with valid config."""
        result = driver.run(step_id="test", config=config, inputs={}, ctx=None)
        assert "data" in result
        assert isinstance(result["data"], pd.DataFrame)

    def test_run_with_missing_connection_raises_error(self, driver):
        """Test driver raises error when connection missing."""
        with pytest.raises(ValueError, match="resolved_connection"):
            driver.run(step_id="test", config={"query": "SELECT 1"}, inputs={}, ctx=None)

    def test_discover_returns_resources(self, driver, config):
        """Test discovery returns list of resources."""
        result = driver.discover(config)
        assert "resources" in result
        assert isinstance(result["resources"], list)

    def test_doctor_with_valid_connection(self, driver, config):
        """Test healthcheck with valid connection."""
        ok, details = driver.doctor(config["resolved_connection"])
        assert ok is True
        assert details["category"] == "ok"
```

### CLI Test Template
```python
from click.testing import CliRunner

class TestConnectionsListCommand:
    """Tests for connections list command."""

    @pytest.fixture
    def runner(self):
        """Create CLI runner."""
        return CliRunner()

    def test_list_with_json_flag(self, runner):
        """Test list command with --json flag."""
        result = runner.invoke(connections_list, ["--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)

    def test_list_without_connections(self, runner):
        """Test list command when no connections exist."""
        with patch("osiris.cli.connections.get_connections", return_value=[]):
            result = runner.invoke(connections_list)
            assert result.exit_code == 0
            assert "No connections" in result.output
```

---

## See Also

- **Overview**: `overview.md`
- **Driver Contract**: `drivers.md`
- **CLI Contract**: `cli.md`
- **Full Checklist**: `../checklists/COMPONENT_AI_CHECKLIST.md`
