# ADR-0026: E2B Transparent Proxy

## Status
Accepted

## Context
The current approach to E2B execution uses nested sessions, which introduces several issues. These include incorrect artifact paths, duplication of log lines, and differences in log output between local and E2B runs. This situation complicates analysis and reduces the reliability of results. There is a need to unify local and E2B execution to ensure consistency, easier management, and better integration with other tools.

The nested session model causes complexity in maintaining session state and artifacts, leading to discrepancies in the user experience and data integrity. Moreover, the duplication of logs and artifacts makes it harder to trace execution flow and debug issues effectively. A more deterministic and transparent handling of sessions is required to improve the overall reliability and maintainability of the pipeline.

## Decision
We will adopt a transparent proxy architecture for E2B execution:

- The E2B sandbox will no longer spawn a nested `osiris run`.
- Instead, the host will pass the session ID, manifest, and configuration directly to the sandbox.
- The sandbox will execute steps deterministically but will write logs and artifacts under a single session ID.
- The structure of logs and artifacts will be identical between local and E2B runs.
- The E2B adapter will remain but serve only as a transport layer, forwarding commands and data without altering session management.

This approach ensures that the session management is centralized and consistent across environments, eliminating the nested session complexity. It preserves the contract between local and remote execution, making third-party integrations straightforward and reliable.

## Consequences
- Advantages:
  - Full parity between local and E2B runs.
  - Clean and unified log history without duplication.
  - Simplified HTML report generation due to consistent session data.
  - Improved integration for third-party tools with a single, consistent contract.

- Risks:
  - Increased complexity in implementing the E2B client.
  - Necessity to carefully handle session data transmission to avoid inconsistencies.
  - Potential challenges in migrating existing workflows to the new model.

- Eliminates nested sessions, simplifying session lifecycle management.
- Enables deterministic and transparent execution across environments.

## Alternatives Considered
- Option 1: Passing session ID as a quick hack. This approach is fast to implement but does not fully resolve the underlying issues.
- Option 2: Direct invocation of drivers. This provides better control but introduces complexity and reduces modularity.
- Option 3: Transparent proxy (chosen). This preserves the existing contract, ensures full parity, and simplifies integration while addressing the core issues.

## Related ADRs
- ADR-0010: Superseded by this ADR (Transparent Proxy replaces Nested Session model).
