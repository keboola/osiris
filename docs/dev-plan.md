# Osiris Post-0.1.1 Development Plan

## Overview

This development plan addresses the critical architecture issue identified in v0.1.1: context mismatch between cached database discovery and user requests causing LLM failures. The solution implements a contract-backed pipeline system with component registry, LLM context builder, and canonical run manifests.

## Problem Statement

**Root Cause**: Context mismatch where cached discovery contains different schema (e.g., movies database) but user requests e-commerce data (Supabase-to-Shopify), causing system hangs and empty LLM responses.

**Solution Strategy**: Introduce component specs, fingerprinted caching, and deterministic compilation for reproducible execution.

## Success Metrics

- First-try validity rate: +50-70% vs baseline
- Chat response time: ≤3s E2E (including validation)
- Validation overhead: ≤350ms p50
- Schema-mismatch incidents: eliminated
- Manual edits post-chat: significantly reduced

---

## Milestone M0: Discovery Cache Fingerprinting (Hot-fix) ✅ COMPLETE

**Goal**: Eliminate stale discovery reuse when input options or component specs change.

**Status**: ✅ **COMPLETE** (Released in v0.1.2)
**Owner**: Backend Developer
**Duration**: 1-2 weeks (Actual: 1.5 weeks)
**Priority**: Critical (blocks other milestones)

### Tasks

#### M0.1: Implement Cache Fingerprinting Logic
- **Owner**: Backend Developer  
- **Effort**: 3-4 days
- **Description**: Create SHA-256 fingerprinting for component specs and input options
- **Deliverables**:
  - `osiris/core/cache_fingerprint.py` with canonical JSON serialization
  - Fingerprint functions for component_type, version, connection_ref, input options, spec schema
  - TTL-based cache invalidation logic

#### M0.2: Update Discovery Cache Storage
- **Owner**: Backend Developer
- **Effort**: 2-3 days  
- **Description**: Modify cache storage to include fingerprints and enable invalidation
- **Deliverables**:
  - Updated cache entry schema with fingerprint metadata
  - Cache lookup with fingerprint validation
  - Automatic invalidation on fingerprint mismatch

#### M0.3: Basic Connection Config Validation
- **Owner**: Backend Developer
- **Effort**: 2-3 days
- **Description**: Add JSON Schema validation for connection configurations
- **Deliverables**:
  - JSON Schema definitions for mysql/supabase connections
  - Integration with `osiris run` command
  - `--mode warn|strict|off` validation flags

### Acceptance Criteria ✅
- [x] Cache invalidates when component options change (schema, table, columns)
- [x] Cache invalidates when component spec schema changes
- [x] Basic validation catches missing required fields (connection, table, mode)
- [x] `OSIRIS_VALIDATION=off` bypass works for rollback
- [x] Unit tests cover positive/negative fingerprinting scenarios
- [x] Integration test shows cache miss after options change

### Definition of Done ✅
- ✅ All tests pass
- ✅ Cache fingerprinting eliminates stale discovery reuse
- ✅ Basic validation provides clear error messages
- ✅ Rollback mechanism tested and documented

---

## Milestone M1a: Component Registry Foundation

**Goal**: Self-describing components with JSON Schema validation and friendly error messages.

**Owner**: Backend Developer + DevOps Engineer
**Duration**: 2-3 weeks
**Priority**: High (enables M2)

### Tasks

#### M1a.1: Component Spec Schema Design
- **Owner**: Backend Developer
- **Effort**: 3-4 days
- **Description**: Create JSON Schema for component specification cards
- **Deliverables**:
  - `components/spec.schema.json` with apiVersion, kind, configSchema structure
  - Validation for required fields, modes, capabilities
  - Extension points for future constraint systems

#### M1a.2: Bootstrap Component Specs (Manual)
- **Owner**: Backend Developer
- **Effort**: 4-5 days
- **Description**: Analyze existing connectors and hand-write initial component specs
- **Deliverables**:
  - `components/mysql.table/spec.yaml` based on existing mysql connector code
  - `components/supabase.table/spec.yaml` based on existing supabase connector code
  - Minimal examples and capability declarations

#### M1a.3: Component Registry Implementation
- **Owner**: Backend Developer
- **Effort**: 5-6 days
- **Description**: Build component spec loader, validator, and CLI interface
- **Deliverables**:
  - `osiris/components/registry.py` with spec loading and validation
  - CLI commands: `osiris components list`, `osiris components spec <type>`
  - JSON Schema validation integration

#### M1a.4: Friendly Error Mapper
- **Owner**: Backend Developer
- **Effort**: 3-4 days
- **Description**: Convert cryptic JSON Schema errors to actionable user guidance
- **Deliverables**:
  - Error mapping table for common validation failures
  - Human-readable error messages with why/how-to-fix/examples
  - Integration with validation pipeline

