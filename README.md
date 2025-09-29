# Osiris Pipeline v0.3.1

**The deterministic compiler for AI-native data pipelines.**
You describe outcomes in plain English; Osiris compiles them into **reproducible, production-ready manifests** that run with the **same behavior everywhere** (local or cloud).

## 🚀 Quick Start

```bash
# Setup
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Initialize configuration
osiris init

# Start conversation - describe what you want in plain English
osiris chat
```

## 🎯 What Makes Osiris Different

- **Compiler, not orchestrator** - Others schedule what you hand-craft. Osiris generates, validates, and compiles pipelines from plain English.
- **Determinism as a contract** - Fingerprinted manifests guarantee reproducibility across environments.
- **Conversational → executable** - Describe intent; Osiris interrogates real systems and proposes a feasible plan.
- **Run anywhere, same results** - Transparent adapters deliver execution parity (local and E2B today).
- **Boring by design** - Predictable, explainable, portable — industrial-grade AI, not magical fragility.

## 📊 Visual Overview

### Pipeline Execution Dashboard
![Osiris Dashboard](docs/img/logs-dashb.jpg)
*Interactive HTML dashboard showing pipeline execution metrics and performance*

### Run Overview with E2B Integration
![Run Overview](docs/img/run-overview.jpg)
*Comprehensive run overview showing E2B cloud execution with <1% overhead*

### Step-by-Step Pipeline Execution
![Pipeline Steps](docs/img/run-pipeline-steps.jpg)
*Detailed view of pipeline steps with row counts and execution times*

## Example Conversation

```
$ osiris chat

You: "Identify customers inactive for 90 days and export to CSV for re-activation campaign"

Osiris: I'll help you identify inactive customers. Let me explore your database...
        Found tables: customers, orders, sessions. I'll create a pipeline that:
        1. Identifies customers with no activity in the last 90 days
        2. Exports their details for your re-activation campaign

        Here's the generated pipeline:
        [Shows OML pipeline with SQL queries and transformations]

        Shall I compile this for execution?

You: "Yes, compile and run it locally"

Osiris: ✓ Pipeline compiled (manifest hash: a3f2b1c4)
        ✓ Execution complete: 847 inactive customers exported to output/inactive_customers.csv
        View report: osiris logs html --open
```

## ✨ Key Features

- **AI-native pipeline generation** from plain English descriptions
- **Deterministic compilation** with fingerprinted, reproducible manifests
- **Run anywhere** with identical behavior (local or E2B cloud)
- **Interactive HTML reports** with comprehensive observability
- **AI Operation Package (AIOP)** for LLM-friendly debugging and analysis
- **LLM-friendly** with machine-readable documentation for AI assistants

## 🤖 LLM-Friendly Documentation

Osiris provides machine-readable documentation for AI assistants:

- **For Users**: Share [`docs/user-guide/llms.txt`](docs/user-guide/llms.txt) with ChatGPT/Claude to generate pipelines
- **For Developers**: Use [`docs/developer-guide/llms.txt`](docs/developer-guide/llms.txt) for AI-assisted development
- **Pro Mode**: Customize AI behavior with `osiris dump-prompts --export` and `osiris chat --pro-mode`

## 🚀 E2B Cloud Execution

Run pipelines in isolated E2B sandboxes with <1% overhead:

```bash
# Run in cloud sandbox
osiris run pipeline.yaml --e2b

# With custom resources
osiris run pipeline.yaml --e2b --e2b-cpu 4 --e2b-mem 8
```

See the [User Guide](docs/user-guide/user-guide.md#2-running-pipelines) for complete E2B documentation.

## 🤖 AI Operation Package (AIOP)

Every pipeline run automatically generates a comprehensive AI Operation Package for LLM analysis:

```bash
# View AIOP export after any run
osiris logs aiop --last

# Generate human-readable summary
osiris logs aiop --last --format md

# Configure in osiris.yaml
aiop:
  enabled: true  # Auto-export after each run
  policy: core   # ≤300KB for LLM consumption
```

AIOP provides four semantic layers for AI understanding:
- **Evidence Layer**: Timestamped events, metrics, and artifacts
- **Semantic Layer**: DAG structure and component relationships
- **Narrative Layer**: Natural language descriptions with citations
- **Metadata Layer**: LLM primer and configuration

See [AIOP Architecture](docs/architecture/aiop.md) for details.

## 📚 Documentation

For comprehensive documentation, visit the **[Documentation Hub](docs/README.md)**:

- **[Quickstart](docs/quickstart.md)** - 10-minute setup guide
- **[User Guide](docs/user-guide/user-guide.md)** - Complete usage documentation
- **[Architecture](docs/architecture.md)** - Technical deep-dive with diagrams
- **[Developer Guide](docs/developer-guide/README.md)** - Module patterns and LLM contracts
- **[Examples](docs/examples/)** - Ready-to-use pipelines

## 🚦 Roadmap

- **v0.2.0** ✅ - Conversational agent, deterministic compiler, E2B parity
- **v0.3.0** ✅ - AI Operation Package (AIOP) for LLM-friendly debugging
- **v0.3.1 (Current)** ✅ - Fixed validation warnings for ADR-0020 compliant configs
- **M2** - Production workflows, approvals, orchestrator integration
- **M3** - Streaming, parallelism, enterprise scale
- **M4** - Iceberg tables, intelligent DWH agent

See [docs/roadmap/](docs/roadmap/) for details.

## License

Apache-2.0
