# Osiris Component Package (OCP) Technical Specification

**Version**: 1.0.0 (Proposed)
**Status**: Specification Draft
**Scope**: Format and distribution for third-party components

## 1. Package Format

### 1.1 Distribution Formats

#### 1.1.1 PyPI Distribution (Primary)

**Format**: Standard Python wheel and source distributions

```
my-component-osiris-1.0.0-py3-none-any.whl
my-component-osiris-1.0.0.tar.gz
```

**Contents**:
```
my_component_osiris-1.0.0.dist-info/
├── WHEEL
├── METADATA
├── entry_points.txt
├── top_level.txt
└── RECORD

my_component/
├── __init__.py
├── spec.yaml
├── driver.py
├── [additional modules].py
└── [data files]

[optional] tests/
[optional] docs/
```

**Installation**:
```bash
pip install my-component-osiris

# Verify entry point registration
python -c "import importlib.metadata; print(list(importlib.metadata.entry_points(group='osiris.components')))"
```

#### 1.1.2 Tarball Distribution (Alternative)

**Format**: Self-contained tar.gz archive

```
shopify-osiris-1.0.0.tar.gz
```

**Contents**:
```
shopify-osiris-1.0.0/
├── pyproject.toml
├── setup.py (optional, for older pip)
├── src/shopify_osiris/
│   ├── __init__.py
│   ├── spec.yaml
│   ├── driver.py
│   └── connector.py (optional)
├── tests/
├── README.md
├── LICENSE
└── MANIFEST.in
```

**Installation**:
```bash
# From tarball directly
pip install ./shopify-osiris-1.0.0.tar.gz

# Or extract then install
tar -xzf shopify-osiris-1.0.0.tar.gz
cd shopify-osiris-1.0.0
pip install .

# With optional dependencies
pip install ".[e2b,dev]"
```

### 1.2 Minimum Package Metadata

#### pyproject.toml Requirements

```toml
[project]
name = "{family}-osiris"              # REQUIRED: lowercase, hyphens
version = "0.1.0"                      # REQUIRED: semver
description = "..."                    # REQUIRED: 1-2 lines
readme = "README.md"                   # REQUIRED
license = {text = "Apache-2.0"}        # REQUIRED (or MIT, BSD-3-Clause)
authors = [...]                        # RECOMMENDED
requires-python = ">=3.11"             # REQUIRED
dependencies = [
    "osiris-pipeline>=0.5.0,<1.0.0",  # REQUIRED: version constraint
]

[project.entry-points."osiris.components"]
"{family}.{role}" = "{package}:load_spec"  # REQUIRED: entry point format

[tool.setuptools.package-data]
{package} = ["spec.yaml", "*.yaml"]    # REQUIRED: include spec
```

#### Entry Point Contract

**Entry Point Group**: `osiris.components`

**Entry Point Format**:
```
component-name = package_name:load_spec
```

**Example**:
```
shopify.extractor = shopify_osiris:load_spec
hubspot.writer = hubspot_osiris.main:load_component_spec
```

**Function Signature**:
```python
def load_spec() -> dict[str, Any]:
    """Load component specification.

    Returns:
        Complete specification dictionary matching spec.schema.json

    Raises:
        FileNotFoundError: If spec.yaml not found
        yaml.YAMLError: If spec.yaml malformed
        ValueError: If spec missing required fields
    """
```

### 1.3 Component Specification (spec.yaml)

#### Schema Reference

**File Location**: `{package_dir}/spec.yaml` or `{package_dir}/spec.json`

**Schema**: Must validate against `/osiris/components/spec.schema.json`

**Minimum Required Fields**:
```yaml
name: "{family}.{role}"              # REQUIRED: lowercase, dot-separated
version: "0.1.0"                      # REQUIRED: semver
title: "Component Title"              # REQUIRED
description: "Detailed description"   # REQUIRED
modes: [extract]                      # REQUIRED: at least one valid mode
capabilities: {}                      # REQUIRED: boolean capability flags
configSchema:                         # REQUIRED: JSON Schema
  type: object
  properties: {}
  required: []
```

