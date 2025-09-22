# ADR-0012: Separate Extractors and Writers

**Status**: Implemented  
**Date**: 2025-01-02  
**Decision Makers**: Engineering Team

## Context

The original component design considered combined components (e.g., `mysql.table`) that could handle both reading and writing operations. During implementation of M1a.2 Bootstrap Component Specs, we needed to decide whether to:
1. Create combined components with multiple modes
2. Separate extractors and writers into distinct components

Additionally, we needed to standardize terminology for data writing operations ('load' vs 'write').

## Decision

We will **separate extractors and writers** into distinct component specifications:
- `mysql.extractor` for reading data
- `mysql.writer` for writing data
- Each component has focused responsibilities and modes

We will **standardize on 'write' mode** for data writing operations:
- Use `write` mode instead of `load` for new components
- Deprecate `load` mode but maintain for backward compatibility
- Writers support both `write` and `discover` modes

## Consequences

### Positive
- **Cleaner separation of concerns**: Each component has a single responsibility
- **Simpler configuration**: Users configure only what they need
- **Better discoverability**: Clear naming makes component purpose obvious
- **Mode consistency**: All writers use 'write' mode, all extractors use 'extract'
- **Discovery capability**: Writers can inspect target schemas independently

### Negative
- **More components**: Doubles the number of component specs to maintain
- **Migration required**: Existing pipelines using 'load' mode need updates
- **Documentation updates**: All references to 'load' mode need revision

### Neutral
- Component count increases but each is simpler
- Pipeline YAML may be slightly longer but more explicit

## Implementation Notes

1. **Component Naming Convention**:
   - Extractors: `{source}.extractor` (e.g., `mysql.extractor`)
   - Writers: `{target}.writer` (e.g., `mysql.writer`)

2. **Mode Support**:
   - Extractors: `['extract', 'discover']`
   - Writers: `['write', 'discover']`

3. **Backward Compatibility**:
   - Schema retains 'load' in enum but marks as deprecated
   - Existing pipelines continue to work
   - Documentation guides users to migrate

## Amendment 1: Write Mode Standardization (2025-01-02)

After initial implementation, we discovered inconsistent use of 'load' vs 'write' terminology. This amendment formalizes the decision to standardize on 'write' mode.

### Additional Context
- Initial writer specs used 'load' mode following legacy conventions
- LLM context and modern ETL tools predominantly use 'write' terminology
- Discovery that writers need 'discover' capability for target schema inspection

### Refined Decision
- All writer components MUST use 'write' mode for data writing
- All writer components SHOULD support 'discover' mode for schema inspection
- The term 'load' is deprecated but retained in schema for compatibility
- Logging events use 'write.*' pattern (e.g., 'write.start', 'write.complete')

### Migration Path
1. Update all writer specs to use 'write' mode
2. Add 'discover' mode to writer capabilities
3. Update documentation to reflect new terminology
4. Provide migration guide for existing pipelines
5. Plan removal of 'load' mode in future major version (2.0)

## References

- [M1a.2 Bootstrap Component Specs](../milestones/m1a.2-bootstrap-component-specs.md)
- [Component Specification Reference](../components-spec.md)
- [ADR-0007: Component Specification and Capabilities](./0007-component-specification-and-capabilities.md)
