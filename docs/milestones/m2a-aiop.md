# Milestone M2a – AI Operation Package (AIOP)

*Implementation plan for ADR-0027: AI Operation Package*
*Date: 2025-01-23*
*Status: Draft*

## Executive Summary

The AI Operation Package (AIOP) is a model-agnostic, JSON-LD based, deterministic, and secret-free structured export of Osiris pipeline runs designed to enable any LLM or AI system to fully understand and operate pipelines through rich semantic context, evidence, and narrative layers. AIOP transforms AI integration from passive log analysis into active, intelligent pipeline operation by providing comprehensive context about pipeline intent, execution, and outcomes in a machine-consumable format that works with GPT, Claude, Gemini, or any future LLM.

**Non-goals for M2a**: Control Layer implementation (operational commands), PII detection/redaction, real-time streaming updates, multi-run comparison analytics, and integration with external observability platforms.

## Scope & Thin Slice

### M2a MVP Boundaries

**In Scope:**
- **Narrative Layer**: Auto-generated natural language explanations of pipeline intent and outcomes
- **Semantic/Ontology Layer**: Formal JSON-LD representation of manifest, OML specs, and component relationships
- **Evidence Layer**: Deterministic, timestamped execution records with stable identifiers
- **CLI Export**: Read-only `osiris logs aiop` command for JSON and Markdown output
- **Determinism**: Stable key/array ordering, canonicalized output
- **Secret Redaction**: Field-level denylist with structural validation
- **Core/Annex Split**: Core package (≤300 KB) with optional Annex NDJSON shards

**Deferred:**
- **Control Layer**: Outlined in `aiop.control.contract.yaml` but not implemented
- **PII Detection**: Future work beyond basic secret redaction
- **Multi-run Comparison**: Complex delta analysis across many runs
- **Real-time Updates**: Streaming AIOP generation during execution
- **Discovery Ingestion**: Full catalog storage (ADR-0029)

## Package Stratification (Core vs Annex)

### Core Package
- **Size**: ≤300 KB default (configurable via `--max-core-bytes`)
- **Content**: Essential narrative, semantic summaries, key evidence
- **Format**: Single JSON document with truncation markers

### Annex Shards
- **Format**: NDJSON files for streaming ingestion
- **Files**:
  - `timeline.ndjson`: Full event stream
  - `metrics.ndjson`: All metrics data points
  - `errors.ndjson`: Error details and stack traces
  - `discovery.ndjson`: Schema catalogs (future M3+, placeholder only in M2a)
- **Size**: Unbounded (with optional compression)

### Configuration via Osiris.yaml & ENV

Configuration follows this precedence order:
```
Precedence: CLI > Environment variables ($OSIRIS_AIOP_*) > Osiris.yaml > built-in defaults
```

**Option Reference:**
- `aiop.enabled` (bool, default true) — auto-export AIOP after each run (even on failure)
- `aiop.policy` (core|annex|custom, default core) — size/stratification strategy
- `aiop.max_core_bytes` (e.g. 300k) — hard cap for Core; deterministic truncation + markers
- `aiop.timeline_density` (low|medium|high, default medium) — how many events go into Core
  - low: key events; medium: + aggregated per-step metrics; high: all incl. debug
- `aiop.metrics_topk` (int, default 100) — keep top-K important metrics/steps in Core
- `aiop.schema_mode` (summary|detailed, default summary) — detail level for Semantic layer (no secrets)
- `aiop.delta` (previous|none, default previous) — comparison with last run of the same pipeline@manifest_hash; first run sets first_run:true
- `aiop.run_card` (bool, default true) — emit Markdown run-card
- `aiop.output.core_path` (path, default logs/aiop/aiop.json)
- `aiop.output.run_card_path` (path, default logs/aiop/run-card.md)
- `aiop.annex.enabled` (bool, default false for core, true for annex) — NDJSON Annex on/off
- `aiop.annex.dir` (path, default logs/aiop/annex)
- `aiop.annex.compress` (none|gzip|zstd, default none) — compression applies to Annex only; Core stays uncompressed
- `aiop.retention.keep_runs` (int, optional) — keep last N Core files
- `aiop.retention.annex_keep_days` (int, optional) — delete Annex shards older than N days

