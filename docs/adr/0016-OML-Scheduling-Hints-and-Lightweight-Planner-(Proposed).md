# ADR 0016: OML Scheduling Hints & Lightweight Planner (Proposed)

## Status
Proposed

## Context
After M1c, Osiris may benefit from **optional scheduling hints** in OML and a **lightweight planner** that interprets these hints to inform local run ordering. We do *not* want a heavy scheduler yet, and the compiler must remain deterministic. Hints must be non‑authoritative and never change manifest semantics; they may help the runner choose a better order or emit warnings.

## Decision
Introduce a small, backward‑compatible set of fields and a minimal planner module:

### OML Extensions (all optional)
- Top‑level `hints`:
  - `priority`: `"low"|"normal"|"high"`
  - `freshness_sla_ms`: integer (desired data freshness)
  - `deadline_at`: RFC3339 timestamp string
- Per‑step `hints`:
  - `priority`: `"low"|"normal"|"high"`
  - `cost_estimate`: number (abstract units)
  - `runs_after`: array&lt;string&gt; (soft ordering; compiler still uses `needs` for hard edges)

These fields are **ignored by the compiler** when producing the manifest DAG. They are copied verbatim into `manifest.yaml` under `steps[].hints` and `pipeline.hints` for the runner to consume.

### Lightweight Planner
- Module: `osiris/core/planner.py`
- Inputs: manifest, current system load, optional CLI flags.
- Output: an **execution schedule** that respects `needs` but can choose step ordering among ready nodes using:
  - priority (high first),
  - cost (small first or CLI‑selectable policy),
  - freshness/deadline warnings (log if violated).
- Deterministic policy by default (tie‑break lexically by `step.id`).

## Consequences
- Gives users a vocabulary to express intent without controlling the DAG.
- Keeps compiler pure; hints are advisory and deterministic to serialize.
- Allows future evolution toward a proper scheduler without breaking OML.

## Alternatives
- Encode hints as labels/tags only — lacks structure and formalism.
- Build a full scheduler now — premature and outside 0.x scope.

## Rollout
- Add schema support (optional fields).
- Copy hints into manifest.
- Implement planner and enable via `osiris run --planner=light`.
- Document in milestone and CHANGELOG.

## References
- ADR‑0014, ADR‑0015
