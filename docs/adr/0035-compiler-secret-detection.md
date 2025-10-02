# ADR-0035: Compiler Secret Detection via Specs and Connections

## Status
Proposed

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
- Cleaner tests (unit/integration don’t rely on keyword lists).
- Compiler emits exact secret keys per pipeline.
