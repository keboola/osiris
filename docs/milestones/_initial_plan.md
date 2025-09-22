# Initial Plan

**Status**: Historical Reference  
**Created**: 2025-09-04  
**Purpose**: Consolidated development planning for post-0.1.1 architecture improvements

## Goals

### Primary Objective
Eliminate context mismatch between cached database discovery and user requests causing LLM failures by implementing a contract-backed pipeline system with component registry, LLM context builder, and canonical run manifests.

### Success Metrics
- [ ] First-try validity rate: +50-70% vs baseline
- [ ] Chat response time: ≤3s E2E (including validation)
- [ ] Validation overhead: ≤350ms p50
- [ ] Schema-mismatch incidents: eliminated
- [ ] Manual edits post-chat: significantly reduced

## Deliverables

### M0: Discovery Cache Fingerprinting ✅
**Status**: Complete (Released in v0.1.2)
- [x] SHA-256 fingerprinting for component specs and input options
- [x] TTL-based cache invalidation logic
- [x] JSON Schema validation for connection configurations
- [x] Validation modes: `--mode warn|strict|off` with ENV override support

### M1a: Component Registry Foundation
**Status**: Next Priority
- [ ] Component spec schema design (JSON Schema Draft 2020-12)
- [ ] Bootstrap component specs for mysql.table and supabase.table
- [ ] Component registry implementation with spec loading and validation
- [ ] Friendly error mapper for actionable user guidance
- [ ] CLI integration: `osiris components list|spec`

### M1b: Post-Generation Validation ✅
**Status**: Complete (v0.1.2)
- [x] Integration with conversational agent for OML validation
- [x] Validation retry mechanism with bounded attempts
- [x] Retry trail artifacts and structured logging
- [x] Test harness for automated validation scenarios

### M2: LLM Context Builder
**Status**: Pending
- [ ] Context export design for minimal LLM consumption
- [ ] Context builder implementation from component registry
- [ ] Prompt manager integration with exported context
- [ ] Post-generation validation in chat flow
- [ ] Token usage optimization

### M3: Compile & Run MVP
**Status**: Pending
- [ ] OML v0.0.1 schema definition
- [ ] Compiler: OML → Run Manifest
- [ ] Secrets management with ENV and --secrets-file support
- [ ] Local runner engine with existing connectors
- [ ] e2b runner engine via Python SDK
- [ ] JSONL logging and artifact generation

## Acceptance Criteria

### Component Registry (M1a)
- [ ] `osiris components list` shows mysql.table and supabase.table with capabilities
- [ ] `osiris components spec <type>` outputs valid JSON Schema
- [ ] Invalid OML configuration shows friendly error with fix suggestion
- [ ] Component specs validate against spec.schema.json
- [ ] Unit tests cover positive/negative validation paths

### Context Builder (M2)
- [ ] 3 guided chat prompts produce valid OML without manual fixes
- [ ] Invalid fields are blocked with actionable error messages
- [ ] Context export includes only essential information for token efficiency
- [ ] Validation errors provide actionable fix suggestions
- [ ] Chat response time remains ≤3s including validation
- [ ] Context rebuilds automatically when specs change

