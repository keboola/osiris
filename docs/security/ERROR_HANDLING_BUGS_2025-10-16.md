# Error Handling Inconsistencies - Osiris Codebase

**Detection Date:** 2025-10-16
**Detection Method:** Systematic agent-based code analysis
**Total Issues Found:** 12 (1 Critical, 6 High, 5 Medium)

---

## Executive Summary

A systematic review of error handling patterns revealed **12 inconsistencies** ranging from critical silent failures in validation logic to missing exception chaining. Key patterns identified:

- Silent exception swallowing without logging (8 instances)
- Missing exception chaining (`from e`) (5 instances)
- Dead code (discarded f-strings) (1 instance)
- Inconsistent error message formats across modules

**Impact:** Silent failures reduce debuggability, critical validation errors go unnoticed, and error context is lost during re-raises.

---

## CRITICAL Issues

### BUG-ERR-001: Exception Context Loss in E2B Status Validation

**Severity:** CRITICAL
**File:** `/Users/padak/github/osiris/osiris/remote/e2b_adapter.py:474-476`
**Category:** Silent failure in critical path

**Current Code:**
```python
except Exception as e:
    if prepared.run_params.get("verbose"):
        print(f"⚠️  Failed to parse status.json: {e}")
    # Exception is swallowed, not re-raised or logged
```

**Problem:**
- Critical `status.json` parsing failure is only printed if verbose mode enabled
- No logging happens
- Exception is silently swallowed - execution continues
- Success flag may be incorrectly determined if `status.json` is corrupt

**Attack Surface:** Corrupt status files lead to incorrect success/failure determination

**Impact:**
- Pipeline reported as successful when it actually failed
- No audit trail of validation failures
- Debugging impossible without verbose mode

**Recommended Fix:**
```python
except Exception as e:
    logger.error(f"Failed to parse status.json: {e}", exc_info=True)
    if prepared.run_params.get("verbose"):
        print(f"⚠️  Failed to parse status.json: {e}")
    # Don't silently continue - mark validation as failed
    four_proof_success = False
    success = False
```

**Priority:** P0 - Fix immediately

---

### BUG-ERR-002: Dead Code - Discarded F-String in CLI Bridge

**Severity:** HIGH
**File:** `/Users/padak/github/osiris/osiris/mcp/cli_bridge.py:107`
**Category:** Dead code

**Current Code:**
```python
# Line 107: Dead code - f-string not assigned
f"{error_message} (exit code: {exit_code}, command: {' '.join(cmd[:3])}...)"

# Used message is much simpler (line 111):
message=error_message,  # Keep message clean, don't include context
```

**Problem:**
- The formatted error context is computed but never used (line 107 is a bare f-string)
- The comment says "don't include context" but the code suggests it should be included
- Creates confusion about whether context information should be added to errors

**Impact:** Developer confusion, incomplete error reporting

**Recommended Fix:**
```python
# Option 1: Remove dead code if context shouldn't be included
# (delete line 107)

# Option 2: Use the context in the message if it should be included
error_context = f"{error_message} (exit code: {exit_code}, command: {' '.join(cmd[:3])}...)"
return OsirisError(
    family=family,
    message=error_context,  # Include context
    path=["cli_bridge", "run_cli_json"],
    suggest=suggest,
)
```

**Priority:** P1 - Fix in next sprint

---

## HIGH Severity Issues

### BUG-ERR-003: Silent Exception Swallowing in Component Loading

**Severity:** HIGH
**File:** `/Users/padak/github/osiris/osiris/cli/components_cmd.py:56-57`
**Category:** Silent failure

**Current Code:**
```python
except Exception:
    pass
```

**Context:**
```python
has_driver = False
if driver_path:
    try:
        module_path, class_name = driver_path.rsplit(".", 1)
        module = importlib.import_module(module_path)
        getattr(module, class_name)
        has_driver = True
    except Exception:  # Silent swallow with no logging
        pass
```

**Problem:**
- No logging before swallowing
- No indication if import failed due to missing module, syntax error, or missing class
- Users can't debug why component shows as non-runnable
- Information loss: can't distinguish between "module doesn't exist" vs "class doesn't exist" vs "syntax error"

