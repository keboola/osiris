# ADR 0003: Session-Scoped Logging & Artifacts

## Status
Accepted

## Context
The existing global logging approach in Osiris has led to several challenges. Debugging issues is difficult due to intertwined logs from multiple sessions, and there is a lack of per-session traceability. This makes it hard to audit and analyze individual runs or user interactions. Additionally, without session-scoped artifacts, it is cumbersome to bundle and review the outputs, metrics, and logs specific to a particular session.

## Decision
We will implement session-scoped logging and artifact management in Osiris. Each session will have its own dedicated directory under `./logs/<session_id>/`. This directory will contain:

- Structured JSONL logs capturing detailed, timestamped events.
- Metrics specific to the session.
- Bundled artifacts generated during the session.

To facilitate access and analysis, we will provide CLI tooling under `osiris logs ...` commands, enabling users to query, filter, and review session logs effectively. The session-scoped logs and artifacts will also integrate with the discovery cache to improve traceability and reproducibility.

This approach will include masking of secrets within logs to prevent sensitive data leakage.

## Consequences
- Improved debugging and auditability through clear, isolated logs and artifacts per session.
- Enhanced ability to trace and reproduce issues tied to individual sessions.
- Increased storage usage due to per-session log and artifact retention.
- Necessity to implement log retention policies and storage management to handle accumulated data.
- Additional complexity in managing multiple session directories and ensuring secret masking is consistently applied.
