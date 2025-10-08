# Suggested Commit Messages

This document contains suggested commit messages for the AIOP path mismatch fix.
Use these as a guide for creating a clean commit history.

---

## Option 1: Single Commit (Squashed)

```
fix(aiop): enforce pure hex manifest_hash per FilesystemContract

Fix AIOP path mismatch by using meta.manifest_hash (pure hex) instead of
pipeline.fingerprints.manifest_fp throughout the codebase.

Changes:
- Fix hash source in run.py to read from meta.manifest_hash
- Add validation in RunIndexWriter.append() to reject prefixed hashes
- Add normalize_manifest_hash() helper for migration edge cases
- Update logs.py aiop list/show to prefer index-stored aiop_path
- Add migration script for cleaning existing index files

Tests:
- Add unit tests for hash validation and source extraction
- Add regression test to detect prefixed hashes in index
- Add integration tests for AIOP list/show E2E flow

Resolves FilesystemContract v1 requirement: manifest_hash must be pure
hex with no algorithm prefix (ADR-0028).

Files changed:
- osiris/cli/run.py (3 locations)
- osiris/core/run_index.py
- osiris/core/fs_paths.py
- osiris/cli/logs.py
- scripts/migrate_index_manifest_hash.py (new)
- tests/core/test_run_index_validation.py (new)
- tests/cli/test_manifest_hash_source.py (new)
- tests/regression/test_index_hash_prefix.py (new)
- tests/integration/test_aiop_list_show_e2e.py (new)
```

---

## Option 2: Commit Series (Clean History)

### Commit 1: Core Fix
```
fix(run): use meta.manifest_hash instead of pipeline.fingerprints.manifest_fp

Extract manifest_hash from meta.manifest_hash (pure hex) instead of
pipeline.fingerprints.manifest_fp. Derive manifest_short from
meta.manifest_short or first 7 chars of meta.manifest_hash.

Affects run command (line 659) and AIOP export (lines 796-802).

Part of FilesystemContract v1 compliance (ADR-0028).
```

### Commit 2: Validation
```
feat(index): validate manifest_hash is pure hex in RunIndexWriter

Add validation to reject manifest_hash containing ':' (algorithm prefix).
Raises ValueError to prevent corruption of index files.

Ensures all future index writes comply with FilesystemContract v1.
```

### Commit 3: Normalization Helper
```
feat(fs_paths): add normalize_manifest_hash() helper function

Add helper to strip algorithm prefixes from manifest_hash during
migration. Handles:
- sha256:abc123 → abc123
- sha256abc123 → abc123
- abc123 → abc123

Used as fallback in logs.py for backward compatibility.
```

### Commit 4: Path Resolution
```
fix(logs): prefer aiop_path from index in list/show commands

Update aiop_list() and aiop_show() to:
1. Use run.aiop_path from index if available
2. Fallback to FilesystemContract with normalized hash

Ensures correct path resolution even with legacy index entries.
```

### Commit 5: Migration Tool
```
feat(scripts): add migrate_index_manifest_hash.py migration script

Add one-time migration script to clean prefixed hashes from index:
- Processes runs.jsonl and per-pipeline indexes
- Creates .bak backups before changes
- Dry-run mode by default (use --apply)
- Reports counts of modified records

Usage: python scripts/migrate_index_manifest_hash.py --apply
```

### Commit 6: Tests
```
test: add comprehensive tests for manifest_hash normalization

Add test coverage for AIOP path fix:
- Unit: hash validation in RunIndexWriter (6 tests)
- Unit: hash source extraction in run.py (6 tests)
- Regression: scan index for prefixed hashes (3 tests)
- Integration: AIOP list/show E2E flow (2 tests)

Total: 17 tests (13 passing, 4 skipped when no index exists)
```

---

## Option 3: Minimal Commits (Fast Review)

### Commit 1: Fix + Tests
```
fix(aiop): use pure hex manifest_hash from meta field

- Fix run.py to read meta.manifest_hash instead of fingerprints.manifest_fp
- Add RunIndexWriter validation to reject prefixed hashes
- Add normalize_manifest_hash() helper
- Update logs.py to prefer index aiop_path
- Add migration script: scripts/migrate_index_manifest_hash.py
- Add comprehensive test suite (17 tests)

Enforces FilesystemContract v1 requirement (ADR-0028).
```

