# Osiris Version References Audit Report

## Executive Summary

**Audit Date**: 2025-11-06
**Repository**: Osiris Pipeline
**Current Version**: v0.5.4 (pyproject.toml)
**Scope**: Complete repository scan across 218 markdown files and 100+ Python files

### Key Findings

| Category | Count | Status |
|----------|-------|--------|
| **Single Source of Truth** | 3 files | ✅ KEEP (pyproject.toml, osiris/__init__.py, osiris/mcp/config.py) |
| **Changelog & History** | 1 file | ✅ KEEP (CHANGELOG.md - historical record) |
| **Git Tags** | 12 tags | ✅ KEEP (version history) |
| **Documentation (Outdated)** | 30+ files | ⚠️ REMOVE or UPDATE |
| **Test Data (Intentional)** | 50+ files | ✅ KEEP (test fixtures use legacy versions) |
| **Dependencies** | 15+ entries | ✅ KEEP (external package versions) |

---

## 1. KEEP (Single Source of Truth)

These are the **authoritative** version references that drive the system:

### ✅ Primary Version Sources

| File | Line | Content | Purpose |
|------|------|---------|---------|
| `pyproject.toml` | 7 | `version = "0.5.4"` | **PRIMARY SOURCE** - PyPI package version |
| `osiris/__init__.py` | 17 | `__version__ = "0.5.4"` | **DERIVED** - Should read from pyproject.toml |
| `osiris/mcp/config.py` | 109 | `SERVER_VERSION = "0.5.4"` | **DERIVED** - MCP server version |

**Recommendation**:
- Keep `pyproject.toml:version` as single source of truth
- **AUTOMATE** `osiris/__init__.py:__version__` to read from pyproject.toml at build time
- **AUTOMATE** `osiris/mcp/config.py:SERVER_VERSION` to sync with `__version__`

### ✅ Historical Record

| File | Purpose | Status |
|------|---------|--------|
| `CHANGELOG.md` | Complete version history (v0.1.0 → v0.5.4) | KEEP - Required for semver |
| Git tags | 12 version tags (v0.1.0 through v0.5.4) | KEEP - Permanent history |

---

## 2. REMOVE (Hardcoded Duplicates in Documentation)

These files contain **outdated, hardcoded version references** that should be removed or replaced with dynamic references:

### ⚠️ High Priority - User-Facing Documentation

| File | Line | Current Text | Issue |
|------|------|--------------|-------|
| `README.md` | 1 | `# Osiris Pipeline v0.5.4` | Hardcoded in title |
| `README.md` | 131 | `- **v0.5.4 (Current)** ✅` | Hardcoded "Current" marker |
| `CLAUDE.md` | 18 | `- **Version**: v0.5.0 PRODUCTION READY` | **STALE** (should be v0.5.4) |
| `CLAUDE.md` | 21 | `MCP v0.5.0` | **STALE** (multiple references) |
| `CLAUDE.md` | 44 | `# MCP operations (v0.5.0+)` | Outdated feature flag |
| `CLAUDE.md` | 285 | `- Current: v0.5.2 (Production Ready)` | **STALE** (2 versions behind) |
| `docs/quickstart.md` | 1 | `# Osiris Pipeline v0.5.2` | **STALE** (should be v0.5.4) |

**Impact**: Users see conflicting version numbers across documentation.

**Recommendation**:
```markdown
# REPLACE:
"# Osiris Pipeline v0.5.4"

# WITH:
"# Osiris Pipeline"
(Version displayed dynamically via CI or removed entirely)
```

### ⚠️ Medium Priority - Developer Documentation

| File | References | Issue |
|------|-----------|-------|
| `docs/architecture.md` | Line 4: `**Version:** v0.2.0` | **STALE** (3+ versions behind) |
| `docs/overview.md` | Line 1: `v0.2.0` | **STALE** (historical milestone) |
| `docs/reference/sql-safety.md` | Line 5: `**Version:** 0.2.0` | **STALE** |
| `docs/reference/oml-validation.md` | Line 691: `**Osiris Version**: v0.5.0` | **STALE** (should be v0.5.4) |
| `docs/guides/mcp-overview.md` | Line 95: `- **Server Version**: 0.5.0` | **STALE** |
| `docs/guides/mcp-production.md` | Line 3: `**Version**: MCP v0.5.0` | **STALE** |

