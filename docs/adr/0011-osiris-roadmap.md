

Status Update (2025-09-09):
- M0: Complete (released in v0.1.2)
- M1a.1–M1a.4: Complete
- M1c: Complete (Golden Path)
- New: Milestone M1d (Logs & CLI Unification) added to the near-term plan

# 0011 Osiris Roadmap

## Status
Proposed

## Context
Osiris has reached its first usable MVP phase, capable of generating YAML-based data pipelines through conversational interaction. The architecture is stabilizing, and foundational features like discovery cache, secrets masking, and session-scoped logging are implemented. To sustain momentum and ensure long-term alignment, we need a structured roadmap capturing major milestones and their intent.

## Decision
We adopt a phased roadmap approach that defines clear milestones (M0, M1, …) while remaining flexible to incorporate learning and evolving requirements. Each milestone will include:
- **Theme** (the key capability or area of focus)
- **Deliverables** (tangible features or artifacts)
- **Acceptance Criteria** (tests or validation gates)
- **Impact** (user-facing and architectural benefits)

## Roadmap

### M0 – Foundation Stabilization ✅
- Discovery cache fingerprinting with invalidation
- Connection configuration validation
- Secrets masking (logs and YAML)
- Session-scoped logging & artifacts
- CI workflows, ADR/Milestones documentation, governance
- **Impact**: MVP stabilized, secure, auditable

### M1 – Component Registry & Context-Aware Agent
- Component specs publish config schema and capabilities
- System prompt/context enriched with registry knowledge
- Osiris agent can generate YAML pipelines using registry
- M1d – Logs & CLI Unification: Unify CLI (run vs logs), add HTML Logs Browser, and deprecate legacy runs commands (see ADR-0025).
- **Impact**: Deterministic pipeline generation; extensible component ecosystem

### M2 – Runner Integration
- `osiris run` executes YAML pipelines end-to-end
- E2B sandbox integration for controlled execution
- Unified session artifacts (logs + YAML + results)
- **Impact**: Osiris can execute as well as generate; complete feedback loop

### M3 – Conversational Refinement
- Enhanced conversational agent with memory
- Context-engineering techniques for better prompt grounding
- More robust error handling, clarifications, and UX
- **Impact**: Higher success rate in natural interaction; smoother adoption

### M4 – Process-Oriented Workflows
- Expansion from pure data pipelines to business process workflows
- Ability to compose pipelines into higher-level orchestrations
- Components expose “process contracts” beyond data movement
- **Impact**: Osiris evolves from pipeline tool into process orchestration platform

### M5+ – Future Directions
- Marketplace of components
- Enterprise-grade governance, role-based access, audit trail
- Performance optimizations and scaling
- Integration with additional AI assistants/agents
- **Impact**: Production-grade AI-driven orchestration layer

## Consequences
- Roadmap provides alignment across engineering, product, and stakeholders.
- Explicit milestones make it easier to measure progress and define release scope.
- ADR record ensures roadmap decisions are versioned and auditable.
- Risk: Too rigid milestones may slow iteration, so we explicitly allow scope evolution within phases.