**Environment Variable Mapping:**
- `OSIRIS_AIOP_ENABLED=false`
- `OSIRIS_AIOP_POLICY=annex`
- `OSIRIS_AIOP_MAX_CORE_BYTES=500000`
- `OSIRIS_AIOP_TIMELINE_DENSITY=high`
- `OSIRIS_AIOP_METRICS_TOPK=200`
- `OSIRIS_AIOP_SCHEMA_MODE=detailed`
- `OSIRIS_AIOP_DELTA=none`
- `OSIRIS_AIOP_RUN_CARD=false`
- `OSIRIS_AIOP_OUTPUT_CORE_PATH=/tmp/aiop.json`
- `OSIRIS_AIOP_OUTPUT_RUN_CARD_PATH=/tmp/run-card.md`
- `OSIRIS_AIOP_ANNEX_ENABLED=true`
- `OSIRIS_AIOP_ANNEX_DIR=/tmp/annex`
- `OSIRIS_AIOP_ANNEX_COMPRESS=gzip`
- `OSIRIS_AIOP_RETENTION_KEEP_RUNS=20`
- `OSIRIS_AIOP_RETENTION_ANNEX_KEEP_DAYS=7`

### Truncation Markers & Annex Files

**Truncation markers** appear at the truncated object level:
- `timeline.truncated: true`, `timeline.dropped_events: <n>`, `timeline.annex_ref: "<path>"`
- `metrics.truncated: true`, `metrics.dropped_series: <n>`

**Annex NDJSON files:**
- `timeline.ndjson`: 1 event/line with @id, run_session_id, step_id, ts_ms
- `metrics.ndjson`: 1 metric/line with @id, run_session_id, step_id, ts_ms
- `errors.ndjson`: 1 error/line with @id, run_session_id, step_id, ts_ms

### Planned CLI: osiris init (spec only)

**Purpose:** Generate or merge a commented Osiris.yaml with AIOP defaults.

**Behavior:**
- Non-destructive merge by default; preserve existing values; add only missing aiop keys
- Flags (for later implementation): `--force` (backup + overwrite), `--no-comments`, `--aiop-policy {core,annex,custom}`, `--stdout`, `--path <file>`

**Template to be generated:**
```yaml
# Osiris configuration
# Precedence of settings: CLI > Environment ($OSIRIS_AIOP_*) > Osiris.yaml > built-in defaults
# AIOP: AI Operation Package — structured export for LLMs (Narrative, Semantic, Evidence; Control in future)
aiop:
  enabled: true            # Auto-generate AIOP after each run (even on failure)
  policy: core             # core = Core only (LLM-friendly); annex = Core + NDJSON Annex; custom = Core + fine-tuning knobs
  max_core_bytes: 300k     # Hard cap for Core size; deterministic truncation with markers when exceeded

  # How many timeline events go into Core (Annex can still contain all)
  timeline_density: medium # low = key events only; medium = + aggregated per-step metrics (default); high = all incl. debug
  metrics_topk: 100        # Keep top-K metrics/steps in Core (errors/checks prioritized)
  schema_mode: summary     # summary = names/relations/fingerprints; detailed = adds small schema/config excerpts (no secrets)
  delta: previous          # previous = compare to last run of same pipeline@manifest_hash (first_run:true if none); none = disable
  run_card: true           # Also write Markdown run-card for PR/Slack

  output:
    core_path: logs/aiop/aiop.json         # Where to write Core JSON
    run_card_path: logs/aiop/run-card.md   # Where to write Markdown run-card

  annex:
    enabled: false         # Enable NDJSON Annex (timeline/metrics/errors shards)
    dir: logs/aiop/annex   # Directory for Annex shards
    compress: none         # none|gzip|zstd (applies to Annex only; Core is always uncompressed for readability)

  retention:
    keep_runs: 50          # Keep last N Core files (optional)
    annex_keep_days: 14    # Delete Annex shards older than N days (optional)
```

## Architecture & Data Model

### JSON-LD Approach

**@context Definition**: `docs/reference/aiop.context.jsonld`
```json
{
  "@context": {
    "@vocab": "https://osiris.dev/ontology/v1/",
    "osiris": "osiris://",
    "xsd": "http://www.w3.org/2001/XMLSchema#",
    "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
    "Pipeline": "osiris:Pipeline",
    "Run": "osiris:Run",
    "Step": "osiris:Step",
    "Artifact": "osiris:Artifact",
    "Metric": "osiris:Metric",
    "Issue": "osiris:Issue",
    "Intent": "osiris:Intent",
    "OMLSpec": "osiris:OMLSpec",
    "Manifest": "osiris:Manifest"
  }
}
```