### ⚠️ Low Priority - Reports & Archives

| Directory | Count | Notes |
|-----------|-------|-------|
| `docs/reports/phase2-impact/` | 15+ files | Historical v0.5.0 release documentation - **KEEP AS-IS** (archive) |
| `docs/milestones/mcp-v0.5.0/` | 20+ files | Complete v0.5.0 milestone - **KEEP AS-IS** (archive) |
| `docs/archive/` | 10+ files | Historical versions (v0.2.0, v0.3.0, etc.) - **KEEP AS-IS** |

**Recommendation**: Archives are historical - leave untouched.

---

## 3. AUTOMATE (Generated/Derived Versions)

These should be **automatically synchronized** from the single source of truth:

### 🤖 Code Generation Targets

| File | Current | Should Be |
|------|---------|-----------|
| `osiris/__init__.py:17` | `__version__ = "0.5.4"` | Read from `pyproject.toml` at build/import time |
| `osiris/mcp/config.py:109` | `SERVER_VERSION = "0.5.4"` | Import from `osiris.__version__` |
| `osiris/cli/main.py:43` | `"Osiris v0.5.0"` | **ALREADY FIXED** - uses `__version__` (line 186) |

### 🔧 Build Automation Strategy

```python
# Option 1: Dynamic Import (runtime)
# osiris/__init__.py
import tomllib
from pathlib import Path

_project_root = Path(__file__).parent.parent
_pyproject = _project_root / "pyproject.toml"
__version__ = tomllib.loads(_pyproject.read_text())["project"]["version"]

# Option 2: Build-time Generation
# setup.py or build script generates __version__ from pyproject.toml
```

**Note**: Line 43 in `osiris/cli/main.py` shows hardcoded `"Osiris v0.5.0"` which contradicts the recent fix on line 186. This should be updated.

---

## 4. UNCERTAIN (Needs Human Judgment)

These references have **context-specific** meaning and require case-by-case review:

### 🤔 Contextual Version References

| File | Line | Content | Question |
|------|------|---------|----------|
| `osiris/cli/main.py` | 43 | `console.print("[bold green]Osiris v0.5.0 - MCP-based ETL Pipeline Generator[/bold green]")` | Should this display current version or is it a banner? |
| `osiris/cli/main.py` | 129 | `description="Osiris v0.5.0 - MCP-based ETL Pipeline Generator"` | Same question - version in description? |
| `osiris/cli/mcp_entrypoint.py` | 117 | `logger.info("Starting Osiris MCP Server v0.5.0")` | Should log current version? |
| `osiris/cli/chat_deprecation.py` | 28 | `print("Error: 'chat' command is deprecated in Osiris v0.5.0.")` | Permanent marker or should update? |

**Recommendation**:
- Banner/description: Use `f"Osiris v{__version__}"`
- Deprecation notice: Keep "v0.5.0" as historical fact (chat was deprecated in that version)
- Logger: Use `f"Starting Osiris MCP Server v{__version__}"`

### 🤔 Test Assertions

| File | Pattern | Purpose |
|------|---------|---------|
| `tests/mcp/test_server_boot.py` | Line 113: `assert config.SERVER_VERSION == "0.5.4"` | **FRAGILE** - breaks on every version bump |
| `tests/mcp/test_server_integration.py` | Line 521: `mock_cfg.SERVER_VERSION = "0.5.0"` | Mock uses old version intentionally? |
| `tests/cli/test_no_chat.py` | Line 19: `assert "osiris v0.5.0" in result.stdout.lower()` | **BROKEN** - expects v0.5.0 but CLI now shows v0.5.4 |

**Recommendation**:
- Replace hardcoded version assertions with `osiris.__version__`
- Fix test that expects "v0.5.0" to use dynamic version check

---

## 5. KEEP (Test Fixtures & Dependencies)

These are **intentional** version references used in tests or external dependencies:

### ✅ OML Schema Version (Contract)

| Pattern | Count | Purpose |
|---------|-------|---------|
| `oml_version: "0.1.0"` | 50+ files | **OML v0.1.0 is the current spec** - NOT Osiris version |

