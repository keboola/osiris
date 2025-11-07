# Third-Party Component Packaging - Executive Summary

## Overview

This package includes a complete strategy for third-party Osiris Component Packages (OCPs) - enabling independent developers to build, test, and distribute components without modifying core Osiris code.

## Documents Included

### 1. **THIRD_PARTY_COMPONENT_PACKAGING_STRATEGY.md** (Main Strategy Document)
   - **Length**: ~1500 lines
   - **Audience**: Architects, Technical Leads
   - **Content**:
     - Current state analysis
     - Comprehensive OCP model design
     - Package structure specifications
     - Security and dependency management
     - Implementation roadmap (4 phases)
     - Comparison with alternatives
     - Backwards compatibility approach

   **Key Sections**:
   - Package Format (PyPI, Tarball, Git-based)
   - Entry Point Discovery & Registration
   - Security Configuration (Allowlist/Denylist)
   - Migration Path for Built-in Components
   - Distribution Checklist
   - Compatibility Matrix

### 2. **THIRD_PARTY_COMPONENT_IMPLEMENTATION_GUIDE.md** (Developer Quick Start)
   - **Length**: ~400 lines
   - **Audience**: Component Developers
   - **Content**:
     - 5-minute quick start
     - Step-by-step implementation (10 detailed steps)
     - Code templates (minimal boilerplate)
     - Common issues & solutions
     - E2B testing guide
     - Release checklist

   **Key Sections**:
   - Quick Start CLI (from template)
   - Create Package Structure
   - Write pyproject.toml (minimal example)
   - Create spec.yaml
   - Implement Driver
   - Write Tests
   - Build & Publish
   - Troubleshooting

### 3. **THIRD_PARTY_COMPONENT_PACKAGING_SPEC.md** (Technical Specification)
   - **Length**: ~900 lines
   - **Audience**: Implementers, Maintainers
   - **Content**:
     - Formal specification for OCP format
     - Package metadata requirements
     - Entry point contract (detailed)
     - Spec.yaml schema reference
     - Driver interface contract
     - Runtime discovery algorithm
     - Security verification strategy
     - Dependency management rules
     - Validation checklist
     - CI/CD pipeline template

   **Key Sections**:
   - Distribution Formats (PyPI, Tarball)
   - Entry Point Group: `osiris.components`
   - Specification Requirements
   - Driver Signature & Interface
   - Runtime Discovery Order
   - Plugin Security Configuration
   - Verification Strategy
   - Dependency Conflict Detection
   - Component Validation Rules

### 4. **THIRD_PARTY_COMPONENT_EXAMPLES.md** (Practical Examples)
   - **Length**: ~500 lines
   - **Audience**: All Developers
   - **Content**:
     - 4 complete, runnable examples
     - Shopify Extractor (API integration)
     - PostgreSQL Writer (multiple write modes)
     - DuckDB Transformer (SQL processing)
     - Pipeline integration example
     - Test implementations
     - Execution commands

   **Key Examples**:
   1. Shopify Extractor (Extract customers, orders, products via API)
   2. PostgreSQL Writer (Append, replace, upsert modes)
   3. DuckDB Transformer (SQL-based data transformation)
   4. Complete OML Pipeline using all three components

## Current Architecture Analysis

### Built-in Components (Current State)

Located in `/Users/padak/github/osiris/`:
- **Specs**: `components/` (9 components)
  - duckdb.processor
  - filesystem.csv_writer
  - filesystem.csv_extractor
  - graphql.extractor
  - mysql.extractor
  - mysql.writer
  - supabase.extractor
  - supabase.writer

- **Drivers**: `osiris/drivers/` (6 drivers)
  - duckdb_processor_driver.py
  - filesystem_csv_writer_driver.py
  - filesystem_csv_extractor_driver.py
  - graphql_extractor_driver.py
  - mysql_extractor_driver.py
  - supabase_writer_driver.py

- **Discovery**: `osiris/components/registry.py` (ComponentRegistry)
- **Registry**: `osiris/core/driver.py` (DriverRegistry)
- **Schema**: `components/spec.schema.json`

### Issues Addressed

1. **Split Implementation**: Specs and drivers in different locations → **OCP co-locates them**
2. **Hard-coded Registry**: No plugin discovery → **Entry points enable dynamic loading**
3. **High Contribution Barrier**: Requires core PRs → **Separate repos with simple registration**
4. **Monolithic Growth**: Core grows with each component → **Core stays focused, plugins extend**
5. **Version Coupling**: All components version with core → **Independent versioning via packages**

## Key Design Decisions

### 1. Entry Points (Python Standard)

**Why**: Standard Python mechanism, no custom infrastructure
```toml
[project.entry-points."osiris.components"]
"shopify.extractor" = "shopify_osiris:load_spec"
```

**Benefits**:
- Auto-discovery via `importlib.metadata`
- Standard packaging tools
- Works with pip, poetry, uv
- No custom registry needed

### 2. Package Structure

