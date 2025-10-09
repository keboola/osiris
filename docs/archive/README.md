# Archive (Deprecated / Historical Docs)

## Purpose

This folder contains deprecated, superseded, or historical documentation that is kept for reference only. These files are **not part of the current developer workflow** and should not be linked from human or AI guides. The content here has been replaced by the restructured documentation in `docs/developer-guide/human/` and `docs/developer-guide/ai/`.

---

## Policy

- **No new content** should be authored in this directory
- Files placed here are **out of date** or have been **replaced** by current documentation
- **Don't cross-link** from active docs; link only when documenting migration history
- This directory is **not indexed** by CI, build tools, or AI routers

---

## What's In This Archive

### Developer Module Documentation (Legacy)
**Replaced by**: `docs/developer-guide/human/modules/`

- `module-cli.md` - CLI commands and patterns
- `module-components.md` - Component Registry & validation
- `module-connectors.md` - Connection management
- `module-core.md` - LLM agent & compilation
- `module-drivers.md` - Driver protocol
- `module-remote.md` - E2B cloud execution
- `module-runtime.md` - Local execution

### LLM Contracts (Legacy)
**Replaced by**: `docs/developer-guide/ai/llms/` and `docs/developer-guide/ai/checklists/`

- `llms.txt` - Main LLM development contract
- `llms-cli.txt` - CLI development patterns
- `llms-drivers.txt` - Driver implementation patterns
- `llms-e2b.txt` - E2B cloud execution patterns
- `llms-testing.txt` - Test writing patterns

### Developer Guide (Legacy Structure)
**Replaced by**: Current `docs/developer-guide/` structure

- `developer-guide/adapters.md` - Execution adapter patterns
- `developer-guide/components.md` - Component development
- `developer-guide/discovery.md` - Database discovery patterns
- `developer-guide/extending.md` - Extension guide

### Concepts & Architecture (Legacy)

- `CONCEPTS.md` - Core concepts guide (replaced by current architecture docs)
- `component-interfaces.md` - Old component interface notes
- `e2b-runtime.md` - DataFrame lifecycle in E2B
- `repository-structure.md` - Old repository structure documentation

### Historical Planning Documents

- `dev-plan.md` - Original development plan
- `seznam-pitch-cz.md` - Czech pitch document

### Milestones (Historical - Pre v0.4.0)
**Replaced by**: `docs/roadmap/` and completed milestones in `docs/milestones/`

**Completed Milestones:**
- `milestones/m0-discovery-cache.md` - M0 Discovery cache (shipped)
- `milestones/m0-session-logs.md` - M0 Session logging (shipped)
- `milestones/m1-component-registry-and-runner.md` - M1 Component Registry (shipped in v0.2.0)
- `milestones/m1a.1-component-spec-schema.md` - M1a.1 Component spec schema (shipped)
- `milestones/m1a.2-bootstrap-component-specs.md` - M1a.2 Bootstrap specs (shipped)
- `milestones/m1a.3-component-registry.md` - M1a.3 Registry implementation (shipped)
- `milestones/m1a.4-friendly-error-mapper.md` - M1a.4 Error mapping (shipped)
- `milestones/m1b-context-builder-and-validation.md` - M1b LLM context (shipped)
- `milestones/m1c-compile-and-run-mvp.md` - M1c Compiler/runner (shipped)
- `milestones/m1c-thin-slice.md` - M1c Thin slice implementation (shipped)
- `milestones/m1d-logs-and-cli-unification.md` - M1d CLI unification (shipped)
- `milestones/m1d_logs_browser.md` - M1d HTML logs (shipped)
- `milestones/m1e-e2b-runner.md` - M1e E2B runner (shipped)
- `milestones/m1f-e2b-proxy.md` - M1f E2B transparent proxy (shipped in v0.2.0)
- `milestones/m2a-aiop.md` - M2a AI Operation Package (shipped in v0.3.0)
- `milestones/filesystem-contract.md` - Filesystem Contract v1 (shipped in v0.4.0)

**Planning Documents:**
- `milestones/0.x-initial-plan.md` - Initial project planning
- `milestones/0.x-m1c-ideas.md` - M1c brainstorming
- `milestones/_initial_plan.md` - Early project structure
- `milestones/milestone-m1-actual-report.md` - M1 completion report
- `milestones/reports/m0-validation-4-test-report.md` - M0 validation report
- `milestones/reports/planning-audit-20250909.md` - Planning audit

---

## How to Restore

If you need to revive content from this archive:

1. **Prefer rewriting** - Match current contracts and checklists rather than copying old content
2. **Move back carefully** - Place under `docs/developer-guide/human/` or `docs/developer-guide/ai/` with focused scope
3. **Update all links** - Ensure relative paths resolve correctly
4. **Validate compliance** - New content must align with:
   - `docs/developer-guide/ai/checklists/COMPONENT_AI_CHECKLIST.md`
   - `docs/developer-guide/ai/llms/overview.md`
   - Current module documentation in `human/modules/`

**Best practice**: Treat archived content as reference material for rewriting, not direct reuse.

---

## Out of Scope

- ❌ CI/CD pipelines do **not** read this directory
- ❌ Not referenced by `BUILD_A_COMPONENT.md`
- ❌ Not indexed by AI routers (`ai/README.md`)
- ❌ Not part of user-facing documentation

---

## Migration History

### 2025-10-09: Filesystem Contract v1 (v0.4.0)
**ADR-0028 Implementation Complete**
- All legacy `logs/` path references removed from production code
- New directory structure: `build/`, `run_logs/`, `aiop/`, `.osiris/`
- 53 commits enforcing deterministic, reproducible filesystem layout
- 1064 tests passing with 100% contract compliance
- See: `docs/adr/0028-filesystem-contract.md` (Status: Final)
- See: `docs/milestones/filesystem-contract.md` (Complete)

### 2025-09-30: Documentation Restructure
**Reason**: Documentation restructured to separate human-readable guides from AI-oriented contracts
**Result**: Clear separation into `human/` (narrative, examples, modules) and `ai/` (contracts, checklists, schemas)

For current documentation structure, see:
- Human documentation: `../developer-guide/human/README.md`
- AI documentation: `../developer-guide/ai/README.md`
- Root navigation: `../developer-guide/README.md`