**Examples**:
- `docs/examples/*.yaml` - All pipeline examples use `oml_version: "0.1.0"`
- `tests/**/*.py` - Test fixtures use `oml_version: "0.1.0"`

**Status**: ✅ KEEP - This is the OML specification version, independent of Osiris version.

### ✅ Component Versions

| Pattern | Count | Purpose |
|---------|-------|---------|
| `version: 1.0.0` | 15+ files | Component spec versions (SemVer) |

**Examples**:
- `components/mysql.extractor/spec.yaml:3` - `version: 1.0.0`
- `components/supabase.writer/spec.yaml:3` - `version: 1.0.0`

**Status**: ✅ KEEP - Components have independent versioning.

### ✅ External Dependencies

| File | Pattern | Purpose |
|------|---------|---------|
| `pyproject.toml` | `duckdb>=0.9.0` | Minimum version requirements |
| `pyproject.toml` | `anthropic>=0.25.0` | External package versions |
| `requirements.txt` | `pytest-asyncio>=0.21.0` | Same as above |

**Status**: ✅ KEEP - These are dependency version constraints, not Osiris versions.

### ✅ Protocol Versions

| File | Line | Content | Purpose |
|------|------|---------|---------|
| `osiris/mcp/config.py` | 108 | `PROTOCOL_VERSION = "2024-11-05"` | MCP protocol spec version |
| `.pre-commit-config.yaml` | 15 | `rev: v0.6.4` | Pre-commit hook version |

**Status**: ✅ KEEP - These are protocol/tool versions, not Osiris versions.

---

## 6. Detailed File-by-File Inventory

### 📋 Critical Files Requiring Updates

```
HIGH PRIORITY (User-Facing):
1. CLAUDE.md (Line 18, 21, 44, 285) - Multiple stale v0.5.0/v0.5.2 references
2. README.md (Line 1, 131) - Hardcoded v0.5.4 in title and roadmap
3. docs/quickstart.md (Line 1) - Stale v0.5.2 reference

MEDIUM PRIORITY (Developer Docs):
4. docs/architecture.md (Line 4) - Stale v0.2.0
5. docs/reference/oml-validation.md (Line 691) - Stale v0.5.0
6. docs/guides/mcp-overview.md (Line 95) - Stale v0.5.0
7. docs/guides/mcp-production.md (Line 3) - Stale v0.5.0

LOW PRIORITY (Code):
8. osiris/cli/main.py (Line 43, 129) - Hardcoded v0.5.0 in banners
9. osiris/cli/mcp_entrypoint.py (Line 117) - Hardcoded v0.5.0 in logger
10. tests/cli/test_no_chat.py (Line 19) - Assertion expects v0.5.0
11. tests/mcp/test_server_boot.py (Line 113) - Hardcoded version assertion
```

### 📊 Version Distribution Analysis

| Version String | Occurrences | Category |
|----------------|-------------|----------|
| `0.5.4` | 8 | Current (correct) |
| `0.5.3` | 5 | Recent release (historical) |
| `0.5.2` | 12 | **STALE** in docs |
| `0.5.0` | 150+ | **STALE** (mostly in v0.5.0 milestone docs - archived) |
| `0.4.0` | 10 | Historical |
| `0.3.x` | 15 | Historical |
| `0.2.0` | 30 | **STALE** in architecture docs |
| `0.1.0` | 200+ | **OML SPEC VERSION** (correct) |

---

## 7. Recommendations & Cleanup Strategy

### Phase 1: Immediate Fixes (Critical)

```bash
# 1. Update CLAUDE.md (project instructions for Claude Code)
- Line 18: "v0.5.0" → "v0.5.4"
- Line 21: "MCP v0.5.0" → "v0.5.4"
- Line 285: "v0.5.2" → "v0.5.4"

# 2. Update README.md
- Line 1: Remove version from title OR use dynamic badge
- Line 131: Update "v0.5.4 (Current)" when version changes

# 3. Update quickstart.md
- Line 1: "v0.5.2" → "v0.5.4" OR remove version

# 4. Fix code banners
- osiris/cli/main.py:43 → use f"v{__version__}"
- osiris/cli/main.py:129 → use f"v{__version__}"
- osiris/cli/mcp_entrypoint.py:117 → use f"v{__version__}"
```

