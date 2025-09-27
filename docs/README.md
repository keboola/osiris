# Osiris Documentation Hub

Welcome to the Osiris Pipeline documentation. Osiris is an LLM-first ETL pipeline system that uses AI to help you create and run data pipelines.

## 🚀 Quick Navigation

### Getting Started
- **[Quickstart](quickstart.md)** - Get up and running with Osiris in 5 minutes
- **[Overview](overview.md)** - What is Osiris and how it works (non-technical)
- **[Architecture](architecture.md)** - Technical deep-dive with detailed diagrams:
  - Conversational Agent architecture (7 focused diagrams)
  - Compilation and execution flows
  - E2B transparent proxy design

### 📚 Guides

#### For Users
- **[User Guide](user-guide/user-guide.md)** - Complete guide covering:
  - Connections & secrets management
  - Running pipelines (local and E2B)
  - Understanding logs and troubleshooting
  - Common issues and solutions
  - Best practices
- **[AI Assistant Guide](user-guide/llms.txt)** - Instructions for ChatGPT/Claude to generate pipelines

#### For Developers
- **[Developer Guide](developer-guide/README.md)** - Comprehensive development documentation:
  - Module architecture (7 modules documented)
  - LLM contracts for AI-assisted development
  - Testing patterns and guidelines
  - Contributing guidelines
- **[LLM Contracts](developer-guide/)** - Machine-readable instructions:
  - [`llms.txt`](developer-guide/llms.txt) - Main development contract
  - [`llms-drivers.txt`](developer-guide/llms-drivers.txt) - Driver patterns
  - [`llms-cli.txt`](developer-guide/llms-cli.txt) - CLI patterns
  - [`llms-testing.txt`](developer-guide/llms-testing.txt) - Test patterns

### 📖 Reference Documentation
- **[Pipeline Format (OML)](reference/pipeline-format.md)** - OML v0.1.0 specification
- **[CLI Reference](reference/cli.md)** - All command-line options and flags
- **[Component Specifications](reference/components-spec.md)** - Component spec format and schema
- **[SQL Safety Rules](reference/sql-safety.md)** - Context-specific SQL validation
- **[Events & Metrics Schema](reference/events_and_metrics_schema.md)** - Log format and observability
- **[AIOP Architecture](architecture/aiop.md)** - AI Operation Package technical documentation
- **[AIOP Schema](reference/aiop.schema.json)** - AIOP JSON-LD schema and context

### 💡 Examples & Future Plans
- **[Example Pipelines](examples/)** - Ready-to-use pipeline examples:
  - MySQL to CSV export
  - MySQL to Supabase replication
- **[Roadmap](roadmap/)** - Future development plans:
  - [M2: Scheduling & Planning](roadmap/milestone-m2-planning.md)
  - [M3: Scale & Performance](roadmap/milestone-m3-technical-scale.md)
  - [M4: Data Warehouse Agent](roadmap/milestone-m4-dwh-agent.md)
- **[Milestones](milestones/README.md)** - Milestone methodology and tracking

### 🏛️ Architecture & History
- **[Architecture Decision Records](adr/)** - 33 ADRs documenting all design decisions
- **[Archive](archive/)** - Historical documentation and early implementations

## 📦 Current Version

**v0.3.0** (Released: 2025-09-27)
- ✅ AI Operation Package (AIOP) for LLM-friendly debugging
- ✅ Four-layer semantic architecture for AI understanding
- ✅ Automatic export after every pipeline run
- ✅ Delta analysis with "Since last run" comparisons
- ✅ Comprehensive secret redaction with DSN masking
- ✅ 921 tests passing with production-ready quality

## 📚 Documentation Highlights

### Recently Updated
- **AIOP Documentation** - Complete AI Operation Package architecture and usage
- **Architecture diagrams** - New layered Conversational Agent diagrams
- **User Guide** - Added AIOP quickstart, troubleshooting, and best practices
- **Developer Guide** - AIOP development workflow and team operations guide
- **Milestone M2a** - Marked complete with production-ready AIOP system

## 🗺️ Documentation Map

```
For Users:
  Start Here → Quickstart → User Guide → Examples
  Need Help? → User Guide (Common Issues) → CLI Reference

For Developers:
  Start Here → Developer Guide → Module Docs → LLM Contracts
  Contributing? → ADRs → Testing Patterns → Module Docs

For AI Assistants:
  Users → user-guide/llms.txt
  Developers → developer-guide/llms*.txt
```

## 🔍 Finding Information

- **How to run a pipeline?** → [Quickstart](quickstart.md) or [User Guide](user-guide/user-guide.md)
- **Connection setup?** → [User Guide: Connections](user-guide/user-guide.md#1-connections--secrets)
- **Understanding logs?** → [User Guide: Observability](user-guide/user-guide.md#3-observability)
- **Adding a new driver?** → [Developer Guide: Drivers](developer-guide/module-drivers.md)
- **Design decisions?** → [ADRs](adr/)
- **Future features?** → [Roadmap](roadmap/)
