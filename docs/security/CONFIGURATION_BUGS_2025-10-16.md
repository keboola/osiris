# Configuration Handling Bugs - Osiris Codebase

**Detection Date:** 2025-10-16
**Detection Method:** Systematic agent-based code analysis
**Total Issues Found:** 8 (2 High, 3 Medium, 3 Low)

---

## Executive Summary

A systematic review of configuration handling revealed **8 validation and path-related issues**. Key findings:

- **Missing Error Handling:** Environment variable type conversions can crash without try-catch (4 instances)
- **Silent Validation Errors:** Invalid config values ignored without user notification (1 instance)
- **Hardcoded Paths:** E2B sandbox paths not config-driven (1 instance)
- **Insufficient Validation:** MySQL connection errors don't specify which fields are missing (1 instance)

**Impact:** Application crashes on invalid env vars, configuration bugs go unnoticed, limited customization for deployment.

---

## HIGH Severity Issues

### BUG-CFG-001: Missing Try-Catch for Environment Variable Type Conversions

**Severity:** HIGH
**File:** `/Users/padak/github/osiris/osiris/core/llm_adapter.py` (lines 168, 172, 178, 194, 198, 204, 231-232)
**Category:** Validation gap - missing error handling

**Current Code:**
```python
params["temperature"] = float(os.environ.get("LLM_TEMPERATURE", "0.1"))
params["max_completion_tokens"] = int(os.environ.get("LLM_MAX_TOKENS", "2000"))
```

**Problem:**
If a user sets invalid values (e.g., `LLM_TEMPERATURE=abc` or `LLM_MAX_TOKENS=not_a_number`), the code raises `ValueError` without catching it, crashing the application.

**Example Failure:**
```bash
export LLM_TEMPERATURE=abc
python osiris.py chat  # ← Crashes with ValueError
```

**Impact:**
- User Experience: Silent failures or cryptic errors
- Severity: High - prevents LLM initialization
- No helpful error message about which env var is invalid

**Recommended Fix:**
```python
def _parse_env_float(key: str, default: float) -> float:
    """Safely parse environment variable as float."""
    try:
        value = os.environ.get(key)
        return float(value) if value else default
    except ValueError:
        logger.warning(f"Invalid {key}='{value}', using default {default}")
        return default

# Usage:
params["temperature"] = self._parse_env_float("LLM_TEMPERATURE", 0.1)
params["max_completion_tokens"] = self._parse_env_int("LLM_MAX_TOKENS", 2000)
```

**Priority:** P1 - Crashes on invalid input

---

### BUG-CFG-002: Unvalidated Integer Conversion in MCP Config

**Severity:** HIGH
**File:** `/Users/padak/github/osiris/osiris/mcp/config.py` (lines 156, 173-174, 178-179)
**Category:** Validation gap - crash on invalid input

**Current Code:**
```python
self.payload_limit_mb = int(os.environ.get("OSIRIS_MCP_PAYLOAD_LIMIT_MB", self.DEFAULT_PAYLOAD_LIMIT_MB))
self.discovery_cache_ttl_hours = int(
    os.environ.get("OSIRIS_MCP_CACHE_TTL_HOURS", self.DEFAULT_DISCOVERY_CACHE_TTL_HOURS)
)
```

**Problem:**
If environment variables contain non-numeric strings, `int()` raises `ValueError`. While there IS range validation after `payload_limit_mb` conversion, if the conversion itself fails, the constructor crashes.

**Example Failure:**
```bash
export OSIRIS_MCP_PAYLOAD_LIMIT_MB=large
python osiris.py mcp run  # ← Crashes with ValueError
```

**Impact:**
- User Experience: Crashes on invalid env vars
- Severity: Medium-High - affects MCP server startup
- Security: Could be DoS vector if attacker can set env vars

**Recommended Fix:**
```python
try:
    self.payload_limit_mb = int(os.environ.get("OSIRIS_MCP_PAYLOAD_LIMIT_MB", self.DEFAULT_PAYLOAD_LIMIT_MB))
except ValueError as e:
    logger.warning(f"Invalid OSIRIS_MCP_PAYLOAD_LIMIT_MB, using default {self.DEFAULT_PAYLOAD_LIMIT_MB}: {e}")
    self.payload_limit_mb = self.DEFAULT_PAYLOAD_LIMIT_MB
```

**Priority:** P1 - Crashes on invalid input

---

## MEDIUM Severity Issues

### BUG-CFG-003: Silent Validation Error Suppression in AIOP Config

**Severity:** MEDIUM
**File:** `/Users/padak/github/osiris/osiris/core/config.py` (lines 834-839)
**Category:** Silent failure - configuration not applied

**Current Code:**
```python
for env_key, config_key, converter in env_mappings:
    value = os.environ.get(env_key)
    if value is not None:
        with contextlib.suppress(ValueError, TypeError):
            config[config_key] = converter(value)
            # Skip invalid values
```

**Problem:**
If `OSIRIS_AIOP_MAX_CORE_BYTES=invalid`, the `int()` conversion fails silently, and the configuration silently uses the YAML or default value WITHOUT notifying the user. This creates debugging confusion.

