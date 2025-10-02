# ADR-0034: E2B Runtime Unification with Local Runner

## Status
Proposed

## Context
Currently, E2B execution uses a ProxyWorker that serializes DataFrames to pickle/parquet files and reloads them between steps.
Local Runner keeps DataFrames in memory and passes them directly. This causes divergence: different performance, different artifacts, and added complexity.

## Decision
Unify E2B runtime with Local Runner semantics as much as possible:
- Remove pickle-based spill as the default path.
- Introduce an optional Docker-based or microVM-based mode to execute pipelines 1:1 with local Python semantics inside E2B.
- Ensure telemetry, artifact handling, and step execution behave identically across local and E2B runs.

## Consequences
- Simplifies architecture: one runtime model.
- Better performance (no unnecessary serialization).
- Requires design of how to run long-lived in-memory Python processes in E2B sandbox (Docker/microVM).