### Canonical URI Scheme

| Entity | URI Pattern | Example |
|--------|-------------|---------|
| Pipeline | `osiris://pipeline/<name>@<manifest_hash>` | `osiris://pipeline/customer_etl@abc123def` |
| Step | `osiris://pipeline/<name>@<manifest_hash>/step/<step_id>` | `osiris://pipeline/customer_etl@abc123def/step/extract` |
| Run | `osiris://run/@<session_id>` | `osiris://run/@run_1234567890` |
| Artifact | `osiris://run/@<session_id>/artifact/<path>` | `osiris://run/@run_123/artifact/output/data.csv` |
| Evidence | `osiris://run/@<session_id>/evidence/<evidence_id>` | `osiris://run/@run_123/evidence/ev.metric.extract.rows_read.1234567890000` |

**Rules:**
- No trailing slashes
- Lowercase preferred for consistency
- Alphanumeric + underscore + hyphen only in IDs
- UTF-8 encoded paths

**Entity Relations:**
- `produces`: Step → Artifact
- `consumes`: Step → Artifact (from upstream)
- `depends_on`: Step → Step (DAG edges)
- `materializes`: Run → Pipeline
- `verifies`: Evidence → Step
- `remediates`: Control → Issue (future)

### Identifiers & Hashes

**run_fingerprint Composition:**
```
SHA-256({osiris_version}:{env}:{manifest_hash}:{session_id}:{start_timestamp_ms})
```
- `osiris_version`: e.g., "0.2.0"
- `env`: "local" or "e2b"
- `manifest_hash`: From compilation
- `session_id`: e.g., "run_1234567890"
- `start_timestamp_ms`: Unix epoch milliseconds UTC
- **Note**: run_fingerprint is computed for reproducibility but URIs use session_id directly

**evidence_id Scheme:**
```
ev.<type>.<step_id>.<name>.<timestamp_ms_utc>
```
- Types: `metric`, `check`, `artifact`, `event`
- Timestamp: Always milliseconds since Unix epoch UTC
- Reserved: No dots in user values; underscores replace spaces
- **Name field**: May only contain lowercase alphanumeric and underscore (a-z0-9_). Spaces and dashes are converted to underscores
- Examples:
  - `ev.metric.extract.rows_read.1705315200000`
  - `ev.check.transform.quality_check.1705315201500`
  - `ev.artifact.export.output_csv.1705315205000`

**Alignment:**
- `manifest_hash`: Reuse from existing compilation
- `trace_id`: Propagate from session logging if present

### Determinism Rules

1. **Key Ordering**: All JSON objects use lexicographically sorted keys
2. **Array Ordering**:
   - Events: chronological by timestamp
   - Steps: topological DAG order
   - Metrics: grouped by step, then sorted by name
3. **Canonicalization**:
   - Timestamps in ISO 8601 UTC
   - Numbers as JSON numbers (no strings)
   - No trailing whitespace or pretty-printing in canonical form

## CLI Specification

### Command Structure

```bash
# Export AIOP for specific session
osiris logs aiop --session <session_id> --output <path> [--format json|md] [--policy core|annex]

# Export AIOP for last run
osiris logs aiop --last [--format json|md]

# With Annex shards
osiris logs aiop --last --policy annex --annex-dir ./aiop-annex/

# Custom configuration
osiris logs aiop --last --max-core-bytes 500000 --timeline-density high --compress gzip
```

**Parameters:**
- `--timeline-density`: `low` (key events only), `medium` (default, includes metrics), `high` (all events including debug)
- `--compress`: Default: none. When enabled, applies to Annex files only (Core always uncompressed for readability)

### Markdown Run-Card Format

The `--format md` option generates a concise run-card suitable for PR comments:

```markdown
## Pipeline Run: customer_etl_pipeline
**Status**: ✅ Success | **Duration**: 5m 23s | **Rows**: 10,234
**Fingerprint**: `run_abc123def456`

### Evidence
- Metrics: [10,234 rows processed](osiris://run/@run_abc123def456/evidence/ev.metric.extract.rows_read)
- Timeline: [23 events](osiris://run/@run_abc123def456/evidence/timeline)
- Artifacts: [3 files generated](osiris://run/@run_abc123def456/artifacts/)

[View Full AIOP](path/to/aiop.json)
```

### Exit Codes & Error Messages

