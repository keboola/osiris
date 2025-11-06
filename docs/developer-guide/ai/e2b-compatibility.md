# E2B Cloud Sandbox Compatibility Guide

## What is E2B?

E2B is a cloud sandbox execution environment where Osiris pipelines run remotely with complete isolation. It's a v0.5.0 production feature that provides:

- **Ephemeral sandboxes**: Clean, isolated environments for each pipeline run
- **Transparent execution**: Identical behavior to local runs
- **Cloud scalability**: Run pipelines without local resource constraints
- **Reproducible results**: Deterministic execution across environments

## Why E2B Compatibility Matters

Components must work **identically** in both environments:

| Environment | Use Case | Requirements |
|------------|----------|--------------|
| **Local** | Development, quick testing | Direct filesystem access, local .env files |
| **E2B Cloud** | Production, demos, CI/CD | Sandboxed filesystem, injected secrets, uploaded dependencies |

**If your component only works locally, it will fail in production E2B runs.**

## Architecture Overview

### Transparent Proxy Pattern

E2B uses a "transparent proxy" architecture that maintains 100% parity with local execution:

```
Local Run:
  CLI → LocalAdapter → Driver → Data

E2B Run:
  CLI → E2BAdapter → E2BTransparentProxy → ProxyWorker → Driver → Data
             ↑                                    ↓
             └────────── RPC Protocol ────────────┘
```

Key insights:
- **RPC-based**: Not pickle-based serialization
- **<1% overhead**: Minimal performance impact per step
- **Identical artifacts**: Same logs, metrics, and outputs
- **In-memory execution**: No DataFrame serialization between driver calls

### Execution Flow

1. **Host (Local Machine)**:
   - Creates E2B sandbox
   - Resolves all connections and secrets
   - Uploads required files (manifest, configs, drivers)
   - Generates execution commands

2. **Sandbox (E2B Cloud)**:
   - ProxyWorker receives commands
   - Executes drivers with resolved configs
   - Streams events and metrics back to host
   - Creates artifacts in sandbox filesystem

3. **Collection**:
   - Host downloads artifacts from sandbox
   - Writes status.json with execution summary
   - Terminates sandbox and cleans up

## Key Differences: Local vs E2B

### Filesystem Access

| Aspect | Local Execution | E2B Cloud Execution |
|--------|----------------|---------------------|
| **Base Path** | Your project directory | `/home/user/session/{session_id}/` |
| **Paths** | Absolute paths work | MUST use config-driven paths |
| **Access** | Direct filesystem access | Sandboxed, isolated environment |
| **Artifacts** | Written to `logs/run_*/` | Written to sandbox, then downloaded |

**CRITICAL**: Never use hardcoded paths like `Path.home()` or `/Users/...`

### Environment Variables

| Aspect | Local Execution | E2B Cloud Execution |
|--------|----------------|---------------------|
| **Secrets** | From `.env` or shell exports | Injected securely into sandbox |
| **Access** | `os.getenv()` works | Access via resolved config only |
| **Resolution** | At runtime | Resolved on host before upload |

### Dependencies

| Aspect | Local Execution | E2B Cloud Execution |
|--------|----------------|---------------------|
| **Installation** | Your virtual environment | Must be in requirements.txt |
| **System packages** | Available if installed | Limited to sandbox environment |
| **Custom modules** | Available from codebase | Uploaded to sandbox |

### Network Access

| Aspect | Local Execution | E2B Cloud Execution |
|--------|----------------|---------------------|
| **Latency** | Low (local network) | May have higher latency |
| **Restrictions** | None (your network) | Sandbox network policies apply |
| **Timeouts** | Configure as needed | 600-second default timeout |

## E2B Compatibility Checklist

### Filesystem (CRITICAL)

- [ ] **NEVER use hardcoded paths**
  - ❌ BAD: `Path.home() / ".osiris"`
  - ✅ GOOD: `ctx.base_path / ".osiris"`

- [ ] **ALWAYS use config-driven paths from context**
  - ❌ BAD: `/Users/padak/github/osiris/testing_env`
  - ✅ GOOD: `ctx.base_path` or paths from config

- [ ] **Use relative paths within base_path**
  - ✅ GOOD: `ctx.base_path / "output" / f"{step_id}.csv"`

- [ ] **Check file paths are within base_path contract**
  - All artifacts under `{base_path}/.osiris/`
  - Session logs under `{base_path}/logs/run_{session_id}/`

