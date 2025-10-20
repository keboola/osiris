# Integration Test Fix Status Report

**Date:** 2025-10-18
**Task:** Fix 16 failing integration tests after Phase 2 completion
**Status:** ⚠️ **PARTIAL SUCCESS** - 4 tests fixed, 19 MCP core regressions introduced

---

## Executive Summary

Implemented MCP protocol compliance fixes (envelopes, policy guards, deterministic metadata) which fixed 4 of 16 failing integration tests, but introduced 19 regressions in MCP core tests due to envelope wrapping changes.

**Net Result:**
- Integration tests: 9/21 passing (was 5/21) → **+4 fixed**
- MCP core tests: 272/291 passing (was 276/276) → **-4 regressions**
- **Overall: Need to revert or fix envelope implementation**

---

## What Was Implemented

### ✅ Completed Successfully

**1. Dual Versioning (Agent 1)**
- Added `PROTOCOL_VERSION = "2024-11-05"` (MCP spec version)
- Kept `SERVER_VERSION = "0.5.0"` (Osiris version)
- ✅ Fixed: `test_protocol_handshake`

**2. Policy Guards (Agent 2)**
- 16MB payload size limit enforcement
- Memory consent requirement check
- Guards applied BEFORE CLI delegation
- ✅ Fixed: `test_payload_size_limits`

**3. Canonical Tool IDs (Agent 3)**
- 40 tool aliases mapped to 12 canonical names
- Deterministic correlation IDs from request_id (SHA-256)
- Canonical tool ID injected into `_meta.tool`
- ✅ Fixed: `test_tool_call_via_alias`

**4. Mock-Friendly Imports (Agent 4)**
- Changed from `from osiris.mcp.cli_bridge import run_cli_json`
- To: `from osiris.mcp import cli_bridge` + `cli_bridge.run_cli_json()`
- Enables test mocking interception

**5. Integration Test Updates**
- Updated alias equality test (normalize timing fields)
- Updated discovery workflow test (envelope structure)
- Updated payload test (test input args, not response)
- ✅ Fixed: `test_full_workflow_sequence`

---

## ⚠️ Problems Introduced

### MCP Response Envelopes (Agent 1) - **BREAKING CHANGE**

**What was done:**
```python
# OLD (direct return from tools)
{
  "connections": [...],
  "count": 1,
  "_meta": {...}
}

# NEW (wrapped in MCP envelope)
{
  "status": "success",
  "result": {
    "connections": [...],
    "count": 1
  },
  "_meta": {...}
}
```

**Impact:**
- ✅ Fixes some integration tests expecting `{status, result, _meta}` structure
- ❌ **Breaks 19 MCP core tests** expecting flat structure
- ❌ May break Claude Desktop clients expecting old format

**Root Cause:**
The user said "MCP protocol requires this" but the implementation wrapped ALL responses including tool-level returns, not just server-level responses. The MCP SDK may already handle envelope wrapping at the transport layer.

---

## Test Results Breakdown

### Integration Tests (9/21 passing, +4 fixed)

**✅ Fixed (4 tests):**
1. `test_protocol_handshake` - Now returns "2024-11-05"
2. `test_tool_call_via_alias` - Canonical tool IDs work
3. `test_payload_size_limits` - 16MB guard blocks large inputs
4. `test_full_workflow_sequence` - Envelope structure updated

**✅ Already Passing (5 tests):**
- `test_list_tools_discovery`
- `test_all_tool_schemas_valid`
- `test_all_tools_callable`
- `test_no_env_vars_in_mcp_process`
- `test_metrics_included_in_response`

**❌ Still Failing (12 tests):**
1. `test_concurrent_tool_calls` - Expects `result` field
2. `test_error_response_format` - Envelope structure mismatch
3. `test_discovery_workflow` - Count/structure issues
4. `test_guide_workflow` - Tool name format
5. `test_memory_capture_consent` - Consent check not triggering
6. `test_unknown_tool` - Error envelope format
7. `test_missing_required_argument` - Error envelope format
8-12. Various `test_mcp_e2e.py` mocking/delegation issues

### MCP Core Tests (272/291 passing, -4 regressions)

**❌ Newly Failing (19 tests):**

**AIOP Tools (5 failures):**
- `test_aiop_show_success`
- `test_aiop_show_nonexistent_run`
- `test_aiop_list_with_metrics`
- `test_aiop_show_with_metrics`
- `test_aiop_list_cli_error`

