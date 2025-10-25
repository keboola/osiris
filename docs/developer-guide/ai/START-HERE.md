# AI Component Development - START HERE

## Purpose

Single entry point for AI-assisted component development in Osiris. This guide routes you to the right documents based on your specific task.

## How This Works

1. Identify your task below
2. Follow the recommended path
3. Load only the documents you need
4. Don't read everything - be selective

## Prerequisites (Read First!)

**IMPORTANT:** Before building components, understand Osiris architecture:

→ **`../human/CONCEPTS.md`** - **READ THIS FIRST**
   - Explains 5 core abstractions: Component, Connector, Driver, Registry, Runner
   - Shows how they work together
   - Essential for understanding the system
   - ~15 minute read

**Core Principles:**
- **LLM-First**: Osiris is conversational ETL - AI discovers schemas, generates SQL, creates pipelines
- **Spec-First**: Components are self-describing via `spec.yaml` (declarative)
- **Runtime Separation**: Spec (what) vs Driver (how) vs Connector (where)
- **Security First**: Secrets never in specs, connection fields with override policies
- **Validation**: Schema → Semantic → Runtime (3-layer validation)

**Quick Mental Model:**
```
Component (spec.yaml)      → What operations are possible?
   ↓ used by
Registry                   → Catalog of all components
   ↓ referenced by
Compiler                   → Validates OML pipelines
   ↓ creates
Runner                     → Executes pipeline steps
   ↓ uses
Driver (implementation)    → How to execute operation?
   ↓ uses
Connector                  → Where/how to connect?
```

**After reading CONCEPTS.md**, proceed to task router below.

---

## Key Concepts You MUST Understand

These are fundamental concepts referenced throughout component development. Read this before proceeding.

### Metrics & Telemetry
**Why it matters:** Every component must emit metrics for observability.

**Required metrics:**
- `rows_read` - Number of rows extracted (extractors)
- `rows_written` - Number of rows written (writers)
- `rows_processed` - Number of rows transformed (transformers)

**How to emit:**
```python
ctx.log_metric("rows_read", count, tags={"step": step_id, "table": table_name})
```

**Units:** rows, ms (milliseconds), bytes, seconds, files, code
**Reference:** checklists/metrics_events_contract.md (MET-001 to MET-003)

---

### Secrets & Security
**Why it matters:** Prevent credential leaks in logs and specs.

**Rules:**
1. Declare secrets in spec.yaml: `secrets: ["/config/password"]`
2. Never log secrets: Use `mask_url()` or `mask_connection_for_display()`
3. Use JSON Pointers: `/config/api_key`, `/connection/password`
4. Test with suppressions: `# pragma: allowlist secret`

**x-connection-fields override policies:**
- `forbidden` - Security fields (password, token) → NEVER override
- `allowed` - Infrastructure (host, port) → Can override
- `warning` - Ambiguous (headers) → Warn if overridden

**Reference:** reference/x-connection-fields.md

---

### Filesystem Contract
**Why it matters:** Components must work in both local AND E2B cloud.

**CRITICAL RULE:** NEVER hardcode paths!

```python
# ❌ WRONG
Path.home() / ".osiris"
/Users/padak/data

# ✅ CORRECT
ctx.base_path / ".osiris"
config["output_dir"]
```

**All paths must be:**
- Config-driven (from config or ctx.base_path)
- Relative to base_path
- Never use Path.home(), absolute paths

**Reference:** CLAUDE.md Filesystem Contract, e2b-compatibility.md

---

### Data Passing Between Steps
**Why it matters:** Components communicate via standardized data structures.

**Standard format:**
```python
# Output from step
return {
    "data": dataframe,  # pandas DataFrame
    "metadata": {...}   # Optional
}

# Input to next step
def run(self, *, inputs, ...):
    upstream_df = inputs["previous_step_id"]["data"]
```

**Rules:**
- Always use pandas DataFrame for tabular data
- Access via `inputs[step_id]["data"]`
- Never mutate inputs (immutable)

**Reference:** llms/drivers.md (DRV-007, DRV-008)

---

### Driver Protocol (run method)
**Why it matters:** All drivers MUST implement this exact interface.

**Signature:**
```python
def run(self, *, step_id: str, config: dict, inputs: dict, ctx: DriverContext) -> dict:
    """
    Execute component logic.

    Args:
        step_id: Unique step identifier
        config: Resolved configuration (secrets included)
        inputs: Outputs from upstream steps
        ctx: Context for logging, metrics, base_path

    Returns:
        {"data": DataFrame, "metadata": {}}
    """
```

**Critical:** Note the `*` (keyword-only args)!

**Reference:** llms/drivers.md (DRV-001 to DRV-029)

---

### Discovery Mode
**Why it matters:** Components help AI design pipelines by discovering available data.

**Requirements:**
- Mode: `"discover"` in spec.yaml
- Capability: `discover: true`
- Deterministic output (same order every time)
- Include `discovered_at` timestamp
- Return sorted results