### Secrets Handling

- [ ] **Never log secrets** (use masked URLs)
  - ✅ Use `mask_connection_for_display(config, family=family)`

- [ ] **Access via resolved config, not environment**
  - ❌ BAD: `os.getenv("DATABASE_PASSWORD")`
  - ✅ GOOD: `config["resolved_connection"]["password"]`

- [ ] **Verify secrets are in `secrets` array in spec.yaml**
  - Example: `secrets: ["/connection/password", "/connection/api_key"]`

- [ ] **Test secret masking in artifacts**
  - Check `artifacts/{step_id}/cleaned_config.json`
  - Passwords should show as `***MASKED***`

### Dependencies

- [ ] **Declare all Python packages in requirements.txt**
  - Include exact versions: `pandas==2.0.3`
  - Test in clean virtualenv

- [ ] **Use standard library when possible**
  - Reduces upload size and dependencies

- [ ] **Avoid system-level packages**
  - No `apt-get`, `/usr/bin/` dependencies

- [ ] **Test with `--e2b-install-deps` flag**
  - Verifies auto-installation works

### Network Access

- [ ] **Implement retries with exponential backoff**
  - Initial delay: 1 second, max delay: 10 seconds
  - Example: See `osiris/drivers/supabase_writer_driver.py`

- [ ] **Use timeouts (default: 30s for API calls)**
  - Don't rely on instant responses

- [ ] **Handle transient failures gracefully**
  - Network errors, temporary unavailability

- [ ] **Test with network latency in mind**
  - E2B may have higher latency than local

### Resource Limits

- [ ] **Memory: Assume 2GB limit**
  - Don't load entire large datasets into memory
  - Process in chunks if needed

- [ ] **CPU: Shared resources**
  - Avoid CPU-intensive operations
  - Use efficient algorithms

- [ ] **Disk: Limited ephemeral storage**
  - Clean up temporary files
  - Don't assume unlimited disk space

- [ ] **Time: Operations may timeout**
  - Default sandbox timeout: 600 seconds
  - Long-running operations need progress tracking

### Driver Implementation

- [ ] **Read from `config["resolved_connection"]`**
  - NOT from environment variables
  - See CONN-001 in connection contract

- [ ] **Emit metrics with `ctx.log_metric()`**
  - `rows_read`, `rows_written`, `step_duration_ms`
  - See MET-001, MET-002, MET-003

- [ ] **Return DataFrame in `data` key**
  - `return {"data": df}`
  - See DRV-002 in driver protocol

- [ ] **Use keyword-only arguments**
  - `def run(self, *, step_id, config, inputs, ctx)`
  - See DRV-001

## Testing for E2B Compatibility

### Local Testing

```bash
# From testing_env/
cd /Users/padak/github/osiris/testing_env

# Compile your pipeline
python ../osiris.py compile path/to/pipeline.yaml

# Test locally first
python ../osiris.py run --last-compile --verbose

# Test in E2B
python ../osiris.py run --last-compile --e2b --e2b-install-deps --verbose
```

### Compare Artifacts

```bash
# Local artifacts
ls -la logs/run_*/artifacts/

# E2B artifacts (should be identical)
ls -la logs/run_*/artifacts/

# Compare specific files
diff logs/run_LOCAL/artifacts/step1/output.csv \
     logs/run_E2B/artifacts/step1/output.csv
```

### Verify Events and Metrics

```bash
# Check events parity
jq '.event_type' logs/run_LOCAL/events.jsonl | sort | uniq -c
jq '.event_type' logs/run_E2B/events.jsonl | sort | uniq -c

# Check metrics parity
jq '.metric' logs/run_LOCAL/metrics.jsonl | sort | uniq -c
jq '.metric' logs/run_E2B/metrics.jsonl | sort | uniq -c
```

### Check Execution Status

```bash
# View status
cat logs/run_*/status.json

# Expected output:
# {
#   "status": "success",
#   "execution_duration": 3.2,
#   "steps_completed": 3,
#   "steps_total": 3
# }
```

## Common E2B Errors and Solutions

### 1. Path Not Found

**Error**: `FileNotFoundError: /Users/padak/...`

**Cause**: Hardcoded absolute path

**Fix**:
```python
# ❌ Before
output_path = Path("/Users/padak/github/osiris/testing_env/output/data.csv")

# ✅ After
output_path = ctx.base_path / "output" / "data.csv"
```

### 2. Module Not Found