#### M1a.5: CLI Integration
- **Owner**: DevOps Engineer
- **Effort**: 2-3 days
- **Description**: Add component management commands to CLI
- **Deliverables**:
  - `osiris/cli/components_cmd.py` with list/spec subcommands
  - Integration with existing CLI structure
  - Help text and usage examples

### Acceptance Criteria
- [ ] `osiris components list` shows both mysql.table and supabase.table with capabilities
- [ ] `osiris components spec mysql.table --format=json` outputs valid schema
- [ ] Invalid OML configuration shows friendly error with fix suggestion
- [ ] Component specs validate against spec.schema.json
- [ ] Registry loads specs from filesystem with caching
- [ ] Unit tests cover positive/negative validation paths

### Definition of Done
- Component registry loads and validates specs correctly
- CLI commands work with proper error handling
- Friendly error messages guide users to fixes
- Comprehensive test coverage for registry and validation

---

## Milestone M2: LLM Context Builder

**Goal**: Export minimal component context to LLM system prompt for valid OML generation.

**Owner**: AI/ML Engineer + Backend Developer
**Duration**: 2-3 weeks
**Priority**: High (critical for LLM improvement)

### Tasks

#### M2.1: Context Export Design
- **Owner**: AI/ML Engineer
- **Effort**: 2-3 days
- **Description**: Design minimal context format for LLM consumption
- **Deliverables**:
  - Context schema with component names, required fields, enums, defaults
  - ≤2 examples per component for token efficiency
  - Context size analysis and optimization strategy

#### M2.2: Context Builder Implementation  
- **Owner**: Backend Developer
- **Effort**: 4-5 days
- **Description**: Build context exporter from component registry
- **Deliverables**:
  - `osiris/prompts/build_context.py` with registry integration
  - CLI: `osiris prompts build-context --out .osiris_prompts/context.json`
  - Disk caching with mtime-based invalidation

#### M2.3: Prompt Manager Integration
- **Owner**: AI/ML Engineer  
- **Effort**: 3-4 days
- **Description**: Wire exported context into conversational agent
- **Deliverables**:
  - Update `osiris/core/prompt_manager.py` to load context
  - System prompt templating with component context
  - Context inclusion in LLM requests

#### M2.4: Post-Generation Validation
- **Owner**: Backend Developer
- **Effort**: 3-4 days
- **Description**: Validate LLM-generated OML against component specs
- **Deliverables**:
  - Integration with `osiris/cli/chat.py` for OML validation
  - Validation error display with actionable messages
  - Retry mechanism for invalid generations

#### M2.5: Chat Flow Enhancement
- **Owner**: AI/ML Engineer
- **Effort**: 2-3 days
- **Description**: Improve chat experience with validation feedback
- **Deliverables**:
  - Clear validation error display in Rich formatting
  - Guided correction prompts for common mistakes
  - Context-aware retry suggestions

### Acceptance Criteria
- [ ] 3 guided chat prompts (Supabase→Supabase append/merge, MySQL→Supabase merge) produce valid OML
- [ ] Invalid fields are blocked (cannot use fields not in configSchema)
- [ ] Context export includes only essential information for token efficiency
- [ ] Validation errors provide actionable fix suggestions
- [ ] Chat response time remains ≤3s including validation
- [ ] Context rebuilds automatically when specs change

### Definition of Done
- Context builder exports minimal, effective LLM context
- Chat validation blocks invalid OML with helpful errors
- LLM generation success rate improves significantly
- Token usage stays within acceptable limits

---

## Milestone M3: Compile & Run MVP

**Goal**: Deterministic execution pipeline with canonical Run Manifests for local and e2b execution.

**Owner**: Backend Developer + DevOps Engineer + Security Engineer
**Duration**: 3-4 weeks
**Priority**: Medium (enables full workflow)

### Tasks

#### M3.1: OML Schema Definition
- **Owner**: Backend Developer
- **Effort**: 2-3 days
- **Description**: Define minimal OML v0.0.1 schema for MVP
- **Deliverables**:
  - OML JSON Schema with version, name, sources, sinks, params
  - Validation rules and constraints
  - Migration path from existing YAML format

#### M3.2: Compiler Implementation
- **Owner**: Backend Developer
- **Effort**: 6-7 days
- **Description**: Build OML to Run Manifest compiler
- **Deliverables**:
  - `osiris/compile.py` with deterministic compilation
  - `osiris compile pipeline.yaml --out cfg/` CLI command
  - Per-step JSON config generation
  - Canonical Run Manifest YAML output

#### M3.3: Secrets Management
- **Owner**: Security Engineer
- **Effort**: 4-5 days
- **Description**: Implement secure secrets handling
- **Deliverables**:
  - `osiris/secrets.py` with ENV and --secrets-file support
  - Connection reference resolution (@mysql, @supabase)
  - No secrets in manifests/logs policy enforcement
  - Secrets rotation support for long-running jobs