- `0`: Success
- `1`: General error
- `2`: Missing session (`Error: Session 'run_xyz' not found`)
- `4`: Size limit exceeded (Warning: truncated but AIOP generated successfully)

**Note**: `osiris logs aiop` does NOT require a git repository (read-only export works anywhere)

## File & Code Changes

### New Files

**osiris/core/run_export_v2.py**
```python
"""AIOP builder with pure functions for deterministic export."""

def build_aiop(
    session_data: dict,
    manifest: dict,
    events: list[dict],
    metrics: list[dict],
    artifacts: list[Path],
    max_bytes: int = 1_000_000
) -> dict:
    """Build complete AIOP with all layers."""

def build_narrative_layer(manifest: dict, run_summary: dict) -> dict:
    """Generate natural language narrative."""

def build_semantic_layer(manifest: dict, oml_spec: dict) -> dict:
    """Build JSON-LD semantic representation."""

def build_evidence_layer(events: list, metrics: list, artifacts: list) -> dict:
    """Compile evidence with stable IDs."""

def canonicalize_json(data: dict) -> str:
    """Produce deterministic JSON string."""
```

**docs/reference/aiop.context.jsonld**
- JSON-LD context defining Osiris ontology

**docs/reference/aiop.schema.json**
- JSON Schema for AIOP envelope validation

**docs/reference/aiop.control.contract.yaml** (stub only)
```yaml
# Draft Control Layer contract for future implementation
capabilities:
  - id: rerun_step
    description: Re-execute a specific step
    pre_conditions:
      - step_status: failed
    post_conditions:
      - step_status: running
    dry_run: true  # Not enforced in M2a
```

### JSON-LD @context & Schema Versioning

**Context Versioning Strategy:**
```jsonld
{
  "@context": [
    "https://osiris.dev/context/v1",  # Base ontology (immutable)
    {
      "@version": 1.1,
      "@base": "osiris://",
      "osiris": "https://osiris.dev/vocab#",
      "schema": "https://schema.org/",
      "dcterms": "http://purl.org/dc/terms/",

      # Core vocabulary mappings
      "Pipeline": "osiris:Pipeline",
      "Step": "osiris:Step",
      "Evidence": "osiris:Evidence",
      "Metric": "osiris:Metric",

      # Semantic properties
      "executedBy": {"@id": "osiris:executedBy", "@type": "@id"},
      "hasEvidence": {"@id": "osiris:hasEvidence", "@type": "@id"},
      "measures": {"@id": "osiris:measures", "@type": "@id"}
    }
  ]
}
```

**Schema Evolution Rules:**
- **v1.0**: Initial AIOP format (immutable baseline)
- **v1.1+**: Additive changes only (new fields allowed)
- **v2.0**: Breaking changes require new major version
- **Package includes**: `"@context"` and `"schemaVersion": "1.0"`

### Graph Export Hints & LTM Hooks

**Triple Generation (Future GraphRAG):**
```json
{
  "graph_hints": {
    "triples": [
      ["osiris://run/@run_123", "rdf:type", "osiris:PipelineRun"],
      ["osiris://run/@run_123", "osiris:executedPipeline", "customer_etl"],
      ["osiris://run/@run_123", "osiris:hasStep", "osiris://run/@run_123/step/extract"],
      ["osiris://run/@run_123/step/extract", "osiris:rowsProcessed", "10234"]
    ],
    "embeddings_ready": ["narrative.summary", "semantic.intent"],
    "ltm_touchpoints": {
      "pipeline_pattern": "mysql_to_csv_export",
      "data_lineage": ["source.mysql.customers", "target.csv.output"],
      "performance_baseline": {"p50_duration_ms": 323000}
    }
  }
}
```

**LTM Integration Points:**
- **Pipeline Pattern Recognition**: Classify common workflow types
- **Performance Baselines**: Track p50/p95/p99 for similar pipelines
- **Failure Patterns**: Identify recurring error signatures
- **Data Lineage**: Build source→target dependency graph

### Modified Files

**osiris/cli/logs.py**
```python
# Using existing Rich-based CLI patterns (no Click)
def add_aiop_command(logs_group):
    """Add AIOP export command to logs group."""

    @logs_group.command(name='aiop')
    def aiop_command(args):
        """Export AI Operation Package for a pipeline run."""
        session = args.session or get_last_session() if args.last else None
        policy = args.policy or 'core'
        format = args.format or 'json'

        # Build AIOP with stratification
        if policy == 'full' and args.annex_dir:
            export_with_annex(session, args.annex_dir, args)
        else:
            export_core_only(session, args.output, format)
```

