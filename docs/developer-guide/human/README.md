# Osiris Developer Guide (Human)

> **For AI Agents**: See [`../ai/README.md`](../ai/README.md)

---

## Start Here: 3-Step Onboarding

**New to Osiris component development?**

1. **[CONCEPTS.md](CONCEPTS.md)** - Understand Component, Driver, Connector, Registry, Runner (15 min read)
2. **[BUILD_A_COMPONENT.md](BUILD_A_COMPONENT.md)** - Step-by-step guide with code examples (30 min)
3. **[modules/](modules/)** - Deep dive into specific subsystems (reference as needed)

---

## Common Tasks

| Task | Start Here | Then Read |
|------|------------|-----------|
| **Build an extractor** | [BUILD_A_COMPONENT.md](BUILD_A_COMPONENT.md) | [examples/shopify.extractor/](examples/shopify.extractor/) |
| **Build a writer** | [BUILD_A_COMPONENT.md](BUILD_A_COMPONENT.md) | [modules/drivers.md](modules/drivers.md) |
| **Build a processor** | [BUILD_A_COMPONENT.md](BUILD_A_COMPONENT.md) | [modules/drivers.md](modules/drivers.md) |
| **Add connection type** | [modules/connectors.md](modules/connectors.md) | [BUILD_A_COMPONENT.md Step 4](BUILD_A_COMPONENT.md#step-4-define-connections--doctor) |
| **Implement discovery** | [modules/components.md](modules/components.md) | [../ai/checklists/discovery_contract.md](../ai/checklists/discovery_contract.md) |
| **Run locally** | [BUILD_A_COMPONENT.md Step 7](BUILD_A_COMPONENT.md#step-7-validate-locally) | - |
| **Run in E2B** | [modules/remote.md](modules/remote.md) | - |
| **Write tests** | [BUILD_A_COMPONENT.md Step 8](BUILD_A_COMPONENT.md#step-8-write-tests) | [../llms-testing.txt](../llms-testing.txt) |

---

## Documentation Structure

```
human/
├── README.md              ← You are here
├── CONCEPTS.md            ← Core abstractions (START HERE)
├── BUILD_A_COMPONENT.md   ← Step-by-step guide
│
├── modules/               ← Deep dives into subsystems
│   ├── components.md      ← Component Registry & validation
│   ├── connectors.md      ← Connections & secrets
│   ├── drivers.md         ← Driver protocol & runtime
│   ├── runtime.md         ← Local execution orchestration
│   ├── remote.md          ← E2B cloud execution
│   ├── cli.md             ← CLI commands
│   └── core.md            ← LLM agent & compilation
│
└── examples/              ← Reference implementations
    └── shopify.extractor/ ← Complete example with inline docs
        ├── spec.yaml
        ├── driver_skeleton.py
        ├── connections.example.yaml
        ├── discovery.sample.json
        └── e2e_manifest.yaml
```

---

## Module Quick Reference

| Module | Purpose | Key Files |
|--------|---------|-----------|
| **components** | Spec registry, validation | `osiris/components/registry.py` |
| **connectors** | Connection management, secrets | `osiris/connectors/<family>/` |
| **drivers** | Step execution logic | `osiris/drivers/*_driver.py` |
| **runtime** | Local orchestration | `osiris/core/runner_v0.py` |
| **remote** | E2B cloud execution | `osiris/remote/e2b_transparent_proxy.py` |
| **cli** | User commands | `osiris/cli/` |
| **core** | LLM agent, compilation | `osiris/core/conversational_agent.py` |

---

## Development Workflow

### Setup

```bash
# 1. Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Install pre-commit hooks
make pre-commit-install
```

### Build Loop

```bash
# 1. Write spec
vim components/mycomponent/spec.yaml

# 2. Validate
osiris components validate mycomponent --level strict

# 3. Implement driver
vim osiris/drivers/mycomponent_driver.py

# 4. Write tests
vim tests/drivers/test_mycomponent_driver.py

# 5. Run tests
make test

# 6. Format code
make fmt

# 7. Test locally
cd testing_env
python ../osiris.py compile test.yaml
python ../osiris.py run --last-compile --verbose
```

---

## Key Concepts Recap

- **Component** = What (declarative spec in YAML)
- **Driver** = How (imperative Python code)
- **Connector** = Where (connection management, reusable)
- **Registry** = Catalog (validates and serves metadata)
- **Runner** = Executor (orchestrates driver execution)

**Read full explanations**: [CONCEPTS.md](CONCEPTS.md)

---

## Getting Help

### Quick Navigation

```
Question:                    Answer:
────────────────────────── ─────────────────────────────────
"How do I start?"           CONCEPTS.md
"How do I build X?"         BUILD_A_COMPONENT.md
"How does Y work?"          modules/Y.md
"What's an example?"        examples/shopify.extractor/
"What are the rules?"       ../ai/checklists/
```

### Common Questions

**Q: Where do I start?**
A: Read [CONCEPTS.md](CONCEPTS.md), then [BUILD_A_COMPONENT.md](BUILD_A_COMPONENT.md)

**Q: How do I validate my spec?**
A: `osiris components validate <name> --level strict --verbose`

**Q: What metrics must I emit?**
A: See [BUILD_A_COMPONENT.md Step 5](BUILD_A_COMPONENT.md#step-5-emit-telemetry)

**Q: How do connections work?**
A: Read [modules/connectors.md](modules/connectors.md)

**Q: What's a complete example?**
A: See [examples/shopify.extractor/](examples/shopify.extractor/)

---

## AI-Assisted Component Development

You can either follow the step-by-step guide in [BUILD_A_COMPONENT.md](BUILD_A_COMPONENT.md), or you can ask an AI system (e.g., Claude) to generate a component for you. Use the prompt template in [`../ai/build-new-component.md`](../ai/build-new-component.md) as your starting point. The template includes all necessary context from LLM contracts and validation rules, allowing the AI to generate production-quality components automatically.

---

## Resources

- **Reference Docs**: [`../../reference/`](../../reference/)
- **Architecture Decisions**: [`../../adr/`](../../adr/)
- **AI Compliance**: [`../ai/checklists/`](../ai/checklists/)
- **User Guide**: [`../../user-guide/user-guide.md`](../../user-guide/user-guide.md)

---

**Ready to build?** → [BUILD_A_COMPONENT.md](BUILD_A_COMPONENT.md)