#### M3.4: Local Runner Engine
- **Owner**: Backend Developer
- **Effort**: 5-6 days
- **Description**: Execute Run Manifests locally with existing connectors
- **Deliverables**:
  - `osiris/run/runner.py` orchestration engine
  - `osiris/run/engines/local.py` with connector integration
  - JSONL logging with run_id, step, metrics
  - Artifact generation (metrics.json, manifest.yaml)

#### M3.5: e2b Runner Engine
- **Owner**: DevOps Engineer
- **Effort**: 4-5 days
- **Description**: Remote execution via e2b Python SDK
- **Deliverables**:
  - `osiris/run/engines/e2b.py` with API key management
  - Config/manifest upload and execution
  - Log streaming from sandbox
  - Exit code and artifact handling

#### M3.6: CLI Integration & Testing
- **Owner**: DevOps Engineer
- **Effort**: 3-4 days
- **Description**: Complete CLI integration with comprehensive testing
- **Deliverables**:
  - `osiris run <pipeline.yaml>` with engine selection
  - Parameter passing and secrets file handling
  - Integration tests with docker-compose for MySQL/Supabase
  - E2E CLI testing with mocked e2b

### Acceptance Criteria
- [ ] `osiris compile` generates cfg/*.json + cfg/manifest.yaml from OML
- [ ] `osiris run --engine=local` executes data movement (append/merge)
- [ ] `osiris run --engine=e2b` uploads and executes in sandbox
- [ ] No secrets appear in manifests, logs, or artifacts
- [ ] JSONL logs contain run_id, step, duration, row counts
- [ ] Exit codes are meaningful (0=success, 2=validation, 3=compile, 4=run, 5=config)
- [ ] Generated manifests are deterministic and reproducible

### Definition of Done
- Complete compile → manifest → run workflow functional
- Both local and e2b execution engines working
- Comprehensive logging and artifact generation
- Security review passed for secrets handling
- Full integration test suite passing

---

## Cross-Milestone Considerations

### Dependencies
- **M1a blocks M2**: Context builder requires component specs
- **M2 enhances M0**: Better LLM context reduces cache mismatches
- **M3 consumes M1a+M2**: Compiler validates against specs, runner uses context

### Risk Mitigation
- **Rollback strategy**: `OSIRIS_VALIDATION=off` flag for each milestone
- **Backward compatibility**: Existing YAML pipelines continue working
- **Performance monitoring**: SLO tracking throughout implementation
- **User communication**: Migration guide and deprecation warnings

### Testing Strategy
- **Unit tests**: Registry, validation, compiler, runner components
- **Integration tests**: Docker-compose for real database testing
- **E2E tests**: Full compile→run workflow with golden file validation
- **Performance tests**: Response time and validation overhead measurement

### Documentation Requirements
- Migration guide for users upgrading from v0.1.x
- Component spec authoring guide for new connectors
- Troubleshooting guide for validation errors
- ADR documentation for architectural decisions

---

## Implementation Schedule

| Milestone | Duration | Dependencies | Risk Level | Status |
|-----------|----------|--------------|------------|--------|
| M0        | 1-2 weeks| None         | Low        | ✅ COMPLETE (v0.1.2) |
| M1a       | 2-3 weeks| M0 complete  | Medium     | 🔄 Next Priority |
| M2        | 2-3 weeks| M1a complete | Medium     | ⏳ Pending |
| M3        | 3-4 weeks| M1a+M2 complete | High    | ⏳ Pending |

**Total Timeline**: 8-12 weeks for complete implementation
**Progress**: Week 2 of 12 complete (M0 delivered)

## Resource Allocation

- **Backend Developer**: Lead on M0, M1a, M2.2, M2.4, M3.1, M3.2, M3.4 (60% allocation)
- **AI/ML Engineer**: Lead on M2.1, M2.3, M2.5 (30% allocation)  
- **DevOps Engineer**: Lead on M1a.5, M3.5, M3.6 (25% allocation)
- **Security Engineer**: Lead on M3.3 (15% allocation)

## Quality Gates

Each milestone must pass:
- [ ] All acceptance criteria met
- [ ] Unit test coverage >80%
- [ ] Integration tests passing
- [ ] Performance SLOs within bounds
- [ ] Security review (where applicable)
- [ ] Documentation updated

## Next Steps

1. ~~**Week 1**: Begin M0 implementation with cache fingerprinting~~ ✅ COMPLETE
2. ~~**Week 2**: Complete M0 and begin component spec analysis for M1a~~ ✅ M0 COMPLETE
3. **Week 3-4**: M1a implementation with bootstrap component specs 🔄 **CURRENT FOCUS**
   - Begin with component spec schema design (M1a.1)
   - Manual bootstrap of mysql.table and supabase.table specs (M1a.2)
   - Component registry implementation (M1a.3)
4. **Week 5-6**: M2 context builder and LLM integration
5. **Week 7-10**: M3 compiler and runner implementation
6. **Week 11-12**: Final integration testing and documentation
