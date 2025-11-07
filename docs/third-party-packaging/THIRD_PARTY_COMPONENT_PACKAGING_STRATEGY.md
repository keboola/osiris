# Third-Party Component Packaging Strategy for Osiris

**Date**: November 2025
**Status**: Proposal (Based on ADR-0024 Analysis)
**Scope**: Packaging and distribution format for third-party Osiris components

## Executive Summary

This document proposes a practical packaging strategy for third-party Osiris Component Packages (OCPs), extending ADR-0024's vision with concrete implementation details. The strategy enables developers to build, test, and distribute components independently while maintaining seamless integration with the Osiris runtime.

## Current State Analysis

### Existing Component Architecture

**Monolithic Structure:**
- Component specs: `components/*/spec.yaml` (9 components)
- Driver implementations: `osiris/drivers/*.py` (6 drivers)
- Hard-coded driver registry in `DriverRegistry.populate_from_component_specs()`
- No support for external package discovery

**Registry Flow:**
```
ComponentRegistry.load_specs() → specs from components/ directory
    ↓
DriverRegistry.populate_from_component_specs() → creates driver factories
    ↓
Runner.get(component_name) → instantiates driver
```

**Key File Locations:**
- `/Users/padak/github/osiris/osiris/core/driver.py` - Registry implementation
- `/Users/padak/github/osiris/osiris/components/registry.py` - Component discovery
- `/Users/padak/github/osiris/components/spec.schema.json` - Specification schema
- `/Users/padak/github/osiris/pyproject.toml` - Build metadata
- `/Users/padak/github/osiris/tests/packaging/test_component_spec_packaging.py` - Packaging tests

### Current Constraints

1. **Specs and drivers split** across directories (drift risk)
2. **No plugin discovery mechanism** - all components must be in core
3. **Shared version coupling** - all components version with core
4. **High contribution friction** - requires core repo PR
5. **No allowlist/security control** for external components

## Proposed Third-Party Packaging Strategy

### 1. Package Structure (OCP - Osiris Component Package)

Each third-party component becomes a standalone Python package following this structure:

```
shopify-osiris/
├── pyproject.toml                 # Build metadata + entry points
├── src/
│   └── shopify_osiris/
│       ├── __init__.py            # Package initialization (exports load_spec)
│       ├── spec.yaml              # Component specification
│       ├── driver.py              # Driver implementation (or multiple files)
│       ├── connector.py           # Optional: Connector if different from core
│       ├── py.typed               # PEP 561 marker (optional, for type checking)
│       └── _compat.py             # Optional: Compatibility layer
├── tests/
│   ├── conftest.py                # Shared fixtures
│   ├── test_driver.py             # Driver unit tests
│   ├── test_spec.py               # Spec validation tests
│   └── test_integration.py        # E2B integration tests
├── docs/
│   ├── README.md                  # Component overview
│   ├── USAGE.md                   # Usage examples
│   └── DEVELOPMENT.md             # Contributing guide
├── LICENSE
├── README.md
└── CHANGELOG.md
```

### 2. Component Specification Format (spec.yaml)

Each OCP includes `spec.yaml` with required runtime metadata:

```yaml
# spec.yaml in package root or package/spec.yaml
name: shopify.extractor
version: 1.0.0
title: Shopify Data Extractor
description: Extract customers, orders, products from Shopify stores

family: shopify
role: extractor

modes:
  - extract
  - discover

capabilities:
  discover: true
  adHocAnalytics: false
  inMemoryMove: false
  streaming: false
  bulkOperations: true
  transactions: false
  partitioning: false
  customTransforms: false

configSchema:
  type: object
  properties:
    shop_url:
      type: string
      description: Shopify store URL (e.g., mystore.myshopify.com)
    api_key:
      type: string
      description: Shopify API key
    resource:
      type: string
      enum: [customers, orders, products, inventory]
      description: Resource to extract
  required: [shop_url, api_key, resource]

secrets:
  - /api_key

compatibility:
  requires:
    - python>=3.11
    - osiris>=0.5.0
    - osiris<1.0.0
  platforms:
    - linux
    - darwin
    - windows
    - docker

# Runtime configuration for plugin loader
x-runtime:
  driver: shopify_osiris.driver:ShopifyExtractorDriver
  requirements:
    imports:
      - shopify_python_api
    packages:
      - shopify-python-api>=14.0.0
  min_osiris_version: 0.5.0
  max_osiris_version: 0.9.99
  plugin_version: 1.0.0

# LLM hints for agent-driven generation
llmHints:
  inputAliases:
    shop_url:
      - shopify_url
      - store_url
    api_key:
      - api_token
      - shopify_key
  promptGuidance: |
    Extract data from Shopify stores using shopify.extractor.
    Requires shop_url (store domain) and api_key (API credentials).
    Resource field selects data type: customers, orders, products, or inventory.
  yamlSnippets:
    - "type: shopify.extractor"
    - "shop_url: mystore.myshopify.com"
    - "api_key: {{ shopify_api_key }}"
    - "resource: customers"
  commonPatterns:
    - pattern: customer_extraction
      description: Extract all customer records with profiles
    - pattern: order_analytics
      description: Extract orders with financial summaries

limits:
  maxRows: 1000000
  maxSizeMB: 5120
  maxDurationSeconds: 7200
  maxConcurrency: 3
  rateLimit:
    requests: 100
    period: minute
```

### 3. Python Entry Points (pyproject.toml)

Register the component via standard Python entry points:

```toml
# pyproject.toml
[build-system]
requires = ["setuptools>=61.0", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "shopify-osiris"
version = "1.0.0"
description = "Shopify component for Osiris ETL pipeline"
readme = "README.md"
license = {text = "Apache-2.0"}
authors = [{name = "Your Name", email = "your@email.com"}]
requires-python = ">=3.11"

dependencies = [
    "osiris-pipeline>=0.5.0,<1.0.0",
    "shopify-python-api>=14.0.0",
    "aiofiles>=23.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.0.0",
    "pytest-asyncio>=0.21.0",
    "pytest-cov>=4.0.0",
    "black>=23.0.0",
    "ruff>=0.1.0",
]
e2b = [
    "e2b-code-interpreter>=2.0.0",
]

# Entry point registration - enables auto-discovery
[project.entry-points."osiris.components"]
"shopify.extractor" = "shopify_osiris:load_spec"

[project.urls]
Repository = "https://github.com/yourorg/shopify-osiris"
Documentation = "https://github.com/yourorg/shopify-osiris/blob/main/README.md"

[tool.setuptools.packages.find]
where = ["src"]
include = ["shopify_osiris*"]

[tool.setuptools.package-data]
shopify_osiris = ["spec.yaml", "*.json", "*.yml"]
```

### 4. Package Initialization (__init__.py)

```python
# src/shopify_osiris/__init__.py
"""Shopify extractor component for Osiris."""

from pathlib import Path
import yaml

__version__ = "1.0.0"
__all__ = ["load_spec"]

def load_spec() -> dict:
    """Load component specification from spec.yaml.

    This function is called by Osiris at runtime via entry points.
    It must return a complete specification dictionary.

    Returns:
        Dictionary containing the component specification

    Raises:
        FileNotFoundError: If spec.yaml is not found
        yaml.YAMLError: If spec.yaml is malformed
    """
    spec_path = Path(__file__).parent / "spec.yaml"

    if not spec_path.exists():
        raise FileNotFoundError(f"Component spec not found at {spec_path}")

    with open(spec_path) as f:
        spec = yaml.safe_load(f)

    if not spec:
        raise ValueError(f"Empty or invalid YAML in {spec_path}")

    # Validate required fields
    required_fields = ["name", "version", "modes", "configSchema"]
    missing = [f for f in required_fields if f not in spec]
    if missing:
        raise ValueError(f"Missing required fields in spec: {', '.join(missing)}")

    return spec
```

### 5. Driver Implementation Pattern

