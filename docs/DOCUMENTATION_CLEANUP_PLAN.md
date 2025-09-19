# Documentation Cleanup Plan

## Existing Documentation Status

### Files to Archive (`[TO ARCHIVE]`)
These files are superseded or obsolete and should be moved to `docs/archive/`:

- **e2b-vs-local-run-plan.md** - [TO ARCHIVE] - Planning document, superseded by implementation
- **e2b-vs-local-run.md** - [TO ARCHIVE] - Superseded by final-e2b-vs-local-protocol.md
- **m1c-tmp-gpt.md** - [TO ARCHIVE] - Working notes, no longer needed

### Files to Merge (`[TO MERGE]`)
These files contain overlapping content that should be consolidated:

- **final-e2b-vs-local-protocol.md** - [TO MERGE INTO ADR-0026] - Contains comprehensive E2B protocol details
- **E2B_PRODUCTION_HARDENING_REPORT.md** - [TO MERGE INTO ADR-0026] - Contains production metrics and validation
- **e2b_parity.md** - [TO MERGE INTO ADR-0026] - Contains execution flow details

### Files to Refresh (`[TO REFRESH]`)
These files need updating to reflect current implementation:

- **architecture.md** - [TO REFRESH] - Missing transparent proxy architecture, driver layer, M1 updates
- **migration-guide.md** - [TO REFRESH] - May need updates for new project structure (ADR-0028)
- **components-spec.md** - [TO REFRESH] - Should align with new component development guide

### Files to Keep As-Is
These files are current and should remain:

- **events_and_metrics_schema.md** - Current, promote to official reference
- **pipeline-format.md** - Current OML documentation
- **sql-safety.md** - Important security guidelines
- **README.md** - Index file for docs directory

## Recommended Actions

1. **Create archive directory**: `mkdir docs/archive`
2. **Move obsolete files**: `git mv [files] docs/archive/`
3. **Consolidate E2B docs into ADR-0026**:
   - Extract key protocol details from final-e2b-vs-local-protocol.md
   - Add production metrics from E2B_PRODUCTION_HARDENING_REPORT.md
   - Include execution flow from e2b_parity.md
4. **Update architecture.md** with:
   - Transparent proxy architecture
   - Driver layer documentation
   - M1 milestone achievements
5. **Archive after merge**: Move merged E2B docs to archive