**Error**: `ModuleNotFoundError: No module named 'some_package'`

**Cause**: Missing dependency in requirements.txt

**Fix**:
```bash
# Add to requirements.txt
echo "some_package==1.2.3" >> requirements.txt

# Test with auto-install
osiris run --last-compile --e2b --e2b-install-deps
```

### 3. Connection Timeout

**Error**: `TimeoutError: Connection timed out after 5s`

**Cause**: Network latency in E2B sandbox

**Fix**:
```python
# ❌ Before
response = requests.get(url, timeout=5)

# ✅ After
response = requests.get(url, timeout=30)  # Higher timeout for E2B
```

### 4. Permission Denied

**Error**: `PermissionError: Access denied to /var/log/...`

**Cause**: Attempting to access system paths

**Fix**:
```python
# ❌ Before
log_file = "/var/log/myapp.log"

# ✅ After
log_file = ctx.base_path / "logs" / "myapp.log"
```

### 5. Secret Leaked in Logs

**Error**: CI fails with "Secret detected in logs"

**Cause**: Unmasked credentials in output

**Fix**:
```python
# ❌ Before
ctx.log_info(f"Connecting to {config['resolved_connection']['password']}")

# ✅ After
from osiris.cli.helpers.connection_helpers import mask_connection_for_display
masked = mask_connection_for_display(config, family="mysql")
ctx.log_info(f"Connecting to {masked['host']}")
```

### 6. DataFrame Not Available

**Error**: `TypeError: input_df of type NoneType`

**Cause**: Step output not cached properly (historical issue, now fixed)

**Fix**: Ensure driver returns `{"data": df}` and inputs are properly declared in manifest

## E2B Best Practices

### DO: Use Config-Driven Paths

```python
def run(self, *, step_id, config, inputs, ctx):
    """E2B-compatible driver implementation."""

    # ✅ GOOD: Use context base_path
    output_dir = ctx.base_path / "output"
    output_file = output_dir / f"{step_id}.csv"

    # Ensure directory exists
    output_dir.mkdir(parents=True, exist_ok=True)

    # Write output
    df.to_csv(output_file, index=False)

    return {"data": df}
```

### DO: Implement Retry Logic

```python
import time
import random

def _execute_with_retry(self, operation, max_attempts=3):
    """Execute operation with exponential backoff."""

    for attempt in range(max_attempts):
        try:
            return operation()
        except (ConnectionError, TimeoutError) as e:
            if attempt == max_attempts - 1:
                raise

            # Exponential backoff with jitter
            delay = min(10, (2 ** attempt) + random.uniform(0, 1))
            time.sleep(delay)
```

### DO: Declare Dependencies

```bash
# requirements.txt
pandas==2.0.3
requests==2.31.0
sqlalchemy==2.0.20
```

### DO: Mask Secrets

```python
from osiris.cli.helpers.connection_helpers import mask_connection_for_display

# Mask before logging
masked_config = mask_connection_for_display(
    config,
    family="mysql"  # Spec-aware masking
)
ctx.log_info(f"Connected to {masked_config['host']}")
```

### DON'T: Use Hardcoded Paths

```python
# ❌ BAD: Hardcoded paths
home_dir = Path.home()
project_root = Path("/Users/padak/github/osiris")
output_path = "/tmp/output.csv"

# ✅ GOOD: Config-driven paths
output_path = ctx.base_path / "output.csv"
```

### DON'T: Access Environment Directly

```python
# ❌ BAD: Direct environment access
password = os.getenv("DB_PASSWORD")

# ✅ GOOD: Resolved connection
password = config["resolved_connection"]["password"]
```

### DON'T: Assume Fast Network

```python
# ❌ BAD: Low timeout
response = requests.get(url, timeout=1)

# ✅ GOOD: Reasonable timeout with retry
for attempt in range(3):
    try:
        response = requests.get(url, timeout=30)
        break
    except requests.Timeout:
        if attempt == 2:
            raise
```

### DON'T: Use System Packages

```python
# ❌ BAD: System-level dependency
subprocess.run(["ffmpeg", "-i", "input.mp4"])

# ✅ GOOD: Python package
import moviepy.editor as mp
clip = mp.VideoFileClip("input.mp4")
```

## Example: E2B-Compatible Driver

Complete example showing all best practices:

```python
"""E2B-compatible MySQL extractor driver."""

import pandas as pd
import time
import random
from pathlib import Path
from typing import Any, Dict, Optional


class MySQLExtractorDriver:
    """MySQL extractor with full E2B compatibility.

    Implements:
    - Config-driven paths (no hardcoded paths)
    - Retry logic with exponential backoff
    - Secret-safe logging
    - Proper metric emission
    - Resolved connection access
    """

    __version__ = "1.0.0"

    def run(
        self,
        *,
        step_id: str,
        config: dict,
        inputs: Optional[dict] = None,
        ctx: Any = None
    ) -> dict:
        """
        Extract data from MySQL database.

        Args:
            step_id: Unique step identifier
            config: Step configuration with resolved_connection
            inputs: Optional inputs from upstream steps
            ctx: Execution context with base_path and logging

        Returns:
            Dict with 'data' key containing pandas DataFrame

        Implements:
            - CONN-001: Read from resolved_connection
            - DRV-001: Keyword-only arguments
            - DRV-002: Return DataFrame in data key
            - MET-001: Emit rows_read metric
        """
        # CONN-001: Read from resolved_connection
        conn_info = config.get("resolved_connection", {})
        if not conn_info:
            raise ValueError(
                f"Step {step_id}: 'resolved_connection' is required"
            )

        # Validate required connection fields
        required = ["host", "database", "user", "password"]
        for field in required:
            if not conn_info.get(field):
                raise ValueError(
                    f"Step {step_id}: connection field '{field}' is required"
                )

        # Get query from config
        query = config.get("query")
        if not query:
            raise ValueError(f"Step {step_id}: 'query' is required")

        # Log with masked credentials
        if ctx:
            from osiris.cli.helpers.connection_helpers import (
                mask_connection_for_display
            )
            masked = mask_connection_for_display(config, family="mysql")
            ctx.log_info(
                f"Connecting to {masked['host']}/{masked['database']}"
            )

        # Execute query with retry logic
        df = self._execute_with_retry(
            lambda: self._execute_query(conn_info, query, ctx)
        )

        # MET-001: Emit metric with unit and step tag
        if ctx and hasattr(ctx, "log_metric"):
            ctx.log_metric(
                "rows_read",
                len(df),
                unit="rows",
                tags={"step": step_id}
            )

        # DRV-002: Return DataFrame in data key
        return {"data": df}

    def _execute_query(
        self,
        conn_info: dict,
        query: str,
        ctx: Any
    ) -> pd.DataFrame:
        """Execute SQL query and return DataFrame."""
        import sqlalchemy

        # Build connection string (will be masked in logs)
        conn_str = (
            f"mysql+pymysql://{conn_info['user']}:"
            f"{conn_info['password']}@{conn_info['host']}/"
            f"{conn_info['database']}"
        )

        # Create engine
        engine = sqlalchemy.create_engine(conn_str)

        try:
            # Execute query with timeout (E2B-friendly)
            df = pd.read_sql(
                query,
                engine,
                timeout=30  # Higher timeout for E2B
            )

            if ctx:
                ctx.log_info(f"Fetched {len(df)} rows")

            return df

        finally:
            engine.dispose()

    def _execute_with_retry(
        self,
        operation,
        max_attempts: int = 3
    ):
        """
        Execute operation with exponential backoff.

        Handles transient network errors common in E2B sandbox.
        """
        for attempt in range(max_attempts):
            try:
                return operation()

            except (ConnectionError, TimeoutError) as e:
                if attempt == max_attempts - 1:
                    raise

                # Exponential backoff with jitter
                delay = min(10, (2 ** attempt) + random.uniform(0, 1))
                time.sleep(delay)

    def discover(self, config: dict, ctx: Any = None) -> dict:
        """
        Discover available tables and columns.

        Implements DISC-001, DISC-002, DISC-003.
        """
        import hashlib
        import json
        from datetime import datetime, timezone

        conn_info = config.get("resolved_connection", {})

        # Query tables and columns
        resources = self._query_schema(conn_info)

        # DISC-002: Sort alphabetically
        resources.sort(key=lambda r: r["name"])
        for resource in resources:
            if "fields" in resource:
                resource["fields"].sort(key=lambda f: f["name"])

        # DISC-001: Build discovery output
        discovery = {
            "discovered_at": datetime.now(timezone.utc).isoformat().replace(
                "+00:00", "Z"
            ),
            "resources": resources,
            "fingerprint": None
        }

        # DISC-003: Compute SHA-256 fingerprint
        discovery_copy = discovery.copy()
        discovery_copy.pop("fingerprint")
        canonical = json.dumps(discovery_copy, sort_keys=True)
        fingerprint = hashlib.sha256(canonical.encode()).hexdigest()
        discovery["fingerprint"] = f"sha256:{fingerprint}"

        return discovery

    def _query_schema(self, conn_info: dict) -> list[dict]:
        """Query database schema for tables and columns."""
        # Implementation details...
        pass

    def doctor(
        self,
        connection: dict,
        timeout: float = 2.0
    ) -> tuple[bool, dict]:
        """
        Test connection health.

        Implements DOC-001, DOC-002, DOC-003.
        """
        import time
        import socket

        try:
            start = time.time()

            # Test connection
            self._test_connection(connection, timeout)

            latency_ms = (time.time() - start) * 1000

            # DOC-002: Use standard category
            return True, {
                "latency_ms": round(latency_ms, 2),
                "category": "ok",
                "message": "Connection successful"
            }

        except Exception as e:
            # Classify error by type
            category = self._classify_error(e)

            # DOC-003: No secrets in message
            return False, {
                "latency_ms": None,
                "category": category,
                "message": f"Error: {type(e).__name__}"
            }

    def _classify_error(self, error: Exception) -> str:
        """Classify error into standard category."""
        # Implementation details...
        pass

    def _test_connection(self, connection: dict, timeout: float):
        """Test database connection."""
        # Implementation details...
        pass
```

