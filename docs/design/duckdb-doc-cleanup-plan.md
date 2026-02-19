# DuckDB Documentation Cleanup Plan

## Current State - Duplicate Content

### ADRs
1. **ADR 0022** (`docs/adr/0022-streaming-io-and-spill.md`)
   - Status: **Deferred**
   - Topic: RowStream interface for streaming
   - Mentions DuckDB as spill strategy
   - Not implemented in M1

2. **ADR 0043** (`docs/adr/0043-duckdb-data-exchange.md`)
   - Status: **Proposed**
   - Topic: DuckDB file-based data exchange
   - Replaces in-memory DataFrames
   - NEW decision based on current problems

### Design Docs
3. **duckdb-data-exchange.md** - Detailed design document
4. **duckdb-codex-review.md** - Request for second opinion
5. **duckdb-codex-review-response.md** - Codex feedback
6. **duckdb-implementation-checklist.md** - Implementation tasks

## Problem: Overlap & Confusion

**ADR 0022 vs ADR 0043:**
- Both address same problem (memory pressure, spilling)
- Different approaches:
  - ADR 0022: RowStream abstraction
  - ADR 0043: DuckDB file exchange
- ADR 0022 deferred, ADR 0043 proposed
- Risk of confusion about direction

**Design docs sprawl:**
- 4 separate documents in `docs/design/`
- Some content duplicated between them
- No clear "entry point"

## Recommended Cleanup

### Step 1: Update ADR 0022 Status

**Action:** Update ADR 0022 to reference ADR 0043

Add to bottom of ADR 0022:
```markdown
## Superseded By

This ADR has been superseded by **ADR 0043: DuckDB-Based Data Exchange**.

The RowStream abstraction is no longer the recommended approach. Instead:
- DuckDB handles streaming internally via batch inserts
- No custom iterator protocol needed
- Simpler driver contract

See ADR 0043 for current direction.
```

Status: Change from "Deferred" to "Superseded"

### Step 2: Consolidate Design Docs

**Keep in `docs/design/`:**

1. **duckdb-prototype-learnings.md** (NEW - will create during prototype)
   - What we learned from prototype
   - Performance characteristics
   - Edge cases discovered
   - Final recommendations

**Archive to `docs/design/archive/`:**

2. **duckdb-data-exchange.md** → `archive/duckdb-data-exchange-initial.md`
   - Original design doc
   - Useful for historical reference
   - Contains detailed driver patterns

3. **duckdb-codex-review.md** → `archive/duckdb-codex-review-request.md`
   - Request sent to Codex
   - Keep for audit trail

4. **duckdb-codex-review-response.md** → Keep in `docs/design/`
   - Codex feedback is valuable
   - Contains critical insights
   - Reference during implementation

5. **duckdb-implementation-checklist.md** → DELETE
   - Will be replaced by actual prototype code
   - Checklist no longer accurate after Codex review
   - Implementation will be iterative, not checklist-driven

### Step 3: Update ADR 0043 Based on Decisions

**Incorporate your feedback:**

1. **Streaming to DuckDB** (not pandas intermediate)
   ```python
   # Use DuckDB native batch insert
   con.execute("INSERT INTO main VALUES (?, ?, ?)", batch)
   ```

2. **Shared .duckdb file** (not separate per step)
   ```
   .osiris_sessions/<session_id>/
   └── pipeline_data.duckdb    # Single file
       ├── extract_actors      # Table
       ├── transform_actors    # Table
       └── extract_movies      # Table
   ```

3. **No fallback** (DuckDB required)
   - Remove hybrid approach
   - Simplify: Pure DuckDB only

4. **No performance heuristics**
   - Same code path for small/large datasets
   - Let DuckDB handle optimization

**Update ADR 0043 Decision section:**
```markdown
## Decision (Updated After Prototype)

We will replace in-memory DataFrame passing with **DuckDB file-based streaming** between pipeline steps.

### Key Changes

1. **Streaming Writes**: Drivers stream data directly to DuckDB in batches
   - No pandas intermediate step
   - Memory-efficient for large datasets

2. **Shared Database File**: All steps write to same `.duckdb` file
   - Each step creates its own table: `<step_id>`
   - Session file: `.osiris_sessions/<session_id>/pipeline_data.duckdb`

3. **Required Dependency**: DuckDB is core dependency
   - No fallback to DataFrames
   - Simpler code, unified behavior

4. **Uniform Performance**: Same code path for all dataset sizes
   - DuckDB optimizes internally
   - No special handling for small datasets
```

### Step 4: Final Documentation Structure

```
docs/
├── adr/
│   ├── 0022-streaming-io-and-spill.md (Status: Superseded → points to 0043)
│   └── 0043-duckdb-data-exchange.md (Status: Accepted after prototype)
│
└── design/
    ├── duckdb-codex-review-response.md (Keep - valuable insights)
    ├── duckdb-prototype-learnings.md (NEW - create during prototype)
    │
    └── archive/ (NEW directory)
        ├── duckdb-data-exchange-initial.md
        └── duckdb-codex-review-request.md
```

## Actions Before Prototype

1. ✅ Update ADR 0022 status to "Superseded"
2. ✅ Create `docs/design/archive/` directory
3. ✅ Move initial design docs to archive
4. ✅ Delete implementation checklist (outdated)
5. ✅ Update ADR 0043 with streaming + shared file approach
6. ⏭️  Build prototype
7. ⏭️  Document learnings in `duckdb-prototype-learnings.md`
8. ⏭️  Update ADR 0043 status to "Accepted"

## Prototype Focus

**Goal:** Learn by doing, not by planning

**Scope:**
- MySQL extractor → streams to DuckDB
- PostHog extractor → streams to DuckDB
- CSV extractor → streams to DuckDB
- DuckDB processor → SQL transform
- CSV writer → reads from DuckDB

**Questions to answer:**
- How does batch streaming perform?
- Can multiple steps write to same .duckdb file safely?
- What's the actual memory footprint?
- Any edge cases with concurrent reads/writes?
- Schema handling in DuckDB?

**Non-goals:**
- Full driver migration
- Runtime adapter changes
- E2B integration
- Production-ready code

Let's build, measure, learn!
