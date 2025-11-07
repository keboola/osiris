# Osiris Component Developer Skill

## Overview

This Claude skill enables development of Osiris components in isolated projects, completely separate from the main Osiris repository. It provides comprehensive guidance for creating production-ready extractors, writers, and processors that integrate seamlessly with the Osiris ecosystem.

## Installation & Usage

### For Component Developers (Using the Skill)

1. **In your separate project** (e.g., PostHog, Keboola connector), ask Claude:
   ```
   "Load the Osiris component developer skill and help me create a PostHog extractor"
   ```

2. **Claude will guide you through**:
   - Creating the project structure
   - Writing spec.yaml with all required fields
   - Implementing the driver with correct signature
   - Adding discovery and doctor capabilities
   - Validating against 57-rule checklist
   - Packaging for distribution

3. **Test your component locally**:
   ```bash
   # In your component project
   pip install -e .
   pytest tests/
   ```

4. **Package for distribution**:
   ```bash
   python -m build
   # Creates dist/your_component-1.0.0-py3-none-any.whl
   ```

### For Osiris Maintainers (Installing Third-Party Components)

1. **Install the packaged component**:
   ```bash
   pip install path/to/component.whl
   # Or from PyPI
   pip install osiris-posthog
   ```

2. **Verify installation**:
   ```bash
   osiris component list
   # Should show new component
   ```

3. **Test the component**:
   ```bash
   # Discovery
   osiris discover posthog.extractor @posthog.prod

   # Health check
   osiris doctor posthog.extractor @posthog.prod

   # Run in pipeline
   osiris run test-pipeline.yaml --e2b
   ```

## Skill Contents

### 1. osiris-component-developer.md (Main Skill)
- Complete component architecture knowledge
- 57-rule validation checklist
- Driver implementation patterns
- Testing strategies
- Packaging instructions
- Security guidelines

### 2. posthog-example.md (Complete Example)
- Full PostHog extractor implementation
- All required files with working code
- Tests and documentation
- Ready-to-use template

### 3. README.md (This File)
- Usage instructions
- Workflow examples
- Integration guide

## Component Development Workflow

```mermaid
graph LR
    A[Developer loads skill] --> B[Create component structure]
    B --> C[Write spec.yaml]
    C --> D[Implement driver.py]
    D --> E[Add tests]
    E --> F[Validate checklist]
    F --> G[Package component]
    G --> H[Distribute via PyPI/tarball]
    H --> I[Install in Osiris]
    I --> J[Use in pipelines]
```

## Key Features Supported

- ✅ **All Osiris Capabilities**: Discovery, Doctor, Connections
- ✅ **E2B Cloud Compatible**: No hardcoded paths
- ✅ **Security Model**: x-connection-fields with override policies
- ✅ **Standardized Packaging**: PyPI or tarball distribution
- ✅ **Full Testing**: Spec validation, driver tests, E2E tests
- ✅ **57-Rule Validation**: Complete checklist compliance

## Example: Creating a PostHog Component

1. **Start new project**:
   ```bash
   mkdir posthog-osiris
   cd posthog-osiris
   ```

2. **Ask Claude**:
   ```
   "Use the Osiris component developer skill to create a PostHog extractor that can:
   - Extract events, persons, and cohorts
   - Support date filtering
   - Handle pagination
   - Implement discovery and doctor"
   ```

3. **Claude will**:
   - Create complete project structure
   - Generate spec.yaml with schemas
   - Implement driver with all capabilities
   - Add comprehensive tests
   - Provide packaging instructions

4. **Test locally**:
   ```bash
   pip install -e .
   pytest tests/
   ```

5. **Package and distribute**:
   ```bash
   python -m build
   twine upload dist/*
   ```

## Component Validation Checklist Summary

The skill includes a comprehensive 57-rule checklist covering:

- **SPEC (10)**: Name pattern, version, schemas
- **CAP (4)**: Capabilities declaration
- **DISC (6)**: Discovery determinism
- **CONN (4)**: Connection resolution
- **LOG (6)**: Metrics and logging
- **DRIVER (6)**: Implementation requirements
- **HEALTH (3)**: Doctor capability
- **PKG (5)**: Packaging standards
- **RETRY/DET (4)**: Idempotency
- **AI (9)**: LLM-friendly design

## Security Best Practices

- Never hardcode credentials
- Use config["resolved_connection"]
- Declare secrets in spec.yaml
- Implement x-connection-fields policies
- Mask sensitive data in logs
- Validate all inputs

## Support & Resources

- **Osiris Documentation**: [Component Architecture](../docs/developer-guide/COMPONENT-DOCS-MASTER-INDEX.md)
- **Examples**: See `posthog-example.md` for complete implementation
- **Validation**: Run through 57-rule checklist in skill

## Contributing

To improve this skill:
1. Update `osiris-component-developer.md` with new patterns
2. Add more examples to `posthog-example.md`
3. Update this README with new workflows

## Version

- Skill Version: 1.0.0
- Osiris Compatibility: >=0.5.4
- Last Updated: 2025-11-07