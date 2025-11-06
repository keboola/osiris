# Osiris Developer Guide

> **For Users**: See [`docs/user-guide/user-guide.md`](../user-guide/user-guide.md)
> **For Contributors**: You're in the right place!

---

## Documentation Structure

The developer documentation is organized into two main paths:

### 📘 For Human Developers
**Start here**: [`human/README.md`](human/README.md)

Clear, narrative guides for building components and understanding the codebase:
- **[human/BUILD_A_COMPONENT.md](human/BUILD_A_COMPONENT.md)** - Step-by-step practical guide
- **[human/CONCEPTS.md](human/CONCEPTS.md)** - Core abstractions explained
- **[human/modules/](human/modules/)** - Module-by-module documentation
- **[human/examples/](human/examples/)** - Complete example scaffolds

### 🤖 For AI Agents / LLMs
**Start here**: [`ai/README.md`](ai/README.md)

Machine-readable contracts and validation rules for code generation:
- **[ai/llms/](ai/llms/)** - LLM contracts for each domain
- **[ai/checklists/](ai/checklists/)** - Machine-verifiable rules (MUST/SHOULD/MAY)
- **[ai/schemas/](ai/schemas/)** - JSON schemas for validation

---

## Quick Navigation

### Building a New Component
1. **Understand concepts**: [`human/CONCEPTS.md`](human/CONCEPTS.md)
2. **Follow the guide**: [`human/BUILD_A_COMPONENT.md`](human/BUILD_A_COMPONENT.md)
3. **Study examples**: [`human/examples/shopify.extractor/`](human/examples/shopify.extractor/)
4. **Validate**: `osiris components validate <name> --level strict`

### Using AI Assistants
1. **Load router**: [`ai/README.md`](ai/README.md)
2. **Pick contract**: Based on your task (components, drivers, connectors, CLI, testing)
3. **Check rules**: [`ai/checklists/COMPONENT_AI_CHECKLIST.md`](ai/checklists/COMPONENT_AI_CHECKLIST.md)

### Understanding Existing Code
| Task | Start Here |
|------|------------|
| "How do components work?" | [`human/CONCEPTS.md`](human/CONCEPTS.md) |
| "How do drivers execute?" | [`human/modules/drivers.md`](human/modules/drivers.md) |
| "How do connections work?" | [`human/modules/connectors.md`](human/modules/connectors.md) |
| "How does E2B work?" | [`human/modules/remote.md`](human/modules/remote.md) |
| "How does the CLI work?" | [`human/modules/cli.md`](human/modules/cli.md) |
| "What's the LLM agent?" | [`human/modules/core.md`](human/modules/core.md) |

---

## Reference Documentation

### Specifications
- **[../reference/components-spec.md](../reference/components-spec.md)** - Component spec format (full schema)
- **[../reference/pipeline-format.md](../reference/pipeline-format.md)** - OML pipeline format (v0.1.0)
- **[../reference/cli.md](../reference/cli.md)** - CLI command reference
- **[../reference/events_and_metrics_schema.md](../reference/events_and_metrics_schema.md)** - Telemetry schemas
- **[../reference/sql-safety.md](../reference/sql-safety.md)** - SQL validation rules

### Architecture Decisions
- **[../adr/](../adr/)** - Architecture Decision Records (ADRs 0001-0033)
  - Key ADRs for component developers:
    - ADR-0005, 0007, 0008: Component specs and registry
    - ADR-0012: Extractors vs writers separation
    - ADR-0020: Connection resolution and secrets
    - ADR-0021: Healthcheck (doctor) capability
    - ADR-0024: Component packaging (OCP model, future)
    - ADR-0027: AIOP exports for LLM debugging
    - ADR-0033: Resilience and retry policies (proposed)

---

## Migration Notice

**Previous documentation locations have moved**:
- `docs/COMPONENT_AI_CHECKLIST.md` → [`ai/checklists/COMPONENT_AI_CHECKLIST.md`](ai/checklists/COMPONENT_AI_CHECKLIST.md)
- `docs/developer-guide/CONCEPTS.md` → [`human/CONCEPTS.md`](human/CONCEPTS.md)
- `docs/developer-guide/module-*.md` → [`human/modules/*.md`](human/modules/)

**Reason**: Separated human-readable narrative guides from AI-oriented machine-verifiable contracts for better usability.

---

## Development Workflow

### Local Setup
```bash
# 1. Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Install pre-commit hooks
make pre-commit-install

# 4. Run tests
make test
```

### Development Loop
```bash
# Auto-format code
make fmt

# Run linters
make lint

# Security checks
make security

# Run tests
make test

# Test specific module
pytest tests/components/test_registry.py -v
```

### Testing with Real Pipelines
```bash
cd testing_env

# Compile pipeline
python ../osiris.py compile ../docs/examples/mysql_to_supabase.yaml

# Run locally
python ../osiris.py run --last-compile --verbose

# Run in E2B (if E2B_API_KEY set)
python ../osiris.py run --last-compile --e2b --verbose

# View logs
python ../osiris.py logs show --last
```

---

## Key Principles

1. **Contract-First**: Define interfaces before implementation
2. **LLM-Friendly**: Clear patterns, self-describing metadata
3. **Deterministic**: Same inputs → same outputs (for AIOP)
4. **Observable**: Structured events, metrics, AIOP exports
5. **Testable**: Pure functions, clear side effects
6. **Modular**: Components independently versioned (future OCP)

---

## Getting Help

### Common Questions

**Q: Where do I start building a component?**
A: Read [`human/CONCEPTS.md`](human/CONCEPTS.md) then [`human/BUILD_A_COMPONENT.md`](human/BUILD_A_COMPONENT.md)

**Q: How do I validate my component spec?**
A: `osiris components validate <name> --level strict --verbose`

**Q: What metrics must my driver emit?**
A: See [`ai/checklists/metrics_events_contract.md`](ai/checklists/metrics_events_contract.md)

**Q: How do connections work?**
A: Read [`human/modules/connectors.md`](human/modules/connectors.md) and [`ai/checklists/connections_doctor_contract.md`](ai/checklists/connections_doctor_contract.md)

**Q: What's the difference between component, driver, and connector?**
A: See the comparison tables in [`human/CONCEPTS.md`](human/CONCEPTS.md)

**Q: How do I use AI to help write code?**
A: Start with [`ai/README.md`](ai/README.md) router, then load relevant contracts

**Q: Where are the compliance rules for CI?**
A: [`ai/checklists/COMPONENT_AI_CHECKLIST.md`](ai/checklists/COMPONENT_AI_CHECKLIST.md) has 57 machine-verifiable rules

---

## Resources

- **User Guide**: [`../user-guide/user-guide.md`](../user-guide/user-guide.md)
- **Architecture**: [`../architecture.md`](../architecture.md)
- **Examples**: [`../examples/`](../examples/)
- **CHANGELOG**: [`../../CHANGELOG.md`](../../CHANGELOG.md)

---

**Remember**:
- **Component** = What (declarative spec)
- **Driver** = How (imperative code)
- **Connector** = Where (connection management)
- **Registry** = Catalog (validation, discovery)
- **Runner** = Executor (orchestration)

**Start building**: [`human/BUILD_A_COMPONENT.md`](human/BUILD_A_COMPONENT.md)