**Impact:** Silent failures reduce debuggability

**Recommended Fix:**
```python
except Exception as e:
    logger.debug(f"Failed to load runtime driver {driver_path}: {e}")
    has_driver = False
```

**Priority:** P1 - Affects user debugging experience

---

### BUG-ERR-004: Silent Exception in Session Config Loading

**Severity:** HIGH
**File:** `/Users/padak/github/osiris/osiris/cli/helpers/session_helpers.py:36-39`
**Category:** Silent failure in configuration

**Current Code:**
```python
try:
    fs_config, _, _ = load_osiris_config()
    logs_dir = fs_config.resolve_path(fs_config.run_logs_dir)
    return logs_dir
except Exception:  # Silent swallow
    return Path("run_logs")
```

**Problem:**
- Multiple different errors could occur: file not found, YAML parsing error, missing keys, type errors
- All are silently swallowed without any indication
- Users won't know if they're using fallback due to misconfiguration vs. legitimate missing file
- No logging to help debug configuration issues

**Impact:** Configuration errors go unnoticed, users can't debug

**Recommended Fix:**
```python
except FileNotFoundError:
    logger.debug("osiris.yaml not found, using default run_logs directory")
    return Path("run_logs")
except Exception as e:
    logger.warning(f"Failed to load filesystem config: {e}, falling back to run_logs")
    return Path("run_logs")
```

**Priority:** P1 - Affects configuration troubleshooting

---

### BUG-ERR-005: Silent Exception in E2B Log Download

**Severity:** HIGH
**File:** `/Users/padak/github/osiris/osiris/remote/e2b_adapter.py:403-405`
**Category:** Silent failure in artifact collection

**Current Code:**
```python
except Exception as e:
    if prepared.run_params.get("verbose"):
        print(f"[DEBUG] Failed to download remote logs: {e}")
    # Exception silently swallowed, no logging
```

**Problem:**
- Silently swallows log download failures
- Only prints in verbose mode
- No logger call, so operators can't see this in production logs
- Could mask important artifact loss

**Impact:** Lost artifacts without user awareness

**Recommended Fix:**
```python
except Exception as e:
    logger.warning(f"Failed to download remote logs: {e}")
    if prepared.run_params.get("verbose"):
        print(f"[DEBUG] Failed to download remote logs: {e}")
    # Mark that artifacts may be incomplete
    downloaded_count = 0
```

**Priority:** P1 - Affects artifact collection reliability

---

### BUG-ERR-006: Silent Exception in E2B Warning Extraction

**Severity:** HIGH
**File:** `/Users/padak/github/osiris/osiris/remote/e2b_adapter.py:520-521`
**Category:** Silent failure in error reporting

**Current Code:**
```python
try:
    stderr_content = stderr_file.read_text()
    warning_lines = self._extract_warning_lines(stderr_content)
    for line in warning_lines[-10:]:
        print(f"   {line}")
except Exception:  # Silent swallow
    pass
```

**Problem:**
- Exception occurs while trying to **report errors**
- Silent swallowing means user gets no feedback about why warnings couldn't be displayed
- Could mask filesystem issues or encoding problems

**Impact:** Lost error context, users don't know warnings exist

**Recommended Fix:**
```python
except Exception as e:
    logger.debug(f"Failed to extract warnings from stderr: {e}")
    print(f"   [Failed to read warnings: {str(e)[:50]}...]")
```

**Priority:** P1 - Affects error visibility

---

### BUG-ERR-007: Inconsistent Exception Chaining in Driver

**Severity:** MEDIUM-HIGH
**File:** `/Users/padak/github/osiris/osiris/drivers/supabase_writer_driver.py:310-311`
**Category:** Inconsistent error chaining

**Current Code:**
```python
except Exception as retry_e:
    raise RuntimeError(f"Batch write failed after retry: {str(retry_e)}") from retry_e
```

**Problem:**
- This occurrence (line 311): Proper exception chaining with `from retry_e` ✓
- Other occurrences in same file don't have this
- Inconsistent approach to error chaining makes stack traces unpredictable