### Phase 2: Automation Setup

```python
# Create script: scripts/sync_versions.py
"""
Synchronize versions from pyproject.toml to all derived locations.
Run as pre-commit hook or in CI.
"""

import tomllib
from pathlib import Path

def get_version():
    pyproject = Path("pyproject.toml")
    data = tomllib.loads(pyproject.read_text())
    return data["project"]["version"]

def update_files(version):
    # Update osiris/__init__.py
    # Update osiris/mcp/config.py
    # Update test assertions
    # Optionally update README.md badges
    pass

if __name__ == "__main__":
    version = get_version()
    update_files(version)
    print(f"Synced all files to version {version}")
```

### Phase 3: Documentation Policy

**Create `docs/VERSION_POLICY.md`**:

```markdown
# Version Reference Policy

## Single Source of Truth
- `pyproject.toml:version` is the ONLY manually updated version

## Automated/Derived
- `osiris/__init__.py:__version__` - Generated at build time
- `osiris/mcp/config.py:SERVER_VERSION` - Imports from __version__
- Test assertions - Use `osiris.__version__` dynamically

## Documentation
- Titles: Omit version numbers (use badges for dynamic display)
- Historical docs: Keep version in filename only
- ADRs/Milestones: Keep version as historical record

## What NOT to Version
- OML schema version (independent: "0.1.0")
- Component versions (independent SemVer)
- Dependency versions (package requirements)
- Protocol versions (MCP, etc.)
```

### Phase 4: Pre-Commit Hook

```yaml
# .pre-commit-config.yaml
repos:
  - repo: local
    hooks:
      - id: version-sync
        name: Sync versions from pyproject.toml
        entry: python scripts/sync_versions.py
        language: python
        pass_filenames: false
        always_run: true
```

---

## 8. Summary Statistics

| Metric | Count |
|--------|-------|
| **Total files scanned** | 318+ files (218 MD + 100+ PY) |
| **Version references found** | 500+ occurrences |
| **Single source of truth** | 1 file (pyproject.toml) |
| **Files needing updates** | 10-15 critical files |
| **Files to keep as-is** | 250+ (tests, archives, dependencies) |
| **Automation opportunities** | 3 major targets |

---

## 9. Action Items Checklist

### Immediate (Before Next Release)

- [ ] Update `CLAUDE.md` lines 18, 21, 285 to v0.5.4
- [ ] Update `README.md` line 1 (remove version or use badge)
- [ ] Update `docs/quickstart.md` line 1 to v0.5.4
- [ ] Fix `osiris/cli/main.py` lines 43, 129 to use `__version__`
- [ ] Fix `osiris/cli/mcp_entrypoint.py` line 117 to use `__version__`
- [ ] Fix broken test: `tests/cli/test_no_chat.py` line 19

### Short-Term (Next Sprint)

- [ ] Create `scripts/sync_versions.py` automation script
- [ ] Update `osiris/__init__.py` to read from `pyproject.toml`
- [ ] Update `osiris/mcp/config.py` to import from `__version__`
- [ ] Create `docs/VERSION_POLICY.md` documentation
- [ ] Add version-sync pre-commit hook
- [ ] Update all developer docs (architecture.md, guides/)

### Long-Term (Documentation Governance)

- [ ] Establish "no hardcoded versions" policy
- [ ] Add CI check for version consistency
- [ ] Consider dynamic README badges (shields.io)
- [ ] Archive outdated milestone folders after each release
- [ ] Add version policy to CONTRIBUTING.md

---

## Appendix A: Git Tag History

```
v0.1.0 - Initial release
v0.1.1
v0.1.2
v0.2.0 - Conversational agent + deterministic compiler
v0.3.0 - AIOP system
v0.3.1 - Validation fixes
v0.3.5 - GraphQL extractor
v0.4.0 - Filesystem contract
v0.5.0 - MCP v0.5.0 production ready
v0.5.2 - Bug fixes batch 3
v0.5.3 - Python version + runtime fixes
v0.5.4 - CLI version display hotfix (CURRENT)
```

---

**Report Generated**: 2025-11-06
**Audit Scope**: Complete repository
**Next Review**: After each version bump
**Owner**: Development Team