**Why**: Follows Python conventions, easy to test
```
src/shopify_osiris/
├── __init__.py (exports load_spec)
├── spec.yaml (component metadata)
├── driver.py (implementation)
└── connector.py (optional)

tests/
├── test_spec.py (validation)
└── test_driver.py (implementation)
```

**Benefits**:
- Clear separation of concerns
- Easy to test each layer
- Familiar to Python developers

### 3. Spec.yaml Requirement

**Why**: Single source of truth for component metadata
- Loaded at runtime by `load_spec()` entry point
- Validates against existing `spec.schema.json`
- Includes runtime metadata in `x-runtime` section

### 4. Security by Configuration

**Why**: Flexible security model for different deployment scenarios
```yaml
plugins:
  enabled: true/false          # Master toggle
  allowlist: [...]             # Approved packages
  sandbox:
    provider: e2b|docker|none  # Sandboxing
```

**Benefits**:
- Enterprise can disable plugins
- Allowlist for approved suppliers
- Optional sandboxing via E2B

## Implementation Phases

### Phase 1: Foundation (Weeks 2-3)
- Extend `ComponentRegistry` with entry point discovery
- Add plugin security configuration
- Update `DriverRegistry` for plugin support
- Write plugin discovery tests

**Files**: `osiris/components/registry.py`, `osiris/core/driver.py`

### Phase 2: Developer Experience (Weeks 4-6)
- Create `cookiecutter` template
- Build `osiris component create` scaffolder
- Document entry point contract
- Convert Supabase to OCP (reference implementation)

**Files**: New `tools/component_scaffold/`, docs

### Phase 3: Security & Testing (Weeks 7-9)
- Implement allowlist/denylist config
- Add component signature verification (optional)
- Create E2B compatibility tests
- Write security guidelines

**Files**: Config extensions, test utilities

### Phase 4: Community (Ongoing)
- Publish OCP guide on GitHub
- Enable component submissions
- Build component directory
- Create example components

## Distribution Flow

```
Developer                 PyPI Registry            Osiris User
   |                           |                        |
   +-- Create OCP              |                        |
   |   (src/component/)         |                        |
   |                            |                        |
   +-- Test locally             |                        |
   |   (pytest)                 |                        |
   |                            |                        |
   +-- Build                    |                        |
   |   (python -m build)        |                        |
   |                            |                        |
   +-- Upload                   |                        |
       (twine upload)           |                        |
       ....................... + .................... |
                                |                        |
                                +-- pip install          |
                                    {component}          |
                                        |               |
                                        +-- Entry point
                                            registered
                                                |
                                                +-- osiris components
                                                    list
                                                    (component visible)
                                                        |
                                                        +-- Use in pipeline
```

## Minimal Component (Reference)

### Size

```
pyproject.toml      50-100 lines
spec.yaml           50-100 lines
driver.py          100-150 lines
__init__.py         20-30 lines
tests/              50-100 lines
README.md           50-100 lines
─────────────────────────────
Total:              ~400 lines
```

### Time to Create

- From scratch: **4-6 hours**
- From template: **1-2 hours**
- Using scaffolder CLI: **30 minutes**

## Testing Strategy

### Unit Tests (Required)
```bash
pytest tests/ --cov=src/
# Must have >80% coverage
```

### Spec Validation (Required)
```bash
python -c "
from my_component import load_spec
from jsonschema import validate
from osiris.components.registry import ComponentRegistry

spec = load_spec()
registry = ComponentRegistry()
validate(instance=spec, schema=registry._schema)
"
```

### E2B Compatibility (Recommended)
```bash
pytest -m e2b --e2b-api-key=$E2B_API_KEY
```

### CI/CD (GitHub Actions Template Provided)
- Lint, type check, tests across Python 3.11-3.13
- Spec validation
- Compatibility matrix (multiple Osiris versions)
- Coverage reporting

## Distribution Recommendations

### For Public Components
**Use**: PyPI + GitHub
- Standard Python package
- `pip install component-osiris`
- Automatic dependency resolution
- Version management
- Public discovery

### For Private/Internal Components
**Use**: Private PyPI or Tarball
- Host on private package index
- `pip install --index-url https://internal.pypi/`
- Or `pip install ./component.tar.gz`
- No public exposure

### For Enterprise
**Use**: PyPI + Allowlist
```yaml
plugins:
  enabled: true
  allowlist:
    - approved-component-osiris==1.0.0
  sandbox:
    provider: e2b
    policy: strict
```

## Migration Strategy for Built-in Components

### Timeline

1. **v0.6.0**: First external OCP ships (reference implementation)
2. **v0.7.0**: Plugin discovery in core, built-in components still available
3. **v0.8.0**: Announce deprecation of built-in versions
4. **v0.9.0**: Remove from built-in (users must install OCP package)

### Backwards Compatibility

- Pipelines using built-in components continue working
- Automatic migration: `pip install {component}-osiris`
- Deprecation warnings guide users to OCP
- Core stays stable, plugins are optional

## Security Considerations

### Design Principles

