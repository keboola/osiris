# Milestone M1: Component Registry and Runner

## Status
🔄 **In Progress** (Target: v0.2.0)

## Overview

M1 establishes the foundation for contract-backed pipeline generation and execution by introducing a Component Registry with self-describing components and a deterministic pipeline runner. This milestone directly addresses the need for reliable, reproducible pipeline generation and execution identified in the post-0.1.1 analysis.

### ADR-Driven Design
This milestone implements the architectural decisions documented in ADRs 0005-0008:
- **Registry-Driven Approach** (ADR-0005): Components declare their configuration and secrets, enabling deterministic generation
- **Deterministic Execution** (ADR-0006): Runner ensures reproducible, auditable pipeline execution
- **Contract-Based Specifications** (ADR-0007): Machine-readable specs enable AI-driven generation
- **Centralized Registry** (ADR-0008): Single source of truth for all component capabilities

### Key Objectives
- Enable components to self-describe their configuration and capabilities
- Provide machine-readable context to the LLM for valid pipeline generation
- Implement deterministic compilation from OML to canonical Run Manifests
- Execute pipelines locally and via e2b with full audit trail

### Links to Key Documents

#### Architecture Decision Records (ADRs)
- **Component Registry & Specifications**:
  - [ADR-0005: Component Specification and Registry](../adr/0005-component-specification-and-registry.md) - Core decision on registry-driven approach
  - [ADR-0007: Component Specification and Capabilities](../adr/0007-component-specification-and-capabilities.md) - Detailed spec requirements
  - [ADR-0008: Component Registry](../adr/0008-component-registry.md) - Registry implementation details
- **Pipeline Execution**:
  - [ADR-0006: Pipeline Runner and Execution](../adr/0006-pipeline-runner-and-execution.md) - Runner architecture and design
