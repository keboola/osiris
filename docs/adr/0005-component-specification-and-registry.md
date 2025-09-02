

# 0005 Component Specification and Registry

## Status
Proposed

## Context
To enable deterministic YAML generation and secure handling of secrets, Osiris needs a standardized way for components to declare their configuration, supported capabilities, and sensitive fields. Currently, secrets masking relies on static heuristics, which is not sustainable. As the ecosystem grows (e.g., new connectors such as Shopify), each component must define:
- Config schema (JSON Schema–like)
- Capabilities (discovery, in-memory movement, ad-hoc analytics, etc.)
- Secrets specification (which fields are sensitive)
- Version information

This registry-driven approach will allow Osiris agents to:
- Generate valid pipeline YAMLs deterministically
- Know how to mask secrets without relying on heuristics
- Present meaningful options in conversational interfaces
- Support new components without code changes to the core

## Decision
- Introduce a **Component Specification** format (YAML/JSON) describing each component’s config schema, secrets, and capabilities.
- Store specifications in a **Component Registry** accessible to Osiris agents and runtime.
- Components must declare which config fields are secrets.
- Capabilities will be machine-readable (e.g., `supports: [discovery, ad_hoc_query, in_memory]`).
- Runner will compile pipeline YAML into a canonical JSON config by merging base pipeline with component specs.
- Secrets masking will be driven by the specification, removing the need for static regexes.
- Versioning: Each component spec includes a version and backward-compatibility notes.

## Consequences
- Deterministic YAML generation: ensures pipelines are reproducible and audit-ready.
- Improved security: only declared secret fields are masked.
- Extensibility: new connectors can be onboarded by adding their spec to the registry.
- More maintainable than heuristic approaches.
- Requires initial investment in defining and maintaining specs.
- Developers must update the registry when component config changes.
