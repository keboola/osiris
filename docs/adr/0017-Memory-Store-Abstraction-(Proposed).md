
# ADR 0017: Memory Store Abstraction (Proposed)

## Status
Proposed

## Context
Pipelines need a reliable place to store small, long‑lived artifacts: schema snapshots, fingerprints, retry trails, embeddings, and cross‑run metadata. We want a **pluggable memory store** that is simple at first (local filesystem) but can grow (S3/GCS, SQLite/Postgres) without changing OML or manifests.

## Decision
Define a minimal interface and default implementation.

### Interface
- Namespace: `osiris/core/memory_store.py`
- Abstraction: 
  - `put(namespace: str, key: str, data: bytes, content_type?: str) -> Digest`
  - `get(namespace: str, key: str) -> bytes`
  - `exists(namespace: str, key: str) -> bool`
  - `list(namespace: str, prefix: str) -> Iterator[Entry]`
  - `delete(namespace: str, key: str) -> None`
- All writes are **content‑addressed**; the returned digest (SHA‑256) is recorded in logs/artifacts.

### Default Backend
- Local filesystem under `.osiris_store/` with subfolders by namespace.
- Metadata sidecar `*.meta.json` for content type and digest.

### Usage Examples
- Store compile fingerprints and `meta.json` copies for provenance.
- Persist retry trails/HITL summaries for later inspection.
- Cache schema samples for validation tests.

### Security
- Never store secrets; enforce redaction on writes.
- Optional encryption at rest can be added later.

## Consequences
- Stable place for cross‑run knowledge without introducing a database dependency now.
- Clear upgrade path to cloud backends.

## Alternatives
- Reuse session log directory only — ephemeral and poorly indexed.
- Push to an external DB now — adds ops burden too early.

## References
- ADR‑0009 (Secrets)
- ADR‑0013 (Retry)
- ADR‑0015 (Compile)
