# 0024: Component Packaging as Osiris Plugins (OCP Model)

**Status**: Proposed  
**Date**: 2025-01-09  
**Author**: System Architecture Team  

## Summary

This ADR proposes the Osiris Component Package (OCP) model, a plugin architecture that allows third-party developers to distribute Osiris components as self-contained Python packages. Each OCP bundles a component spec, driver implementation, optional connector, and tests into a single pip-installable package that auto-registers with the Osiris runtime via Python entry points. This eliminates the current dual-registry problem and enables a scalable ecosystem where developers can contribute components without modifying core Osiris code.

## Context

The current Osiris architecture has several pain points that limit extensibility:

1. **Split Implementation**: Component specifications live in `components/*/spec.yaml` while driver implementations reside in `osiris/drivers/*.py`, creating a maintenance burden and potential for drift.

2. **Hard-coded Registry**: The Runner uses a hard-coded Driver Registry, leading to mismatches between declared components (in specs) and runnable components (with drivers).

3. **High Contribution Barrier**: Third-party developers wanting to contribute components (e.g., Shopify, HubSpot, Snowflake) must:
   - Fork the core repository
   - Add files to multiple locations
   - Submit PRs that modify core code
   - Wait for core team review and release cycles

4. **Monolithic Growth**: As more components are added, the core repository grows unbounded, increasing CI times and dependency conflicts.

5. **Version Coupling**: All components share the same version as core, preventing independent updates and bug fixes.

**Note**: The OCP model primarily affects the runtime discovery and driver loading layer of Osiris. The compiler will continue to validate against component specs, while the runner will dynamically discover and load drivers from installed OCPs.

## Decision

We will introduce the **Osiris Component Package (OCP)** model with the following design:

### Package Structure
Each OCP is a standard Python package with this structure:
```
shopify_osiris/
├── pyproject.toml           # Package metadata + entry points
├── spec.yaml                # Component specification
├── driver.py                # Driver implementation
├── connector.py             # Optional: Connector if needed
├── tests/                   # Component-specific tests
└── __init__.py              # Package initialization
```

### Component Specification Enhancement
The `spec.yaml` will include runtime metadata:
```yaml
family: shopify
role: extractor
version: 1.0.0
x-runtime:
  driver: shopify_osiris.driver:ShopifyExtractorDriver
  min_osiris_version: 0.2.0
  max_osiris_version: 0.9.99
```

### Python Entry Points
OCPs register via standard Python entry points in `pyproject.toml`:
```toml
[project.entry-points."osiris.components"]
shopify.extractor = "shopify_osiris:load_spec"
```

### Runtime Discovery
The Osiris runtime will:
1. Scan installed packages for `osiris.components` entry points
2. Load and validate component specs
3. Build the runtime registry dynamically
4. Verify API compatibility before registration

### Security Model
- **Plugin Control**: A `--disable-plugins` flag (and corresponding config setting) allows enterprise environments to run Osiris with all plugins disabled, using only built-in components
- **Allowlist Mode**: Production environments can restrict to approved OCPs via configuration
- **Sandboxing**: Driver execution in restricted contexts (future enhancement)
- **Signature Verification**: Optional cryptographic signing of OCPs

#### Sandbox Preference (e2b)
Osiris recommends executing OCP drivers in an e2b sandbox by default when plugins are enabled. The e2b runtime provides secure, isolated execution environments with fine-grained control over network access, filesystem permissions, and resource limits. This ensures that untrusted or third-party plugins cannot compromise the host system or access sensitive data outside their designated scope.

- **Configuration Example**:
  ```yaml
  # osiris.yaml
  plugins:
    enabled: true  # Set to false to disable all plugins
    allowlist:
      - shopify-osiris==1.2.3
      - hubspot-osiris>=2.0.0
    sandbox:
      provider: e2b        # e2b|none|docker
      policy: strict       # strict|permissive
      network: deny        # deny|egress-only|allow
      fs_access: readonly  # readonly|readwrite|none
  ```

