# DuckDB E2B Test Checklist

## Follow-up PR Test Additions

### 1. E2B Live Tests (`tests/e2b/test_e2b_duckdb.py`)

- [ ] **test_e2b_duckdb_transform_simple**
  - MySQL extract (1 table)
  - DuckDB transform (basic SELECT)
  - CSV write
  - Verify row count preserved

- [ ] **test_e2b_duckdb_aggregation**
  - MySQL extract (orders table)
  - DuckDB GROUP BY aggregation
  - Verify aggregated results

- [ ] **test_e2b_duckdb_multi_input**
  - Two MySQL extracts
  - DuckDB JOIN operation
  - Verify joined output

- [ ] **test_e2b_duckdb_window_functions**
  - DuckDB with ROW_NUMBER, RANK
  - Verify window function results

### 2. Parity Tests Updates (`tests/parity/test_parity_e2b_vs_local.py`)

- [ ] **Enable E2B execution for DuckDB tests**
  - Remove local-only restriction
  - Add E2B_LIVE_TESTS check
  - Compare results between environments

- [ ] **test_duckdb_determinism**
  - Ensure ORDER BY in all queries
  - Verify identical results local vs E2B

### 3. Integration Tests (`tests/integration/test_mysql_duckdb_supabase.py`)

- [ ] **test_full_pipeline_with_transform**
  - MySQL → DuckDB → Supabase
  - End-to-end data validation
  - Check Supabase table contents

- [ ] **test_transform_error_handling**
  - Invalid SQL in DuckDB step
  - Verify graceful error reporting
  - Check pipeline stops correctly

- [ ] **test_large_dataset_transform**
  - Generate 10K+ rows
  - Transform with DuckDB
  - Monitor memory usage

### 4. Driver Tests (`tests/drivers/test_duckdb_transform_driver.py`)

- [ ] **test_driver_interface**
  - Verify Driver protocol compliance
  - Check run() signature

- [ ] **test_empty_input_handling**
  - No upstream data
  - Verify appropriate error/empty result

- [ ] **test_config_validation**
  - Missing 'query' key
  - Empty query string
  - Verify validation errors

### 5. Component Registry Tests

- [ ] **test_duckdb_component_discovery**
  - Verify spec.yaml loaded
  - Check component appears in registry
  - Validate x-runtime.driver mapping

### 6. Performance Tests

- [ ] **test_transform_performance**
  - Measure transform overhead
  - Compare local vs E2B timing
  - Set performance baselines

### 7. Mock Driver Improvements

- [ ] **Extend mock to handle more SQL patterns**
  - CTEs (WITH clauses)
  - UNION operations
  - Subqueries

- [ ] **Add query validation**
  - Basic SQL syntax check
  - Reject DDL operations
  - Log rejected queries

## Test Fixtures Needed

```python
@pytest.fixture
def duckdb_pipeline():
    """Pipeline with DuckDB transform step."""
    return {
        "pipeline": {"id": "duckdb-test", "name": "DuckDB Test"},
        "steps": [
            {
                "id": "extract",
                "component": "mysql.extractor",
                "mode": "read",
                "config": {"query": "SELECT * FROM test_table"},
                "needs": []
            },
            {
                "id": "transform",
                "component": "duckdb.processor",
                "mode": "transform",
                "config": {"query": "SELECT * FROM input_df WHERE score > 100"},
                "needs": ["extract"]
            },
            {
                "id": "write",
                "component": "filesystem.csv_writer",
                "mode": "write",
                "config": {"path": "output.csv"},
                "needs": ["transform"]
            }
        ]
    }

@pytest.fixture
def duckdb_driver():
    """DuckDB driver instance for testing."""
    from tests.mocks.duckdb_processor_driver import DuckDBProcessorDriver
    return DuckDBProcessorDriver()
```

## Acceptance Criteria

- [ ] All tests pass locally
- [ ] All tests pass in E2B with `E2B_LIVE_TESTS=1`
- [ ] No memory leaks in large dataset tests
- [ ] Performance within 10% of local execution
- [ ] Error messages are clear and actionable
- [ ] Metrics properly emitted (rows_read, rows_written, duration)

## Notes

- Start with mock driver to unblock E2B
- Production driver can be added incrementally
- Focus on parity between local and E2B first
- Large dataset handling can be deferred to M3 (streaming)
