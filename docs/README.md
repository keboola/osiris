# Osiris Documentation

**Start here.** This repository uses a structured docs governance model to keep documentation organized and maintainable.

## Documentation Structure

- **ADRs** → `docs/adr/` — Concise, stable architectural decisions (with Status field).
- **Milestones (Initiatives)** → `docs/milestones/<slug>/`
  - `00-initiative.md` — Index, goal, Definition of Done (DoD), KPIs
  - `10-plan.md` — Scope, risks, effort estimates
  - `20-execution.md` — Checklists, sub-agents, PR/issues links
  - `30-verification.md` — Tests, metrics, verification commands
  - `40-retrospective.md` — What went well / areas to improve
  - `attachments/` — Bulky reports, coverage data, detailed audits
- **Design (Work-in-Progress)** → `docs/design/` — Technical designs pending acceptance
- **Reference (Stable Specs)** → `docs/reference/` — Specifications, schema, formats
- **Guides (How-To)** → `docs/guides/` — User and operator guides
- **Reports (One-Off)** → `docs/reports/<date>-<topic>/` — Analysis, audits, findings
- **Archive (Completed)** → `docs/archive/<slug>-v<semver>/` — Completed initiatives (kept for history)

## Current Initiatives

### MCP v0.5.0
- **ADR**: [`docs/adr/0036-mcp-interface.md`](adr/0036-mcp-interface.md) — CLI-first security architecture
- **Milestone**: [`docs/milestones/mcp-finish-plan.md`](milestones/mcp-finish-plan.md)
- **Phase 1-3**: ✅ Complete (CLI security, functional parity, comprehensive testing)
- **Phase 4**: 📋 In Progress (Documentation & Release Preparation)
- **Reference**: [`docs/reference/mcp-tool-reference.md`](reference/mcp-tool-reference.md)
- **Reports**: [`docs/reports/`](reports/)

### AIOP (AI Operation Package)
- **ADR**: [`docs/adr/0027-aiop.md`](adr/0027-aiop.md)
- **Milestone**: [`docs/milestones/m2a-aiop.md`](milestones/m2a-aiop.md) — ✅ Complete
- **Reference**: [`docs/reference/aiop.schema.json`](reference/aiop.schema.json)

## Legacy Navigation (for reference)

### 🚀 Getting Started
- **[Quickstart](quickstart.md)** - Get up and running in 5 minutes
- **[Overview](overview.md)** - What is Osiris and how it works
- **[Architecture](architecture.md)** - Technical deep-dive with diagrams

### 📚 Guides
- **[User Guide](user-guide/user-guide.md)** - For end users
- **[Developer Guide](developer-guide/README.md)** - For contributors
- **[LLM Contracts](developer-guide/)** - Machine-readable patterns for AI

### 📖 Reference
- **[Pipeline Format (OML)](reference/pipeline-format.md)** - OML v0.1.0 specification
- **[CLI Reference](reference/cli.md)** - Command-line options
- **[Component Specifications](reference/components-spec.md)** - Component spec format
- **[SQL Safety Rules](reference/sql-safety.md)** - SQL validation rules
- **[Events & Metrics Schema](reference/events_and_metrics_schema.md)** - Log formats

### 💡 Examples & Roadmap
- **[Example Pipelines](examples/)** - Ready-to-use pipeline examples
- **[Roadmap](roadmap/)** - Future development plans

### 🏛️ Architecture & Decisions
- **[Architecture Decision Records](adr/)** - All design decisions (35+ ADRs)
- **[Archive](archive/)** - Historical documentation

## Contributor Guidelines

- **Update initiative indices** (`00-initiative.md`) when scope or DoD changes.
- **Link reports** from the initiative's `attachments/` or `docs/reports/` with back-references.
- **Keep ADRs short** — Link to milestones for implementation details.
- **Prefer incremental docs** — Small, focused documents over giant monoliths.
- **Archive on completion** — Move completed initiatives to `docs/archive/<slug>-v<semver>/` to keep active folders clean.

## Version Status

**Current Release**: v0.5.0 (in progress)
- ✅ Phase 1-3: Security, Functionality, Testing
- 📋 Phase 4: Documentation & Release Preparation

**Previous Release**: v0.3.1 (2025-09-27) - AIOP + Full testing suite