**Impact:** Debugging harder with incomplete stack traces

**Recommended Fix:**
Make exception chaining consistent throughout the file:
```python
except Exception as e:
    logger.error(f"Failed to write batch {i // batch_size}: {str(e)}")
    if retries > 0:
        try:
            # Retry logic
            rows_written += len(batch)
        except Exception as retry_e:
            # Always chain the original exception
            raise RuntimeError(f"Batch write failed after retry: {str(retry_e)}") from e
    else:
        raise RuntimeError(f"Batch write failed: {str(e)}") from e
```

**Priority:** P2 - Code quality improvement

---

### BUG-ERR-008: Missing Exception Chaining in MySQL Client

**Severity:** MEDIUM
**File:** `/Users/padak/github/osiris/osiris/connectors/mysql/client.py:102-104`
**Category:** Missing exception context

**Current Code:**
```python
except SQLAlchemyError as e:
    logger.error(f"Failed to connect to MySQL: {e}")
    raise
```

**Problem:**
- Good logging ✓
- Bare `raise` is OK and maintains stack trace ✓
- **However:** For SQLAlchemy errors originating from pymysql, multiple layers of wrapping occur
- The original cause (pymysql.Error) is buried
- Better to use `raise ... from e` for explicit clarity

**Impact:** Minor - stack traces work but could be clearer

**Recommended Fix:**
```python
except SQLAlchemyError as e:
    logger.error(f"Failed to connect to MySQL: {e}", exc_info=True)
    raise  # Bare raise is OK, but could be more explicit
```

**Priority:** P3 - Nice to have improvement

---

## MEDIUM Severity Issues

### BUG-ERR-009: Inconsistent Error Message Formats

**Severity:** MEDIUM
**Category:** Code consistency

**Problem:** Error message formats vary significantly across modules:

**In supabase_writer_driver.py:**
```python
raise ValueError(f"Step {step_id}: Unknown configuration keys: ...")
raise RuntimeError("HTTP SQL channel not configured (missing sql_url or key)")
```

**In mysql/client.py:**
```python
raise ValueError("database, user, and password are required")
```

**In supabase/client.py:**
```python
raise ValueError("Supabase URL and key are required (config or env vars)")
```

**In connections_cmd.py:**
```python
raise ValueError("Missing required Supabase URL or key")
```