**Example output:**
```json
{
    "tables": [
        {"name": "customers", "row_count": 1000},
        {"name": "orders", "row_count": 5000}
    ],
    "discovered_at": "2025-10-26T10:00:00Z"
}
```

**Reference:** checklists/discovery_contract.md (DISC-001 to DISC-006)

---

### Connection Doctor (Healthcheck)
**Why it matters:** Validate connections before pipeline execution.

**Requirements:**
- Implement `doctor()` method
- Return error categories: `auth`, `network`, `permission`, `timeout`, `ok`
- Measure latency_ms
- Never leak secrets in errors

**Example:**
```python
def doctor(self, *, connection, timeout=2.0):
    try:
        # Test connection
        return (True, {"status": "ok", "latency_ms": 50})
    except Exception as e:
        return (False, {"status": "error", "category": "auth", "message": str(e)})
```

**Reference:** checklists/connections_doctor_contract.md

---

### Validation Rules (57 Total)
**Why it matters:** Comprehensive checklist ensures production-ready components.

**11 Rule Domains:**
- SPEC (10 rules) - Specification structure
- CAP (4) - Capabilities
- DISC (6) - Discovery
- CONN (4) - Connections
- LOG (6) - Logging & metrics
- DRIVER (6) - Driver implementation
- HEALTH (3) - Connection doctor
- PKG (5) - Packaging
- RETRY (3) - Retries
- DET (3) - Determinism
- AI (7) - AI-specific

**Reference:** checklists/COMPONENT_AI_CHECKLIST.md

---

**After understanding these concepts**, proceed to Task Router below.

---

## Task Router

### Task 1: "Build a new component from scratch"

**Path to follow:**

1. **Choose your API type** → Read `decision-trees/api-type-selector.md`
   - REST API component
   - GraphQL API component
   - SQL database component

2. **Select authentication** → Read `decision-trees/auth-selector.md`
   - API keys, OAuth, Basic auth, etc.

3. **Handle pagination** (if API-based) → Read `decision-trees/pagination-selector.md`
   - Offset, cursor, page-based, link-header

4. **Use the recipe template** → Read `recipes/[chosen-type]-extractor.md`
   - Copy the complete working example
   - Adapt to your specific API

5. **Validate your work** → Read `checklists/COMPONENT_AI_CHECKLIST.md`
   - Run through all validation steps
   - Ensure nothing is missed

6. **Ensure E2B compatibility** → Read `e2b-compatibility.md`
   - Critical for production deployments
   - Components must work locally AND in cloud sandbox
   - Test with `--e2b` flag

7. **Final build** → Read `build-new-component.md`
   - Complete implementation guide
   - All required files and structure

### Task 2: "Debug a failing component"

**Path to follow:**

1. **Identify the error** → Read `error-patterns.md`
   - Find your error pattern
   - Understand root cause

2. **Apply the fix** → Follow troubleshooting section in error-patterns.md
   - Step-by-step resolution
   - Common pitfalls

3. **Validate the fix** → Run component doctor
   ```bash
   osiris connections doctor <connection-name>
   ```

4. **Verify discovery** (if applicable) → Read `checklists/discovery_contract.md`
   - Ensure discovery mode works
   - Check all discovery requirements

### Task 3: "Understand component architecture"

**Path to follow (in order):**

1. **Schema reference** → Read `../../reference/components-spec.md`
   - Complete schema documentation
   - All required fields

2. **Core concepts** → Read `../human/CONCEPTS.md`
   - Fundamental principles
   - Design patterns

3. **Connection fields** → Read `../../reference/x-connection-fields.md`
   - Advanced authentication patterns
   - Dynamic field configuration

**You're done** - you now understand the architecture.

### Task 4: "Add capability to existing component"

**Path to follow:**

1. **Find the capability section** → Read `build-new-component.md`
   - Locate section for your capability
   - Understand requirements

2. **Check the contract** → Read appropriate checklist:
   - Discovery mode? → `checklists/discovery_contract.md`
   - Connection testing? → `checklists/connections_doctor_contract.md`
   - Validation? → `checklists/COMPONENT_AI_CHECKLIST.md`

3. **Update three layers:**
   - `spec.yaml` - Component specification
   - `driver.py` - Implementation logic
   - `tests/` - Test coverage

### Task 5: "Review/approve a component PR"

**Path to follow:**

1. **Run validation** → Read `checklists/COMPONENT_AI_CHECKLIST.md`
   - Verify all checklist items pass
   - Check test coverage

2. **Test manually** → Run connections doctor
   ```bash
   osiris connections doctor <connection-name>
   ```

3. **Verify contracts** → Check relevant checklists:
   - Discovery contract
   - Connection doctor contract

## Quick Reference by Question

