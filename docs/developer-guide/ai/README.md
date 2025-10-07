# Osiris AI Agent Router

**Purpose**: Route AI agents to the correct documentation based on development intent.

**Audience**: AI agents, automated validators, CI systems

---

## How AI Agents Use This Documentation

AI agents should:
1. **Identify intent** from user request
2. **Look up intent** in routing table below
3. **Load specified documents** in order
4. **Generate/validate** code according to loaded contracts
5. **Verify compliance** using checklists

---

## Routing Table

| Intent | Load These Documents (in order) | Purpose |
|--------|--------------------------------|---------|
| **Build extractor** | `llms/components.md` → `llms/drivers.md` → `checklists/COMPONENT_AI_CHECKLIST.md` → `checklists/discovery_contract.md` | Generate extractor component with discovery |
| **Build writer** | `llms/components.md` → `llms/drivers.md` → `checklists/COMPONENT_AI_CHECKLIST.md` | Generate writer component |
| **Build processor** | `llms/components.md` → `llms/drivers.md` → `checklists/COMPONENT_AI_CHECKLIST.md` | Generate processor component |
| **Validate connections** | `llms/connectors.md` → `checklists/connections_doctor_contract.md` | Implement connection resolution and healthcheck |
| **Implement driver** | `llms/drivers.md` → `checklists/COMPONENT_AI_CHECKLIST.md` → `checklists/metrics_events_contract.md` | Implement Driver protocol |
| **Implement discovery** | `llms/components.md` → `checklists/discovery_contract.md` → `schemas/discovery_output.schema.json` | Add discovery mode to component |
| **Emit telemetry** | `llms/drivers.md` → `checklists/metrics_events_contract.md` → `schemas/events.schema.json` → `schemas/metrics.schema.json` | Add proper metric/event emission |
| **Run CLI commands** | `llms/cli.md` | Generate CLI command sequences |
| **Write tests** | `llms/testing.md` → `checklists/COMPONENT_AI_CHECKLIST.md` | Generate test cases |
| **Full component audit** | `llms/overview.md` → `checklists/COMPONENT_AI_CHECKLIST.md` → All checklists | Comprehensive validation |

---

## Document Hierarchy

```
ai/
├── README.md (this file)        ← Router for AI agents
│
├── llms/                        ← LLM contracts (how to generate code)
│   ├── overview.md              ← Determinism, fingerprints, machine-readable outputs
│   ├── components.md            ← Component spec generation
│   ├── connectors.md            ← Connection resolution patterns
│   ├── drivers.md               ← Driver implementation patterns
│   ├── cli.md                   ← CLI command generation
│   └── testing.md               ← Test generation patterns
│
├── checklists/                  ← Validation rules (what to verify)
│   ├── COMPONENT_AI_CHECKLIST.md       ← 57 component rules
│   ├── discovery_contract.md           ← Discovery mode requirements
│   ├── metrics_events_contract.md      ← Telemetry requirements
│   └── connections_doctor_contract.md  ← Connection/healthcheck requirements
│
└── schemas/                     ← JSON schemas (machine-readable formats)
    ├── events.schema.json       ← Event stream schema
    ├── metrics.schema.json      ← Metrics stream schema
    └── discovery_output.schema.json  ← Discovery output format
```

---

## AI Agent Workflow

### Example: Build Extractor

```
User Request: "Build a Shopify extractor component"

1. Intent Recognition: "build extractor"

2. Load Documents:
   - llms/components.md        (learn spec format)
   - llms/drivers.md           (learn driver patterns)
   - checklists/COMPONENT_AI_CHECKLIST.md  (validation rules)
   - checklists/discovery_contract.md      (discovery requirements)

3. Generate:
   - components/shopify.extractor/spec.yaml
   - osiris/drivers/shopify_extractor_driver.py

4. Validate Against Checklists:
   - SPEC-001 through SPEC-010 (spec completeness)
   - DRIVER-001 through DRIVER-006 (driver protocol)
   - DISC-001 through DISC-003 (discovery mode)
   - LOG-001 through LOG-006 (telemetry)

5. Output:
   - Generated code
   - Validation report
   - CLI commands to test
```

