# Osiris Pipeline — Overview (v0.2.0)

Osiris is the **deterministic compiler for AI‑native data pipelines**.  
You describe outcomes in plain English; Osiris compiles them into **reproducible, production‑ready manifests** that run with the **same behavior everywhere** (local or cloud).

---

## 1) Executive Summary

**Breakthrough:** Osiris turns **ambiguous, plain‑language intent** into a **deterministic, portable pipeline** — without forcing teams to master a dozen tools. It combines the **creativity of AI** with the **safety of compilers**: same inputs → same outputs, every time.

**Why it matters (value):**
- **AI without chaos.** Guardrails, validation, and deterministic manifests make AI‑assisted pipelines **safe for production**.
- **Speed without fragility.** Idea → compiled pipeline **in minutes**, not weeks; fewer rewrites.
- **Portability without lock‑in.** **Parity adapters** run the same manifest anywhere (local or E2B today; Keboola/Kubernetes on the roadmap).
- **Transparency without toil.** Deep observability and **AI‑ready run bundles** make every run explainable to humans and usable by AI.

**Tagline:** *Osiris is the reliable bridge between human intent and machine execution for AI‑native data work.*

---

## 2) What Makes Osiris Different

- **Compiler, not orchestrator.** Others schedule what you hand‑craft. Osiris **generates, validates, and compiles** pipelines from plain English.
- **Determinism as a contract.** Fingerprinted manifests guarantee **reproducibility** across environments.
- **Conversational → executable.** Analysts, domain experts, and engineers can describe intent; Osiris interrogates real systems and proposes a **feasible** plan.
- **Run anywhere, same results.** Transparent adapters deliver **execution parity** (local and E2B today).
- **Boring by design.** Predictable, explainable, portable — **industrial‑grade** AI, not magical fragility.

---

## 3) Key Capabilities

- **Conversational Pipeline Synthesis.** Describe outcomes; Osiris explores available sources, asks clarifying questions, and synthesizes an **OML** (Osiris Markup Language) pipeline grounded in reality.
- **Deterministic Compiler & Runtime.** OML compiles to a **fingerprinted manifest**. If it compiles, it’s **production‑ready**: validated configs, resolved dependencies, and an execution plan.
- **Transparent Execution Adapters.** Run the same manifest **locally** or in **E2B sandboxes** with identical logs, metrics, and artifacts. *(Roadmap: Keboola, Kubernetes/OpenShift, enterprise schedulers.)*
- **Comprehensive Observability.** Structured **events + metrics**, interactive **HTML reports**, and an **AI‑ready Run Context Bundle** enable post‑mortems and “AI SRE” workflows.
- **Self‑Describing Component Registry.** JSON‑Schema specs power validation, secret masking, and rich LLM context. Adding components is intentionally simple. *(Planned community compatibility: Airbyte, Singer, Mage, Boomi, Keboola connectors.)*

> **Delivered in v0.2.0 (M1):** conversational → OML flow, deterministic compiler, local/E2B parity adapters, HTML reports, component registry, unified CLI.  
> **On the roadmap:** Scheduling & lineage (M2), streaming & parallelism (M3), Iceberg & DWH agent (M4), organizational memory.

---

## 4) How Osiris Works (at a glance)

1. **Chat** – `osiris chat` captures intent (e.g., “Identify customers inactive for 90 days and export a re‑activation list”); Osiris knows your **available connectors** and capability context.
2. **Synthesize OML** – The agent explores schemas, validates assumptions, and proposes an **OML pipeline**.
3. **Compile** – `osiris compile` validates OML and produces a **deterministic manifest** (your source of truth in Git).
4. **Run** – `osiris run` executes via adapters with **full parity** (add `--e2b` for sandboxed cloud execution).
5. **Observe** – `osiris logs html --open` shows interactive reports; the **AI bundle** enables automated analysis.

---

## 5) Who It’s For

- **Data Analysts:** self‑service pipelines without learning a stack.
- **Data Engineers:** standard, reproducible manifests; focus on the hard 10%.
- **ML/AI Teams:** fast, explainable data prep; AI‑ready run artifacts.
- **Leaders:** faster outcomes, fewer incidents, no lock‑in.

---

## 6) Roadmap & Ambition

- **M2 — Production Readiness:** workflows & approvals; **automatic impact analysis**; ownership that mirrors your org; native integration with existing orchestrators.
- **M3 — Technical Scale:** **limitless** scaling via chunking/parallelism; live health & clear cost controls.
- **M4 — Intelligent Persistence:** **Iceberg** tables and a **DWH Agent** that persists/serves datasets for pipelines and AI agents.