## Consequences

### Positive

1. **Single Source of Truth**: Component spec and driver are co-located, eliminating registry drift.

2. **Improved Developer Experience**:
   ```bash
   pip install shopify-osiris
   osiris components list  # shopify.extractor appears
   ```

3. **Independent Versioning**: Each OCP can evolve at its own pace with semantic versioning.

4. **Clean Core**: Osiris core remains focused on the runtime, validation, and interfaces.

5. **Ecosystem Growth**: Lower barrier enables community contributions without core team bottleneck.

6. **Testing Isolation**: Component tests run in their own package context.

### Negative / Risks

1. **Security Concerns**: 
   - Malicious packages could execute arbitrary code
   - Mitigation: --disable-plugins flag, allowlists, sandboxing, code signing

2. **Namespace Conflicts**:
   - Two OCPs might claim the same `family.role`
   - Mitigation: Fail fast with clear error messages

3. **API Compatibility**:
   - OCPs might break with core updates
   - Mitigation: Version ranges, compatibility matrix

4. **Dependency Hell**:
   - OCPs might have conflicting dependencies
   - Mitigation: Virtual environments, dependency resolution

5. **Discovery Performance**:
   - Scanning many packages could slow startup
   - Mitigation: Caching, lazy loading

## Alternatives Considered

1. **Status Quo (Monolithic)**:
   - Keep all drivers in core
   - Pro: Simple, single repository
   - Con: Poor scalability, high maintenance burden

2. **Component Registry Filter**:
   - Filter registry to show only components with drivers
   - Pro: Solves mismatch problem
   - Con: Doesn't address third-party distribution

3. **Git Submodules**:
   - Components as git submodules
   - Pro: Separate repositories
   - Con: Complex workflow, poor Python integration

4. **Dynamic Loading from URLs**:
   - Download components at runtime
   - Pro: No installation needed
   - Con: Security nightmare, network dependency

## Status

**Proposed** - This architecture is planned for implementation post-M1c. It is explicitly out of scope for the current Golden Path milestone (MySQL → Supabase) but represents the future direction for component extensibility.

## Next Steps

1. **Define Entry Point Contract** (M2):
   - Formalize the `osiris.components` entry point interface
   - Document the `load_spec()` function signature

2. **Create Scaffold Generator** (M2):
   - Provide `cookiecutter` template for new OCPs
   - Include example driver, tests, and CI configuration

3. **Reference Implementation** (M2):
   - Ship `supabase-osiris` as the first official OCP
   - Demonstrate migration from monolithic to plugin

4. **Runtime Enhancement** (M2):
   - Implement OCP discovery in `DriverRegistry`
   - Add `--runnable` filter to `osiris components list`
   - Implement `--disable-plugins` flag and configuration

5. **Security Framework** (M3):
   - Design allowlist configuration format
   - Implement basic sandboxing for driver execution
   - Add plugin enable/disable configuration
   - Develop e2b driver adapter with policy presets for common security profiles

6. **CI/CD Updates** (M2):
   - Add tests ensuring installed OCPs load successfully
   - Create compatibility matrix testing

## References

- [0005: Component Specification and Registry](./0005-component-specification-and-registry.md) - Core component architecture
- [0006: Pipeline Runner and Execution](./0006-pipeline-runner-and-execution.md) - Runtime execution model
- [0008: Component Registry](./0008-component-registry.md) - Current registry implementation
- [0015: Compile Contract Determinism](./0015-compile-contract-determinism-fingerprints-nosecrets.md) - Compiler architecture
- [0022: Streaming IO and Spill](./0022-streaming-io-and-spill.md) - Related runtime architecture
- [0023: Remote Object Store Writers](./0023-remote-object-store-writers.md) - Component interaction patterns
- [Python Entry Points Documentation](https://packaging.python.org/en/latest/specifications/entry-points/)
- [PEP 517](https://peps.python.org/pep-0517/) - Python build system specifications
