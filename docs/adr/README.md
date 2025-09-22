# Architecture Decision Records (ADRs)

## Release v0.2.0 Status

| ADR ID | Title | Status |
|--------|-------|--------|
| ADR-0013 | Chat Retry Policy | Accepted |
| ADR-0019 | Chat State Machine | Accepted |
| ADR-0020 | Connection Resolution | Accepted |
| ADR-0022 | Streaming IO | Deferred (planned M2) |
| ADR-0023 | Remote Object Store | Deferred (planned M2) |
| ADR-0025 | CLI UX Unification | Accepted |
| ADR-0026 | E2B Transparent Proxy | Accepted |
| ADR-0027 | Run Export Context Builder | Partially Accepted |

Status values reflect the v0.2.0 implementation state (see each ADR for details and milestone notes).

## Complete ADR Index

| ADR ID | Title | Status | Date | Link |
|--------|-------|--------|------|------|
| ADR-0001 | Logging Configuration | Implemented | | [0001-logging-configuration.md](0001-logging-configuration.md) |
| ADR-0002 | Discovery Cache Fingerprinting | Implemented | | [0002-discovery-cache-fingerprinting.md](0002-discovery-cache-fingerprinting.md) |
| ADR-0003 | Session-Scoped Logging & Artifacts | Implemented | | [0003-session-scoped-logging.md](0003-session-scoped-logging.md) |
| ADR-0004 | Configuration Precedence Engine | Implemented | | [0004-configuration-precedence-engine.md](0004-configuration-precedence-engine.md) |
| ADR-0005 | Component Specification and Registry | Accepted | | [0005-component-specification-and-registry.md](0005-component-specification-and-registry.md) |
| ADR-0006 | Pipeline Runner and Execution | Implemented | | [0006-pipeline-runner-and-execution.md](0006-pipeline-runner-and-execution.md) |
| ADR-0007 | Component Specification and Capabilities | Accepted | | [0007-component-specification-and-capabilities.md](0007-component-specification-and-capabilities.md) |
| ADR-0008 | Component Registry | Accepted | | [0008-component-registry.md](0008-component-registry.md) |
| ADR-0009 | Secrets Handling Strategy | Accepted | | [0009-secrets-handling-strategy.md](0009-secrets-handling-strategy.md) |
| ADR-0010 | E2B Integration for Pipeline Execution | Superseded by ADR-0026 | | [0010-e2b-integration-for-pipeline-execution.md](0010-e2b-integration-for-pipeline-execution.md) |
| ADR-0011 | Osiris Roadmap | Implemented | | [0011-osiris-roadmap.md](0011-osiris-roadmap.md) |
| ADR-0012 | Separate Extractors and Writers | Proposed | | [0012-separate-extractors-and-writers.md](0012-separate-extractors-and-writers.md) |
| ADR-0013 | Chat Retry Policy for Post-Generation Validation | Accepted | | [0013-chat-retry-policy.md](0013-chat-retry-policy.md) |
| ADR-0014 | OML v0.1.0 — Intent Schema & Guardrails | Implemented | | [0014-OML_v0.1.0-scope-and-schema.md](0014-OML_v0.1.0-scope-and-schema.md) |
| ADR-0015 | Compile Contract — Determinism, Fingerprints & No-Secrets | Implemented | | [0015-compile-contract-determinism-fingerprints-nosecrets.md](0015-compile-contract-determinism-fingerprints-nosecrets.md) |
| ADR-0016 | OML Scheduling Hints & Lightweight Planner | Proposed | | [0016-OML-Scheduling-Hints-and-Lightweight-Planner-(Proposed).md](0016-OML-Scheduling-Hints-and-Lightweight-Planner-(Proposed).md) |
| ADR-0017 | Memory Store Abstraction | Proposed | | [0017-Memory-Store-Abstraction-(Proposed).md](0017-Memory-Store-Abstraction-(Proposed).md) |
| ADR-0018 | Agent-Call Adapter | Proposed | | [0018-Agent-Call-Adapter-(Proposed).md](0018-Agent-Call-Adapter-(Proposed).md) |
| ADR-0019 | Chat State Machine and OML Synthesis | Accepted | | [0019-chat-state-machine-and-oml-synthesis.md](0019-chat-state-machine-and-oml-synthesis.md) |
| ADR-0020 | Connection Resolution and Secrets | Accepted | | [0020-connection-resolution-and-secrets.md](0020-connection-resolution-and-secrets.md) |
| ADR-0021 | Component Health Check Capability | Accepted | | [0021-component-health-check-capability.md](0021-component-health-check-capability.md) |
| ADR-0022 | Streaming IO and Spill | Deferred | | [0022-streaming-io-and-spill.md](0022-streaming-io-and-spill.md) |
| ADR-0023 | Remote Object Store Writers | Deferred | | [0023-remote-object-store-writers.md](0023-remote-object-store-writers.md) |
| ADR-0024 | Component Packaging as Osiris Plugins (OCP Model) | Proposed | | [0024-component-packaging.md](0024-component-packaging.md) |
| ADR-0025 | CLI UX Unification (Run vs Logs) | Accepted | | [0025-cli-ux-unification.md](0025-cli-ux-unification.md) |
| ADR-0026 | E2B Transparent Proxy | Accepted | | [0026-e2b-transparent-proxy.md](0026-e2b-transparent-proxy.md) |
| ADR-0027 | Run Export Context for AI | Partially Accepted | | [0027-run-export-context-for-AI.md](0027-run-export-context-for-AI.md) |
| ADR-0028 | Git Project Structure & Reproducibility | Proposed | | [0028-git-integration.md](0028-git-integration.md) |
| ADR-0029 | Osiris Memory Store | Proposed | | [0029-memory.md](0029-memory.md) |
| ADR-0030 | Agentic OML Generation | Proposed | | [0030-agents.md](0030-agents.md) |
| ADR-0031 | OML Control Flow and Conditional Execution | Proposed | | [0031-oml-control-flow.md](0031-oml-control-flow.md) |
| ADR-0032 | Runtime Parameters and Environment Profiles | Proposed | | [0032-runtime-parameters-profiles.md](0032-runtime-parameters-profiles.md) |
| ADR-0033 | Pipeline Resilience and Retry Policies | Proposed | | [0033-resilience-retry-policies.md](0033-resilience-retry-policies.md) |