---

## Key Principles for AI Agents

### Determinism (Critical)

From `llms/overview.md`:
- All outputs MUST be deterministic (same input → same output)
- JSON keys MUST be sorted (`sort_keys=True`)
- Timestamps MUST be ISO 8601 UTC
- Evidence IDs MUST follow stable pattern: `ev.<type>.<step_id>.<name>.<timestamp_ms>`

### Machine-Readable Outputs

All generated code must produce:
- **Structured logs**: JSON Lines format
- **Typed metrics**: name, value, unit, tags
- **Deterministic artifacts**: Sorted keys, stable filenames
- **Schema-compliant events**: Validate against `schemas/events.schema.json`

### Compliance First

Before generating code:
1. Load relevant checklists
2. Understand MUST vs SHOULD rules
3. Generate code that passes all MUST rules
4. Add comments for SHOULD rules not implemented

---

## Quick Reference Cards

### Component Generation

**Required Files**:
- `components/<name>/spec.yaml`
- `osiris/drivers/<name>_driver.py`

**Required Sections** in spec.yaml:
- name, version, modes, capabilities, configSchema
- secrets (JSON Pointers)
- x-runtime.driver

**Validation Command**:
```bash
osiris components validate <name> --level strict --json
```

**Expected Output**:
```json
{
  "component": "<name>",
  "is_valid": true,
  "errors": []
}
```

### Driver Implementation

**Protocol Signature**:
```python
def run(*, step_id: str, config: dict, inputs: dict | None, ctx: Any) -> dict:
```

**Required Returns**:
- Extractors: `{"df": pandas.DataFrame}`
- Writers: `{}`
- Processors: `{"df": pandas.DataFrame}`

**Required Metrics**:
- Extractors: `rows_read`
- Writers: `rows_written`
- Processors: `rows_processed`

**Validation**:
```python
# Check protocol compliance
assert hasattr(driver, "run")
assert callable(driver.run)

# Check signature
import inspect
sig = inspect.signature(driver.run)
assert all(p.kind == inspect.Parameter.KEYWORD_ONLY for p in list(sig.parameters.values())[1:])
```

### Connection Resolution

**Input** (from user):
```yaml
config:
  connection: "@shopify.default"
```

**Output** (to driver):
```python
config = {
  "resolved_connection": {
    "shop_domain": "mystore.myshopify.com",
    "access_token": "actual_token_from_env"
  }
}
```

**Validation Command**:
```bash
osiris connections doctor --json
```

**Expected Output**:
```json
{
  "connections": [
    {
      "family": "shopify",
      "alias": "default",
      "ok": true,
      "latency_ms": 150,
      "category": "ok",
      "message": "Connection successful"
    }
  ]
}
```

---

## Error Handling

When validation fails, AI agents should:

1. **Parse error output**:
```json
{
  "is_valid": false,
  "errors": [
    {
      "rule_id": "SPEC-001",
      "message": "Missing required field: modes",
      "fix_hint": "Add modes: [extract] to spec.yaml"
    }
  ]
}
```

2. **Apply fixes** based on `fix_hint`

3. **Re-validate** until `is_valid: true`

---

## Prompt Templates

Use these ready-to-go templates to instruct an LLM (like Claude) to generate new Osiris components automatically:

- **[build-new-component.md](build-new-component.md)** - Template for building a new component (fill placeholders for `<COMPONENT_NAME>`, `<API_OR_RESOURCE>`, `<connection_fields>`)

These templates include all necessary context from LLM contracts and checklists, formatted for direct use with AI assistants.

---

## See Also

- **Human Docs**: [`../human/README.md`](../human/README.md)
- **Reference**: [`../../reference/`](../../reference/)
- **ADRs**: [`../../adr/`](../../adr/)

---

**For AI Agents**: Start with `llms/overview.md` to understand core principles, then use routing table above for specific tasks.