```python
# src/shopify_osiris/driver.py
"""Shopify extractor driver implementation."""

import logging
from typing import Any

import pandas as pd
from shopify_python_api import Session, Customer, Order, Product

logger = logging.getLogger(__name__)


class ShopifyExtractorDriver:
    """Driver for extracting data from Shopify stores."""

    def run(
        self,
        *,
        step_id: str,
        config: dict,
        inputs: dict | None = None,
        ctx: Any = None,
    ) -> dict:
        """Extract data from Shopify.

        Args:
            step_id: Step identifier
            config: Configuration containing shop_url, api_key, resource
            inputs: Not used for extractors
            ctx: Execution context for logging metrics

        Returns:
            {"df": DataFrame} with extracted data

        Raises:
            ValueError: If required config fields are missing
            shopify_python_api.ShopifyError: If API call fails
        """
        shop_url = config.get("shop_url")
        api_key = config.get("api_key")
        resource = config.get("resource")

        if not all([shop_url, api_key, resource]):
            raise ValueError(f"Step {step_id}: missing required config")

        if resource not in ["customers", "orders", "products", "inventory"]:
            raise ValueError(f"Step {step_id}: invalid resource '{resource}'")

        try:
            session = Session(
                shop=shop_url,
                api_key=api_key,
                api_version="2024-01"
            )

            logger.info(f"Extracting {resource} from {shop_url}")

            if resource == "customers":
                data = self._extract_customers(session)
            elif resource == "orders":
                data = self._extract_orders(session)
            elif resource == "products":
                data = self._extract_products(session)
            else:  # inventory
                data = self._extract_inventory(session)

            df = pd.DataFrame(data)

            if ctx:
                ctx.emit_metric("rows_extracted", len(df))

            return {"df": df}

        except Exception as e:
            logger.error(f"Extraction failed: {e}")
            raise

    def _extract_customers(self, session: Session) -> list[dict]:
        """Extract customer records."""
        customers = Customer.read(session=session)
        return [c.to_dict() for c in customers]

    # Additional extraction methods...
```

### 6. Testing Strategy

```python
# tests/test_driver.py
"""Tests for Shopify extractor driver."""

import pytest
import pandas as pd
from pathlib import Path

from shopify_osiris.driver import ShopifyExtractorDriver


@pytest.fixture
def driver():
    """Create driver instance."""
    return ShopifyExtractorDriver()


def test_driver_requires_config(driver):
    """Test that driver rejects missing config."""
    with pytest.raises(ValueError, match="missing required config"):
        driver.run(
            step_id="test_step",
            config={},  # Missing required fields
        )


def test_driver_validates_resource(driver):
    """Test that driver validates resource field."""
    config = {
        "shop_url": "test.myshopify.com",
        "api_key": "test_key",
        "resource": "invalid_resource"
    }

    with pytest.raises(ValueError, match="invalid resource"):
        driver.run(step_id="test_step", config=config)


def test_spec_validity():
    """Verify spec.yaml is valid and complete."""
    from shopify_osiris import load_spec
    import jsonschema

    spec = load_spec()

    # Check required fields
    assert "name" in spec
    assert "version" in spec
    assert "modes" in spec
    assert "configSchema" in spec

    # Check component name format
    assert "." in spec["name"]
    parts = spec["name"].split(".")
    assert len(parts) == 2
    assert parts[1] in ["extractor", "writer", "processor"]


# tests/test_integration_e2b.py
@pytest.mark.integration
def test_driver_in_e2b_sandbox(tmp_path):
    """Test that driver can be imported and run in E2B-like environment."""
    import sys
    import importlib

    # Simulate E2B sandbox isolation
    sandbox_path = tmp_path / "sandbox"
    sandbox_path.mkdir()

    # Copy module to sandbox
    import shutil
    from shopify_osiris import driver

    driver_src = Path(driver.__file__)
    driver_dst = sandbox_path / driver_src.name
    shutil.copy(driver_src, driver_dst)

    # Add to path and test import
    original_path = sys.path.copy()
    try:
        sys.path.insert(0, str(sandbox_path))
        spec = importlib.util.spec_from_file_location(
            "shopify_driver", driver_dst
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        # Verify driver class exists
        assert hasattr(module, "ShopifyExtractorDriver")

    finally:
        sys.path = original_path
```

### 7. Distribution Formats

#### Option A: PyPI Distribution (Recommended for Public Components)

**Advantages:**
- Standard Python package distribution
- Automatic dependency resolution
- Version management and updates
- Easy discovery and installation