| Question | Document to Read |
|----------|-----------------|
| "What metrics must I emit?" | See "Key Concepts" → Metrics & Telemetry above |
| "How do I avoid leaking secrets?" | See "Key Concepts" → Secrets & Security above |
| "What auth type should I use?" | `decision-trees/auth-selector.md` |
| "How do I implement pagination?" | `decision-trees/pagination-selector.md` |
| "What API type is this?" | `decision-trees/api-type-selector.md` |
| "What fields are required in spec.yaml?" | `build-new-component.md` section 2 |
| "How do I test discovery mode?" | `checklists/discovery_contract.md` |
| "What's the x-connection-fields syntax?" | `../../reference/x-connection-fields.md` |
| "How do I debug connection errors?" | `error-patterns.md` |
| "What does component doctor check?" | `checklists/connections_doctor_contract.md` |
| "How do I structure driver code?" | `recipes/[api-type]-extractor.md` |
| "What's the complete spec schema?" | `../../reference/components-spec.md` |
| "How do I make my component work in E2B?" | `e2b-compatibility.md` |
| "Why does my component fail in E2B?" | `e2b-compatibility.md` → Common E2B Errors |
| "What are the E2B best practices?" | `e2b-compatibility.md` → Best Practices |

## Document Index (Organized by Purpose)

### Decision Making (Start Here)
- `decision-trees/api-type-selector.md` - Choose REST/GraphQL/SQL
- `decision-trees/auth-selector.md` - Choose auth mechanism
- `decision-trees/pagination-selector.md` - Choose pagination strategy

### Working Examples (Copy These)
- `recipes/rest-api-extractor.md` - Complete REST API example
- `recipes/graphql-extractor.md` - Complete GraphQL example
- `recipes/sql-extractor.md` - Complete SQL database example

### Step-by-Step Guides
- `build-new-component.md` - Complete build guide (all steps)
- `e2b-compatibility.md` - E2B cloud sandbox compatibility (CRITICAL for production)
- `dependency-management.md` - Dependency and package management
- `error-patterns.md` - Common errors and fixes

### Validation (Check Your Work)
- `checklists/COMPONENT_AI_CHECKLIST.md` - Master validation checklist
- `checklists/discovery_contract.md` - Discovery mode requirements
- `checklists/connections_doctor_contract.md` - Doctor test requirements

### Reference (Look Up Details)
- `../../reference/components-spec.md` - Complete schema specification
- `../../reference/x-connection-fields.md` - Advanced auth patterns

### Human Context (Background Reading)
- `../human/CONCEPTS.md` - Core concepts and philosophy
- `../human/TESTING.md` - Testing approach

## Anti-Patterns: Don't Do This

❌ **Don't read all 25+ documents** - You'll waste time and get confused

❌ **Don't start without knowing your API type** - Different types need different approaches

❌ **Don't skip validation checklists** - They catch 80% of common errors

❌ **Don't copy-paste without understanding** - Understand why the pattern works

❌ **Don't hardcode secrets** - Always use connection fields and environment variables

❌ **Don't skip discovery mode** - It's required for Osiris chat to work

❌ **Don't skip E2B testing** - Components MUST work in cloud sandbox for production

## Pro Tips

✅ **Start with decision trees** - They ask the right questions upfront

✅ **Use recipes as templates** - They're complete, tested examples

✅ **Validate early and often** - Run component doctor during development

✅ **Read only what you need** - Focus on your current task

✅ **Test with real credentials** - Never use fake test data

✅ **Follow the contracts** - Discovery and doctor contracts are non-negotiable

✅ **Test E2B early** - Use `--e2b` flag to catch compatibility issues early

## Typical Workflow Example

**Scenario: Building a new Stripe API extractor**

1. Read `decision-trees/api-type-selector.md` → Determined it's REST API
2. Read `decision-trees/auth-selector.md` → Determined it's Bearer token
3. Read `decision-trees/pagination-selector.md` → Determined it's cursor-based
4. Read `recipes/rest-api-extractor.md` → Used as template
5. Built spec.yaml, driver.py, tests
6. Read `checklists/COMPONENT_AI_CHECKLIST.md` → Validated everything
7. Ran `osiris connections doctor stripe-test` → All checks passed
8. Done in ~45 minutes

## Document Maintenance

This START-HERE.md file is the canonical entry point. If you add new documents to the ai/ directory:

1. Add them to the appropriate section above
2. Add relevant Q&A to Quick Reference
3. Update task paths if they change workflows
4. Keep this file under 300 lines

## Getting Help

If you're stuck:

1. Check `error-patterns.md` for your specific error
2. Review the relevant recipe for a working example
3. Verify against the appropriate checklist
4. Test with `osiris connections doctor`

## Version Info

- Last updated: 2025-10-26
- Osiris version: v0.5.0
- Document count: 15+ files in ai/ directory
- Maintenance: Update paths when files move

---

**Ready to start?** Pick your task above and follow the path. Don't overthink it.
