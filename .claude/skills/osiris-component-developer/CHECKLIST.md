# Component Validation Checklist (57 Rules)

All Osiris components must pass these 57 validation rules before distribution.

## SPECIFICATION (10 rules)

- [ ] **SPEC-001**: Component name follows `family.type` pattern (e.g., `posthog.extractor`, `mysql.writer`)
- [ ] **SPEC-002**: Semantic version format `X.Y.Z` (e.g., `1.0.0`, `2.3.1`)
- [ ] **SPEC-003**: Has `description` and `author` fields
- [ ] **SPEC-004**: Declares `modes` array (`extract`, `write`, `transform`, or `discover`)
- [ ] **SPEC-005**: Includes `configSchema` using JSON Schema Draft 2020-12
- [ ] **SPEC-006**: Includes `connectionSchema` if component uses connections
- [ ] **SPEC-007**: Lists all `secrets` as JSON Pointers (e.g., `/api_key`, `/password`)
- [ ] **SPEC-008**: Has `x-connection-fields` with override policies (`allowed`, `forbidden`, `warning`)
- [ ] **SPEC-009**: Includes at least one complete `example`
- [ ] **SPEC-010**: All examples validate against `configSchema`

## CAPABILITIES (4 rules)

- [ ] **CAP-001**: Declares `capabilities` array
- [ ] **CAP-002**: Has `discover` capability if mode includes `discover`
- [ ] **CAP-003**: Has `healthcheck` capability (recommended for all components)
- [ ] **CAP-004**: All declared capabilities are actually implemented in driver

## DISCOVERY (6 rules)

- [ ] **DISC-001**: Returns deterministic output (same input → same output)
- [ ] **DISC-002**: Output resources are alphabetically sorted by `name`
- [ ] **DISC-003**: Includes SHA-256 fingerprint of discovered resources
- [ ] **DISC-004**: Returns schema: `{discovered_at, resources[], fingerprint}`
- [ ] **DISC-005**: `discovered_at` in ISO 8601 format with `Z` suffix
- [ ] **DISC-006**: Handles timeouts gracefully (default 10.0 seconds)

## CONNECTIONS (4 rules)

- [ ] **CONN-001**: Reads from `config["resolved_connection"]`, NOT environment variables
- [ ] **CONN-002**: NEVER reads from `os.environ` directly (use resolved_connection)
- [ ] **CONN-003**: Validates all required connection fields before use
- [ ] **CONN-004**: Respects override policies from `x-connection-fields`

## LOGGING & METRICS (6 rules)

- [ ] **LOG-001**: Never logs secrets in plain text
- [ ] **LOG-002**: Uses masking for sensitive data in error messages
- [ ] **MET-001**: Extractors emit `rows_read` metric
- [ ] **MET-002**: Writers emit `rows_written` metric
- [ ] **MET-003**: All metrics include `unit` and `tags` with `step` identifier
- [ ] **MET-004**: Checks `ctx` before using: `if ctx and hasattr(ctx, "log_metric")`

## DRIVER IMPLEMENTATION (6 rules)

- [ ] **DRIVER-001**: Exact signature: `def run(self, *, step_id: str, config: dict, inputs: dict | None = None, ctx: Any = None) -> dict`
- [ ] **DRIVER-002**: Returns `{"df": DataFrame}` for extractors
- [ ] **DRIVER-003**: Never mutates `inputs` parameter
- [ ] **DRIVER-004**: Has `finally` block for resource cleanup
- [ ] **DRIVER-005**: Handles all exceptions gracefully
- [ ] **DRIVER-006**: Implements all capabilities declared in spec.yaml

## HEALTHCHECK (3 rules)

- [ ] **DOC-001**: Returns `tuple[bool, dict]` from `doctor()` method
- [ ] **DOC-002**: Uses standard error categories: `auth`, `network`, `permission`, `timeout`, `ok`, `unknown`
- [ ] **DOC-003**: Default timeout is 2.0 seconds

## PACKAGING (5 rules)

- [ ] **PKG-001**: Has `requirements.txt` with exact versions (e.g., `pandas>=2.0.0`)
- [ ] **PKG-002**: Has `__init__.py` with `load_spec()` function
- [ ] **PKG-003**: Spec.yaml and driver.py are co-located in same directory
- [ ] **PKG-004**: No hardcoded paths (E2B compatible) - no `Path.home()`, no `/Users/...`
- [ ] **PKG-005**: All file paths use `ctx.base_path` if available

## RETRY & DETERMINISM (4 rules)

- [ ] **RETRY-001**: Operations are idempotent (can be retried safely)
- [ ] **RETRY-002**: No side effects on failure
- [ ] **DET-001**: Same input produces same output (deterministic)
- [ ] **DET-002**: Discovery is deterministic (same fingerprint on repeat)

## AI/LLM FRIENDLY (9 rules)

- [ ] **AI-001**: Clear descriptions for all schema fields
- [ ] **AI-002**: Examples cover common use cases
- [ ] **AI-003**: Error messages are actionable (tell user what to fix)
- [ ] **AI-004**: Config has sensible defaults where possible
- [ ] **AI-005**: Input aliases for convenience (e.g., `table` alias for `table_name`)
- [ ] **AI-006**: YAML snippet examples in docstrings or README
- [ ] **AI-007**: Connection template provided in examples
- [ ] **AI-008**: OML pipeline examples included in README
- [ ] **AI-009**: Discovery output sample provided in docs

---

## Validation Commands

```bash
# Spec validation
osiris component validate ./spec.yaml

# Driver signature check
python -c "import inspect; from driver import YourDriver; print(inspect.signature(YourDriver().run))"

# Discovery determinism
osiris discover your.component @connection --repeat

# Doctor health check
osiris doctor your.component @connection

# E2B compatibility
grep -r "Path.home()" . && echo "FAIL: Found hardcoded paths"
grep -r "os.environ\[" . && echo "FAIL: Found direct env access"
```

## Quick Reference

### MUST have:
- spec.yaml with all required fields
- driver.py with exact signature
- __init__.py with load_spec()
- requirements.txt
- At least one example
- x-connection-fields policies

### MUST NOT have:
- Hardcoded credentials
- Hardcoded file paths
- Direct os.environ access
- Secrets in logs
- Mutations of inputs

### SHOULD have:
- Discovery capability
- Doctor/healthcheck capability
- Pagination support (if applicable)
- Filtering support (if applicable)
- Comprehensive tests
- README with examples