**Installation:**
```bash
pip install shopify-osiris
osiris components list  # shopify.extractor now visible
```

**Packaging:**
```bash
cd shopify-osiris/
pip install build
python -m build
# Produces: dist/shopify_osiris-1.0.0-py3-none-any.whl
#           dist/shopify_osiris-1.0.0.tar.gz
```

#### Option B: Tarball Distribution (for Private/Internal Components)

**Advantages:**
- No PyPI dependency
- Easy to host internally
- Self-contained with all dependencies listed
- Suitable for enterprise distribution

**Packaging:**
```bash
cd shopify-osiris/
tar -czf shopify-osiris-1.0.0.tar.gz \
  --exclude=.git \
  --exclude=__pycache__ \
  --exclude=.pytest_cache \
  --exclude=build \
  --exclude=dist \
  .

# Contents of tarball:
# shopify-osiris-1.0.0/
# ├── pyproject.toml
# ├── src/shopify_osiris/
# │   ├── spec.yaml
# │   └── driver.py
# ├── tests/
# └── INSTALL.md
```

**Installation from tarball:**
```bash
# Option 1: Direct path installation (development)
pip install ./shopify-osiris-1.0.0.tar.gz

# Option 2: Extract then install
tar -xzf shopify-osiris-1.0.0.tar.gz
cd shopify-osiris-1.0.0
pip install .

# Option 3: With optional dependencies
pip install "shopify-osiris[e2b,dev]"
```

#### Option C: Git-based Installation (for Contributors)

**Installation:**
```bash
pip install git+https://github.com/yourorg/shopify-osiris.git@v1.0.0

# For development:
git clone https://github.com/yourorg/shopify-osiris.git
cd shopify-osiris
pip install -e ".[dev,e2b]"
```

### 8. Runtime Discovery and Registration

#### Extended ComponentRegistry (Proposed Enhancement)

```python
# osiris/components/registry.py (enhancement)
class ComponentRegistry:
    """Enhanced registry supporting both built-in and third-party components."""

    def load_specs(self) -> dict[str, dict[str, Any]]:
        """Load component specs from all sources.

        Discovery order:
        1. Built-in components: components/*.yaml
        2. Entry-point plugins: osiris.components entry points
        3. Configuration-specified: via config allowlist
        """
        specs = {}

        # Load built-in components (existing logic)
        specs.update(self._load_builtin_specs())

        # Load third-party via entry points
        specs.update(self._load_plugin_specs())

        # Validate no conflicts
        self._check_conflicts(specs)

        return specs

    def _load_plugin_specs(self) -> dict[str, dict[str, Any]]:
        """Load third-party component specs via entry points."""
        import importlib.metadata

        specs = {}

        try:
            entry_points = importlib.metadata.entry_points()
            group = entry_points.select(group="osiris.components")
        except AttributeError:
            # Python 3.9 compatibility
            group = importlib.metadata.entry_points().get("osiris.components", [])

        for ep in group:
            try:
                load_spec = ep.load()
                spec = load_spec()
                component_name = spec.get("name")

                if not component_name:
                    logger.warning(f"Entry point {ep.name} returned spec without 'name'")
                    continue

                # Check against security policy
                if not self._is_plugin_allowed(component_name, ep.value):
                    logger.warning(f"Plugin {component_name} blocked by security policy")
                    continue

                specs[component_name] = spec
                logger.info(f"Loaded plugin component: {component_name}")

            except Exception as e:
                logger.error(f"Failed to load entry point {ep.name}: {e}")
                # Continue with other plugins

        return specs

    def _is_plugin_allowed(self, component_name: str, plugin_path: str) -> bool:
        """Check if plugin is allowed by security policy."""
        # Check config for allowlist/denylist
        from osiris.core.config import Config

        config = Config.load()
        plugins_cfg = config.data.get("plugins", {})

        if not plugins_cfg.get("enabled", True):
            return False  # All plugins disabled

        allowlist = plugins_cfg.get("allowlist", [])
        if allowlist and component_name not in allowlist:
            return False

        denylist = plugins_cfg.get("denylist", [])
        if denylist and component_name in denylist:
            return False

        return True

    def _check_conflicts(self, specs: dict[str, dict[str, Any]]) -> None:
        """Warn about namespace conflicts."""
        families = {}
        for name, spec in specs.items():
            family = spec.get("family", name.split(".")[0])
            role = spec.get("role", name.split(".")[-1])
            key = f"{family}.{role}"

            if key not in families:
                families[key] = []
            families[key].append(name)

        for key, names in families.items():
            if len(names) > 1:
                logger.warning(
                    f"Multiple components claim {key}: {', '.join(names)}. "
                    f"First registered ({names[0]}) will be used."
                )
```

