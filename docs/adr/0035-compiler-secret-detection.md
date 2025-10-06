# ADR-0035: Compiler Secret Detection via Specs and Connections

## Status
Accepted (Phase 1)

## Context
Today, compiler uses hardcoded keyword lists (`password`, `key`, etc.) to detect secrets in configs.
But Osiris already has two better sources of truth:
- `osiris_connections.yaml` where secrets are defined via env var placeholders.
- Component `spec.yaml` where inputs are marked as secret.

The current keyword-based detection causes false positives/negatives and diverges from what components and connections actually require.

## Decision
Extend compiler to collect secrets from:
- Connection definitions (`osiris_connections.yaml`), reading variables that resolve from `.env`.
- Component specs, honoring the `secret: true` flag.
- Only fallback to keyword detection if no spec is available.

## Consequences
- More accurate secret detection.
- Cleaner tests (unit/integration don't rely on keyword lists).
- Compiler emits exact secret keys per pipeline.

## Implementation Status (December 2024)

**Current State: 80% Implemented (Phase 1 Complete)**

The spec-based secret detection (`x-secret` fields) has been fully implemented and is production-ready. Connection-based detection remains to be integrated.

### Phase 1: Spec-Based Detection ✅ COMPLETE

#### Implementation Files:
- `osiris/core/compiler_v0.py:358-393` - Secret detection implementation
  - `_collect_all_secret_keys()` - Main collection method
  - `_secret_keys_for_component()` - Extracts `x-secret` fields from specs
  - `_pointer_to_segments()` - JSON pointer parsing for nested secrets
  - `_validate_no_secrets()` - Validates no inline secrets in OML (lines 149-175)

#### Key Features Implemented:
```python
def _secret_keys_for_component(self, component_name: str, spec: dict) -> set[str]:
    """Extract secret field keys from component spec using x-secret markers."""
    secret_keys = set()

    # Parse x-secret fields from spec
    for x_secret in spec.get("x-secret", []):
        # Convert JSON pointer to field name
        # e.g., "/auth/password" -> "password"
        segments = self._pointer_to_segments(x_secret)
        if segments:
            secret_keys.add(segments[-1])

    return secret_keys
```

#### Fallback Mechanism:
```python
# COMMON_SECRET_NAMES defined in compiler_v0.py:16-36
COMMON_SECRET_NAMES = {
    "password", "passwd", "pass", "pwd",
    "secret", "key", "token", "auth",
    "credential", "api_key", "apikey",
    "access_token", "refresh_token",
    "private_key", "client_secret"
}

# Falls back to keywords if no spec available
if not spec:
    return COMMON_SECRET_NAMES
```

#### Test Coverage:
- `tests/unit/test_compiler_secret_collection.py` - 6 comprehensive tests (100% pass rate)
  - `test_collect_all_secret_keys_with_x_secret` - x-secret field parsing
  - `test_secret_keys_for_component_with_spec` - Component spec integration
  - `test_secret_keys_for_component_without_spec` - Fallback behavior
  - `test_pointer_to_segments` - JSON pointer parsing
  - `test_generate_configs_filters_x_secret_fields` - Secret filtering from configs
  - `test_primary_key_not_treated_as_secret` - Exception handling for non-secrets

#### Production Usage:
The compiler now correctly:
1. Reads `x-secret` fields from component specs
2. Filters these fields from compiled manifests
3. Validates that OML doesn't contain inline secrets
4. Falls back to keyword detection for components without specs

### Phase 2: Connection-Based Detection ⏳ PLANNED

#### What's Missing (20%):
1. **Connection Secret Collection**:
   - Parse `osiris_connections.yaml` during compilation
   - Extract `${VAR}` patterns from connection definitions
   - Add these to the set of required secrets

2. **Compile-Time Validation**:
   - Check if required env vars are set
   - Emit warnings for missing connection secrets
   - Example: "Connection mysql.prod requires MYSQL_PASSWORD (not set)"

#### Proposed Implementation:
```python
# In compiler_v0.py - to be added
def _collect_connection_secrets(self, oml: dict) -> set[str]:
    """Extract required env vars from connection definitions."""
    from ..core.config import load_connections_yaml, parse_connection_ref

    connections = load_connections_yaml(substitute_env=False)  # Get raw ${VAR}
    required_vars = set()

    for step in oml.get("steps", []):
        config = step.get("config", {})
        conn_ref = config.get("connection")

        if conn_ref and conn_ref.startswith("@"):
            family, alias = parse_connection_ref(conn_ref)
            if family and alias and family in connections:
                conn_def = connections[family].get(alias, {})
                # Extract all ${VAR} patterns
                required_vars.update(self._extract_env_vars_from_dict(conn_def))

    return required_vars

def _extract_env_vars_from_dict(self, data: dict) -> set[str]:
    """Recursively extract ${VAR} patterns from dictionary."""
    import re
    env_vars = set()

    def walk(obj):
        if isinstance(obj, str):
            # Find all ${VAR} patterns
            matches = re.findall(r'\$\{([^}]+)\}', obj)
            env_vars.update(matches)
        elif isinstance(obj, dict):
            for value in obj.values():
                walk(value)
        elif isinstance(obj, list):
            for item in obj:
                walk(item)

    walk(data)
    return env_vars
```

### Phase 3: Integration ⏳ FUTURE

Once both Phase 1 and 2 are complete:
1. **Unified Secret Collection**:
   - Combine spec-based and connection-based secrets
   - Provide single source of truth for required secrets

2. **Enhanced Validation**:
   - Compile-time error if critical secrets missing
   - Runtime warning for optional secrets
   - Clear error messages with remediation steps

3. **Documentation Generation**:
   - Auto-generate list of required env vars per pipeline
   - Include in compiled manifest metadata
   - Support `--show-secrets` flag for debugging

### Git Evidence:
- Secret detection integrated throughout compiler development
- Recent test fix: `238b28e` - "test: fix CLI validation tests for ADR-0020 and secret detection patterns"

### Effort Estimate:
- **Phase 2** (Connection-based detection): 1-2 days
- **Phase 3** (Full integration): 1 day

### Recommendation:
Accept Phase 1 as complete. Phase 2 should be prioritized as it will significantly improve the developer experience by catching missing secrets at compile time rather than runtime. The implementation is straightforward and builds on existing connection resolution infrastructure (ADR-0020).