1. **Zero Secrets in MCP**: OCP drivers never see secrets directly
2. **Credential Delegation**: Secrets resolved by CLI, not MCP
3. **Allow/Deny Lists**: Admin controls which plugins can run
4. **Sandboxing Option**: E2B isolates untrusted code
5. **Transparent Execution**: Admin can inspect plugin source

### Threat Model

| Threat | Mitigation |
|--------|-----------|
| Malicious code in plugin | Allowlist + sandboxing (E2B) |
| Data exfiltration | Network isolation (E2B) |
| Dependency confusion | Pinned versions in pyproject.toml |
| API key leakage | Secrets not passed to plugins |
| Namespace collision | Warning + first-registered wins |

## Comparison with Alternatives

| Approach | Pros | Cons | Recommendation |
|----------|------|------|-----------------|
| **OCP (Entry Points)** | Standard, auto-discovery, clean | Requires entry point awareness | ✅ **Use this** |
| **Git Submodules** | Separate repos | Complex workflow, poor Python integration | ❌ Avoid |
| **URL Downloads** | No installation | Security nightmare | ❌ Avoid |
| **Docker Plugins** | Isolation | Overhead, E2B incompatible | ❌ For future |
| **Config-Based Loading** | Flexible | Hard to version, package issues | ❌ Secondary only |

## Next Steps (Recommendations)

### Immediate (Weeks 1-2)
1. Read THIRD_PARTY_COMPONENT_PACKAGING_STRATEGY.md (20 min)
2. Review current implementation in driver.py, registry.py (30 min)
3. Create prototype OCP (1-2 hours)

### Short-term (Weeks 3-4)
1. Implement Phase 1 (entry point discovery) in core
2. Write comprehensive tests
3. Create cookiecutter template

### Medium-term (Weeks 5-8)
1. Implement scaffolder CLI
2. Convert reference component (Supabase)
3. Document and publish guide

### Long-term (Weeks 9+)
1. Security hardening (optional signing)
2. Component registry/marketplace
3. Community contribution workflow

## Key Files in Osiris Codebase

**Current Implementation** (to understand):
- `/Users/padak/github/osiris/osiris/components/registry.py` (140 lines) - Component discovery
- `/Users/padak/github/osiris/osiris/core/driver.py` (250 lines) - Driver registry
- `/Users/padak/github/osiris/components/spec.schema.json` (483 lines) - Specification schema
- `/Users/padak/github/osiris/pyproject.toml` (270 lines) - Build configuration

**To Modify** (for plugin support):
- `osiris/components/registry.py` - Add `_load_plugin_specs()` method
- `osiris/core/driver.py` - Handle plugin namespace conflicts
- `osiris/core/config.py` - Add plugin configuration
- `.osiris/config.yaml` - Add plugin sections

**To Create** (for developer experience):
- `tools/component_scaffold/` - Cookiecutter template
- `docs/guides/component-development.md` - Developer guide
- `osiris/cli/component_cmd.py` - Scaffolder CLI command

## Questions & Discussion Points

1. **Signature Verification**: Required for security or optional?
   - **Recommendation**: Optional, implement in Phase 3 if needed

2. **Central Registry**: GitHub list or automatic PyPI discovery?
   - **Recommendation**: Start with GitHub, add PyPI search in Phase 4

3. **Version Compatibility**: Strict semantic versioning required?
   - **Recommendation**: Recommended but not enforced; warnings issued for conflicts

4. **E2B Integration**: Plugin bundling or just driver execution?
   - **Recommendation**: Just driver execution; bundle via transparent proxy

5. **Breaking Changes**: How to handle Osiris core updates?
   - **Recommendation**: Use version constraints in spec (`min_osiris_version`, `max_osiris_version`)

## Glossary

- **OCP**: Osiris Component Package - third-party component distribution
- **Entry Point**: Python mechanism for dynamic plugin discovery
- **Spec**: Component specification (spec.yaml) defining metadata & interface
- **Driver**: Implementation class that executes component logic
- **Registry**: In-memory mapping of component names to driver factories
- **Allowlist**: Configuration restricting plugins to approved list
- **E2B**: Encrypted, containerized sandbox for secure execution
- **MCP**: Model Context Protocol - Osiris server for LLM integration

## Resources

- **Documentation**: Included in this package (4 documents)
- **Examples**: Complete working components with tests
- **Templates**: Cookiecutter and pyproject.toml templates
- **Guides**: Implementation guide + specification document
- **Schema**: Component spec JSON schema (existing)

## Support & Feedback

For questions on:
- **Architecture/Design**: See THIRD_PARTY_COMPONENT_PACKAGING_STRATEGY.md
- **Implementation Details**: See THIRD_PARTY_COMPONENT_PACKAGING_SPEC.md
- **Getting Started**: See THIRD_PARTY_COMPONENT_IMPLEMENTATION_GUIDE.md
- **Working Examples**: See THIRD_PARTY_COMPONENT_EXAMPLES.md

---

**Document Version**: 1.0.0 (November 2025)
**Status**: Proposal (Ready for Review)
**Next Review**: After Phase 1 completion