Throughout: **transparency, predictability, no vendor lock‑in, outcome‑first**.

---

## 7) License & Positioning

Open source under **Apache 2.0** (core). Run locally, in your cloud, or inside your orchestrator. You **own** what you depend on.

---

## 8) Quick Links

- **Quickstart:** [docs/quickstart.md](quickstart.md)
- **Architecture:** [docs/architecture.md](architecture.md)
- **User Guide:** [docs/user-guide/user-guide.md](user-guide/user-guide.md)
- **Examples:** [docs/examples/](examples/)
- **ADR Index:** [docs/adr/](adr/)
- **Roadmap:** [docs/roadmap/](roadmap/)

---

### Diagram — From Intent to Deterministic Execution

```mermaid
graph TB
    U[User] -->|Plain English| CHAT[osiris chat]
    CHAT --> DISC[Discovery & Feasibility]
    DISC --> OML[OML Spec]
    OML --> COMP[Deterministic Compiler]
    COMP --> M[Fingerprint Manifest]
    M --> RUN[osiris run]
    RUN --> LCL[Local Adapter]
    RUN --> E2B[E2B Adapter]
    LCL --> OBS[Events • Metrics • Artifacts]
    E2B --> OBS
    OBS --> HTML[HTML Report]
    OBS --> AIOP[AI Operation Package]
```

---

## 10) AI Operation Package (AIOP)

### Quickstart: Enable AIOP in 3 Steps

Get AI-friendly pipeline analysis in under 2 minutes:

1. **Enable AIOP** - Run `osiris init` and set `aiop.enabled: true` (default in new installs)
2. **Run any pipeline** - AIOP automatically exports after each run (success or failure)
3. **Find your exports** - Check `logs/aiop/aiop.json` and `logs/aiop/run-card.md`

```bash
# Initialize with AIOP enabled
osiris init
# Edit osiris.yaml: ensure aiop.enabled: true

# Run any pipeline
osiris run my-pipeline.yaml

# View the AI-friendly export
cat logs/aiop/aiop.json | jq '.narrative.summary'
# or browse the human-readable summary
open logs/aiop/run-card.md
```

**Result**: After every run, Osiris automatically generates:
- **`logs/aiop/aiop.json`** - Structured AI operation package
- **`logs/aiop/run-card.md`** - Human-readable run summary
- **`logs/aiop/latest.json`** - Symlink to most recent export
- **`logs/aiop/index/`** - Run catalog for delta analysis

### What is AIOP?

The **AI Operation Package (AIOP)** is a comprehensive, structured export of pipeline execution data designed for AI consumption. Unlike traditional logs or simple JSON dumps, AIOP provides a multi-layered context that enables AI systems to deeply understand and reason about pipeline runs.

### AIOP Layers

1. **Evidence Layer** - Timestamped, citeable records of what happened
   - Timeline of events with stable IDs (`ev.event.run_start.run.123`)
   - Aggregated metrics (rows processed, duration, errors)
   - Artifact references and data lineage
   - Delta analysis: "Since last run" comparisons

2. **Semantic Layer** - Formal model of pipeline structure and relationships
   - DAG representation with nodes and edges
   - Component capabilities and configurations
   - OML version and manifest fingerprint

3. **Narrative Layer** - Natural language description with citations
   - Intent discovery from manifest, README, commit messages
   - Causal explanations of execution flow
   - Cross-references to evidence IDs
   - Provenance tracking with trust levels

4. **Metadata Layer** - Package metadata and AI controls
   - LLM primer with Osiris concepts and glossary
   - Example commands for debugging and analysis
   - Size hints for LLM chunking
   - Truncation markers when size-limited

### Autopilot Export Behavior

AIOP runs automatically after each pipeline execution:

- **Triggered**: Every run completion (success, failure, or interruption)
- **Path templating**: `logs/aiop/{session_id}_aiop.json` prevents overwrites
- **Indexing**: Updates `logs/aiop/index/runs.jsonl` and `by_pipeline/<hash>.jsonl`
- **Retention**: Configurable cleanup (default: keep last 50 runs)
- **Latest symlink**: `logs/aiop/latest.json` always points to newest export

### Policies: Core vs Annex