**Example:**
```bash
export OSIRIS_AIOP_MAX_CORE_BYTES=unlimited  # User expects this to work
python osiris.py run pipeline.yaml  # Silently ignores, uses default
# User thinks unlimited was set, but it wasn't!
```

**Impact:**
- User Experience: Silent failures, configuration not applied as intended
- Severity: Medium - affects AIOP behavior without user awareness
- Debugging: User can't tell why config didn't apply

**Recommended Fix:**
```python
for env_key, config_key, converter in env_mappings:
    value = os.environ.get(env_key)
    if value is not None:
        try:
            config[config_key] = converter(value)
        except (ValueError, TypeError) as e:
            logger.warning(f"Invalid {env_key}={value}, ignoring: {e}")
```

**Priority:** P2 - Silent failures

---

### BUG-CFG-004: Unvalidated Integer Conversions in AIOP Retention Config

**Severity:** MEDIUM-HIGH
**File:** `/Users/padak/github/osiris/osiris/core/config.py` (lines 858, 860-861)
**Category:** Crash on invalid input

**Current Code:**
```python
if "OSIRIS_AIOP_RETENTION_KEEP_RUNS" in os.environ:
    config.setdefault("retention", {})["keep_runs"] = int(os.environ["OSIRIS_AIOP_RETENTION_KEEP_RUNS"])

if "OSIRIS_AIOP_RETENTION_ANNEX_KEEP_DAYS" in os.environ:
    config.setdefault("retention", {})["annex_keep_days"] = int(os.environ["OSIRIS_AIOP_RETENTION_ANNEX_KEEP_DAYS"])
```

**Problem:**
Unlike the mappings that use `contextlib.suppress()`, these direct conversions will raise `ValueError` if the env var is non-numeric, crashing the application with no fallback.

**Impact:**
- User Experience: Crashes without helpful error message
- Severity: High - application startup failure

**Recommended Fix:**
```python
if "OSIRIS_AIOP_RETENTION_KEEP_RUNS" in os.environ:
    try:
        keep_runs = int(os.environ["OSIRIS_AIOP_RETENTION_KEEP_RUNS"])
        config.setdefault("retention", {})["keep_runs"] = keep_runs
    except ValueError:
        logger.warning(f"Invalid OSIRIS_AIOP_RETENTION_KEEP_RUNS value, using default")
```

**Priority:** P1 - Crashes on invalid input

---

### BUG-CFG-005: Insufficient Validation in MySQL Connection Config

**Severity:** MEDIUM
**File:** `/Users/padak/github/osiris/osiris/connectors/mysql/client.py` (lines 49-62)
**Category:** Poor error messages

**Current Code:**
```python
self.host = config.get("host", "localhost")
self.port = config.get("port", 3306)
self.database = config.get("database")
self.user = config.get("user")
self.password = config.get("password")
# ...
if not all([self.database, self.user, self.password]):
    raise ValueError("database, user, and password are required")
```

**Issues:**
1. Port defaults to integer `3306` but could receive string `"3306"` from config - should validate and coerce type
2. No validation that host is not an empty string (differs from database/user/password)
3. Error message doesn't tell user WHICH fields are missing

**Example:**
```yaml
mysql:
  host: ""
  port: "3306"  # String instead of int
  # Missing database, user, password
```

**Error:** `ValueError: database, user, and password are required`
**Better:** `ValueError: MySQL connection missing required fields: database, user, password`

**Recommended Fix:**
```python
# Validate required fields with detailed errors
missing = []
if not config.get("database"):
    missing.append("database")
if not config.get("user"):
    missing.append("user")
if not config.get("password"):
    missing.append("password")

if missing:
    raise ValueError(f"MySQL connection missing required fields: {', '.join(missing)}")

# Coerce port to integer
try:
    self.port = int(config.get("port", 3306))
except (ValueError, TypeError):
    raise ValueError(f"Invalid port value: {config.get('port')}, must be an integer")
```

**Priority:** P2 - UX improvement

---

### BUG-CFG-006: Hardcoded Paths in E2B Proxy

**Severity:** MEDIUM
**File:** `/Users/padak/github/osiris/osiris/remote/e2b_transparent_proxy.py` (multiple lines)
**Category:** Hardcoded paths - not config-driven

**Current Code:**
All E2B sandbox paths are hardcoded:
```python
await self.sandbox.commands.run(f"mkdir -p /home/user/session/{self.session_id}")
await self.sandbox.files.write("/home/user/rpc_protocol.py", rpc_content)
await self.sandbox.files.write(f"/home/user/osiris/remote/rpc_protocol.py", rpc_content)
```

And in `proxy_worker.py` (line 181):
```python
self.session_dir = Path(f"/home/user/session/{self.session_id}")
```

**Problems:**
1. E2B sandbox root is hardcoded to `/home/user` - what if E2B changes this?
2. Session path structure `/home/user/session/{session_id}` is not configurable
3. If users want different artifact paths, no way to customize
4. No alignment with FilesystemContract v1 (ADR-0028)

