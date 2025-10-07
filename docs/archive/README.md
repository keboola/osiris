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

## What Moved Here

### Developer Guide (Legacy)
Replaced by `docs/developer-guide/human/modules/`

- `module-components.md` - Component Registry & validation (replaced by `human/modules/components.md`)
- `module-connectors.md` - Connection management (replaced by `human/modules/connectors.md`)
- `module-drivers.md` - Driver protocol (replaced by `human/modules/drivers.md`)
- `module-runtime.md` - Local execution (replaced by `human/modules/runtime.md`)
- `module-remote.md` - E2B cloud execution (replaced by `human/modules/remote.md`)
- `module-cli.md` - CLI commands (replaced by `human/modules/cli.md`)
- `module-core.md` - LLM agent & compilation (replaced by `human/modules/core.md`)

### Concepts (Legacy)
Replaced by `docs/developer-guide/human/CONCEPTS.md`

- `CONCEPTS.md` - Old duplicate of core concepts guide

### LLM Contracts (Legacy)
Replaced by `docs/developer-guide/ai/llms/` and `docs/developer-guide/ai/checklists/`

- `llms.txt` - Main LLM contract (replaced by `ai/llms/overview.md`)
- `llms-drivers.txt` - Driver patterns (replaced by `ai/llms/drivers.md`)
- `llms-cli.txt` - CLI patterns (replaced by `ai/llms/cli.md`)
- `llms-testing.txt` - Test patterns (replaced by `ai/llms/testing.md`)
- `llms-e2b.txt` - E2B patterns (replaced by `ai/llms/drivers.md` and `human/modules/remote.md`)

### Runtime & E2B (Legacy Notes)

- `e2b-runtime.md` - DataFrame lifecycle in E2B (details now in `human/modules/remote.md`)

### Milestones & Planning (Historical)

- `milestones/` - Historical milestone planning docs (current roadmap in `docs/roadmap/`)
- `dev-plan.md` - Old development plan
- `developer-guide/` - Old developer guide structure (replaced by human/ai split)

### Miscellaneous

- `component-interfaces.md` - Old component interface notes
- `repository-structure.md` - Old repository structure documentation

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

**Date**: 2025-09-30
**Reason**: Documentation restructured to separate human-readable guides from AI-oriented contracts
**Result**: Clear separation into `human/` (narrative, examples, modules) and `ai/` (contracts, checklists, schemas)

For current documentation structure, see:
- Human documentation: `../developer-guide/human/README.md`
- AI documentation: `../developer-guide/ai/README.md`
- Root navigation: `../developer-guide/README.md`