**Extended Fields** (Recommended):
```yaml
family: "{family}"                    # RECOMMENDED: component family
role: "{role}"                        # RECOMMENDED: component role

secrets:                              # RECOMMENDED: secret field paths
  - /password
  - /auth_token

x-secret:                             # RECOMMENDED: additional secret paths
  - /resolved_connection/password

x-connection-fields:                  # RECOMMENDED: connection field metadata
  - name: host
    override: allowed|forbidden|warning

compatibility:                        # RECOMMENDED: version constraints
  requires:
    - python>=3.11
    - osiris>=0.5.0
  platforms:
    - linux
    - darwin

x-runtime:                            # REQUIRED: runtime configuration
  driver: "{package}.{module}:{ClassName}"
  min_osiris_version: "0.5.0"
  max_osiris_version: "0.9.99"
  requirements:
    imports: [...]
    packages: [...]

llmHints:                             # RECOMMENDED: for agent-driven generation
  promptGuidance: "..."
  commonPatterns: [...]
```

### 1.4 Driver Implementation

#### Interface Contract

**Location**: Path specified in `x-runtime.driver`

**Required Method Signature**:
```python
class DriverClassName:
    def run(
        self,
        *,
        step_id: str,
        config: dict,
        inputs: dict | None = None,
        ctx: Any = None,
    ) -> dict:
        """Execute the driver step.

        Args:
            step_id: Unique identifier for this pipeline step
            config: Configuration dictionary (validated against spec)
            inputs: Data from upstream steps, typically {"df": DataFrame}
            ctx: Execution context for logging/metrics (optional)

        Returns:
            Output dictionary:
            - Extractors: {"df": DataFrame}
            - Writers: {} (empty dict)
            - Transformers: {"df": DataFrame}

        Raises:
            ValueError: If config invalid
            RuntimeError: If execution fails
        """
        ...
```

**Key Requirements**:
1. **Immutability**: Must not mutate `inputs` or `config`
2. **Error Handling**: Raise descriptive exceptions with context
3. **Logging**: Use `logging` module, not print statements
4. **Metrics**: Emit progress via `ctx.emit_metric()` if available
5. **Determinism**: Same inputs must produce same outputs (unless streaming)

#### Example Implementation

```python
# src/my_component/driver.py
import logging
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)


class MyExtractorDriver:
    """Docstring required."""

    def run(
        self,
        *,
        step_id: str,
        config: dict,
        inputs: dict | None = None,
        ctx: Any = None,
    ) -> dict:
        """Implementation."""
        # Validate config
        required_fields = ["host", "database", "user"]
        missing = [f for f in required_fields if f not in config]
        if missing:
            raise ValueError(f"Step {step_id}: missing {missing}")

        try:
            # Log operation
            logger.info(f"Extracting from {config['host']}/{config['database']}")

            # Perform extraction
            # (implementation details omitted)
            df = pd.DataFrame()

            # Emit metrics
            if ctx:
                ctx.emit_metric("rows_extracted", len(df))
                ctx.emit_metric("duration_ms", 1234)

            return {"df": df}

        except Exception as e:
            logger.error(f"Extraction failed: {e}")
            raise RuntimeError(f"Step {step_id}: {e}") from e
```

## 2. Entry Point Discovery

### 2.1 Runtime Discovery Mechanism

**Discovery Order** (Proposed Enhancement):

```
1. Built-in components: components/*.yaml
   └─ Loaded via ComponentRegistry._load_builtin_specs()

2. Third-party plugins: osiris.components entry points
   └─ Loaded via ComponentRegistry._load_plugin_specs()

3. Configuration allowlist: .osiris/config.yaml
   └─ Filter/validation applied
```

**Discovery Code** (Proposed):

```python
import importlib.metadata

def discover_components() -> dict[str, dict]:
    """Discover all available components."""
    components = {}

    # Load built-in
    from osiris.components.registry import ComponentRegistry
    registry = ComponentRegistry()
    components.update(registry.load_specs())

    # Load plugins via entry points
    entry_points = importlib.metadata.entry_points()
    group = entry_points.select(group="osiris.components")

    for ep in group:
        try:
            load_spec = ep.load()
            spec = load_spec()
            name = spec.get("name")

            # Check security policy
            if not is_allowed(name, ep.value):
                logger.warning(f"Plugin {name} blocked by policy")
                continue

            components[name] = spec
            logger.info(f"Loaded plugin: {name}")

        except Exception as e:
            logger.error(f"Failed to load {ep.name}: {e}")

    return components
```

### 2.2 Namespace Conflict Resolution

**Policy**: First registered component wins, warning issued

