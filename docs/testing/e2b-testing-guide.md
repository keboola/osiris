# E2B Testing Guide

## Overview

This guide covers the E2B (remote sandbox) testing infrastructure for Osiris Pipeline. The test suite ensures parity between local and E2B execution while preventing orphaned sandboxes and leaked secrets.

> **Note**: E2B CI is temporarily disabled on PRs. Use 'Run workflow' (workflow_dispatch) to execute live test suites manually.

## Test Categories

### 1. Smoke Tests (`test_e2b_smoke.py`)
- **Purpose**: Quick validation that E2B adapter works correctly
- **When**: Run on every PR (mocked)
- **Requirements**: No API key needed for mocked tests
- **Coverage**:
  - Adapter prepare phase
  - Mock execution flow
  - Artifact collection
  - Error handling

### 2. Live Tests (`test_e2b_live.py`)
- **Purpose**: Validate real E2B sandbox execution
- **When**: Manual testing and nightly CI
- **Requirements**: `E2B_API_KEY` and `E2B_LIVE_TESTS=1`
- **Coverage**:
  - Real sandbox creation and execution
  - Environment variable handling
  - Failure scenarios
  - Resource configuration
  - Artifact collection

### 3. Parity Tests (`test_parity_e2b_vs_local.py`)
- **Purpose**: Ensure identical behavior between local and E2B
- **When**: Nightly CI runs
- **Requirements**: `E2B_API_KEY` for live comparison
- **Coverage**:
  - Result consistency
  - Log normalization and comparison
  - Artifact matching
  - Error handling parity
  - Data volume testing

### 4. Orphan Cleanup (`test_orphan_cleanup.py`)
- **Purpose**: Detect and clean up abandoned sandboxes
- **When**: Nightly and on-demand
- **Requirements**: `E2B_API_KEY` for live cleanup
- **Coverage**:
  - Sandbox age detection
  - Cleanup logic
  - Lifecycle tracking
  - Exception handling

## Prerequisites and Secrets

### Setup for Live Testing
1. Create `testing_env/.env` with your API key:
   ```bash
   echo "E2B_API_KEY=your-api-key-here" > testing_env/.env
   ```

2. Enable live tests by exporting:
   ```bash
   export E2B_LIVE_TESTS=1
   ```

## Running Tests

### Local Development

```bash
# Offline/mocked smoke tests (no API key needed)
make test-e2b-smoke

# Live smoke tests (creates & tears down real sandbox)
export E2B_API_KEY="your-api-key"
export E2B_LIVE_TESTS=1
make test-e2b-smoke

# Parity tests (preflight bypass ON by default)
make test-e2b-parity

# Enforce real preflight validation when cfg layout is ready
OSIRIS_TEST_DISABLE_PREFLIGHT=0 pytest -m parity -vv

# Check for orphaned sandboxes
make test-e2b-orphans

# Cleanup orphaned sandboxes (dry-run)
make e2b-cleanup

# Force cleanup (use with caution)
make e2b-cleanup-force
```

### CI/CD Pipeline

#### PR Checks (Automatic)
- **Trigger**: Label `e2b` or changes under `osiris/remote/**` or `tests/e2b/**`
- **Behavior**: Uses repository secret `E2B_API_KEY` if present; otherwise skips gracefully
- Smoke tests with optional real E2B client
- Secret redaction verification
- No failures if API key missing or E2B service outage

#### Nightly Tests (Scheduled)
- Full parity testing between local and E2B execution
- Uploads artifacts (diffs/logs) for analysis
- Fails on real parity regressions
- Live E2B execution when secrets available
- Orphan detection and cleanup
- Requires secrets in GitHub Actions

#### Manual Triggers
```yaml
# Trigger specific test type via GitHub UI
workflow_dispatch:
  inputs:
    test_type: [smoke, parity, full, orphan-cleanup]
```

## Test Fixtures

### `conftest.py` Fixtures

1. **`e2b_env`**: Provides E2B environment configuration
2. **`e2b_sandbox`**: E2B adapter with optional mocking
3. **`execution_context`**: Test execution context with temp directories
4. **`small_pipeline`**: Simple test pipeline
5. **`resource_intensive_pipeline`**: Pipeline for resource testing

### Adapter Mocking

The test suite uses a dual approach:
- **Mocked transport**: For CI and local testing without API keys
- **Real E2B adapter**: For live testing with actual sandboxes

```python
# Create test adapter
adapter = _create_test_e2b_adapter(
    use_real=True,  # Use real adapter
    api_key=api_key  # None for mocked transport
)
```

## Environment Variables

### Required for Live Tests
- `E2B_API_KEY`: E2B service API key
- `E2B_LIVE_TESTS=1`: Enable live sandbox creation

### Optional Configuration
- `MYSQL_PASSWORD`: For database connection tests
- `SUPABASE_SERVICE_ROLE_KEY`: For Supabase tests
- `E2B_TIMEOUT`: Custom sandbox timeout (default: 300s)

## Secret Management