**osiris/core/session_reader.py**
- Add helper methods if needed for AIOP data collection

**docs/reference/cli.md**
- Document new `osiris logs aiop` command

## Security & Redaction Proof

### No-Secrets-By-Construction Policy

**Field-Level Denylist:**
```python
SECRET_FIELDS = {
    'password', 'key', 'token', 'secret', 'credential',
    'api_key', 'auth', 'authorization', 'private_key'
}

def redact_secrets(data: dict) -> dict:
    """Recursively redact secret fields."""
    for key in list(data.keys()):
        if any(secret in key.lower() for secret in SECRET_FIELDS):
            data[key] = '[REDACTED]'
```

**Structural Validation:**
- HMAC signature over raw event slices before redaction
- Unit test with injected fake secrets that must be caught
- Connection strings parsed and sanitized

**PII Handling**: Out of scope for M2a (noted for future work)

### Test Example: Secret Leak Detection
```python
def test_aiop_redacts_secrets():
    """AIOP must never contain secrets."""
    fake_manifest = {
        'steps': [{
            'config': {
                'connection': '@mysql.default',
                'password': 'FAKE_SECRET_12345'  # Must be redacted
            }
        }]
    }
    aiop = build_aiop(manifest=fake_manifest, ...)

    # Assert no secrets in serialized output
    json_str = json.dumps(aiop)
    assert 'FAKE_SECRET_12345' not in json_str
    assert '[REDACTED]' in json_str
```

## Evidence & Timeline

### Evidence Layer Content

**Aggregated Metrics:**
- Total rows processed: `cleanup_complete.total_rows`
- Total duration: `run_end - run_start`
- Per-step metrics: `rows_read`, `rows_written`, `duration_ms`
- Memory usage snapshots

**Timeline Events (Machine-Parseable):**
```json
{
  "timeline": [
    {"ts": "2024-01-15T10:00:00Z", "type": "START", "session": "run_123"},
    {"ts": "2024-01-15T10:00:01Z", "type": "STEP_START", "step_id": "extract"},
    {"ts": "2024-01-15T10:00:05Z", "type": "METRICS", "step_id": "extract",
     "metrics": {"rows_read": 1000}},
    {"ts": "2024-01-15T10:00:06Z", "type": "STEP_COMPLETE", "step_id": "extract"},
    {"ts": "2024-01-15T10:05:00Z", "type": "COMPLETE", "total_rows": 1000}
  ]
}
```

**Delta Analysis** (Core summary only):
```json
{
  "delta": {
    "rows": {"current": 1000, "previous": 950, "change": "+5.3%"},
    "duration": {"current": "5m", "previous": "4m30s", "change": "+11.1%"},
    "lookup_strategy": "manifest_hash",
    "previous_run": "run_1234567889"
  }
}
```

**Lookup Strategy:**
1. Same `manifest_hash` (exact pipeline version)
2. Fallback to same `pipeline_name` (latest prior run)
3. Return `"delta": null` if no comparable run found
4. For first runs, delta contains `"first_run": true` instead of comparison values

**Artifact References:**
```json
{
  "artifacts": [
    {
      "@id": "osiris://run/@run_123/artifact/output/results.csv",
      "path": "logs/run_123/artifacts/output/results.csv",
      "size_bytes": 45678,
      "content_hash": "sha256:abc123...",
      "mime_type": "text/csv"
    }
  ]
}
```

## Narrative Layer Content Policy

### Source Material
- **Osiris Overview**: Extract from `docs/overview.md`
- **OML Glossary**: Component descriptions from registry
- **Manifest Summary**: Pipeline name, steps, connections
- **Run Outcome**: Success/failure, row counts, duration

### Generation Rules
- **Tone**: Neutral, factual, no marketing language
- **Length**: 3-5 paragraphs maximum
- **Structure**: Context → Intent → Execution → Outcome
- **Citations**: Link to evidence IDs inline

### Example Narrative
```
This pipeline 'customer_etl_pipeline' implements a data extraction and
transformation workflow using Osiris v0.2.0. The pipeline extracts customer
data from MySQL and exports it to CSV format for analysis.

The execution completed successfully in 5 minutes 23 seconds, processing
10,234 rows [ev.metric.total.rows_processed]. The extraction step retrieved
data from the production database [ev.event.step_start.extract], followed
by transformation and CSV export [ev.event.step_complete.export].

All data quality checks passed with no warnings or errors recorded in the
execution timeline [ev.check.quality.passed].
```