- **Overall Strategy**:
  - [ADR-0011: Osiris Roadmap](../adr/0011-osiris-roadmap.md#m1--component-registry--context-aware-agent) - M1 in context of full roadmap

#### Planning Documents
- **Implementation Plan**: [Post-0.1.1 Implementation Plan](../post_0.1.1_plan.md#m1--component-registry-specs--capabilities)
- **Development Timeline**: [Development Plan - M1a](../dev-plan.md#milestone-m1a-component-registry-foundation)

## Milestone Phases

### Phase M1a: Component Registry Foundation
**Duration**: 2-3 weeks  
**Priority**: High (enables M2)  
**Status**: 🔄 Starting  
**Related ADRs**: [ADR-0005](../adr/0005-component-specification-and-registry.md), [ADR-0007](../adr/0007-component-specification-and-capabilities.md), [ADR-0008](../adr/0008-component-registry.md)

#### Objectives
- Define component specification schema per ADR-0005
- Bootstrap initial component specs for MySQL and Supabase
- Implement registry loader and validator as specified in ADR-0008
- Provide friendly error messages for validation failures

#### Deliverables

##### M1a.1: Component Spec Schema ✅
- [x] Create `components/spec.schema.json` with JSON Schema Draft 2020-12
- [x] Define required fields: name, version, modes, capabilities, configSchema
- [x] Add optional fields: title, description, constraints, examples, secrets, redaction
- [x] Validate schema structure with jsonschema library

##### M1a.2: Bootstrap Component Specs
- [ ] Analyze existing `osiris/connectors/mysql` extractor and writer implementations
- [ ] Create `components/mysql.extractor/spec.yaml` with configuration schema
- [ ] Create `components/mysql.writer/spec.yaml` with configuration schema
- [ ] Analyze existing `osiris/connectors/supabase` extractor and writer implementations
- [ ] Create `components/supabase.extractor/spec.yaml` with configuration schema
- [ ] Create `components/supabase.writer/spec.yaml` with configuration schema
- [ ] Include ≤2 examples per component for LLM context efficiency
- [ ] Validate all specs against `components/spec.schema.json`
- [ ] Test that examples validate against their configSchema

##### M1a.3: Component Registry Implementation
- [ ] Create `osiris/components/registry.py` with spec loading logic
- [ ] Implement spec validation against schema
- [ ] Add caching with mtime-based invalidation
- [ ] Expose `get_secret_map(component_type)` for runtime redaction
- [ ] Handle spec versioning and backward compatibility

##### M1a.4: Friendly Error Mapper
- [ ] Create error mapping table for common validation failures
- [ ] Map JSON Schema paths to human-readable field names
- [ ] Generate actionable fix suggestions with examples
- [ ] Include links to component documentation

##### M1a.5: CLI Integration
- [ ] Create `osiris/cli/components_cmd.py` with Click commands
- [ ] Implement `osiris components list` to show all components
- [ ] Implement `osiris components spec <type>` with JSON/YAML output
- [ ] Add help text and usage examples
- [ ] Integrate with existing Rich terminal formatting

#### Acceptance Criteria
- [ ] Component specs validate against spec.schema.json
- [ ] `osiris components list` displays all four components (mysql.extractor, mysql.writer, supabase.extractor, supabase.writer) with capabilities
- [ ] `osiris components spec mysql.extractor --format=json` outputs valid schema
- [ ] Invalid configurations show friendly errors with fix suggestions
- [ ] Registry loads specs from filesystem with proper caching
- [ ] Unit tests achieve >80% coverage for registry code

### Phase M1b: Context Builder and Validation
**Duration**: 2 weeks  
**Priority**: High (critical for LLM improvement)  
**Status**: ⏳ Pending  
**Related ADRs**: [ADR-0007](../adr/0007-component-specification-and-capabilities.md)

#### Objectives
- Export minimal component context for LLM consumption (per ADR-0007)
- Integrate context into conversational agent
- Validate LLM-generated OML against component specs
- Improve chat experience with validation feedback

#### Deliverables

##### M1b.1: Context Export Design
- [ ] Design minimal context schema for token efficiency
- [ ] Include only: names, required fields, enums, defaults, ≤2 examples
- [ ] Analyze token usage and optimize structure
- [ ] Define context versioning strategy

##### M1b.2: Context Builder Implementation
- [ ] Create `osiris/prompts/build_context.py`
- [ ] Extract minimal context from Component Registry
- [ ] Implement disk caching with spec-based invalidation
- [ ] Add CLI: `osiris prompts build-context --out .osiris_prompts/context.json`

##### M1b.3: Prompt Manager Integration
- [ ] Update `osiris/core/prompt_manager.py` to load context
- [ ] Inject context into system prompt template
- [ ] Ensure context is included in all LLM requests
- [ ] Monitor token usage impact

##### M1b.4: Post-Generation Validation
- [ ] Integrate validation in `osiris/cli/chat.py`
- [ ] Validate generated OML against component specs
- [ ] Display validation errors with Rich formatting
- [ ] Implement retry mechanism for invalid generations

#### Acceptance Criteria
- [ ] Context export includes only essential information
- [ ] 3 test prompts (Supabase→Supabase append/merge, MySQL→Supabase) generate valid OML
- [ ] Invalid fields are blocked with actionable error messages
- [ ] Chat response time remains ≤3s including validation
- [ ] Context rebuilds automatically when specs change

### Phase M1c: Compiler and Manifest Generation
**Duration**: 1.5 weeks  
**Priority**: Medium  
**Status**: ⏳ Pending  
**Related ADRs**: [ADR-0006](../adr/0006-pipeline-runner-and-execution.md)

#### Objectives
- Compile OML to deterministic Run Manifests (per ADR-0006)
- Generate per-step configuration files
- Ensure reproducible pipeline execution
- Maintain backward compatibility with existing YAMLs

#### Deliverables

##### M1c.1: OML Schema Definition
- [ ] Define OML v0.0.1 schema with version, name, sources, sinks
- [ ] Add optional params for runtime configuration
- [ ] Ensure compatibility with existing YAML format
- [ ] Document migration path for future versions

##### M1c.2: Compiler Implementation
- [ ] Create `osiris/compile.py` with pure function design
- [ ] Parse and validate OML against component specs
- [ ] Generate `cfg/<step>.json` for each pipeline step
- [ ] Produce canonical `cfg/manifest.yaml` with execution plan
- [ ] Implement deterministic output (same input → same output)

##### M1c.3: CLI Integration
- [ ] Add `osiris compile <pipeline.yaml> --out cfg/` command
- [ ] Support `--mode warn|strict|off` validation flags
- [ ] Display compilation progress with Rich
- [ ] Handle errors gracefully with clear messages

#### Acceptance Criteria
- [ ] `osiris compile` generates deterministic cfg/*.json + manifest.yaml
- [ ] Compilation is idempotent (same input → same output)
- [ ] No secrets appear in compiled manifests
- [ ] Backward compatible with existing pipeline YAMLs
- [ ] Golden file tests pass for sample pipelines

### Phase M1d: Pipeline Runner MVP
**Duration**: 2 weeks  
**Priority**: Medium  
**Status**: ⏳ Pending  
**Related ADRs**: [ADR-0006](../adr/0006-pipeline-runner-and-execution.md), [ADR-0005](../adr/0005-component-specification-and-registry.md)

#### Objectives
- Execute compiled manifests locally (per ADR-0006)
- Integrate with existing connectors
- Generate structured logs and metrics with proper secrets masking (per ADR-0005)
- Prepare for e2b remote execution

#### Deliverables

##### M1d.1: Secrets Management
- [ ] Create `osiris/secrets.py` with ENV and --secrets-file support
- [ ] Implement connection reference resolution (@mysql, @supabase)
- [ ] Enforce no-secrets policy in manifests/logs
- [ ] Add secrets rotation support for long-running jobs
- [ ] Use registry secret map for automatic redaction

##### M1d.2: Local Runner Engine
- [ ] Create `osiris/run/runner.py` orchestration engine
- [ ] Implement `osiris/run/engines/local.py` 
- [ ] Integrate with existing mysql/supabase connectors
- [ ] Generate JSONL logs with run_id, step, metrics
- [ ] Produce artifacts: metrics.json, manifest.yaml

##### M1d.3: e2b Runner Engine
- [ ] Create `osiris/run/engines/e2b.py` with Python SDK
- [ ] Implement manifest/config upload to sandbox
- [ ] Stream logs from remote execution
- [ ] Handle exit codes and artifact retrieval
- [ ] Manage API keys securely

##### M1d.4: CLI and Testing
- [ ] Add `osiris run <pipeline.yaml>` with engine selection
- [ ] Support `--engine=local|e2b` flag
- [ ] Accept `--secrets-file` and `--param k=v` options
- [ ] Create integration tests with docker-compose
- [ ] Mock e2b for E2E testing

#### Acceptance Criteria
- [ ] `osiris run --engine=local` executes data movement (append/merge)
- [ ] `osiris run --engine=e2b` uploads and executes in sandbox
- [ ] JSONL logs contain run_id, step, duration, row counts
- [ ] Exit codes are meaningful (0=success, 2=validation, 3=compile, 4=run, 5=config)
- [ ] No secrets appear in logs or artifacts
- [ ] Integration tests pass with real databases

## Success Metrics

### Quantitative
- **First-try validity rate**: +50-70% improvement vs baseline
- **Chat response time**: ≤3s E2E including validation
- **Validation overhead**: ≤350ms p50
- **Compilation time**: ≤500ms for typical pipelines
- **Test coverage**: >80% for new components

### Qualitative
- Component specs are clear and maintainable
- Error messages guide users to solutions
- Pipeline execution is deterministic and reproducible
- System is extensible for new components

## Risk Mitigation

### Technical Risks
- **Performance degradation**: Cache contexts aggressively, lazy-load components
- **Token limit exceeded**: Keep context minimal, implement on-demand loading
- **Validation too strict**: Default to warn mode, provide escape hatches

### Operational Risks
- **Breaking changes**: Maintain backward compatibility, provide migration tools
- **User confusion**: Clear documentation, migration guides, helpful errors
- **Rollback needed**: Feature flags (OSIRIS_VALIDATION=off), keep old code paths

## Dependencies

### Prerequisites (from M0)
- ✅ Discovery cache fingerprinting (prevents stale data)
- ✅ Basic connection validation (ensures valid configs)
- ✅ Session-scoped logging (provides audit trail)

### Enables (for future milestones)
- M2: Enhanced LLM context from registry
- M3: Refined conversational flows with validation
- M4: Process-oriented workflows built on components

## Testing Strategy

### Unit Tests
- Component registry validation (positive/negative cases)
- Compiler determinism and idempotence
- Runner state management
- Error mapper accuracy

### Integration Tests
- Docker-compose with MySQL + Supabase
- End-to-end: compile → run → verify
- Secrets masking verification
- Multi-step pipeline execution

### Performance Tests
- Context generation time
- Compilation overhead
- Validation latency impact
- Token usage monitoring

## Documentation Requirements

### User-Facing
- Migration guide from v0.1.x
- Component spec authoring guide
- Troubleshooting validation errors
- CLI command reference

### Developer
- Component registry API docs
- Spec schema reference
- Runner engine interface
- Testing guide

## Implementation Notes

### File Structure
```
components/
  spec.schema.json           # Component spec JSON Schema
  mysql.table/
    spec.yaml               # MySQL component specification
  supabase.table/
    spec.yaml               # Supabase component specification

osiris/
  components/
    __init__.py
    registry.py             # Component registry implementation
  compile.py                # OML to manifest compiler
  secrets.py                # Secrets management
  run/
    __init__.py
    runner.py               # Orchestration engine
    engines/
      local.py              # Local execution engine
      e2b.py                # e2b sandbox engine
  cli/
    components_cmd.py       # Component management commands
  prompts/
    build_context.py        # LLM context builder

tools/
  spec_lint.py              # Component spec validator
  gen_spec_from_code.py     # Optional spec generator
```

### Key Design Decisions

#### Pure JSON Schema for MVP
- Start with JSON Schema Draft 2020-12 only
- Defer custom constraint language to later milestone
- Focus on required fields, enums, defaults

#### Hybrid Compilation Strategy
- Direct execution for simple pipelines
- Always emit manifest for audit trail
- Explicit compilation for complex workflows

#### Incremental Validation
- Default to warning mode (`--mode=warn`)
- Strict mode is opt-in initially
- Provide clear migration path

## Completion Criteria

### Phase M1a ✅ Complete when:
- [ ] All component specs validate and load correctly
- [ ] CLI commands work with proper error handling
- [ ] Friendly error messages guide users to fixes
- [ ] Test coverage >80% for registry code

### Phase M1b ✅ Complete when:
- [ ] Context builder exports minimal, effective LLM context
- [ ] Chat validation blocks invalid OML with helpful errors
- [ ] LLM generation success rate improves by 50%+
- [ ] Token usage stays within limits

### Phase M1c ✅ Complete when:
- [ ] Compiler generates deterministic manifests
- [ ] Compilation is fast (<500ms) and idempotent
- [ ] No secrets in manifests
- [ ] Backward compatibility maintained

### Phase M1d ✅ Complete when:
- [ ] Complete compile → manifest → run workflow functional
- [ ] Both local and e2b execution engines working
- [ ] Comprehensive logging and artifact generation
- [ ] Security review passed for secrets handling

## Next Steps

1. **Immediate** (Week 3): Begin M1a.1 - Component spec schema design
2. **Week 3-4**: Complete M1a with bootstrap specs and registry
3. **Week 5**: M1b context builder and validation
4. **Week 6**: M1c compiler implementation
5. **Week 7-8**: M1d runner and execution engines

## References

### Milestone Documents
- **Previous**: [M0 Milestone: Discovery Cache](m0-discovery-cache.md) - Foundation for M1
- **Previous**: [M0 Milestone: Session Logs](m0-session-logs.md) - Logging infrastructure

### Architecture Decision Records
- **[ADR-0005](../adr/0005-component-specification-and-registry.md)**: Component Specification and Registry
  - Establishes need for standardized component declarations
  - Defines registry-driven approach for secrets masking
  - Enables deterministic YAML generation
  
- **[ADR-0006](../adr/0006-pipeline-runner-and-execution.md)**: Pipeline Runner and Execution
  - Defines runner requirements: determinism, extensibility, auditability
  - Specifies artifact management and session logging
  - Prepares for e2b integration
  
- **[ADR-0007](../adr/0007-component-specification-and-capabilities.md)**: Component Specification and Capabilities
  - Details configuration schema requirements
  - Defines capability declarations (discovery, analytics, in-memory)
  - Specifies security-sensitive field handling
  
- **[ADR-0008](../adr/0008-component-registry.md)**: Component Registry
  - Single source of truth for component specs
  - Enables AI-driven pipeline generation
  - Foundation for future workflow orchestration
  
- **[ADR-0011](../adr/0011-osiris-roadmap.md)**: Osiris Roadmap
  - Places M1 in context of overall product evolution
  - Shows progression from M0 (foundation) to M1 (registry) to M2+ (advanced features)

### Planning Documents
- **[Post-0.1.1 Implementation Plan](../post_0.1.1_plan.md)**: Detailed technical implementation
- **[Development Plan](../dev-plan.md)**: Timeline and resource allocation
