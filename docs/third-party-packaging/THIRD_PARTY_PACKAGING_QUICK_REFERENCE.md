# Third-Party Component Packaging - Quick Reference Card

## TL;DR

Create a Python package with:
1. `spec.yaml` - Component metadata
2. `driver.py` - Implementation
3. `__init__.py` with `load_spec()` entry point
4. Register via `pyproject.toml`

Then publish to PyPI. Done.

---

## 5-Minute Setup

```bash
# 1. Create structure
mkdir my-component && cd my-component
mkdir -p src/my_component tests

# 2. Create pyproject.toml
cat > pyproject.toml << 'EOF'
[build-system]
requires = ["setuptools>=61.0", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "my-component-osiris"
version = "0.1.0"
description = "My component"
requires-python = ">=3.11"
dependencies = ["osiris-pipeline>=0.5.0,<1.0.0"]

[project.entry-points."osiris.components"]
"my.extractor" = "my_component:load_spec"

[tool.setuptools.package-data]
my_component = ["spec.yaml"]
EOF

# 3. Create spec.yaml
cat > src/my_component/spec.yaml << 'EOF'
name: my.extractor
version: 0.1.0
modes: [extract]
capabilities: {}
configSchema:
  type: object
  properties:
    url: {type: string}
  required: [url]

x-runtime:
  driver: my_component.driver:MyDriver
  requirements:
    packages: [pandas]
EOF

# 4. Create driver
cat > src/my_component/driver.py << 'EOF'
import pandas as pd

class MyDriver:
    def run(self, *, step_id, config, inputs=None, ctx=None):
        return {"df": pd.DataFrame()}
EOF

# 5. Create __init__.py
cat > src/my_component/__init__.py << 'EOF'
from pathlib import Path
import yaml

def load_spec():
    with open(Path(__file__).parent / "spec.yaml") as f:
        return yaml.safe_load(f)
EOF

# 6. Test
pip install -e . && python -c "from my_component import load_spec; print(load_spec())"

# 7. Publish
python -m build && twine upload dist/*
```

---

## File Checklist

### Required Files

```
my-component-osiris/
├── pyproject.toml              ✓ REQUIRED
├── src/my_component/
│   ├── __init__.py             ✓ REQUIRED (has load_spec)
│   ├── spec.yaml               ✓ REQUIRED
│   ├── driver.py               ✓ REQUIRED
│   └── [other files]           ○ Optional
├── tests/
│   ├── test_spec.py            ○ Recommended
│   └── test_driver.py          ○ Recommended
└── README.md                   ○ Recommended
```

---

## Entry Point Format

```toml
[project.entry-points."osiris.components"]
"{family}.{role}" = "{package}:load_spec"
```

**Examples**:
```toml
"shopify.extractor" = "shopify_osiris:load_spec"
"postgres.writer" = "postgres_osiris.main:get_spec"
"duckdb.processor" = "duckdb_osiris:component_spec"
```

**Requirements**:
- Entry point group: `osiris.components` (exact)
- Name format: `family.role` (lowercase, dot-separated)
- Function: Must return complete spec dict

---

## Driver Interface

```python
class MyDriver:
    def run(
        self,
        *,
        step_id: str,
        config: dict,
        inputs: dict | None = None,
        ctx = None,
    ) -> dict:
        # Validate config
        # Execute logic
        # Return {"df": DataFrame} or {}
```

**Rules**:
- Use keyword-only args (the `*,`)
- Don't mutate inputs
- Raise exceptions on error
- Use `logging` module
- Return dict (extractors: `{"df": df}`, writers: `{}`)

---

## Spec.yaml Essentials

```yaml
name: family.role            # REQUIRED
version: 0.1.0              # REQUIRED semver
title: Component Title      # REQUIRED
description: Description    # REQUIRED
modes: [extract]            # REQUIRED list
capabilities: {}            # REQUIRED empty dict OK
configSchema:               # REQUIRED JSON Schema
  type: object
  properties: {}
  required: []

x-runtime:                  # REQUIRED
  driver: package.module:ClassName
  requirements:
    packages: [...]
```

**Optional Sections**:
```yaml
family: shopify             # Recommended
role: extractor             # Recommended
secrets: [/password]        # Recommended
compatibility:
  requires:
    - python>=3.11
    - osiris>=0.5.0
x-connection-fields: [...]  # Recommended
llmHints:                   # Recommended
  promptGuidance: "..."
```

---

## Installation Variants

```toml
[project.optional-dependencies]
dev = [
    "pytest>=7.0.0",
    "black>=23.0.0",
    "ruff>=0.1.0",
]
e2b = [
    "e2b-code-interpreter>=2.0.0",
]
```

**Usage**:
```bash
pip install my-component-osiris          # Basic
pip install "my-component-osiris[dev]"   # With dev tools
pip install "my-component-osiris[e2b]"   # With E2B
pip install "my-component-osiris[dev,e2b]"  # Both
```