## Validation & Tests

### Required Tests

1. **JSON Schema Validation**
```python
def test_aiop_validates_against_schema():
    """AIOP must conform to schema."""
    aiop = build_aiop(...)
    validate(instance=aiop, schema=load_schema('aiop.schema.json'))
```

2. **Deterministic Ordering**
```python
def test_aiop_deterministic():
    """Same input produces identical AIOP."""
    aiop1 = build_aiop(data)
    aiop2 = build_aiop(data)
    assert canonicalize_json(aiop1) == canonicalize_json(aiop2)
```

3. **Local vs E2B Parity**
```python
def test_aiop_parity():
    """AIOP identical for local and E2B runs."""
    local_aiop = build_aiop(local_run)
    e2b_aiop = build_aiop(e2b_run)
    # Ignore only timestamps and unique IDs
    assert normalize(local_aiop) == normalize(e2b_aiop)
```

4. **Size Limit & Truncation**
```python
def test_aiop_truncation():
    """Large AIOP truncates with markers."""
    large_data = generate_many_events(10000)
    aiop = build_aiop(large_data, max_bytes=100_000)
    assert aiop['truncated'] == True
    assert aiop['dropped_events'] > 0
```

5. **CLI End-to-End**
```python
def test_cli_aiop_export(tmp_path):
    """CLI exports valid AIOP."""
    result = runner.invoke(cli, [
        'logs', 'aiop', '--last',
        '--output', str(tmp_path / 'aiop.json')
    ])
    assert result.exit_code == 0
    assert (tmp_path / 'aiop.json').exists()
```

## Performance & Size Controls

### Target Metrics
- **Generation Time**: <2 seconds for typical run
- **Memory Footprint**: <50 MB for builder process
- **Output Size**: <300 KB typical, <1 MB maximum

### Truncation Strategy
```python
TRUNCATION_RULES = {
    'events': {'keep': 'first_100_last_100', 'drop_marker': 'events_truncated'},
    'metrics': {'keep': 'aggregates_only', 'drop_marker': 'metrics_truncated'},
    'artifacts': {'keep': 'references_only', 'drop_marker': 'content_omitted'}
}
```

### Size Hints for LLMs
```json
{
  "size_hints": {
    "nominal_tokens": 15000,
    "chunks": [
      {"name": "narrative", "byte_range": [0, 5000]},
      {"name": "semantic", "byte_range": [5001, 25000]},
      {"name": "evidence", "byte_range": [25001, 75000]}
    ]
  }
}
```

## Execution Sequence (Lightning Mode)

Target: complete within a day (subject to review cycles)

### PR 1: Schema & CLI Foundation (start immediately)
- `docs/reference/aiop.context.jsonld`
- `docs/reference/aiop.schema.json`
- `osiris/cli/logs.py` (stub command)
- `docs/reference/cli.md` updates

### PR 2: Evidence Layer
- `osiris/core/run_export_v2.py` (evidence builder)
- Tests for metrics aggregation
- Timeline generation

### PR 3: Semantic/Ontology Layer
- Semantic layer builder
- JSON-LD validation
- Component relationship mapping

### PR 4: Narrative Layer + Run-card
- Narrative generation from templates
- Markdown run-card renderer
- Citation linking

### PR 5: Parity & Truncation & Redaction
- Parity tests (Local vs E2B)
- Size/truncation handling
- Secret redaction validation

### PR 6: Docs & Polish
- Examples and tutorials
- Performance optimization
- Integration tests

## Acceptance Criteria

1. ✅ AIOP validates against `aiop.schema.json` and `aiop.context.jsonld`
2. ✅ No secrets appear in output (unit tests verify)
3. ✅ Deterministic output for same manifest/run (except timestamps/IDs)
4. ✅ AIOP size <300 KB for golden path
5. ✅ `osiris logs aiop --last` produces valid JSON and MD
6. ✅ MD run-card links cite evidence IDs correctly
7. ✅ Truncation markers appear when size limit exceeded
8. ✅ CLI returns appropriate exit codes
9. ✅ `--policy annex` generates NDJSON shard files correctly
10. ✅ Delta calculation works correctly for first run (no previous), subsequent runs, and missing previous runs
11. ✅ Precedence documented exactly as: CLI > Environment ($OSIRIS_AIOP_*) > Osiris.yaml > built-in defaults
12. ✅ Each AIOP option has a one-line description (timeline_density, schema_mode, metrics_topk, etc.)
13. ✅ ENV mappings listed and unambiguous
14. ✅ Truncation marker format documented at object level; Annex files and compression default (none) are explicit
15. ✅ Delta behavior: first runs set first_run:true; lookup by pipeline@manifest_hash
16. ✅ Evidence ID charset ([a-z0-9_]), UTC ms timestamps, and URI canonical forms are spelled out
17. ✅ Planned osiris init is specified with flags, behavior, and the exact YAML template block

