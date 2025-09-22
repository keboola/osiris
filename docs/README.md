# Osiris Documentation Index

Welcome to the Osiris documentation. This index provides a structured navigation to all documentation resources.

## 📚 Documentation Structure

### Overview
- [System Overview](./overview.md) - High-level architecture and concepts
- [Architecture](./architecture.md) - Technical architecture details

### User Guide
Start here if you're new to Osiris:
- [Kickstart Guide](./user-guide/kickstart.md) - Get started quickly
- [How-To Guide](./user-guide/how-to.md) - Common tasks and workflows
- [Crash Course](./user-guide/crashcourse.md) - Deep dive tutorial

### Developer Guide
For extending and contributing to Osiris:
- [Component Development](./developer-guide/components.md) - Building custom components
- [Adapters](./developer-guide/adapters.md) - Execution adapter architecture
- [Discovery System](./developer-guide/discovery.md) - Schema discovery contracts
- [Extending Osiris](./developer-guide/extending.md) - Extension points
- [LLM Instructions](./developer-guide/llms.txt) - Machine-readable instructions for AI development

### Reference Documentation
Technical specifications and formats:
- [Component Specifications](./reference/components-spec.md) - Component registry and specs
- [Pipeline Format](./reference/pipeline-format.md) - OML YAML format specification
- [Events & Metrics Schema](./reference/events_and_metrics_schema.md) - Observability schemas

### System Documentation
Security and internals:
- [SQL Safety](./system/sql-safety.md) - SQL injection prevention and safety measures

### Architecture Decision Records (ADRs)
Key design decisions and their rationale:

#### Core ADRs
- [ADR-0005: Session-Scoped Logging](./adr/0005-session-scoped-logging.md) - Structured logging system
- [ADR-0008: Component Registry](./adr/0008-component-registry.md) - Component discovery and management
- [ADR-0014: Discovery Framework](./adr/0014-llm-discovery-framework.md) - LLM-driven schema discovery
- [ADR-0025: OML v0.1.0 Specification](./adr/0025-oml-v0.1.0-specification.md) - Pipeline format specification

#### E2B & Execution
- [ADR-0026: E2B Transparent Proxy](./adr/0026-e2b-transparent-proxy.md) - Cloud execution architecture (comprehensive)

#### Future Enhancements
- [ADR-0027: Run Export Context](./adr/0027-run-export.md) - AI-friendly execution analysis
- [ADR-0028: Git Integration](./adr/0028-git-integration.md) - Version control for pipelines
- [ADR-0029: Memory Store](./adr/0029-memory-store.md) - Persistent knowledge base
- [ADR-0030: Agentic OML Generation](./adr/0030-agentic-oml-generation.md) - Improved LLM generation
- [ADR-0031: OML Control Flow](./adr/0031-oml-control-flow.md) - Conditional execution patterns
- [ADR-0032: Runtime Parameters](./adr/0032-runtime-parameters-profiles.md) - Parameters and profiles
- [ADR-0033: Resilience & Retry](./adr/0033-resilience-retry-policies.md) - Failure handling

[View all ADRs →](./adr/)

### Milestones & Roadmap
Project planning and progress:

#### Completed Milestones
- [M0: Foundation](./milestones/m0-foundation.md) - Core infrastructure
- [M1: Core MVP](./milestones/m1-core-mvp.md) - Working pipeline system
  - [M1a: Component Registry](./milestones/m1a-component-registry.md)
  - [M1b: Connection Management](./milestones/m1b-connection-management.md)
  - [M1c: Compiler](./milestones/m1c-compiler.md)
  - [M1d: Runner](./milestones/m1d-runner.md)
  - [M1e: Error Handling](./milestones/m1e-error-handling.md)
  - [M1f: E2B Integration](./milestones/m1f-e2b-integration.md)

#### Upcoming Milestones
- [M2: Scheduling & Planning](./milestones/m2-scheduling-planning.md) - Production features
- [M3: Technical Scale](./milestones/m3-technical-scale.md) - Performance optimization
- [M4: Data Warehouse Agent](./milestones/m4-data-warehouse-agent.md) - Intelligent DWH management

### Roadmap
- [2025 Vision](./roadmap/2025-vision.md) - Strategic direction
- [OSS Release Plan](./roadmap/oss-release-plan.md) - Open source strategy
- [Future Integrations](./roadmap/future-integrations.md) - Planned connectors

## 🔍 Quick Links

### Getting Started
1. Read the [Overview](./overview.md)
2. Follow the [Kickstart Guide](./user-guide/kickstart.md)
3. Try the [Crash Course](./user-guide/crashcourse.md)

### For Developers
1. Understand the [Architecture](./architecture.md)
2. Review [Component Development](./developer-guide/components.md)
3. Study the [Discovery System](./developer-guide/discovery.md)

### Key Features
- **LLM-First Design**: Natural language pipeline generation
- **E2B Cloud Execution**: Transparent proxy with <1% overhead (see [ADR-0026](./adr/0026-e2b-transparent-proxy.md))
- **HTML Reports**: `osiris logs html --open` for comprehensive analysis
- **Progressive Discovery**: Smart schema exploration with caching

## 📖 Documentation Standards

All documentation follows these principles:
- **Concise**: Direct, actionable information
- **Current**: Reflects actual implementation
- **Cross-linked**: Easy navigation between related topics
- **Examples**: Real-world usage patterns

## 🚀 Latest Updates

**v0.1.2 (Current)**
- E2B transparent proxy implementation complete
- Comprehensive documentation overhaul
- 33 ADRs documenting all design decisions
- HTML report generation for session analysis

For detailed changes, see the [CHANGELOG](../CHANGELOG.md) in the repository root.