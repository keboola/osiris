# ADR-0042: Driver Context API Contract

## Status
Proposed

## Context

Osiris drivers receive a `ctx` (context) object when executing, but there is **no formal specification** of what methods this object provides. This leads to runtime crashes when drivers assume methods exist.

### Problem: Inconsistent Context Usage

Discovered on 2025-11-09 when the PostHog driver crashed:

```python
# PostHog driver (WRONG - crashed)
ctx.log(f"[{step_id}] Starting extraction")
# Error: 'RunnerContext' object has no attribute 'log'

# MySQL driver (CORRECT - works)
logger.info(f"Step {step_id}: Starting extraction")
ctx.log_metric("rows_read", 1000)
```

The PostHog driver assumed `ctx.log()` existed, but the actual `RunnerContext` class only provides:
- `ctx.log_metric()` - For metrics
- `ctx.output_dir` - For artifacts path

### Impact

**Without a formal contract:**
- ❌ Developers guess what methods exist
- ❌ Bugs only discovered at runtime (not code review)
- ❌ No documentation for component authors
- ❌ Inconsistent patterns across drivers

**Example bugs prevented by this ADR:**
- PostHog driver: `ctx.log()` crash (10 locations fixed)
- Future drivers: would repeat same mistake

## Decision

We will establish a **minimal, explicit Driver Context API contract** that all drivers must follow.

### Minimal Context Interface

```python
class DriverContext:
    """Minimal context provided to all drivers during execution.

    This is the ONLY contract drivers can rely on.
    """
    output_dir: Path  # Step's artifacts directory

    def log_metric(self, name: str, value: Any, **kwargs) -> None:
        """Log a metric to metrics.jsonl.

        Args:
            name: Metric name (e.g., "rows_read")
            value: Metric value (numeric or string)
            **kwargs: Optional tags (e.g., step="extract-actors")
        """
        ...
```

### Drivers MUST Use Standard Logging

For logging messages (not metrics), drivers MUST use Python's standard `logging` module:

```python
import logging

logger = logging.getLogger(__name__)

def run(*, step_id: str, config: dict, inputs: dict, ctx) -> dict:
    # ✅ CORRECT - Standard logging
    logger.info(f"[{step_id}] Starting extraction")
    logger.error(f"[{step_id}] Failed: {error}")
    logger.debug(f"[{step_id}] Processing {len(data)} rows")

    # ✅ CORRECT - Metrics via context
    ctx.log_metric("rows_read", 1000)
    ctx.log_metric("rows_written", 500, step=step_id)

    # ✅ CORRECT - Artifacts directory
    artifact_path = ctx.output_dir / "data.json"

    # ❌ WRONG - These do NOT exist
    ctx.log("message")       # NO!
    ctx.emit_event(...)      # NO!
    ctx.write_artifact(...)  # NO!

    return {"df": result_dataframe}
```

### Rationale: Why Minimal?

1. **Simplicity:** Less API surface = easier to understand
2. **Flexibility:** Internal logging can change without breaking drivers
3. **Testability:** Standard logger can be mocked easily
4. **Portability:** Drivers work in any execution environment (LOCAL, E2B, future)

### Documentation Requirements

All driver development docs MUST include:
1. Explicit listing of available `ctx` methods
2. Code examples showing correct usage
3. Anti-patterns showing what NOT to do

## Consequences

### Advantages

1. **Clear Contract**
   - Developers know exactly what's available
   - Code reviews can catch violations
   - No runtime surprises

2. **Better Error Messages**
   - If driver uses wrong API → clear error at review time
   - Not cryptic `'RunnerContext' object has no attribute 'log'`

3. **Standard Patterns**
   - All drivers use same logging approach
   - Easier to read and maintain
   - Consistent log formats

4. **Future-Proof**
   - Minimal API is stable
   - Internal changes don't break drivers
   - Easy to add new capabilities later

### Risks

1. **Migration Effort**
   - Existing drivers may use wrong patterns
   - **Mitigation:** Audit all drivers, fix violations
   - **Status:** PostHog driver already fixed (2025-11-09)

2. **Developer Training**
   - New contributors may not know the contract
   - **Mitigation:** Document in CLAUDE.md, component-developer skill
   - **Status:** Documentation updated 2025-11-09

### Migration Checklist

- [x] PostHog driver: Fix `ctx.log()` → `logger.info()` (2025-11-09)
- [ ] Audit all drivers for contract violations
- [x] Update CLAUDE.md with driver guidelines (2025-11-09)
- [ ] Update docs/developer-guide/ai/START-HERE.md
- [ ] Add contract validation to driver registry (optional)
- [x] Update osiris-component-developer skill (2025-11-09)

## Alternatives Considered

### Alternative 1: Rich Context API (Rejected)

**Approach:** Provide many helper methods on `ctx`:
```python
ctx.log_info("message")
ctx.log_error("error")
ctx.emit_event("event_type", data={})
ctx.write_artifact("file.json", data)
```

**Why Rejected:**
- Large API surface = more to maintain
- Duplicates Python stdlib functionality
- Harder to change internals without breaking drivers
- Not how Python drivers typically work

### Alternative 2: No Context at All (Rejected)

**Approach:** Pass only primitives (output_dir as string)

**Why Rejected:**
- Metrics need structured logging
- Context provides clean abstraction
- Future extensibility (can add methods without changing signatures)

### Alternative 3: Document Current Chaos (Rejected)

**Approach:** Just document what exists today, allow variations

**Why Rejected:**
- Doesn't solve the problem
- Confusion continues
- Runtime bugs persist

## Related ADRs

- **ADR-0041: E2B PyPI-Based Execution** - PyPI approach eliminates duplicate execution logic, reducing context API surface area needed
- **ADR-0040: Connector-Driver Architecture** (Proposed) - Connector pattern would benefit from standardized context

## Implementation

### Phase 1: Documentation (Completed 2025-11-09)
- [x] Create this ADR
- [x] Update CLAUDE.md
- [x] Update osiris-component-developer skill

### Phase 2: Validation (Future)
- [ ] Add driver contract tests
- [ ] Audit existing drivers
- [ ] Fix violations

### Phase 3: Enforcement (Future)
- [ ] Add linter rule for `ctx.log()` usage
- [ ] Code review checklist
- [ ] CI check for violations

## References

- PostHog driver fix commit: 2025-11-09 (ctx.log → logger.info, 10 locations)
- E2B parity bug report: 2025-11-09 (df vs df_* input keys)
- Driver Development Guide: docs/developer-guide/ai/START-HERE.md
