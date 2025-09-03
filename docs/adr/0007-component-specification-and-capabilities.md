# 0007 Component Specification and Capabilities

## Status
Proposed

## Context
To enable deterministic YAML generation and reliable execution of pipelines, each Osiris component (e.g., extractors, transformers, writers) must expose a formal specification. This specification defines required configuration, supported operations, and declared capabilities.

Currently, components are integrated ad-hoc with implicit expectations. This makes it hard for agents (e.g., generator, validator, runner) to reason about what is possible and how to assemble valid pipelines. By introducing a contract-based component specification, we ensure interoperability, discoverability, and improved user experience.

## Decision
- Each component must provide a machine-readable specification (JSON Schema or equivalent).
- The specification will define:
  - Configuration schema (fields, types, defaults, required vs optional).
  - Capabilities (e.g., discovery, ad-hoc analytics, in-memory movement, validation).
  - Supported input/output data formats.
  - Security-sensitive fields (secrets) for automatic masking.
- The specification will be registered in a component registry, accessible to Osiris agents.
- The generator agent will use these specs to assemble pipelines deterministically.
- The validator agent will validate user YAML against component specifications.
- The runner agent will compile pipeline YAML into runtime configs (JSON, manifests) using specs.

## Consequences
- ✅ Deterministic YAML generation from user intent.
- ✅ Stronger validation and fewer runtime errors.
- ✅ Easier extension with new components (just publish spec).
- ✅ Improved security via explicit secret field definitions.
- 🔄 Additional upfront work for component developers to write specifications.
- 🔄 Requires maintaining registry consistency and versioning.

## Alternatives Considered
- Implicit integration (status quo): rejected due to fragility and lack of determinism.
- Hardcoded capability mapping: rejected due to poor scalability.

## Amendment 1: Mode Standardization (2025-01-02)

### Context
During implementation of M1a.2, we discovered inconsistencies in mode naming conventions, particularly the use of 'load' vs 'write' for data writing operations.

### Decision
- Standardize on 'write' mode for all data writing operations
- Deprecate 'load' mode but maintain in schema for backward compatibility
- All writer components support both 'write' and 'discover' modes
- Component modes are strictly defined: extract, write, transform, discover, analyze, stream

### Impact
- Component specs must use consistent mode terminology
- LLM context generation improved with standardized vocabulary
- Migration path provided for existing 'load' mode usage

## Amendment 2: Required Fields and Capabilities Audit (2025-01-02)

### Context
Audit of component specs against actual connector implementations revealed discrepancies in required fields and capability declarations.

### Decision
- Supabase components now require `key` field (was optional)
- Capabilities must reflect actual implementation, not theoretical support
- CLI enhanced to show both required config and secrets

### Impact
- Breaking change: Supabase configs without `key` will fail validation
- More accurate capability reporting prevents runtime surprises
- CLI provides complete visibility into component requirements

## References
- ADR-0004 Configuration Precedence Engine
- ADR-0006 Session-Scoped Logging and Artifacts
- ADR-0012 Separate Extractors and Writers
