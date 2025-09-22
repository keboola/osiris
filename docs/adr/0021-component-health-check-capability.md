# ADR 0021: Component Health Check Capability

## Status
Accepted

## Context
Osiris exposes `osiris connections doctor` to verify connectivity. Current checks live in the CLI and are generic (e.g., SELECT 1, HTTP ping). We want correctness and extensibility to live with component authors (who know the real readiness criteria, auth scopes, latency constraints) and keep CLI small. We also want unified session logging, redaction, and deterministic outputs.

## Decision
Introduce an optional component capability `doctor(connection, timeout=2.0) -> (ok: bool, details: dict)` implemented by connector clients. The CLI prefers the component's `doctor()` when available and falls back to a generic check otherwise.

### Interface (driver-side)
```python
class ComponentClient(Protocol):
    def doctor(self, connection: dict, timeout: float = 2.0) -> tuple[bool, dict]:
        """
        Returns (ok, details) where details is redaction-safe and may include:
          - "latency_ms": float
          - "category": "auth"|"network"|"permission"|"timeout"|"unknown"
          - "message": str (non-sensitive, redacted)
          - optional metadata
        """
```

### Registry / Spec
- `components/spec.schema.json` may declare `"capabilities": ["doctor", ...]`.
- Drivers that implement `doctor()` should claim the capability. CLI will detect capability via registry or duck-typing.
- No secrets in returned details; authors must respect Osiris redaction rules.

### CLI & Sessions
- `osiris connections doctor` creates a session (type: connections, subtype: doctor) and emits events per alias:
  - `connection_test_start {family, alias}`
  - `connection_test_result {family, alias, ok, latency_ms, category, message}`
- All outputs follow redaction policy.
- Stdout stays clean (Rich summary / JSON only), 3rd party INFO logs suppressed during the command scope.

### Fallbacks
If a driver lacks `doctor()`:
- **mysql**: SELECT 1
- **supabase**: fast HTTP health endpoint (e.g., `/auth/v1/health`) with short timeout
- **duckdb**: file path writable / exists

## Consequences

### Pros
- **Ownership**: health semantics live with component authors
- **Better UX**: fewer false negatives, clearer error categories
- **Observability**: consistent events + redaction

### Cons
- Slightly more API surface for drivers
- Minimal schema update & tests

## Acceptance Criteria
- Drivers MAY implement `doctor()`. CLI prefers it.
- Sessions created for `connections doctor`, with structured events and no secret leaks.
- Fallbacks work for existing drivers.