**Impact:**
- User Experience: Can't customize E2B artifact organization
- Severity: Medium - architectural issue for future scale
- Deployment: Breaks if E2B changes default paths

**Recommended Fix:**
```python
# In MCPFilesystemConfig or new E2BFilesystemConfig class
E2B_SANDBOX_ROOT = os.environ.get("E2B_SANDBOX_ROOT", "/home/user")
SESSION_BASE_PATH = f"{E2B_SANDBOX_ROOT}/session"

# Usage:
session_dir = f"{SESSION_BASE_PATH}/{self.session_id}"
```

**Priority:** P2 - Architectural improvement

---

## LOW Severity Issues

### BUG-CFG-007: Missing Logging for Nested Config Defaults

**Severity:** LOW
**File:** `/Users/padak/github/osiris/osiris/core/conversational_agent.py` (lines 124-131)
**Category:** Transparency

**Current Code:**
```python
validation_config = self.config.get("validation", {})
retry_config = validation_config.get("retry", {})
self.retry_manager = ValidationRetryManager(
    validator=self.validator,
    max_attempts=retry_config.get("max_attempts", 2),  # Has default
    include_history_in_hitl=retry_config.get("include_history_in_hitl", True),
    history_limit=retry_config.get("history_limit", 3),
    diff_format=retry_config.get("diff_format", "patch"),
)
```

**Problem:**
While defaults ARE provided in the `.get()` calls, if `validation.retry` config is missing entirely, there's no logging to tell the user defaults are being used.

**Impact:**
- User Experience: Medium - defaults are used but users don't know
- Severity: Low - functional but lacks transparency

**Recommended Fix:**
```python
validation_config = self.config.get("validation", {})
if "validation" not in self.config:
    logger.info("No 'validation' config found, using defaults")

retry_config = validation_config.get("retry", {})
if "retry" not in validation_config:
    logger.debug("No 'validation.retry' config found, using defaults")
```

**Priority:** P3 - Nice to have

---

### BUG-CFG-008: Confusing Defaults Documentation in MCP Config

**Severity:** LOW
**File:** `/Users/padak/github/osiris/osiris/mcp/config.py` (lines 136-141)
**Category:** Documentation

**Current Code:**
```python
DEFAULT_CACHE_DIR = Path.home() / ".osiris_cache" / "mcp"
DEFAULT_MEMORY_DIR = Path.home() / ".osiris_memory" / "mcp"
DEFAULT_AUDIT_DIR = Path.home() / ".osiris_audit"
DEFAULT_TELEMETRY_DIR = Path.home() / ".osiris_telemetry"
```

**Problem:**
These are class constants that get overridden by filesystem config, but they are used as fallback defaults. In the `__init__` method (lines 188-191), they ARE properly overridden with filesystem config paths. However, the defaults are not well documented as being overridden.

**Impact:**
- User Experience: Low - code path is correct, but documentation unclear
- Severity: Low - not actually a bug, just confusing

**Recommended Fix:**
Add comment explaining the defaults are overridden:
```python
# These defaults are used only if MCPFilesystemConfig cannot load osiris.yaml
# In normal operation, filesystem config values take precedence
DEFAULT_CACHE_DIR = Path.home() / ".osiris_cache" / "mcp"
```

**Priority:** P3 - Documentation only

---

## Summary Table

| Bug ID | Severity | Category | File | Priority |
|--------|----------|----------|------|----------|
| CFG-001 | HIGH | Missing try-catch | llm_adapter.py | P1 |
| CFG-002 | HIGH | Unvalidated int() | mcp/config.py | P1 |
| CFG-003 | MEDIUM | Silent suppression | core/config.py | P2 |
| CFG-004 | MEDIUM-HIGH | Unvalidated int() | core/config.py | P1 |
| CFG-005 | MEDIUM | Poor error messages | mysql/client.py | P2 |
| CFG-006 | MEDIUM | Hardcoded paths | e2b_transparent_proxy.py | P2 |
| CFG-007 | LOW | Missing logging | conversational_agent.py | P3 |
| CFG-008 | LOW | Confusing docs | mcp/config.py | P3 |

---

## Recommended Fix Priority

**Phase 1 (P1 - Critical):**
1. CFG-001, CFG-002, CFG-004: Fix unhandled ValueError in type conversions

**Phase 2 (P2 - Important):**
2. CFG-003: Add logging for silent validation errors
3. CFG-005: Improve error messages
4. CFG-006: Make E2B paths configurable

**Phase 3 (P3 - Nice-to-have):**
5. CFG-007, CFG-008: Documentation and logging improvements

---

## Best Practices

1. **Always wrap env var type conversions in try-catch**
2. **Log warnings for invalid config values**
3. **Provide detailed error messages** (which fields are missing/invalid)
4. **Make all paths config-driven** (no hardcoded absolute paths)
5. **Document config precedence** (CLI > ENV > YAML > defaults)
6. **Validate config at startup** with comprehensive error messages

---

## References

- Main bug report: `docs/security/ARCHITECTURAL_BUGS_2025-10-16.md`
- Detection methodology: `docs/security/AGENT_SEARCH_GUIDE.md`
