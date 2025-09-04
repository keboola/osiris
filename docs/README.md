# Osiris Pipeline Documentation

This directory contains comprehensive documentation for the Osiris MVP - an LLM-first conversational ETL pipeline generator.

## Core Documentation

### 📋 [Architecture](architecture.md)
System architecture overview, core components, and key principles of the LLM-first approach.

### 🏗️ [Repository Structure](repository-structure.md)
Code organization, file structure, and module descriptions.

### 📄 [Pipeline Format](pipeline-format.md)
YAML pipeline specification, configuration options, and format guidelines.

### 🔒 [SQL Safety](sql-safety.md)
Security guidelines, best practices, and safety measures for SQL generation.

## Examples & Samples

### 📁 [Examples Directory](examples/)
- [Sample Pipeline](examples/sample_pipeline.yaml) - Basic pipeline example
- [Top Customers Revenue](examples/top_customers_revenue.yaml) - Business analytics example
- [Examples README](examples/README.md) - Usage instructions for examples

## Planning & Milestones

### 🎯 [Milestones Directory](milestones/)
- [Initial Plan](milestones/_initial_plan.md) - Consolidated development planning
- [M0: Discovery Cache](milestones/m0-discovery-cache.md) - Cache fingerprinting (Complete)
- [M1: Component Registry](milestones/m1-component-registry-and-runner.md) - Registry & runner
- [M1b: Context Builder](milestones/m1b-context-builder-and-validation.md) - Validation & retry

### 📚 [Architecture Decision Records](adr/)
Key architectural decisions documented for the project

## Archived Documentation

### 📦 [Archive Directory](archive/)
- [Component Interfaces](archive/component-interfaces.md) - Legacy interface documentation

## Quick Start

For getting started with Osiris, refer to the main project [CLAUDE.md](../CLAUDE.md) which contains:
- Quick setup instructions
- Common commands
- Development workflow
- Pro mode usage

## Need Help?

1. Start with the [Architecture](architecture.md) for system overview
2. Check [Examples](examples/) for practical usage
3. Review [Pipeline Format](pipeline-format.md) for configuration details
4. Consult [SQL Safety](sql-safety.md) for security guidelines