```python
def check_conflicts(specs: dict[str, dict]) -> list[str]:
    """Check for namespace conflicts."""
    families = {}
    conflicts = []

    for name, spec in specs.items():
        family = spec.get("family", name.split(".")[0])
        key = family  # namespace is family prefix

        if key not in families:
            families[key] = []
        families[key].append(name)

    for family, names in families.items():
        if len(names) > 1:
            msg = f"Namespace conflict in '{family}': {', '.join(names)}"
            logger.warning(msg)
            conflicts.append(msg)

    return conflicts
```

## 3. Security Model

### 3.1 Plugin Security Configuration

**Configuration File**: `.osiris/config.yaml`

```yaml
plugins:
  enabled: true  # Master toggle for all plugins

  # Allowlist mode: only permit listed packages
  allowlist:
    - shopify-osiris==1.0.0
    - hubspot-osiris>=2.0.0,<3.0.0

  # Denylist mode: block listed packages
  denylist:
    - untrusted-osiris
    - experimental-component-alpha

  # Sandbox configuration (for E2B provider)
  sandbox:
    provider: e2b              # e2b|docker|none
    policy: strict             # strict|permissive
    network: deny              # deny|egress-only|allow
    fs_access: readonly        # readonly|readwrite|none

  # Signature verification (optional)
  signature_verification: false
  trusted_signers:
    - "keboola"
    - "youraccount"
```

### 3.2 CLI Overrides

```bash
# Disable all plugins
osiris run pipeline.yaml --disable-plugins

# Allow specific plugin
osiris run pipeline.yaml --allow-plugin shopify-osiris

# Use strict sandbox
osiris run pipeline.yaml --sandbox strict

# Block specific plugin
osiris run pipeline.yaml --block-plugin experimental-osiris
```

### 3.3 Verification Strategy

#### Integrity Verification

```python
def verify_plugin_integrity(spec: dict) -> bool:
    """Verify plugin spec is well-formed."""
    required = ["name", "version", "x-runtime"]
    return all(k in spec for k in required)
```

#### Version Compatibility

```python
def check_compatibility(spec: dict) -> tuple[bool, str]:
    """Check if plugin compatible with current Osiris version."""
    from osiris import __version__
    from packaging import version

    min_version = spec.get("x-runtime", {}).get("min_osiris_version")
    max_version = spec.get("x-runtime", {}).get("max_osiris_version")

    current = version.parse(__version__)

    if min_version and current < version.parse(min_version):
        return False, f"Requires osiris>={min_version}"

    if max_version and current > version.parse(max_version):
        return False, f"Requires osiris<{max_version}"

    return True, "Compatible"
```

#### Optional: Cryptographic Signature Verification

```python
def verify_signature(
    spec: dict,
    signature: str,
    public_key: str
) -> bool:
    """Verify component spec signature.

    Optional security layer for air-gapped or regulated environments.

    Args:
        spec: Component specification dict
        signature: Base64-encoded RSA-2048 signature
        public_key: PEM-encoded public key

    Returns:
        True if signature valid, False otherwise
    """
    import hashlib
    import base64
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding

    # Hash the spec
    spec_json = json.dumps(spec, sort_keys=True)
    spec_hash = hashlib.sha256(spec_json.encode()).digest()

    # Verify signature
    key = serialization.load_pem_public_key(public_key.encode())
    signature_bytes = base64.b64decode(signature)

    try:
        key.verify(
            signature_bytes,
            spec_hash,
            padding.PKCS1v15(),
            hashes.SHA256()
        )
        return True
    except:
        return False
```

## 4. Dependency Management

### 4.1 Specification Requirements

**In spec.yaml**:
```yaml
compatibility:
  requires:
    - python>=3.11
    - osiris>=0.5.0,<1.0.0
    - mysqlclient>=2.0       # External dependencies

x-runtime:
  requirements:
    imports:
      - pandas
      - sqlalchemy
    packages:
      - pandas>=2.0
      - sqlalchemy>=2.0
```

### 4.2 Installation Variants

**Base Installation** (production):
```bash
pip install my-component-osiris
```

**With E2B Support**:
```bash
pip install "my-component-osiris[e2b]"
```

**With Development Tools**:
```bash
pip install "my-component-osiris[dev]"
```

**Full Installation**:
```bash
pip install "my-component-osiris[dev,e2b,docs]"
```

### 4.3 Dependency Resolution

**Rules**:
1. Osiris core dependencies must be compatible (no conflicts)
2. Component may version independently
3. Python 3.11+ required