---

## Testing Template

```python
# tests/test_spec.py
from my_component import load_spec
from jsonschema import Draft202012Validator
from osiris.components.registry import ComponentRegistry

def test_spec_loads():
    spec = load_spec()
    assert "name" in spec

def test_spec_validates():
    spec = load_spec()
    registry = ComponentRegistry()
    errors = list(Draft202012Validator(registry._schema).iter_errors(spec))
    assert not errors

# tests/test_driver.py
from my_component.driver import MyDriver

def test_driver_has_run():
    driver = MyDriver()
    assert callable(driver.run)

def test_driver_returns_dict():
    driver = MyDriver()
    result = driver.run(step_id="test", config={})
    assert isinstance(result, dict)
```

**Run tests**:
```bash
pip install -e ".[dev]"
pytest tests/ -v --cov=src/
```

---

## Build & Publish

```bash
# Install build tools
pip install build twine

# Build
python -m build
# Creates: dist/my_component_osiris-0.1.0-py3-none-any.whl
#          dist/my_component_osiris-0.1.0.tar.gz

# Test upload (optional)
twine upload --repository testpypi dist/*

# Production upload
twine upload dist/*

# Verify
pip install my-component-osiris
python -c "from my_component import load_spec; print(load_spec()['name'])"
```

---

## Release Checklist

```
BEFORE PUBLISHING
☐ All tests pass: pytest tests/
☐ Code formatted: black src/ && ruff check --fix src/
☐ No secrets in code
☐ spec.yaml valid YAML
☐ Entry point callable
☐ Version in pyproject.toml matches spec.yaml
☐ README.md has examples
☐ LICENSE file present
☐ CHANGELOG.md updated

AFTER PUBLISHING
☐ Verify on PyPI: pip install {package}
☐ Test locally: python -c "import {package}"
☐ Create git tag: git tag v0.1.0 && git push --tags
☐ GitHub release notes
☐ Update component registry (if applicable)
```

---

## Common Errors & Fixes

| Error | Fix |
|-------|-----|
| `ModuleNotFoundError: No module named 'my_component'` | `pip install -e .` (editable install) |
| `FileNotFoundError: spec.yaml not found` | Add to `tool.setuptools.package-data` in pyproject.toml |
| `Entry point not registered` | Reinstall: `pip install -e . --force-reinstall` |
| `Spec validation fails` | Validate against JSON schema; check YAML syntax |
| `Driver not found` | Check `x-runtime.driver` path is correct and importable |
| `ImportError in tests` | Run from project root: `pytest` (not `cd tests && pytest`) |

---

## Role Reference

**Common Role Names** (use lowercase):
- `extractor` - Reads data from source
- `writer` - Writes data to destination
- `processor` - Transforms/processes data
- `connector` - Bridges two systems
- `transformer` - SQL/code transformations

**Modes** (for each component):
- `extract` - Read operation
- `write` - Write/update operation
- `transform` - Data transformation
- `discover` - Schema discovery
- `stream` - Streaming operation

---

## Config Schema Quick Examples

### Simple Config
```yaml
configSchema:
  type: object
  properties:
    url:
      type: string
      description: API endpoint
    api_key:
      type: string
      description: Authentication key
  required: [url, api_key]
```

### With Defaults
```yaml
configSchema:
  type: object
  properties:
    host:
      type: string
      default: localhost
    port:
      type: integer
      default: 5432
      minimum: 1
      maximum: 65535
```

### With Enums
```yaml
configSchema:
  type: object
  properties:
    mode:
      type: string
      enum: [read, write, append]
      default: read
```

### With Arrays
```yaml
configSchema:
  type: object
  properties:
    columns:
      type: array
      items:
        type: string
      default: []
```

---

## Minimal Example (30 lines total)

### pyproject.toml (12 lines)
```toml
[build-system]
requires = ["setuptools>=61.0", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "hello-osiris"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = ["osiris-pipeline>=0.5.0,<1.0.0", "pandas"]

[project.entry-points."osiris.components"]
"hello.extractor" = "hello_osiris:load_spec"

[tool.setuptools.package-data]
hello_osiris = ["spec.yaml"]
```

### spec.yaml (8 lines)
```yaml
name: hello.extractor
version: 0.1.0
modes: [extract]
capabilities: {}
configSchema: {type: object, properties: {}, required: []}
x-runtime:
  driver: hello_osiris.driver:HelloDriver
  requirements:
    packages: [pandas]
```

### driver.py (6 lines)
```python
import pandas as pd

class HelloDriver:
    def run(self, *, step_id, config, inputs=None, ctx=None):
        return {"df": pd.DataFrame({"hello": ["world"]})}
```