## Examples

### Minimal JSON Example (~200 lines)
```json
{
  "@context": "https://osiris.dev/ontology/v1/aiop.jsonld",
  "@type": "AIOperationPackage",
  "@id": "osiris://aiop/@run_abc123def456",
  "version": "1.0",
  "generated": "2024-01-15T10:06:00Z",

  "run": {
    "@type": "Run",
    "@id": "osiris://run/@run_abc123def456",
    "session_id": "run_1234567890",
    "fingerprint": "run_abc123def456",
    "status": "completed",
    "start_time": "2024-01-15T10:00:00Z",
    "end_time": "2024-01-15T10:05:00Z",
    "duration_ms": 300000
  },

  "pipeline": {
    "@type": "Pipeline",
    "@id": "osiris://pipeline/@manifest_hash_xyz",
    "name": "customer_etl_pipeline",
    "manifest_hash": "manifest_hash_xyz",
    "steps": [
      {
        "@type": "Step",
        "@id": "osiris://pipeline/@manifest_hash_xyz/step/extract/",
        "step_id": "extract",
        "component": "mysql.extractor",
        "mode": "read",
        "depends_on": [],
        "produces": ["osiris://run/@run_abc123def456/artifact/extract/data.parquet"]
      }
    ]
  },

  "narrative": {
    "@type": "Narrative",
    "summary": "This pipeline 'customer_etl_pipeline' implements a data extraction...",
    "intent": "Extract customer data from MySQL for analysis",
    "outcome": "Successfully processed 10,234 rows in 5 minutes"
  },

  "semantic": {
    "@type": "SemanticLayer",
    "oml_version": "0.1.0",
    "components": {
      "mysql.extractor": {
        "@id": "osiris://component/mysql.extractor",
        "capabilities": ["read", "discover"],
        "schema": {"type": "object", "properties": {...}}
      }
    },
    "dag": {
      "nodes": ["extract", "transform", "export"],
      "edges": [
        {"from": "extract", "to": "transform", "relation": "produces"},
        {"from": "transform", "to": "export", "relation": "produces"}
      ]
    }
  },

  "evidence": {
    "@type": "EvidenceLayer",
    "timeline": [
      {
        "@id": "ev.event.start.run_123",
        "ts": "2024-01-15T10:00:00Z",
        "type": "START",
        "session": "run_123"
      },
      {
        "@id": "ev.event.step_start.extract",
        "ts": "2024-01-15T10:00:01Z",
        "type": "STEP_START",
        "step_id": "extract"
      },
      {
        "@id": "ev.metric.extract.rows_read",
        "ts": "2024-01-15T10:00:05Z",
        "type": "METRICS",
        "step_id": "extract",
        "metrics": {"rows_read": 10234}
      }
    ],
    "metrics": {
      "total_rows": 10234,
      "total_duration_ms": 300000,
      "steps": {
        "extract": {"rows_read": 10234, "duration_ms": 5000}
      }
    },
    "artifacts": [
      {
        "@id": "ev.artifact.extract.data",
        "path": "logs/run_123/artifacts/extract/data.parquet",
        "size_bytes": 1048576,
        "content_hash": "sha256:abc123..."
      }
    ]
  },

  "control": {
    "@type": "ControlLayer",
    "status": "draft",
    "capabilities": ["rerun_step", "modify_config"],
    "dry_run": true
  },

  "metadata": {
    "osiris_version": "0.2.0",
    "aiop_format": "1.0",
    "truncated": false,
    "size_bytes": 45678,
    "size_hints": {
      "nominal_tokens": 5000,
      "chunks": 3
    }
  }
}
```