### Redaction Rules
- All connection strings are masked: `mysql://***@host/db`
- Environment variables in logs are redacted
- Test secrets use pragma comments: `# pragma: allowlist secret`

### CI Secret Storage
GitHub Actions secrets:
- `E2B_API_KEY`
- `MYSQL_PASSWORD`
- `SUPABASE_SERVICE_ROLE_KEY`

## Orphan Prevention

### Automatic Cleanup
- Finally blocks ensure sandbox cleanup
- Fixture teardown handles exceptions
- Nightly CI runs orphan detection

### Manual Cleanup
```python
# Cleanup sandboxes older than 2 hours
cleanup_orphaned_sandboxes(
    client=e2b_client,
    max_age_hours=2,
    dry_run=False
)
```

## Debugging Tests

### Verbose Output
```bash
# Enable verbose E2B adapter output
pytest tests/e2b/ -v -s

# Check specific test
pytest tests/e2b/test_e2b_live.py::TestE2BLiveExecution::test_live_simple_pipeline -v
```

### Common Issues

1. **"E2B_API_KEY not set"**
   - Export the environment variable
   - Or add to `.env` file in project root

2. **"E2B_LIVE_TESTS not enabled"**
   - Set `E2B_LIVE_TESTS=1` for live tests
   - Omit for mocked tests

3. **Sandbox timeout**
   - Increase timeout in adapter config
   - Check sandbox resource limits

4. **Artifact download failures**
   - Verify sandbox completed successfully
   - Check remote logs directory structure

## Test Markers

```ini
# pytest.ini markers
@pytest.mark.e2b         # All E2B-related tests
@pytest.mark.e2b_live    # Tests requiring real E2B
@pytest.mark.e2b_smoke   # Quick smoke tests
@pytest.mark.parity      # Parity comparison tests
@pytest.mark.slow        # Long-running tests
```

## Best Practices

1. **Always use fixtures** for sandbox creation to ensure cleanup
2. **Mock transport layer** for unit tests
3. **Use real adapter** with mocked client for integration tests
4. **Tag test secrets** with pragma comments
5. **Normalize logs** before comparing environments
6. **Track sandbox lifecycle** with try/finally blocks
7. **Run orphan cleanup** regularly in production

## Extending Tests

### Adding New E2B Tests

```python
@pytest.mark.e2b_live
@pytest.mark.skipif(not os.getenv("E2B_API_KEY"), reason="No API key")
def test_new_e2b_feature(e2b_sandbox, execution_context):
    """Test new E2B feature."""
    # Prepare pipeline
    prepared = e2b_sandbox.prepare(pipeline, execution_context)

    # Execute with cleanup
    try:
        result = e2b_sandbox.execute(prepared, execution_context)
        assert result.success
    finally:
        # Cleanup handled by fixture
        pass
```

### Adding Parity Checks

```python
def test_new_parity_check(parity_pipeline):
    """Test new parity aspect."""
    # Execute locally
    local_result = local_adapter.execute(...)

    # Execute on E2B
    e2b_result = e2b_adapter.execute(...)

    # Compare normalized results
    assert normalize(local_result) == normalize(e2b_result)
```

## Monitoring

### CI Dashboard
- Check GitHub Actions for test results
- Review artifact uploads for failures
- Monitor nightly parity reports

### Metrics to Track
- Sandbox creation time
- Execution duration comparison
- Orphan sandbox count
- Secret leak detection rate

## Frequently Seen Errors & Remediation

### Common Test Failures

1. **"No sandbox created" or "E2B_API_KEY not set"**
   - **Cause**: Missing API key
   - **Fix**: Export `E2B_API_KEY` or add to `testing_env/.env`
   - **CI Fix**: Add secret to GitHub repository settings

2. **"LocalAdapter preflight validation failed"**
   - **Cause**: Missing cfg files in expected locations
   - **Fix**: Keep `OSIRIS_TEST_DISABLE_PREFLIGHT=1` (default) until cfg layout is ready
   - **Future**: Remove bypass once proper cfg materialization is implemented

3. **"Secret leaked in logs"**
   - **Cause**: Unredacted credentials in output
   - **Fix**: Check `_redact_connection_string()` in secrets masking
   - **Prevention**: Use `# pragma: allowlist secret` for test-only credentials

4. **"ExecutionContext() got unexpected keyword argument 'logs_dir'"**
   - **Cause**: Version mismatch in ExecutionContext API
   - **Fix**: Use `make_execution_context()` helper from conftest.py

5. **"Driver 'duckdb_processor' not registered"**
   - **Cause**: Missing mock driver for testing
   - **Fix**: Ensure `components/duckdb.processor/spec.yaml` exists

## Troubleshooting

### Enable Debug Logging
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

### Inspect Sandbox Artifacts
```bash
# Download artifacts manually
osiris logs show --session <session_id>
ls -la testing_env/logs/remote/
```

### Verify E2B Client
```python
from osiris.remote.e2b_client import E2BClient
client = E2BClient()
# Test basic operations
```