**Conflict Detection**:
```python
def check_dependency_conflicts(
    installed_packages: dict[str, str],
    component_requires: list[str]
) -> list[str]:
    """Detect dependency version conflicts."""
    from packaging import specifiers, version

    conflicts = []
    for req in component_requires:
        # Parse requirement: "package>=1.0,<2.0"
        name, spec = parse_requirement(req)

        if name in installed_packages:
            installed = installed_packages[name]
            if not specifiers.SpecifierSet(spec).contains(installed):
                conflicts.append(
                    f"{name}: installed {installed} conflicts with {spec}"
                )

    return conflicts
```

## 5. Testing & Validation

### 5.1 Component Validation Rules

```python
# Validation rules that must pass before acceptance
VALIDATION_RULES = {
    "spec_format": "spec.yaml valid YAML and matches schema",
    "driver_location": "driver exists at x-runtime.driver path",
    "driver_interface": "driver has run() method with correct signature",
    "entry_point": "entry point callable and returns spec",
    "no_hardcoded_secrets": "no credentials in code (detected by scanning)",
    "tests_pass": "all tests pass (pytest)",
    "imports_resolve": "all imports work in fresh environment",
    "e2b_compatible": "driver can be imported in E2B sandbox",
    "spec_examples": "spec examples have proper structure",
    "capability_consistency": "capabilities match actual implementation",
}
```

### 5.2 Test Template

**Required Test File**: `tests/test_spec.py`

```python
"""Component specification validation."""

import pytest
from jsonschema import Draft202012Validator


def test_spec_loads():
    """Spec should load without errors."""
    from my_component import load_spec
    spec = load_spec()
    assert spec is not None


def test_spec_schema_validation():
    """Spec must validate against component schema."""
    from my_component import load_spec
    from osiris.components.registry import ComponentRegistry

    spec = load_spec()
    registry = ComponentRegistry()

    validator = Draft202012Validator(registry._schema)
    errors = list(validator.iter_errors(spec))

    assert not errors, f"Spec validation failed: {errors}"


def test_spec_required_fields():
    """Spec must have all required fields."""
    from my_component import load_spec

    spec = load_spec()
    required = ["name", "version", "modes", "configSchema", "x-runtime"]

    for field in required:
        assert field in spec, f"Missing required field: {field}"


def test_spec_name_format():
    """Component name must be family.role format."""
    from my_component import load_spec

    spec = load_spec()
    name = spec["name"]
    parts = name.split(".")

    assert len(parts) == 2, f"Name should be 'family.role', got {name}"
    assert parts[1] in ["extractor", "writer", "processor", "transform"]
```

**Required Test File**: `tests/test_driver.py`

```python
"""Driver implementation tests."""

import pytest


def test_driver_interface():
    """Driver must have run() method."""
    from my_component.driver import MyExtractorDriver

    driver = MyExtractorDriver()
    assert callable(driver.run)


def test_driver_signature():
    """Driver run() must have correct signature."""
    import inspect
    from my_component.driver import MyExtractorDriver

    driver = MyExtractorDriver()
    sig = inspect.signature(driver.run)

    # Check required parameters
    params = list(sig.parameters.keys())
    assert "step_id" in params
    assert "config" in params
```

### 5.3 CI/CD Pipeline

**Recommended GitHub Actions Workflow**:

```yaml
name: Component Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.11", "3.12"]
        osiris-version: ["0.5.0", "0.6.0"]

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v4
        with:
          python-version: ${{ matrix.python-version }}

      - name: Install dependencies
        run: |
          pip install -e ".[dev]"
          pip install osiris-pipeline==${{ matrix.osiris-version }}

      - name: Lint
        run: |
          black --check src/
          ruff check src/

      - name: Type check
        run: mypy src/

      - name: Tests
        run: pytest tests/ -v

      - name: Coverage
        run: pytest tests/ --cov=src/ --cov-report=xml

      - name: Spec validation
        run: |
          python -c "
          from my_component import load_spec
          from osiris.components.registry import ComponentRegistry
          from jsonschema import validate
          spec = load_spec()
          registry = ComponentRegistry()
          validate(instance=spec, schema=registry._schema)
          print('✓ Spec valid')
          "
```

## 6. Distribution Checklist

Before publishing component:

```
SPECIFICATION
 ☐ spec.yaml matches spec.schema.json
 ☐ x-runtime.driver path is correct
 ☐ All configSchema properties defined
 ☐ secrets array populated for sensitive fields

IMPLEMENTATION
 ☐ Driver class exists at specified path
 ☐ run() method signature correct
 ☐ No hardcoded credentials or secrets
 ☐ Proper error handling with descriptive messages
 ☐ Logging using logging module

PACKAGING
 ☐ pyproject.toml has correct entry point
 ☐ Entry point callable: package:load_spec
 ☐ spec.yaml included in package-data
 ☐ Version consistent across files

TESTING
 ☐ All tests pass: pytest tests/
 ☐ Coverage >80%: pytest --cov
 ☐ Spec validation passes
 ☐ No import errors
 ☐ E2B compatibility tested

DOCUMENTATION
 ☐ README.md with usage examples
 ☐ Configuration examples in USAGE.md
 ☐ CHANGELOG.md up to date
 ☐ Code comments on complex logic

SECURITY
 ☐ No hardcoded passwords/tokens
 ☐ Secrets properly marked in spec
 ☐ No eval() or exec() usage
 ☐ Dependencies pinned to safe versions
 ☐ Security scan passed (bandit, detect-secrets)

DISTRIBUTION
 ☐ Build successful: python -m build
 ☐ Local installation works: pip install dist/*
 ☐ Entry point registered: pip show -f package
 ☐ Component discoverable by Osiris
 ☐ Ready for PyPI upload

FINAL CHECKS
 ☐ Git tag created: git tag v0.1.0
 ☐ Release notes written
 ☐ Component listed in registry (if applicable)
```

## 7. Compatibility Matrix

### Osiris Version Support

| Component Version | Min Osiris | Max Osiris | Python | Status |
|-------------------|-----------|-----------|--------|--------|
| 1.0.0 | 0.5.0 | 0.9.99 | 3.11+ | Stable |
| 0.9.0 | 0.4.0 | 0.9.99 | 3.11+ | Legacy |

### Platform Support

```yaml
compatibility:
  platforms:
    - linux       # Ubuntu, Debian, CentOS
    - darwin      # macOS 11+
    - windows     # Windows 10+
    - docker      # Docker container
```

### Python Version Support

```
Minimum: 3.11 (Osiris requirement)
Tested: 3.11, 3.12, 3.13
Recommended: 3.12 or later
```

## 8. References

- **Osiris Documentation**: https://github.com/keboola/osiris
- **Component Spec Schema**: `/osiris/components/spec.schema.json`
- **Python Entry Points**: https://packaging.python.org/specifications/entry-points/
- **Python Packaging Guide**: https://packaging.python.org/
- **PEP 517**: Build backend specification
- **PEP 660**: Editable installs

## Appendix A: Migration from Built-in to OCP

### Converting Existing Component

1. Create package structure (see Section 1.2)
2. Extract spec.yaml from `components/{name}/`
3. Extract driver from `osiris/drivers/`
4. Update driver import paths as needed
5. Create package initialization with `load_spec()`
6. Add comprehensive tests
7. Publish to PyPI

### Deprecation Timeline

**Version N**: Announce deprecation in built-in spec
```yaml
deprecated: true
deprecationMessage: |
  This component is now available as a standalone package.
  Install: pip install my-component-osiris
  See: https://github.com/org/my-component-osiris
```

**Version N+1**: Remove from built-in (minor version bump)

**Migration Support**: Provide upgrade guide and compatibility layer

## Appendix B: Example Package Manifest

### Directory Listing

```
shopify-osiris/
├── pyproject.toml                    (90 lines)
├── src/shopify_osiris/
│   ├── __init__.py                   (30 lines)
│   ├── spec.yaml                     (80 lines)
│   ├── driver.py                     (150 lines)
│   └── py.typed                      (0 bytes, PEP 561)
├── tests/
│   ├── conftest.py                   (20 lines)
│   ├── test_spec.py                  (40 lines)
│   ├── test_driver.py                (60 lines)
│   └── test_e2b_integration.py       (50 lines)
├── docs/
│   ├── README.md                     (100 lines)
│   ├── USAGE.md                      (50 lines)
│   └── DEVELOPMENT.md                (50 lines)
├── .github/workflows/
│   └── tests.yaml                    (50 lines)
├── LICENSE                           (20 lines, Apache-2.0)
├── CHANGELOG.md                      (30 lines)
└── .gitignore
```

**Total Size**: ~100KB (source only), ~5MB (with tests/docs)

**Build Output**:
- `.whl`: ~50KB
- `.tar.gz`: ~30KB
