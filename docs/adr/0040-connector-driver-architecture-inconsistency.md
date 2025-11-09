# 0040 Connector vs Driver Architecture Inconsistency

## Status
Proposed

## Context

Osiris has two architectural patterns for component implementation that are currently used inconsistently across the codebase:

### Current State Analysis

| Component | Connector Exists | Driver Uses Connector | Pattern | Issues |
|-----------|------------------|----------------------|---------|--------|
| **Supabase writer** | ✅ `SupabaseClient` | ✅ Uses it | Connector pattern | ✅ Consistent |
| **MySQL extractor** | ✅ `MySQLClient` + `MySQLExtractor` | ❌ **Ignores it** | **Duplicated code** | ❌ Driver reimplements extraction |
| **GraphQL extractor** | ❌ None | N/A | Monolithic | ❌ All logic in driver |
| **PostHog extractor** | ❌ None | N/A | Monolithic | ❌ All logic in driver |
| **Filesystem CSV** | ✅ Has connector | ✅ Uses it | Connector pattern | ✅ Consistent |

### Architecture Patterns

**Pattern A: Connector Pattern** (Supabase, Filesystem)
```
components/supabase.writer/spec.yaml  ← Component specification
    ↓
osiris/drivers/supabase_writer_driver.py  ← Thin driver (implements Osiris contract)
    ↓ uses
osiris/connectors/supabase/
    ├── client.py       ← Connection management, pooling, doctor()
    ├── extractor.py    ← Extraction logic (reusable)
    └── writer.py       ← Writer logic (reusable)
```

**Pattern B: Monolithic Pattern** (MySQL extractor, GraphQL, PostHog)
```
components/mysql.extractor/spec.yaml
    ↓
osiris/drivers/mysql_extractor_driver.py  ← All logic in one file
    (No connector reuse, duplicated connection code)
```

### Specific Problems

**1. MySQL has duplicated code:**
- `osiris/connectors/mysql/extractor.py` exists with full extraction logic using `MySQLClient`
- `osiris/drivers/mysql_extractor_driver.py` **ignores it** and reimplements everything with direct SQLAlchemy calls
- Result: Two implementations of the same functionality

**2. Connection doctor is hardcoded:**
In `osiris/cli/connections_cmd.py`:
```python
# Hardcoded if-elif chain for connection testing
if test_family == "mysql":
    test_result = check_mysql_connection(resolved_config)
elif test_family == "supabase":
    test_result = check_supabase_connection(resolved_config)
elif test_family == "posthog":  # Had to add this manually
    test_result = check_posthog_connection(resolved_config)
# ... requires code change for every new connector
```

**3. No clear separation of concerns:**
- Connection management logic mixed with extraction logic
- Health check (`doctor()`) implementation scattered across:
  - Component drivers (`posthog_extractor_driver.py:doctor()`)
  - Connector clients (`MySQLClient.doctor()`)
  - CLI helper functions (`check_mysql_connection()`)

## Decision

**We need to decide on ONE consistent pattern**, but this decision is deferred for the following reasons:

1. **Scope is too large** - Affects 7+ components and core CLI code
2. **Breaking changes** - May require component spec updates
3. **Multiple valid approaches** - Each has trade-offs
4. **PostHog integration complete** - Can function with current pattern

### Options for Future Resolution

**Option A: Connector Pattern (Recommended)**
- All components use `osiris/connectors/{family}/` with:
  - `client.py` - Connection management, doctor(), retry logic
  - `extractor.py` or `writer.py` - Reusable business logic
- Drivers become thin wrappers implementing Osiris contract
- Pros: Clean separation, reusable logic, testable components
- Cons: More files, migration effort

**Option B: Monolithic Pattern**
- Remove `osiris/connectors/` entirely
- All logic in `osiris/drivers/`
- Pros: Simpler structure, fewer files
- Cons: Code duplication, harder to test, no reusability

**Option C: Hybrid (Current State)**
- Keep both patterns
- Document when to use each
- Pros: No migration needed
- Cons: Confusing for new contributors, inconsistent

## Consequences

**Immediate (Status Quo):**
- ✅ PostHog component works with monolithic pattern
- ❌ New components require hardcoded CLI changes for `connections doctor`
- ❌ Code duplication between MySQL connector and driver
- ❌ No clear guidelines for new component authors

**Future (If Option A chosen):**
- ✅ Dynamic connector discovery (no hardcoded if-elif)
- ✅ Reusable connection logic across extractors/writers
- ✅ Clear separation: connector = infrastructure, driver = business logic
- ❌ Migration effort for existing components
- ❌ More files to maintain

**Future (If Option B chosen):**
- ✅ Simpler file structure
- ✅ Less indirection
- ❌ Code duplication
- ❌ Harder to share connection logic
- ❌ Testing infrastructure vs business logic becomes harder

## Migration Path (If Option A Chosen)

1. Create connector registry pattern:
   ```python
   # osiris/connectors/registry.py
   def get_connector_client(family: str):
       """Dynamically load connector client."""
       try:
           module = importlib.import_module(f"osiris.connectors.{family}.client")
           return getattr(module, f"{family.capitalize()}Client")
       except (ImportError, AttributeError):
           return None
   ```

2. Migrate components in order:
   - MySQL extractor (fix driver to use existing MySQLExtractor)
   - GraphQL extractor (create connector)
   - PostHog extractor (create connector)
   - Others as needed

3. Update `connections doctor` to use registry:
   ```python
   client_class = get_connector_client(test_family)
   if client_class and hasattr(client_class, 'doctor'):
       client = client_class(resolved_config)
       result = client.doctor()
   ```

## Related Issues

- MySQL extractor driver ignores existing MySQLExtractor connector
- PostHog required manual CLI code changes for connection testing
- No clear component development guidelines

## References

- `osiris/connectors/` - Existing connector implementations
- `osiris/drivers/` - Existing driver implementations
- `osiris/cli/connections_cmd.py:430-490` - Hardcoded connection testing
- PostHog integration PR (2025-11-08)

## Date
2025-11-08

## Author
Claude Code (via user feedback during PostHog integration)