### 9. Security Considerations

#### Configuration-Based Allow/Deny Lists

```yaml
# .osiris/config.yaml
plugins:
  enabled: true  # Set false to disable all plugins

  # Allowlist mode: only these plugins are permitted
  allowlist:
    - shopify-osiris==1.0.0
    - hubspot-osiris>=2.0.0,<3.0.0
    - custom-connector-osiris==0.1.0

  # Denylist mode: these plugins are blocked
  denylist:
    - untrusted-osiris
    - experimental-osiris-alpha

  # Sandbox configuration (E2B recommended)
  sandbox:
    provider: e2b        # e2b|none|docker
    policy: strict       # strict|permissive
    network: deny        # deny|egress-only|allow
    fs_access: readonly  # readonly|readwrite|none

# CLI flag override
# osiris run pipeline.yaml --disable-plugins
# osiris run pipeline.yaml --allow-plugin shopify-osiris
```

#### Verification Strategy

```python
# Proposed: Component signature verification
import hashlib
import json

def verify_component_signature(spec: dict, signature: str, public_key: str) -> bool:
    """Verify component spec was signed by trusted author.

    Optional security layer for production deployments.
    """
    spec_json = json.dumps(spec, sort_keys=True)
    spec_hash = hashlib.sha256(spec_json.encode()).digest()
    # Verify signature with public key...
    return True
```

### 10. Migration Path from Built-in to OCP

#### Convert Existing Component to OCP

**Step 1: Create package structure**
```bash
mkdir shopify-osiris
cd shopify-osiris
python -m venv venv
source venv/bin/activate

# Create directory structure
mkdir -p src/shopify_osiris tests docs
```

**Step 2: Extract files**
```bash
# Copy spec from osiris/components/shopify.extractor/spec.yaml
cp /path/to/osiris/components/shopify.extractor/spec.yaml src/shopify_osiris/

# Copy driver from osiris/drivers/shopify_driver.py
cp /path/to/osiris/drivers/shopify_driver.py src/shopify_osiris/driver.py
```

**Step 3: Create pyproject.toml**
```toml
[project.entry-points."osiris.components"]
"shopify.extractor" = "shopify_osiris:load_spec"
```

**Step 4: Create package init**
```python
# src/shopify_osiris/__init__.py
from pathlib import Path
import yaml

def load_spec():
    spec_path = Path(__file__).parent / "spec.yaml"
    return yaml.safe_load(spec_path.read_text())
```

**Step 5: Test and publish**
```bash
pip install -e ".[dev,e2b]"
pytest tests/
python -m build
twine upload dist/*
```

### 11. Integration Testing

#### Local E2B Compatibility Testing