### __init__.py (4 lines)
```python
from pathlib import Path
import yaml

def load_spec():
    return yaml.safe_load((Path(__file__).parent / "spec.yaml").read_text())
```

---

## Package Naming Convention

**Format**: `{family}-osiris` (lowercase, hyphens)

**Examples**:
- `shopify-osiris` → `shopify.extractor`, `shopify.writer`
- `postgres-osiris` → `postgres.writer`, `postgres.extractor`
- `hubspot-osiris` → `hubspot.extractor`

**Import Path**: Underscores
- Package `shopify-osiris` → module `shopify_osiris`
- Entry point: `shopify_osiris:load_spec`

---

## CLI Commands

```bash
# List available components (includes plugins)
osiris components list

# Show component details
osiris components show shopify.extractor

# Validate spec (proposed future command)
osiris component validate src/my_component/spec.yaml

# Create new component (proposed future command)
osiris component create my-component --template api-extractor

# Run pipeline with components
osiris run pipeline.yaml

# Disable plugins
osiris run pipeline.yaml --disable-plugins

# Allow only specific plugin
osiris run pipeline.yaml --allow-plugin shopify-osiris
```

---

## Version Constraints

**In pyproject.toml** (package requirements):
```toml
dependencies = [
    "osiris-pipeline>=0.5.0,<1.0.0",  # Compatible with 0.5.x, 0.6.x, ... 0.9.x
    "requests>=2.30.0",                # Latest 2.x
    "pandas>=2.0.0,<3.0.0",           # 2.x only
]
```

**In spec.yaml** (component requirements):
```yaml
compatibility:
  requires:
    - python>=3.11
    - osiris>=0.5.0,<1.0.0

x-runtime:
  min_osiris_version: "0.5.0"
  max_osiris_version: "0.9.99"
```

---

## Dependency Best Practices

1. **Pin core dependency**: `osiris-pipeline>=0.5.0,<1.0.0`
2. **Use version ranges**: `pandas>=2.0.0` (allow improvements)
3. **Avoid conflicts**: Check `pip check` after installation
4. **Test compatibility**: Run against multiple Osiris versions
5. **Document requirements**: List in README.md

---

## Directory Structure Summary

```
component-project/
├── src/component_name/          ← All Python code here
│   ├── __init__.py              ← Entry point function
│   ├── spec.yaml                ← Metadata
│   ├── driver.py                ← Main implementation
│   ├── helpers.py               ← Helper functions (optional)
│   └── _compat.py               ← Compatibility layer (optional)
├── tests/                       ← All tests here
│   ├── conftest.py              ← Fixtures
│   ├── test_spec.py             ← Spec validation
│   ├── test_driver.py           ← Driver tests
│   └── test_integration.py      ← E2B/integration tests (optional)
├── docs/                        ← Optional docs
│   ├── README.md
│   └── USAGE.md
├── pyproject.toml              ← Package metadata
├── LICENSE                      ← Apache-2.0 recommended
└── CHANGELOG.md                ← Release notes
```

---

## Performance Considerations

- **Load spec once**: Osiris caches loaded specs
- **Lazy imports**: Import heavy libraries in driver, not module level
- **Streaming**: Don't load entire DataFrame in memory if possible
- **Connection pooling**: Reuse database connections
- **Batch operations**: Use batch inserts/updates when possible

---

## Security Quick Tips

1. ✅ Use `secrets` array in spec for sensitive fields
2. ✅ Never hardcode credentials in code
3. ✅ Use environment variables: `${MY_API_KEY}`
4. ✅ Mark fields as `override: forbidden` in spec
5. ✅ Don't log passwords/tokens
6. ✅ Validate all inputs in driver
7. ✅ Handle exceptions gracefully

---

## Resources

**Complete Guides** (in this package):
- THIRD_PARTY_COMPONENT_PACKAGING_STRATEGY.md (architecture)
- THIRD_PARTY_COMPONENT_PACKAGING_SPEC.md (technical spec)
- THIRD_PARTY_COMPONENT_IMPLEMENTATION_GUIDE.md (step-by-step)
- THIRD_PARTY_COMPONENT_EXAMPLES.md (working code)

**External Resources**:
- Python Packaging: https://packaging.python.org/
- Entry Points: https://packaging.python.org/specifications/entry-points/
- JSON Schema: https://json-schema.org/
- Osiris Docs: https://github.com/keboola/osiris

---

## Quick Links

| Need | Doc | Section |
|------|-----|---------|
| Start now | IMPLEMENTATION_GUIDE.md | Step 1-10 |
| Understand design | PACKAGING_STRATEGY.md | Overview |
| See spec details | PACKAGING_SPEC.md | Section 1-3 |
| Copy-paste examples | EXAMPLES.md | Example 1-4 |
| Fix errors | This card | Common Errors |

---

**Version**: 1.0.0
**Last Updated**: November 2025
**Status**: Ready to Use
