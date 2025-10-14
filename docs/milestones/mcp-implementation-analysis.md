# MCP Implementation Status Analysis

**Date**: 2025-10-15
**Purpose**: Compare documented architecture vs. actual implementation

## Document Roles

1. **ADR-0036** (`docs/adr/0036-mcp-interface.md`)
   - **Role**: Architectural Decision - the WHY and WHAT
   - **Status**: ✅ Complete, documents the design decisions

2. **mcp-final.md** (`docs/milestones/mcp-final.md`)
   - **Role**: Milestone specification - what SHOULD be delivered
   - **Status**: ✅ Complete, describes the target state

3. **mcp-todo.md** (`docs/milestones/mcp-todo.md`)
   - **Role**: Implementation checklist - what NEEDS to be done
   - **Status**: ⚠️ CRITICAL - contains actual work items

## Implementation Gap Analysis

### ✅ DONE (Currently Working)
- Tool naming changed to underscores (`connections_list`, etc.)
- Basic MCP server runs and responds
- Alias system for backward compatibility
- CLI subcommands structure (`mcp run`, `mcp clients`, `mcp tools`)
- OSIRIS_HOME resolution logic

### ❌ NOT DONE (Critical Gaps)

#### 1. CLI-First Adapter (Section 9 in mcp-todo.md)
**Status**: DOCUMENTED but NOT IMPLEMENTED

| Component | Expected | Actual |
|-----------|----------|--------|
| `cli_bridge.py` | Delegates to CLI | **Does not exist** |
| Tool implementation | Calls CLI via subprocess | Directly calls `load_connections_yaml()` |
| Secrets handling | CLI process resolves | MCP expects env vars |
| Connection resolution | Via `osiris connections list --json` | Direct config file access |

**Evidence**:
```python
# Current (WRONG):
connections = load_connections_yaml()  # Expects env vars

# Should be:
result = await cli_bridge.run_cli_json(['connections', 'list'])
```

#### 2. Config-First Paths (Section 1 in mcp-todo.md)
**Status**: NOT IMPLEMENTED

| Requirement | Status |
|-------------|--------|
| `filesystem.mcp_logs_dir` in config | ❌ Missing |
| `osiris init` writes MCP config | ❌ Not updated |
| Server reads from config | ❌ Uses hardcoded paths |
| Logs go to `<base_path>/.osiris/mcp/logs` | ❌ Ad-hoc session directories |

#### 3. Dogfood CLI (Section 2 in mcp-todo.md)
**Status**: PARTIALLY WRONG

Current `mcp clients` output:
```json
"args": ["-lc", "cd /path && exec python -m osiris.cli.mcp_entrypoint"]
```

Should be:
```json
"args": ["-lc", "cd /path && exec python osiris.py mcp run"]
```

## Why mcp-todo.md is Essential

**mcp-todo.md should be KEPT** because it contains:

1. **Concrete implementation tasks** not in other docs
2. **Verification commands** to test each feature
3. **Acceptance criteria** for each component
4. **The actual work breakdown** needed to complete v0.5.0

## Missing Items to Add to mcp-todo.md

Based on the gap analysis, these should be added:

### Section 10: Missing CLI Commands for MCP Delegation

```markdown
## 10) Add missing CLI commands for MCP tool delegation

- [ ] `osiris discovery request --connection <id> --component <id> --json` (NEW)
- [ ] `osiris oml schema --json` (NEW)
- [ ] `osiris guide start --context <file> --json` (NEW)
- [ ] `osiris memory capture --session <id> --json` (NEW)
- [ ] `osiris usecases list --json` (NEW)
```

### Section 11: Test Coverage for CLI Bridge

```markdown
## 11) Test coverage for CLI delegation

- [ ] `tests/mcp/test_cli_bridge.py` - Core bridge functionality
- [ ] `tests/mcp/test_no_env_scenario.py` - Verify works without env vars
- [ ] Update all `tests/mcp/test_tools_*.py` to expect delegation
```

## Recommendation

1. **KEEP mcp-todo.md** - It's the actual work plan
2. **UPDATE mcp-todo.md** - Add sections 10-11 for missing CLI commands and tests
3. **TRACK PROGRESS** - Check off items as they're completed
4. **RENAME** (optional) - Consider renaming to `mcp-v0.5.0-implementation.md` to clarify it's the implementation plan

## Summary

The three documents serve different essential purposes:
- **ADR-0036**: The architectural decision (WHY) ✅
- **mcp-final.md**: The target state (WHAT) ✅
- **mcp-todo.md**: The implementation plan (HOW) ⚠️ **NEEDED**

Without mcp-todo.md, there's no concrete plan to bridge the gap between the documented architecture and the actual implementation. The CLI-first adapter is currently just an idea on paper - the real work is in mcp-todo.md.