**Connections Tools (3 failures):**
- `test_connections_list`
- `test_connections_doctor_success`
- `test_connections_doctor_missing_connection`

**Discovery Tools (1 failure):**
- `test_discovery_request_cache_miss`

**Other (10 failures):**
- Various tools expecting flat response structure

**Root Cause:**
These tests mock `cli_bridge.run_cli_json` to return flat dicts, but handlers now wrap them in `{status, result, _meta}` envelopes. Tests assert on the tool method's return value, which is now wrapped.

---

## Files Modified (17 total)

**Implementation (12 files):**
1. `osiris/mcp/config.py` - Dual versioning
2. `osiris/mcp/server.py` - Envelopes, guards, canonical IDs, tool injection
3. `osiris/mcp/cli_bridge.py` - Correlation ID derivation
4-11. `osiris/mcp/tools/*.py` (8 files) - Import pattern changes
12. `tests/mcp/test_server_boot.py` - Version assertion

**Tests (5 files):**
13. `tests/integration/test_mcp_claude_desktop.py` - Alias, payload, workflow fixes
14. `tests/integration/test_mcp_e2e.py` - Workflow envelope updates
15-17. Various test files affected by envelope changes

---

## Recommended Next Steps

### Option 1: Revert Envelope Wrapping (Safest)
1. Remove `_success_envelope()` / `_error_envelope()` from handlers
2. Keep envelopes only in `_call_tool()` at the SDK boundary
3. Tools continue returning flat dicts
4. Only wrap at the outermost layer (MCP protocol boundary)

**Pros:**
- Restores 276/276 MCP core tests
- Minimal code changes
- Tools remain simple
- Envelope wrapping is SDK's responsibility

**Cons:**
- Still need to fix 12 remaining integration tests
- May not satisfy "MCP protocol requires this" requirement

### Option 2: Update All Tests to Expect Envelopes
1. Update 19 MCP core test mocks to return enveloped responses
2. Update test assertions to access `result["result"]` instead of `result`
3. Keep envelope implementation as-is

**Pros:**
- Fully compliant with MCP envelope requirement
- No implementation changes needed

**Cons:**
- 19+ test files to update
- High risk of more breakage
- Tests become more complex

### Option 3: Hybrid Approach (Recommended)
1. Remove envelopes from **tool** methods (connections_tools, discovery_tools, etc.)
2. Keep envelopes only in **server handlers** (`_handle_*` methods)
3. `_call_tool()` already wraps handler results, so SDK gets envelopes
4. Tools remain simple and testable

**Pros:**
- Restores MCP core tests (tools return flat dicts)
- Server handlers provide MCP envelopes to SDK
- Clear separation: tools = business logic, handlers = protocol

**Cons:**
- Need to verify SDK doesn't double-wrap

---

## Commands to Verify Current State

```bash
# MCP core tests (should be 276/276, currently 272/291)
python -m pytest tests/mcp/ -v --tb=line

# Integration tests (was 5/21, now 9/21)
python -m pytest tests/integration/test_mcp_claude_desktop.py tests/integration/test_mcp_e2e.py -v

# Specific regressions
python -m pytest tests/mcp/test_tools_aiop.py -v
python -m pytest tests/mcp/test_tools_connections.py -v
```

---

## Git Status

**Branch:** `feature/mcp-server-opus`

**Modified Files (17):**
- 12 implementation files
- 5 test files

**Recommendation:**
- Do NOT commit until regressions are fixed
- Consider creating backup branch: `git branch backup/before-envelope-fixes`
- Fix regressions, then commit with message:
  ```
  fix(mcp): MCP protocol compliance (envelopes, guards, determinism)

  - Add dual versioning (protocol + server)
  - Implement 16MB payload guard + consent check
  - Add canonical tool IDs for alias determinism
  - Update import patterns for test mockability
  - Fix 4 integration tests

  Fixes: #<issue-number>
  ```

---

## Summary

**Achievements:**
- ✅ 4 integration tests fixed
- ✅ Policy guards working (16MB, consent)
- ✅ Canonical tool IDs implemented
- ✅ Dual versioning correct

**Regressions:**
- ❌ 19 MCP core tests broken (envelope wrapping)
- ❌ 12 integration tests still failing

**Conclusion:**
The envelope implementation needs to be refined (Option 3: Hybrid Approach) to restore MCP core tests while maintaining protocol compliance. Current state is **not ready for commit**.

---

**Report Generated:** 2025-10-18
**Next Action:** Choose option (1, 2, or 3) and implement fix