## Performance Characteristics

### Expected Overheads

Based on production measurements (v0.5.0):

| Metric | Local | E2B | Overhead |
|--------|-------|-----|----------|
| Sandbox creation | N/A | ~8.3s | One-time cost |
| Dependency install | N/A | 5-15s | When needed |
| Per-step execution | ~830ms | ~840ms | <10ms |
| Artifact download | N/A | ~2.8s | One-time cost |
| Total overhead | N/A | ~11s | <1% for typical pipelines |

### Optimization Tips

1. **Use `--e2b-install-deps`** to avoid manual dependency management
2. **Batch multiple pipelines** to amortize sandbox creation cost
3. **Keep artifacts small** (<100MB) for fast downloads
4. **Minimize step count** to reduce per-step overhead
5. **Use efficient queries** to reduce network transfer time

## Related Documentation

### Core Documentation
- **CLAUDE.md**: Filesystem contract and configuration
- **build-new-component.md**: Complete driver implementation guide
- **checklists/connections_doctor_contract.md**: Connection testing requirements

### E2B Research and Design
- **docs/adr/0010-e2b-integration-for-pipeline-execution.md**: Original E2B decision
- **docs/adr/0026-e2b-transparent-proxy.md**: Transparent proxy architecture
- **docs/adr/0034-e2b-runtime-parity.md**: Runtime unification details
- **docs/testing/e2b-testing-guide.md**: E2B testing infrastructure
- **docs/research/e2b_import_failure_root_cause.md**: Import issue investigation
- **docs/research/e2b_local_parity_rca.md**: Parity bug root cause analysis

### Testing
- **tests/e2b/test_e2b_smoke.py**: Basic E2B functionality tests
- **tests/e2b/test_e2b_live.py**: Live E2B execution tests
- **tests/parity/test_parity_e2b_vs_local.py**: Parity validation tests

## Quick Reference Commands

```bash
# Test component locally
cd testing_env
python ../osiris.py compile pipeline.yaml
python ../osiris.py run --last-compile --verbose

# Test in E2B with dependency auto-install
python ../osiris.py run --last-compile --e2b --e2b-install-deps --verbose

# Compare artifacts
diff -r logs/run_LOCAL/artifacts logs/run_E2B/artifacts

# Check events parity
jq -s 'map(.event_type) | group_by(.) | map({event: .[0], count: length})' \
  logs/run_*/events.jsonl

# Check metrics parity
jq -s 'map(.metric) | group_by(.) | map({metric: .[0], count: length})' \
  logs/run_*/metrics.jsonl

# View E2B logs
cat logs/run_*/osiris.log | grep -i e2b

# Check execution status
cat logs/run_*/status.json | jq
```

## Version Info

- **E2B Integration**: v0.5.0 (Production Ready)
- **Transparent Proxy**: Fully implemented
- **Parity Achievement**: 100% feature parity between local and E2B
- **Last Updated**: 2025-10-26

---

**Ready to build E2B-compatible components?** Follow the checklist above and test with `--e2b` flag early and often.