```python
# tests/test_e2b_integration.py
"""Test component works in E2B sandbox environment."""

import pytest
import tempfile
import shutil
from pathlib import Path


@pytest.mark.integration
@pytest.mark.e2b
def test_component_in_e2b_sandbox(tmp_path):
    """Verify driver works when packaged for E2B execution."""

    # Create sandbox environment
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()

    # 1. Package the component (as E2B uploader would)
    component_dir = sandbox / "shopify_osiris"
    component_dir.mkdir()

    # Copy implementation
    import shopify_osiris
    source_dir = Path(shopify_osiris.__file__).parent
    for py_file in source_dir.glob("*.py"):
        shutil.copy(py_file, component_dir / py_file.name)

    # Copy spec
    spec_file = source_dir / "spec.yaml"
    if spec_file.exists():
        shutil.copy(spec_file, component_dir / "spec.yaml")

    # 2. Simulate E2B import
    import sys
    original_path = sys.path.copy()
    try:
        sys.path.insert(0, str(sandbox))

        # Clean imports
        for mod in list(sys.modules.keys()):
            if mod.startswith("shopify"):
                del sys.modules[mod]

        # Import from sandbox
        import importlib
        spec_module = importlib.import_module("shopify_osiris")

        # 3. Verify functionality
        spec = spec_module.load_spec()
        assert spec["name"] == "shopify.extractor"

        # 4. Instantiate and test driver
        driver_class = getattr(spec_module, "ShopifyExtractorDriver")
        driver = driver_class()

        # Test with mock config
        config = {
            "shop_url": "test.myshopify.com",
            "api_key": "pk_test_key",
            "resource": "customers"
        }

        # Should validate config even if API call fails
        with pytest.raises((ValueError, Exception)):
            # Will fail at API call, not config validation
            driver.run(step_id="test", config=config)

    finally:
        sys.path = original_path
        for mod in list(sys.modules.keys()):
            if mod.startswith("shopify"):
                del sys.modules[mod]


@pytest.mark.integration
def test_spec_json_schema_validation():
    """Verify spec.yaml matches JSON schema."""
    import jsonschema
    from jsonschema import Draft202012Validator

    from shopify_osiris import load_spec

    spec = load_spec()

    # Load schema from osiris package
    from osiris.components.registry import ComponentRegistry
    registry = ComponentRegistry()
    schema = registry._schema

    # Validate spec against schema
    validator = Draft202012Validator(schema)
    errors = list(validator.iter_errors(spec))

    assert not errors, f"Spec validation failed:\n{errors}"
```

## Implementation Roadmap

### Phase 1: Foundation (Core Enhancement)
- Implement `ComponentRegistry._load_plugin_specs()` via entry points
- Add plugin security configuration (allowlist/denylist)
- Update `DriverRegistry.populate_from_component_specs()` for plugin support
- Add tests for entry point discovery

**Timeline**: 2-3 weeks
**Files to Modify**: `osiris/components/registry.py`, `osiris/core/driver.py`

### Phase 2: Developer Experience
- Create `cookiecutter` template for new OCPs
- Document entry point contract
- Build component scaffolder CLI: `osiris component create`
- Create reference implementation (e.g., convert Supabase to OCP)

**Timeline**: 3-4 weeks
**New Files**: `tools/component_scaffold/`, `docs/guides/component-development.md`

### Phase 3: Security & Testing
- Implement allowlist/denylist configuration
- Add component signature verification (optional)
- Enhance E2B compatibility testing
- Create security best practices guide

**Timeline**: 2-3 weeks
**Files to Modify**: `osiris/core/config.py`, component registry

### Phase 4: Documentation & Community
- Write OCP publishing guide
- Create PyPI submission checklist
- Build component directory/registry
- Release example components

**Timeline**: Ongoing

## Recommended OCP Template

### Minimal Directory Structure
```
shopify-osiris/
├── pyproject.toml          # Minimal (60 lines)
├── src/shopify_osiris/
│   ├── __init__.py         # 20 lines
│   ├── spec.yaml           # 50-100 lines
│   └── driver.py           # 100-200 lines
├── tests/
│   ├── conftest.py         # 20 lines
│   ├── test_driver.py      # 50-100 lines
│   └── test_spec.py        # 30 lines
├── README.md               # 50-100 lines
└── LICENSE
```

**Estimated time to create**: 2-4 hours per component

### Scaffolder Output

```bash
$ osiris component create shopify-osiris
Creating component: shopify-osiris
  ✓ Generated directory structure
  ✓ Created pyproject.toml (entry point configured)
  ✓ Created spec.yaml template
  ✓ Created driver.py skeleton
  ✓ Generated test fixtures
  ✓ Added GitHub Actions CI/CD
  ✓ Created CONTRIBUTING.md

Next steps:
  1. cd shopify-osiris
  2. Edit src/shopify_osiris/spec.yaml
  3. Implement src/shopify_osiris/driver.py
  4. Write tests in tests/
  5. pip install -e ".[dev]"
  6. pytest
  7. python -m build
  8. twine upload dist/

See: https://osiris.ai/guides/component-development
```

## Distribution Checklist