**Core Policy** (default): LLM-optimized, size-controlled
- Target: ≤300KB for fast LLM consumption
- Content: Essential narrative, semantic summaries, key evidence
- Truncation: Explicit markers when size exceeded
- Exit code: 4 if truncated, 0 if complete

**Annex Policy**: Full data preservation
- Core: Same as above, with references to annex files
- Annex: Unlimited NDJSON shards (`logs/aiop/annex/`)
  - `timeline.ndjson[.gz]` - Full event stream
  - `metrics.ndjson[.gz]` - All data points
  - `errors.ndjson[.gz]` - Complete error details

```bash
# Enable annex for data-heavy pipelines
osiris logs aiop --last --policy annex --compress gzip
```

### Configuration

AIOP behavior can be configured through `osiris.yaml` (generated by `osiris init`):

```yaml
aiop:
  enabled: true            # Auto-generate AIOP after each run
  policy: core             # core = LLM-friendly size, annex = full data
  max_core_bytes: 300000   # Size limit before truncation
  timeline_density: medium # Event filtering level
  metrics_topk: 100        # Top metrics to include

  output:
    core_path: logs/aiop/{session_id}_aiop.json  # Templated paths
    run_card_path: logs/aiop/{session_id}_runcard.md

  retention:
    keep_runs: 50          # Keep last N exports
    annex_keep_days: 14    # Clean old annex files
```

**Configuration precedence**: CLI > Environment ($OSIRIS_AIOP_*) > YAML > Defaults

### Security: Redaction Guarantees

AIOP automatically redacts sensitive information:

- **Credentials**: `password`, `key`, `token`, `secret` fields → `***`
- **DSN masking**: `postgres://user:pass@host/db` → `postgres://***@host/db`
- **Connection strings**: Redis, MySQL, MongoDB credentials masked
- **PII protection**: Configurable redaction for chat logs and free text

**Guarantee**: No secrets ever appear in AIOP exports, validated by comprehensive test suite.

### Commands

```bash
# Export AIOP for last run (JSON format)
osiris logs aiop --last --format json

# Generate Markdown run-card for human review
osiris logs aiop --last --format md --output runcard.md

# Export with annex shards for large runs
osiris logs aiop --last --policy annex --compress gzip

# Override YAML configuration via CLI
osiris logs aiop --last --timeline-density high --max-core-bytes 500000

# Check if export was truncated
echo $?  # Exit code 4 = truncated, 0 = complete
```

### Troubleshooting

**Empty run-card or missing narrative**
- Check `aiop.enabled: true` in `osiris.yaml`
- Verify pipeline actually ran (check `logs/<session>/events.jsonl`)
- For intent discovery, add `metadata.intent` to your OML or README.md

**Delta always shows "first_run: true"**
- Previous runs must have same `manifest_hash` for comparison
- Check `logs/aiop/index/by_pipeline/<hash>.jsonl` exists
- Delete index file to reset if corrupted

**Annex files not written**
- Set `policy: annex` in config or use `--policy annex` flag
- Check disk space and permissions on `logs/aiop/annex/`
- Verify timeline has events to export

**Symlink issues on Windows**
- Latest symlink falls back to text file with path on Windows
- Use `logs/aiop/latest.json` or check most recent timestamped file

### Examples

#### Example 1: Simple JSON Export for PRs

Quick pipeline summary for pull request comments:

```bash
# Generate compact run-card
osiris logs aiop --last --format md | head -20

# Extract key metrics for PR comment
osiris logs aiop --last --format json | jq '{
  status: .run.status,
  duration: .evidence.metrics.total_duration_ms,
  rows: .evidence.metrics.total_rows,
  intent: .narrative.intent
}'
```

#### Example 2: Annex Mode with Compression

Full data preservation for complex analysis:

```bash
# Export with annex and compression
osiris logs aiop --last --policy annex --compress gzip

# Validate index was updated
jq -r '.session_id' logs/aiop/index/runs.jsonl | tail -5

# Check annex file sizes
ls -lh logs/aiop/annex/*.gz

# Stream metrics for analysis
zcat logs/aiop/annex/metrics.ndjson.gz | jq '.rows_read // empty' | head -10
```

### Use Cases

- **AI Debugging**: Feed AIOP to LLMs for root cause analysis
- **Automated Monitoring**: AI agents can detect anomalies and suggest fixes
- **Documentation**: Markdown run-cards provide executive summaries
- **Compliance**: Evidence layer provides audit trail with citations
- **Knowledge Base**: Build organizational memory from run patterns
- **Delta Analysis**: "Since last run" comparisons for regression detection