### Compile & Run (M3)
- [ ] `osiris compile` generates cfg/*.json + cfg/manifest.yaml from OML
- [ ] `osiris run --engine=local` executes data movement (append/merge)
- [ ] `osiris run --engine=e2b` uploads and executes in sandbox
- [ ] No secrets appear in manifests, logs, or artifacts
- [ ] JSONL logs contain run_id, step, duration, row counts
- [ ] Exit codes are meaningful (0=success, 2=validation, 3=compile, 4=run, 5=config)

## Risks

### Technical Risks
- **Component Registry Complexity**: Custom constraint system may be overkill for MVP
  - *Mitigation*: Start with pure JSON Schema validation, add constraints only if needed
- **LLM Token Usage**: Context export may consume excessive tokens
  - *Mitigation*: Keep context minimal with only required fields and ≤2 examples
- **Performance Regression**: Validation overhead may impact chat responsiveness
  - *Mitigation*: Cache compiled context, lazy-load only referenced components

### Operational Risks
- **Breaking Changes**: New validation may break existing pipelines
  - *Mitigation*: Default to warn mode, provide `OSIRIS_VALIDATION=off` escape hatch
- **User Adoption**: Complex new CLI commands may confuse users
  - *Mitigation*: Maintain backward-compatible aliases, clear migration guide

## Dependencies

### Internal Dependencies
- **M1a blocks M2**: Context builder requires component specs
- **M2 enhances M0**: Better LLM context reduces cache mismatches
- **M3 consumes M1a+M2**: Compiler validates against specs, runner uses context

### External Dependencies
- **LLM Providers**: OpenAI, Anthropic, Google APIs must remain stable
- **Database Access**: Test databases (MySQL, Supabase) required for integration testing
- **e2b Platform**: Remote execution service availability

## Notes

### Product Strategy Clarification
- **Near-term focus**: Stabilize conversational pipeline generator with minimal validation
- **Later expansion**: Multi-agent plumbing, process workflows, advanced analytics
- **Non-goals for v0.1.x**: No distributed event bus, no heavy DSL, not replacing Airflow/Prefect

### Implementation Approach
- **Backward Compatibility**: Keep YAML shape, treat OML as "Osiris YAML dialect"
- **Incremental Validation**: Start with required/enum/defaults, add constraints later
- **Hybrid Compilation**: Direct execution for simple pipelines, explicit compile for complex
- **Security Posture**: Secrets referenced not inlined, spec-driven redaction

### Architecture Decisions
- **Component Bootstrap**: Hand-write initial specs, add code-generation tooling later
- **Validation Timing**: Both prompt-time constraints and post-generation validation
- **Cache Strategy**: Fingerprint-based invalidation with TTL fallback
- **Error Philosophy**: Map technical errors to actionable user guidance

### Testing Strategy
- **Unit Tests**: Registry, validation, compiler, runner components (>80% coverage)
- **Integration Tests**: Docker-compose for real database testing
- **E2E Tests**: Full compile→run workflow with golden file validation
- **Performance Tests**: Response time and validation overhead measurement

### Migration Path
1. **Week 1-2**: ✅ Discovery cache fingerprinting (M0 complete)
2. **Week 3-4**: Component registry with bootstrap specs (M1a)
3. **Week 5-6**: Context builder and LLM integration (M2)
4. **Week 7-10**: Compiler and runner implementation (M3)
5. **Week 11-12**: Final integration testing and documentation

### Resource Allocation
- **Backend Developer**: 60% - Lead on registry, compiler, runner
- **AI/ML Engineer**: 30% - Lead on context builder, prompt integration
- **DevOps Engineer**: 25% - Lead on CLI, e2b integration
- **Security Engineer**: 15% - Lead on secrets management

### Quality Gates
Each milestone must pass:
- [ ] All acceptance criteria met
- [ ] Unit test coverage >80%
- [ ] Integration tests passing
- [ ] Performance SLOs within bounds
- [ ] Security review (where applicable)
- [ ] Documentation updated

## References

### Related Documents
- [ADR-0013: Chat Retry Policy](../adr/0013-chat-retry-policy.md)
- [M1b: Context Builder and Validation](m1b-context-builder-and-validation.md)
- [Component Registry Design](../adr/component-registry-design.md) *(planned)*
- [Canonical Run Manifest](../adr/canonical-run-manifest.md) *(planned)*

### Implementation Files
- `osiris/core/cache_fingerprint.py` - Discovery cache fingerprinting (M0)
- `osiris/components/registry.py` - Component registry (M1a)
- `osiris/prompts/build_context.py` - Context exporter (M2)
- `osiris/compile.py` - OML compiler (M3)
- `osiris/run/runner.py` - Execution orchestrator (M3)

### PR Checklist Template
Use for every PR to enforce core guarantees:
- [ ] Component specs ship with `components/<type>/spec.yaml`
- [ ] `osiris compile` produces canonical Run Manifest (no secrets)
- [ ] `osiris run` works locally and via e2b with meaningful exit codes
- [ ] Logs are JSONL with run_id, step, duration_ms, row counts
- [ ] No secrets in code, logs, or manifest
- [ ] Tests added/updated with >80% coverage
- [ ] Docs updated under Diátaxis structure
- [ ] CHANGELOG.md entry added
