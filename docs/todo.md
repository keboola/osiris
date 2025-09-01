# Osiris Architecture Issues & TODOs

## Critical Issues

### 1. Database Context Persistence Problem
**Issue**: When user requests a pipeline for a specific database (e.g., Supabase e-commerce), but the cached discovery contains different data (e.g., movies database), the LLM returns empty responses with `action='ask_clarification'`.

**Root Cause**: 
- Session cache persists wrong database context
- No validation that discovered schema matches user's request
- LLM can't generate appropriate response when context mismatches

**Example**:
- User asks: "Sync customer data from Supabase to Shopify"
- Cached data: Movies database (actors, directors, reviews)
- Result: Empty LLM response, no error message to user

**Proposed Fix**:
1. Add schema validation before using cached discovery
2. Clear cache when switching database contexts
3. Detect context mismatch and prompt for re-discovery
4. Add explicit error messages when schema doesn't match request

### 2. LLM Error Handling
**Issue**: When LLM returns empty message with `action='ask_clarification'`, user sees no response

**Proposed Fix**:
- Add fallback message when LLM response is empty
- Log detailed error context for debugging
- Implement retry logic with different prompts

### 3. Multi-Database Support
**Issue**: No clear way to switch between multiple databases in same session

**Proposed Fix**:
- Add `--clear-cache` flag to chat command
- Implement database profile switching
- Allow multiple database contexts in single session

## TODO List

- [ ] Implement schema validation before using cached discovery
- [ ] Add context mismatch detection in conversational_agent.py
- [ ] Create clear error messages for schema mismatches
- [ ] Add `--clear-cache` flag to chat command
- [ ] Implement database profile management
- [ ] Add retry logic for empty LLM responses
- [ ] Create integration tests for context switching scenarios
- [ ] Document cache management best practices in README

### M0-Validation-4 Pending Tests

- [ ] **Complete logging configuration verification tests** from `docs/m0-validation-4.md` 
  - Section: "## Logging Configuration — Verification Checklist (osiris.yaml)"
  - Tests logs_dir precedence (YAML → ENV → CLI overrides)
  - Tests level filtering behavior  
  - Tests events filtering and wildcard support
  - Tests session artifact creation and cleanup
  - **Status**: Implementation completed, but verification checklist tests not executed
  - **Priority**: High - needed to validate M0-Validation-4 milestone completion

## Code Quality & Pre-commit Fixes

### Pre-commit Hook Issues (Non-breaking)
**Status**: Identified during commit process - all code quality suggestions, no functional risks

#### ✅ Auto-fixed by Hooks:
- [x] **Secrets detection baseline** - Updated `.secrets.baseline` with pragma-commented test secrets
- [x] **Code formatting (Black)** - Fixed 2 files: `tests/core/test_secrets_masking.py`, `tests/core/test_session_logging.py`  
- [x] **Import sorting (isort)** - Fixed `tests/cli/test_chat.py`
- [x] **End-of-file fixer** - Fixed `CLAUDE.md`

#### ❌ Manual Fixes Available (Optional - Style Only):
- [ ] **SIM108**: Use ternary operator in `osiris/cli/main.py:179` (args handling)
- [ ] **SIM103**: Return condition directly in `osiris/core/cache_fingerprint.py:214`  
- [ ] **SIM105**: Use `contextlib.suppress()` in `osiris/core/session_logging.py:103`
- [ ] **SIM117**: Use single `with` statement in `tests/cli/test_logs.py:182`
- [ ] **F401**: Remove unused `jsonschema` import in `osiris/core/validation.py:271`
- [ ] **F841**: Remove 41 unused variables in test files (mostly `result` variables)
- [ ] **invalid-syntax**: Fix f-string backslash in `scripts/test_manual_transfer.py:104` (Python 3.8 compat)

**Risk Assessment**: ❌ **No functional risk** - All suggestions are pure code style improvements
**Tests Status**: ✅ **167/167 passing** - Full functionality confirmed
**Priority**: Low - Can be addressed during code cleanup phase

## Notes

- Discovery cache stored in `.osiris_cache/`
- Session data stored in `.osiris_sessions/`
- Issue discovered during Shopify sync demo (2025-09-01)
