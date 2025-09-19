# ADR 0008: Component Registry

## Status
Accepted

## Context
In the Osiris pipeline, components are the fundamental building blocks that perform various tasks. Each component can have different configurations, capabilities, versions, and metadata. As the number of components grows, managing them consistently and reliably becomes challenging. There is a need for a centralized registry that declares each component's configuration schema, capabilities (such as discovery, analytics, in-memory processing), versioning, and metadata.

## Decision
We will implement a Component Registry within Osiris that serves as a single source of truth for component specifications. Each component will declare:

- Its configuration schema, ensuring consistent validation of input parameters.
- Its capabilities, including but not limited to discovery, analytics, and in-memory processing.
- Versioning information to track changes and maintain compatibility.
- Metadata to describe the component's purpose, dependencies, and other relevant details.

This registry will enable deterministic generation of YAML configuration files, making pipeline definitions reproducible and easier to manage. It will also facilitate AI assistance by providing structured and comprehensive component information, improving automation and user experience. Consistent validation against component schemas will reduce runtime errors and improve robustness.

Looking forward, the Component Registry will evolve to support business process workflows and secrets management tied directly to component specifications, enhancing security and operational capabilities.

## Consequences
- Improved consistency and reliability in component configuration and usage.
- Easier automation and AI-driven assistance in pipeline creation and management.
- Reduced errors through schema validation and version control.
- A foundation for future extensions, including workflow orchestration and secure secrets handling.

## Amendment (2025-01-03)

### Discover CLI Implementation
The `osiris components discover <type>` command, while part of the CLI interface design, is intentionally deferred to Phase M1d (Pipeline Runner MVP). The discover functionality requires the actual component runner infrastructure to execute discovery mode against live data sources. 

This deferral allows us to:
- Complete the registry foundation without blocking on runner implementation
- Design the discover interface with full knowledge of runner capabilities
- Ensure discover mode integrates properly with the deterministic execution model

The placeholder implementation in M1a.5 marks the interface location and will be completed when the runner infrastructure exists in M1d.