### Before Publishing to PyPI

- [ ] Spec validates against `spec.schema.json`
- [ ] Driver implements `run()` method with correct signature
- [ ] Entry point `load_spec()` tested and working
- [ ] `pyproject.toml` has correct entry point configuration
- [ ] All tests pass: `pytest tests/`
- [ ] E2B compatibility tested: `pytest -m e2b`
- [ ] Documentation complete (README, USAGE, examples)
- [ ] License file included (Apache-2.0 recommended)
- [ ] Changelog updated
- [ ] Version bumped in `spec.yaml` and `pyproject.toml`
- [ ] Security review completed (check for hardcoded secrets)
- [ ] Coverage >80%: `pytest --cov=src`

### Publishing Commands

```bash
# Install build tools
pip install build twine

# Build package
python -m build

# Test upload to TestPyPI first
twine upload --repository testpypi dist/*

# Verify on TestPyPI
pip install --index-url https://test.pypi.org/simple/ shopify-osiris

# Production upload
twine upload dist/*

# Verify installation works
pip install shopify-osiris
python -c "from shopify_osiris import load_spec; print(load_spec()['name'])"
```

## Backwards Compatibility

### Built-in Components

- Existing components in `components/` remain unchanged
- `ComponentRegistry.load_specs()` loads both built-in and plugins
- `DriverRegistry` works with both sources transparently
- No breaking changes to existing pipelines

### Migration Strategy

1. Built-in components stay in core for 2+ releases
2. New external version published as OCP
3. Deprecation notice in core component spec
4. Eventually remove from core (major version)

Example:
```yaml
# components/shopify.extractor/spec.yaml (v0.6.0+)
deprecated: true
deprecationMessage: |
  This component has moved to the shopify-osiris package.
  Install with: pip install shopify-osiris
  See: https://github.com/keboola/shopify-osiris
```

## Comparison with Alternatives

| Approach | Pros | Cons |
|----------|------|------|
| **OCP (Python Entry Points)** | Standard Python, auto-discovery, clean separation, easy testing | Requires entry point awareness |
| **Git Submodules** | Separate repos | Complex workflow, poor Python integration |
| **URL Downloads** | No installation | Security risk, network dependency |
| **Config-Based Loading** | Flexible | Hard to version, package management issues |
| **Docker Plugins** | Isolation | Overhead, complexity, E2B incompatibility |

## Testing & Validation

### Automated Compatibility Testing

```bash
# Test against multiple Osiris versions
tox -e py311-osiris-0.5, py311-osiris-0.6, py312-osiris-0.6

# E2B sandbox testing
pytest -m e2b --e2b-api-key=$E2B_API_KEY

# Spec validation
osiris component validate src/shopify_osiris/spec.yaml
```

### Package Validation Command (Proposed)

```bash
$ osiris component validate shopify-osiris/
Validating shopify-osiris...
  ✓ spec.yaml matches schema
  ✓ driver.py has run() method
  ✓ Entry point registered correctly
  ✓ All imports resolvable
  ✓ Tests pass
  ✓ E2B compatible

Ready to publish! Next: twine upload dist/*
```

## References

- **ADR-0024**: Component Packaging as Osiris Plugins (OCP Model)
- **Component Spec Schema**: `/Users/padak/github/osiris/components/spec.schema.json`
- **Driver Registry**: `/Users/padak/github/osiris/osiris/core/driver.py`
- **Component Registry**: `/Users/padak/github/osiris/osiris/components/registry.py`
- **Python Entry Points**: https://packaging.python.org/en/latest/specifications/entry-points/
- **PEP 517**: Python build system specifications

## Next Steps

1. **Proof of Concept**: Convert MySQL extractor to OCP and test
2. **Entry Point Implementation**: Extend `ComponentRegistry` with plugin support
3. **Documentation**: Create component developer guide
4. **Scaffolder**: Build `osiris component create` command
5. **Community**: Enable external contributions via OCP model

## Questions & Discussion

- Should OCPs include E2B bundle logic or rely on core?
- Version compatibility: Semantic versioning enforced?
- Signature verification: Required for security or optional?
- Central registry: GitHub-based list or PyPI-based discovery?
