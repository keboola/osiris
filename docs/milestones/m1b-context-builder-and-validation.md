# Milestone M1b: Context Builder and Validation

## Status
⏳ **Not Started** (Target: v0.2.0)

## Overview

M1b focuses on bridging the Component Registry (M1a) with the LLM-powered conversational agent to enable accurate, validated pipeline generation. This phase introduces a minimal context export system that provides the LLM with essential component information while managing token usage efficiently.

### Goals

1. **Minimal Context Export**: Extract only essential component information for LLM consumption
2. **Token Efficiency**: Optimize context structure to minimize token usage while maintaining effectiveness  
3. **LLM Integration**: Seamlessly inject component context into prompt templates
4. **Post-Generation Validation**: Validate LLM-generated OML against component specifications
5. **User Feedback**: Provide clear, actionable error messages when generation fails validation

### Deliverables

#### M1b.1: Minimal Component Context Export ✅
- [x] Design minimal context schema optimized for token efficiency
- [x] Extract essential fields: names, required configs, enums, defaults, ≤2 examples
- [x] Implement context builder in `osiris/prompts/build_context.py`
- [x] Add disk caching with spec-based invalidation
- [x] CLI command: `osiris prompts build-context --out .osiris_prompts/context.json`
- [x] Session-aware logging with structured events
- [x] Strict NO-SECRETS guarantee with comprehensive filtering

**Acceptance Criteria**:
- ✅ Context size ≤ 2000 tokens for all 4 components combined (achieved: ~330 tokens)
- ✅ Context rebuilds automatically when component specs change
- ✅ Generated context is valid JSON and follows defined schema
- ✅ Session events emitted: `context_build_start`, `context_build_complete`
- ✅ NO SECRETS in exported context (secret fields excluded, suspicious values redacted)

#### M1b.2: LLM Integration Hooks
- [ ] Update `osiris/core/prompt_manager.py` to load context
- [ ] Inject context into system prompt template
- [ ] Ensure context included in all LLM requests
- [ ] Monitor and report token usage impact
- [ ] Add context versioning for compatibility

**Acceptance Criteria**:
- Context successfully injected into all LLM prompts
- Token usage increase ≤ 15% on average
- No regression in response time (≤3s average)

#### M1b.3: Post-Generation Validation
- [ ] Integrate validation in `osiris/cli/chat.py` after pipeline generation
- [ ] Validate generated OML against component specs from registry
- [ ] Display validation errors with Rich formatting
- [ ] Implement retry mechanism for invalid generations
- [ ] Log validation events to session

**Acceptance Criteria**:
- Invalid field names/types are caught before display
- User sees friendly error messages (using FriendlyErrorMapper from M1a.4)
- Retry mechanism successfully regenerates on validation failure (max 2 retries)
- All validation events logged to session

### Acceptance Criteria (Overall)

1. **Functional Requirements**:
   - [ ] 3 test prompts generate valid OML consistently:
     - Supabase → Supabase with append mode
     - Supabase → Supabase with merge mode  
     - MySQL → Supabase cross-database transfer
   - [ ] Invalid configurations blocked with actionable messages
   - [ ] Context auto-rebuilds when specs change

2. **Performance Requirements**:
   - [ ] Chat response time remains ≤3s including validation
   - [ ] Token usage increase ≤15% with context injection
   - [ ] Context generation completes in <500ms

3. **Quality Requirements**:
   - [ ] Unit test coverage >80% for new code
   - [ ] Integration tests for LLM → validation flow
   - [ ] No regressions in existing chat functionality

### Risks and Mitigations

| Risk | Impact | Mitigation |
|------|---------|------------|
| Token limit exceeded | High | Aggressive context minimization, field filtering |
| LLM ignores context | Medium | Prompt engineering, context positioning experiments |
| Performance degradation | Medium | Caching, lazy loading, async validation |
| Breaking changes to prompt system | Low | Version context schema, maintain compatibility layer |

### Dependencies

- **M1a outputs**: Component Registry APIs, validation system, FriendlyErrorMapper
- **Existing systems**: Conversational agent, prompt manager, chat CLI
- **ADRs**: 
  - [ADR-0007: Component Specification and Capabilities](../adr/0007-component-specification-and-capabilities.md)
  - [ADR-0008: Component Registry](../adr/0008-component-registry.md) (see Amendment re: discover CLI deferral to M1d)
- **Future dependency**: M1d (Pipeline Runner) is required for `osiris components discover` CLI implementation
- **IMPORTANT**: M1b contains NO RUNNER LOGIC - all execution capabilities are deferred to M1d

### Implementation Notes

1. **Context Schema Design**: 
   - Prioritize fields LLMs commonly mistake (e.g., `url` vs `uri`, `key` vs `api_key`)
   - Include enum values inline to prevent hallucination
   - Provide 1-2 minimal examples per component
   - **NO SECRETS**: Context export forbids secrets (redaction handled at source by registry)

2. **Token Optimization**:
   - Use abbreviated field descriptions
   - Compress JSON structure (no pretty printing in prompts)
   - Consider component-specific contexts for focused queries
   - **Token limits**: Target <2000 tokens using GPT-4 tokenizer (tiktoken cl100k_base)

3. **Validation Integration**:
   - Validation should be non-blocking (warn but allow override)
   - Cache validation results to avoid repeated checks
   - Provide "fix" suggestions based on validation errors
   - **NO RUNNER LOGIC**: M1b contains no component execution or runner logic

4. **Cache Invalidation**:
   - Cache invalidation based on: mtime of spec files + context schema version
   - Fingerprint context with SHA-256 for deterministic invalidation
   - Store cache metadata with generation timestamp and spec versions

5. **Logging Events**:
   - `context_build_start`: When context generation begins
   - `context_build_complete`: With size metrics and token count
   - `validation_start`: When OML validation begins
   - `validation_complete`: With pass/fail status and error count
   - `validation_retry`: When regeneration is triggered

### Success Metrics

- **Accuracy**: >90% of generated pipelines pass validation on first attempt
- **Performance**: No measurable degradation in chat responsiveness
- **Usability**: Users report clearer error messages and fewer failed generations
- **Adoption**: Context system used in 100% of pipeline generation requests

### Timeline

**Estimated Duration**: 2 weeks (10 working days)

- Week 1: M1b.1 (Context Export) + M1b.2 (LLM Integration)
- Week 2: M1b.3 (Validation) + Testing/Documentation

### Next Steps

After M1b completion, proceed to:
- **M1c**: Compiler and Manifest Generation - Transform validated OML to deterministic execution manifests
- **M1d**: Pipeline Runner MVP - Execute compiled manifests locally
  - Will implement the deferred `osiris components discover` CLI from M1a.5
  - Will provide actual component execution capabilities (NO RUNNER LOGIC in M1b)

**Note**: The `osiris components discover <type>` command deferred from M1a.5 will be implemented in M1d alongside the runner infrastructure, as documented in [ADR-0008 Amendment](../adr/0008-component-registry.md#amendment-2025-01-03).