### Markdown Run-Card Example
```markdown
## 🚀 Pipeline Run: customer_etl_pipeline

| Metric | Value |
|--------|-------|
| **Status** | ✅ Success |
| **Duration** | 5m 23s |
| **Total Rows** | 10,234 |
| **Run ID** | `run_abc123def456` |

### 📊 Step Metrics
- **Extract**: 10,234 rows in 5s [[evidence]](osiris://run/@run_abc123def456/evidence/ev.metric.extract.rows_read)
- **Transform**: 10,234 rows in 3m [[evidence]](osiris://run/@run_abc123def456/evidence/ev.metric.transform)
- **Export**: 10,234 rows in 2m [[evidence]](osiris://run/@run_abc123def456/evidence/ev.metric.export.rows_written)

### 📁 Artifacts
- `output/customers.csv` (1.2 MB) [[view]](osiris://run/@run_abc123def456/artifact/output/customers.csv)

### 🔍 Evidence Trail
- [Full Timeline](osiris://run/@run_abc123def456/evidence/timeline) (23 events)
- [Execution Log](logs/run_1234567890/osiris.log)
- [AIOP JSON](logs/run_1234567890/aiop.json)

---
*Generated by Osiris v0.2.0 | [View Full AIOP](path/to/aiop.json)*
```

### Failing Test Example: Secret Leakage
```python
import pytest

def test_aiop_must_redact_api_keys():
    """AIOP must never expose API keys."""
    # Inject a fake API key into test data
    malicious_config = {
        'supabase_api_key': 'sk_test_SUPERSECRET123',
        'connection': '@supabase.main'
    }

    manifest = {
        'steps': [{
            'id': 'load',
            'config': malicious_config
        }]
    }

    # Build AIOP
    aiop = build_aiop(manifest=manifest, events=[], metrics=[])

    # Serialize to JSON
    json_output = json.dumps(aiop, indent=2)

    # This test MUST fail if secret appears
    assert 'SUPERSECRET123' not in json_output, "API key leaked in AIOP!"
    assert '[REDACTED]' in json_output, "Secret was not redacted!"
```

## Documentation Updates

### docs/reference/cli.md
Add new section:
```markdown
### osiris logs aiop

Export AI Operation Package for pipeline runs.

**Usage:**
\```bash
osiris logs aiop --session <session_id> [options]
osiris logs aiop --last [options]
\```

**Options:**
- `--session`: Session ID to export
- `--last`: Use the most recent session
- `--output`: Output file path (default: stdout)
- `--format`: Output format (json|md, default: json)
- `--max-bytes`: Maximum size in bytes (default: 1MB)

**Examples:**
\```bash
# Export last run as JSON
osiris logs aiop --last > aiop.json

# Export as Markdown run-card
osiris logs aiop --last --format md

# Export specific session with size limit
osiris logs aiop --session run_123 --max-bytes 500000
\```
```

### docs/overview.md
Add subsection:
```markdown
## AI Operation Package (AIOP)

Osiris generates comprehensive AI Operation Packages that enable LLMs to understand
and operate pipelines. Each AIOP contains:

- **Narrative Layer**: Natural language explanations
- **Semantic Layer**: Formal ontology and relationships
- **Evidence Layer**: Execution proofs and metrics
- **Control Layer**: (Future) Operational interfaces

Export an AIOP using `osiris logs aiop --last` to enable AI-assisted debugging,
analysis, and operations.
```

### Cross-linking
Add to ADR-0027:
```markdown
## Implementation

See [Milestone M2a](../milestones/m2a-aiop.md) for the detailed implementation plan.
```

## Assumptions & Open Questions

### Assumptions
1. JSON-LD libraries are available and performant for our use case
2. 300 KB size limit is sufficient for typical pipelines
3. LLMs can effectively consume structured JSON-LD with citations
4. Existing session logging provides all necessary raw data

### Open Questions
1. Should we support compression (gzip) for large AIOPs?
2. How to handle binary artifacts in evidence (just references vs previews)?
3. Should delta analysis compare to last N runs or just previous?
4. Do we need signature/checksum for the entire AIOP for integrity?
5. Should Control Layer capabilities be discovered from drivers dynamically?

## Summary

This milestone plan operationalizes ADR-0027 into a concrete implementation roadmap for the AI Operation Package feature. The M2a scope focuses on the foundational read-only export capabilities with three core layers (Narrative, Semantic, Evidence), deferring the Control Layer for future work. The implementation emphasizes determinism, security (no secrets), and model-agnostic design to work with any LLM.
