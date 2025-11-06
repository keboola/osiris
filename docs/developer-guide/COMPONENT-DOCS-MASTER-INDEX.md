# Component Development Documentation - Master Index

## Purpose
Central index of ALL component development documentation in Osiris.

Last updated: 2025-10-26

---

## 🎯 START HERE

**For AI/LLM:** [ai/START-HERE.md](ai/START-HERE.md)
- Single entry point for AI-assisted development
- Task-based router
- Loads only what you need

**For Humans:** [human/BUILD_A_COMPONENT.md](human/BUILD_A_COMPONENT.md)
- 9-step walkthrough
- Human-friendly explanations
- Examples and screenshots

---

## 📁 Documentation Structure

### AI Developer Guides (`docs/developer-guide/ai/`)

**Entry Points:**
- `START-HERE.md` - Master router (START HERE!)
- `build-new-component.md` - Complete template (700+ lines)
- `README.md` - AI intent router

**Decision Trees:** (`decision-trees/`)
- `api-type-selector.md` - REST vs GraphQL vs SQL
- `auth-selector.md` - OAuth vs API key vs Basic
- `pagination-selector.md` - Offset vs Cursor vs Link

**Working Recipes:** (`recipes/`)
- `rest-api-extractor.md` - Complete REST API template
- `pagination-cursor.md` - Cursor pagination pattern
- `sql-extractor.md` - Database extractor template (future)

**LLM Contracts:** (`llms/`)
- `components.md` - Spec generation contract
- `drivers.md` - Driver implementation contract
- `overview.md` - Determinism principles

**Validation Checklists:** (`checklists/`)
- `COMPONENT_AI_CHECKLIST.md` - 57 validation rules
- `discovery_contract.md` - Discovery mode requirements
- `connections_doctor_contract.md` - Health check requirements
- `metrics_events_contract.md` - Telemetry requirements

**Troubleshooting:**
- `error-patterns.md` - Common errors and fixes (future)

---

### Human Developer Guides (`docs/developer-guide/human/`)

**Main Guides:**
- `BUILD_A_COMPONENT.md` - Step-by-step walkthrough
- `CONCEPTS.md` - Core concepts (Component, Connector, Driver, etc.)
- `README.md` - Human guide navigation

**Module Deep-Dives:** (`modules/`)
- `components.md` - Registry, validator, spec loader, context builder

**Examples:** (`examples/`)
- `shopify.extractor/` - Complete reference implementation
  - `spec.yaml` - Production component spec
  - `e2e_manifest.yaml` - E2E test pipeline
  - `discovery.sample.json` - Discovery output sample

---

### Reference Documentation (`docs/reference/`)

**Specifications:**
- `components-spec.md` - Complete spec schema reference
- `x-connection-fields.md` - Override policy specification (697 lines)
- `connection-fields.md` - Connection configuration
- `events_and_metrics_schema.md` - Telemetry schema

**Analysis & Quick Refs:**
- `component-specs-analysis.md` - 7-component analysis, 50+ patterns
- `component-spec-quickref.md` - Quick reference checklist
- `component-creation-guide.md` - 7-step creation guide
- `COMPONENT-DOCS-INDEX.md` - Component docs navigation

---

### Architecture Decisions (`docs/adr/`)

**Component-Related ADRs:**
- `0005-component-specification-and-registry.md` - Spec format
- `0007-component-specification-and-capabilities.md` - Modes & capabilities
- `0008-component-registry.md` - Registry implementation
- `0020-connection-resolution-and-secrets.md` - Connection system
- `0021-component-health-check-capability.md` - Doctor capability
- `0024-component-packaging.md` - Packaging strategy

---

## 🗺️ Documentation Map by Task

### Task: "Build new component from scratch"
Path:
1. `ai/START-HERE.md` (router)
2. `ai/decision-trees/api-type-selector.md`
3. `ai/decision-trees/auth-selector.md`
4. `ai/decision-trees/pagination-selector.md`
5. `ai/recipes/rest-api-extractor.md`
6. `ai/build-new-component.md` (template)
7. `ai/checklists/COMPONENT_AI_CHECKLIST.md` (validation)

### Task: "Understand component architecture"
Path:
1. `human/CONCEPTS.md`
2. `reference/components-spec.md`
3. `adr/0005-component-specification-and-registry.md`

### Task: "Debug failing component"
Path:
1. `ai/error-patterns.md` (find error)
2. `ai/checklists/COMPONENT_AI_CHECKLIST.md` (validate)
3. `reference/component-specs-analysis.md` (check patterns)

### Task: "Add discovery mode to existing component"
Path:
1. `ai/checklists/discovery_contract.md`
2. `ai/build-new-component.md` (section 4.2)
3. `human/examples/shopify.extractor/discovery.sample.json`

### Task: "Fix x-connection-fields error"
Path:
1. `reference/x-connection-fields.md` (complete spec)
2. `reference/component-spec-quickref.md` (examples)

---

## 📊 Documentation Statistics

**Total Documents:** 30+
**Total Lines:** ~8,000+
**Coverage:**
- Component Spec: 100%
- Driver Protocol: 100%
- Security Model: 100%
- Testing: 80%
- Troubleshooting: 40%

**Languages:**
- Markdown: 28 files
- YAML: 3 files
- Python: Examples in docs

---

## 🔄 Document Versions

**Last Major Updates:**
- 2025-10-26: Added START-HERE.md, decision-trees/, recipes/
- 2025-10-24: Added component-specs-analysis.md
- 2025-10-20: Updated x-connection-fields.md with override policies

---

## 🤝 Contributing

When adding new component docs:
1. Update this master index
2. Link from START-HERE.md if it's task-relevant
3. Add to appropriate section (ai/, human/, reference/)
4. Update version history below

---

## 🔗 External References

- Component Registry Code: `osiris/components/registry.py`
- Component Specs: `components/*/spec.yaml`
- Driver Implementations: `osiris/drivers/*_driver.py`
- Tests: `tests/components/`, `tests/drivers/`