## What are ADRs?

Architecture Decision Records (ADRs) are documents that capture important decisions about the architecture and design of a project. They serve as a historical record of why certain choices were made, providing context and reasoning that help current and future contributors understand the system's evolution.

## Purpose of ADRs

The primary purpose of ADRs is to document architectural decisions clearly and concisely. This helps prevent knowledge loss, facilitates communication among team members, and supports better decision-making by providing a reference for past decisions.

## Process of Creating ADRs

1. **Identify the decision**: When a significant architectural or design decision needs to be made, create an ADR to document it.
2. **Write the ADR**: Use a clear and consistent format to describe the context, the decision itself, the alternatives considered, and the consequences.
3. **Review and Approve**: Share the ADR with the team for feedback and approval.
4. **Store and Maintain**: Save the ADR in the designated ADR directory within the project repository for easy access and future reference.

## Naming Conventions

Each ADR should have a unique identifier and a descriptive title. The recommended naming format is:

```
NNNN-title.md
```

- `NNNN` is a zero-padded sequential number (e.g., 0001, 0002).
- `title` is a short, lowercase, hyphen-separated description of the decision.

For example: `0001-use-postgresql-for-database.md`

## When to Create a New ADR

Create a new ADR whenever:

- A new architectural or design decision is made that impacts the system.
- An existing decision needs to be revised or replaced.
- Alternatives are considered, and a rationale for the chosen approach needs to be documented.

By maintaining a well-organized set of ADRs, contributors can ensure that the project's architectural history is transparent and accessible, aiding in consistent and informed development.