**Issues:**
- Inconsistent prefix usage (some include step_id, some don't)
- Inconsistent capitalization
- Some include solution hints, others don't
- Makes parsing errors for tooling/automation harder

**Impact:** Operational issues in error handling

**Recommended Fix:**
Create a consistent error message format helper:
```python
class OsirisErrorMessages:
    """Consistent error message formats."""

    @staticmethod
    def step_config_error(step_id: str, message: str) -> str:
        return f"Step {step_id}: {message}"

    @staticmethod
    def missing_config(field: str, context: str = "") -> str:
        msg = f"Missing required field: {field}"
        if context:
            msg += f" ({context})"
        return msg
```

**Priority:** P2 - Code quality improvement

---

### BUG-ERR-010: E2B Client Exception Suppression with nosec

**Severity:** MEDIUM
**File:** `/Users/padak/github/osiris/osiris/remote/e2b_client.py` (multiple locations)
**Category:** Broad exception handling

**Current Code:**
```python
except Exception:  # nosec B110
    pass
```

**Problem:**
- `# nosec B110` suppresses Bandit warnings about broad exception handling
- The nosec suppression is technically correct (this is legitimate use)
- **However:** No logging of swallowed exceptions
- Makes debugging difficult
- Pattern could mask important errors

**Impact:** Debugging difficulty, potential error masking

**Recommended Fix:**
```python
except Exception as e:  # nosec B110 - Best-effort cleanup
    logger.debug(f"Exception during cleanup: {e}")
    pass
```

**Priority:** P2 - Code quality

---

### BUG-ERR-011: Bare Except in Optional Dependency Import

**Severity:** LOW
**File:** `/Users/padak/github/osiris/osiris/cli/run.py:21-26`
**Category:** Pattern inconsistency

**Current Code:**
```python
try:
    from ..remote.e2b_integration import add_e2b_help_text, parse_e2b_args
    E2B_AVAILABLE = True
except ImportError:
    E2B_AVAILABLE = False
    # ...provides fallback implementations
```

**Problem:**
- This is actually a GOOD pattern for optional dependencies
- However, should catch ImportError specifically, not bare except
- Comment clarifies intent, but inconsistent with rest of codebase

**Impact:** Low - actually correct, just stylistically inconsistent

**Recommended Fix:**
```python
# Already correct - catching ImportError specifically
# No change needed, pattern is appropriate
```

**Priority:** P3 - Style consistency only

---

### BUG-ERR-012: Best-Effort Cleanup Pattern

**Severity:** LOW
**File:** `/Users/padak/github/osiris/osiris/drivers/supabase_writer_driver.py:38-42`
**Category:** Appropriate exception swallowing

**Current Code:**
```python
def _reset_test_state() -> None:
    """Reset module-level state for test isolation."""
    global _module_clients
    for client in _module_clients:
        try:
            if hasattr(client, "close"):
                client.close()
        except Exception:  # Silent swallow is appropriate here
            pass
```

**Problem:** None - this is actually correct!

**Analysis:**
- Pattern is appropriate for best-effort cleanup
- Comment clarifies intent
- This is acceptable for test teardown

**Impact:** None

**Priority:** P3 - No fix needed, documented as correct pattern

---

## Summary Table

| Bug ID | Severity | Category | File | Priority |
|--------|----------|----------|------|----------|
| ERR-001 | CRITICAL | Status validation failure | e2b_adapter.py:474 | P0 |
| ERR-002 | HIGH | Dead code | cli_bridge.py:107 | P1 |
| ERR-003 | HIGH | Silent component load failure | components_cmd.py:56 | P1 |
| ERR-004 | HIGH | Silent config load failure | session_helpers.py:36 | P1 |
| ERR-005 | HIGH | Silent log download failure | e2b_adapter.py:403 | P1 |
| ERR-006 | HIGH | Silent warning extraction failure | e2b_adapter.py:520 | P1 |
| ERR-007 | MEDIUM | Inconsistent exception chaining | supabase_writer_driver.py:310 | P2 |
| ERR-008 | MEDIUM | Missing explicit chaining | mysql/client.py:102 | P3 |
| ERR-009 | MEDIUM | Inconsistent error formats | (multiple files) | P2 |
| ERR-010 | MEDIUM | Broad exception with nosec | e2b_client.py | P2 |
| ERR-011 | LOW | Bare except (actually OK) | run.py:21 | P3 |
| ERR-012 | LOW | Best-effort cleanup (OK) | supabase_writer_driver.py:38 | P3 |

---

## Pattern Analysis

### Most Common Issues
1. **Silent exception swallowing** - 8 instances without logging
2. **Missing exception chaining** - 5 instances missing `from e`
3. **Inconsistent error formats** - Multiple styles across codebase

### Best Practices to Implement

1. **Always log before catching exceptions** (except for expected, documented cases)
2. **Use exception chaining** (`raise X from e`) to preserve context
3. **Avoid bare `except:`** - use specific exception types
4. **Use `from e` in re-raises** to maintain stack traces
5. **Document intentional silent catches** with comments explaining why
6. **Create error message format helpers** for consistency
7. **Test error paths** as thoroughly as happy paths

---

## Recommended Fix Priority

**Phase 1 (P0 - Critical):**
1. ERR-001: Status validation failure - could cause incorrect success determination

**Phase 2 (P1 - High):**
2. ERR-002: Dead code cleanup
3. ERR-003, ERR-004, ERR-005, ERR-006: Add logging to silent failures

**Phase 3 (P2 - Medium):**
4. ERR-007, ERR-009, ERR-010: Code quality improvements

**Phase 4 (P3 - Low):**
5. ERR-008, ERR-011, ERR-012: Style consistency (no functional issues)

---

## References

- Main bug report: `docs/security/ARCHITECTURAL_BUGS_2025-10-16.md`
- Detection methodology: `docs/security/AGENT_SEARCH_GUIDE.md`
- Related: Parameter propagation issues affect error message quality