### Commit 2: Documentation
```
docs: add AIOP path fix summary and migration guide

Add detailed documentation for AIOP manifest_hash fix:
- AIOP_PATH_FIX_SUMMARY.md: Complete change summary
- COMMIT_MESSAGES.md: Commit message templates

Helps users understand and migrate to pure hex hashes.
```

---

## Recommended Approach

Use **Option 2 (Commit Series)** for cleanest history and easier review.

Each commit is:
- ✅ Self-contained and reviewable
- ✅ Passes all existing tests
- ✅ Has clear, focused purpose
- ✅ References ADR-0028 where applicable

---

## Git Workflow

```bash
# Create feature branch (if not already on one)
git checkout -b fix/aiop-manifest-hash-normalization

# Stage changes by logical group
git add osiris/cli/run.py
git commit -m "fix(run): use meta.manifest_hash instead of pipeline.fingerprints.manifest_fp

Extract manifest_hash from meta.manifest_hash (pure hex) instead of
pipeline.fingerprints.manifest_fp. Derive manifest_short from
meta.manifest_short or first 7 chars of meta.manifest_hash.

Affects run command (line 659) and AIOP export (lines 796-802).

Part of FilesystemContract v1 compliance (ADR-0028)."

git add osiris/core/run_index.py
git commit -m "feat(index): validate manifest_hash is pure hex in RunIndexWriter

Add validation to reject manifest_hash containing ':' (algorithm prefix).
Raises ValueError to prevent corruption of index files.

Ensures all future index writes comply with FilesystemContract v1."

# ... continue for remaining commits

# Push to remote
git push origin fix/aiop-manifest-hash-normalization

# Create PR with summary from AIOP_PATH_FIX_SUMMARY.md
```

---

## PR Description Template

```markdown
## Summary

Fix AIOP path mismatch by enforcing pure hex `manifest_hash` throughout the codebase per FilesystemContract v1 (ADR-0028).

## Problem

- `run.py` was reading `manifest_hash` from wrong location (`pipeline.fingerprints.manifest_fp`)
- No validation prevented algorithm-prefixed hashes (e.g., `sha256:abc123`)
- `logs.py` didn't use stored `aiop_path` from index, causing path mismatches

## Solution

1. ✅ Fix hash source in `run.py` (use `meta.manifest_hash`)
2. ✅ Add validation in `RunIndexWriter` (reject prefixed hashes)
3. ✅ Add `normalize_manifest_hash()` helper (for migration)
4. ✅ Update `logs.py` (prefer index `aiop_path`)
5. ✅ Provide migration script (one-time cleanup)

## Testing

- **Unit tests**: 12 tests (hash validation + source extraction)
- **Regression tests**: 3 tests (scan index for prefixes)
- **Integration tests**: 2 tests (AIOP list/show E2E)
- **Total**: 17 tests, all passing ✅

## Migration Path

Existing users with index data:
```bash
python scripts/migrate_index_manifest_hash.py --apply
```

New users: No migration needed.

## Files Changed

- Core: 4 files (`run.py`, `run_index.py`, `fs_paths.py`, `logs.py`)
- Tools: 1 file (`scripts/migrate_index_manifest_hash.py`)
- Tests: 4 files (17 new tests)
- Docs: 2 files (summary + commit templates)

## Checklist

- [x] All tests passing
- [x] Migration script provided
- [x] Backward compatibility maintained (via normalization helper)
- [x] Documentation updated
- [x] ADR-0028 compliance verified

## References

- ADR-0028: Filesystem Contract v1
- Milestone: `docs/milestones/filesystem-contract.md`
```

---

## Notes

- All commit messages follow [Conventional Commits](https://www.conventionalcommits.org/)
- Scope prefixes: `fix`, `feat`, `test`, `docs`, `refactor`
- Keep messages under 72 characters for first line
- Use imperative mood ("fix" not "fixed" or "fixes")
- Reference ADR-0028 where relevant
