# Pending Code Review Findings - Fix v0.5.0 Batch 2

**Status**: Ready for implementation
**Priority**: HIGH (all 5 findings)
**Branch**: fix/v0.5.0
**PR**: #50

This document captures 5 HIGH priority findings from code review that need fixing in PR #50.

---

## 1. Guide Sample Pipeline - Outdated OML Format

**File**: `osiris/mcp/tools/guide.py:216` (_get_sample_oml function)

**Issue**: Sample pipeline uses old OML format with 5 critical errors:
1. Uses `version: 0.1.0` instead of `oml_version: "0.1.0"`
2. Missing `mode: read/write/transform` fields in all steps
3. Uses `depends_on: [step-id]` instead of `needs: [step-id]`
4. Unquoted connection refs `@mysql.default` (not `"@mysql.default"`)
5. Invalid component `duckdb.processor` (should be `duckdb.transformer`)

**Impact**: Users get samples that immediately fail validation

**Fix**:
- Replace sample YAML with valid OML v0.1.0 format
- Verify with validator before shipping

**Test**: Add test that validates sample passes OML validator

---

## 2. OSIRIS_HOME Hardcoded Path

**File**: `osiris/mcp/clients_config.py:38`

**Issue**: Hardcodes OSIRIS_HOME to `{base_path}/testing_env`
- In production with `base_path=/srv/osiris/acme`, sets to `/srv/osiris/acme/testing_env`
- Directory doesn't exist in production (only in dev)
- MCP initialization fails in real deployments

**Impact**: Claude Desktop MCP doesn't work in production

**Fix**:
- Change: `osiris_home = f"{base_path}/testing_env"`
- To: `osiris_home = base_path`
- Respects Filesystem Contract v1 where base_path is the project root

**Files**:
- `osiris/mcp/clients_config.py:39` - Change one line
- `tests/mcp/test_clients_config.py:100-106` - Update test assertion

---

## 3. Windows Shell Compatibility

**File**: `osiris/mcp/clients_config.py:47`

**Issue**: Hardcodes `/bin/bash` command
- Doesn't exist on Windows
- Windows users get "file not found" error
- CLI docs claim Windows support but config is Windows-incompatible

**Impact**: Claude Desktop MCP fails on Windows

**Fix**:
- Platform detection: `platform.system() == "Windows"`
- Windows: Use `cmd.exe` with `/c` flag
- Unix: Use `/bin/bash` with `-lc` flag

**Implementation**:
```python
import platform

is_windows = platform.system() == "Windows"
if is_windows:
    command = "cmd.exe"
    args = ["/c", f"cd /d {shlex.quote(base_path)} && ..."]
else:
    command = "/bin/bash"
    args = ["-lc", f"cd {shlex.quote(base_path)} && exec ..."]
```

**Tests**: Add Windows/Linux/macOS platform-specific tests with mock.patch

---

## 4. PYTHONPATH Extension Bug

**File**: `osiris/cli/mcp_entrypoint.py:67-68`

**Issue**: Only sets PYTHONPATH if not already defined
- User has `export PYTHONPATH=/opt/custom` in shell
- setup_environment() skips adding repo_root (conditional check fails)
- Subprocesses via run_cli_json() inherit old PYTHONPATH
- ModuleNotFoundError: No module named 'osiris'

**Impact**: MCP breaks when user has pre-existing PYTHONPATH

**Fix**:
- Change from conditional check to always append
```python
# OLD (BUGGY):
if "PYTHONPATH" not in os.environ:
    os.environ["PYTHONPATH"] = str(repo_root)

# NEW (FIXED):
existing_pythonpath = os.environ.get("PYTHONPATH", "").strip()
if existing_pythonpath:
    os.environ["PYTHONPATH"] = str(repo_root) + ":" + existing_pythonpath
else:
    os.environ["PYTHONPATH"] = str(repo_root)
```

**Test**: Add test with pre-existing PYTHONPATH

---

## 5. Guide References Return Value Ignored

**File**: `osiris/mcp/tools/guide.py:57,67-81`

**Issue**:
- Line 57 calls `_get_relevant_references(next_step)`
- Return value is completely ignored
- Result dict (lines 67-81) doesn't include "references" field
- Users/LLMs don't get resource guidance pointers

**Impact**: Users lose "here's what to read next" context

**Fix**:
1. Line 57: Capture return value
   ```python
   references = self._get_relevant_references(next_step)
   ```

2. Result dict: Add "references" field
   ```python
   result = {
       ...
       "references": references,  # ADD THIS
       "status": "success",
   }
   ```

**Test**: Assert `result["references"]` is present and is a list

---

## Summary Table

| # | File | Line | Issue | Fix Complexity |
|---|------|------|-------|---|
| 1 | guide.py | 216 | Sample OML format outdated | Medium (update YAML) |
| 2 | clients_config.py | 38 | OSIRIS_HOME hardcoded | Trivial (1 line) |
| 3 | clients_config.py | 47 | /bin/bash Windows fail | Low (platform detection) |
| 4 | mcp_entrypoint.py | 67-68 | PYTHONPATH overwrite | Trivial (3 lines) |
| 5 | guide.py | 57,67-81 | References ignored | Trivial (2 lines) |

---

## Implementation Notes

- All 5 fixes are independent (no dependencies between them)
- Can be committed as single "fix(batch2)" commit or 2-3 separate commits
- Add corresponding tests for each fix
- Recommend single comprehensive commit to keep PR #50 organized

---

## Files to Modify

- `osiris/mcp/tools/guide.py` (2 changes: sample YAML + capture references)
- `osiris/mcp/clients_config.py` (2 changes: OSIRIS_HOME + platform shell)
- `osiris/cli/mcp_entrypoint.py` (1 change: PYTHONPATH append)
- `tests/mcp/test_tools_guide.py` (2 tests)
- `tests/mcp/test_clients_config.py` (2-3 tests)
- `tests/cli/test_mcp_entrypoint.py` (1 test)

---

## Next Steps

1. Implement all 5 fixes
2. Run full test suite
3. Commit as "fix(batch2): Fix 5 remaining HIGH priority issues"
4. Push to fix/v0.5.0
5. Update PR #50 body with final summary (15 total bugs fixed)
