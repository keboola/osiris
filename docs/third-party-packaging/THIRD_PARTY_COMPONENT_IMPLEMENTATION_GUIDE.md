# Third-Party Component Implementation Guide

**Quick Reference for Creating Osiris Component Packages (OCPs)**

## 5-Minute Quick Start

### 1. Clone the Template

```bash
git clone https://github.com/keboola/shopify-osiris.git my-component
cd my-component
```

### 2. Edit Configuration

```bash
# Update these files with your component details:
# - pyproject.toml: name, version, dependencies, entry point
# - src/my_component/spec.yaml: component metadata
# - src/my_component/driver.py: implementation
```

### 3. Install & Test

```bash
pip install -e ".[dev]"
pytest tests/
```

### 4. Publish

```bash
python -m build
twine upload dist/*
```

---

## Detailed Implementation Steps

### Step 1: Create Package Structure

```bash
# Create project directory
mkdir my-component
cd my-component

# Create directory layout
mkdir -p src/my_component tests docs

# Initialize git
git init
echo "dist/" >> .gitignore
echo "build/" >> .gitignore
echo "*.egg-info/" >> .gitignore
echo ".pytest_cache/" >> .gitignore
echo ".venv/" >> .gitignore
```

### Step 2: Create pyproject.toml

```toml
[build-system]
requires = ["setuptools>=61.0", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "my-component-osiris"  # Change this! Lowercase, hyphens
version = "0.1.0"
description = "My custom component for Osiris ETL"
readme = "README.md"
license = {text = "Apache-2.0"}
authors = [{name = "Your Name", email = "you@example.com"}]
requires-python = ">=3.11"

dependencies = [
    "osiris-pipeline>=0.5.0,<1.0.0",
    # Add your component's dependencies here
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

# CRITICAL: Register your component via entry point
[project.entry-points."osiris.components"]
"my.extractor" = "my_component:load_spec"  # family.role format

[project.urls]
Repository = "https://github.com/your-org/my-component-osiris"

[tool.setuptools.packages.find]
where = ["src"]

[tool.setuptools.package-data]
my_component = ["spec.yaml"]

# Basic pytest config
[tool.pytest.ini_options]
testpaths = ["tests"]
```

### Step 3: Create spec.yaml

```bash
cat > src/my_component/spec.yaml << 'EOF'
# Component specification following JSON Schema
name: my.extractor
version: 0.1.0
title: My Custom Extractor
description: Extracts data from my data source

# Component family and role for LLM guidance
family: my
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

# Configuration schema (JSON Schema format)
configSchema:
  type: object
  properties:
    connection_url:
      type: string
      description: URL or endpoint of data source
    api_key:
      type: string
      description: API authentication key
    table:
      type: string
      description: Table or resource name to extract
  required: [connection_url, api_key, table]
  additionalProperties: false

# Mark sensitive fields
secrets:
  - /api_key

# Connection field overrides (see x-connection-fields spec)
x-connection-fields:
  - name: connection_url
    override: allowed
  - name: api_key
    override: forbidden

# Compatibility requirements
compatibility:
  requires:
    - python>=3.11
    - osiris>=0.5.0
    - osiris<1.0.0
  platforms:
    - linux
    - darwin
    - windows

# Runtime configuration - tells Osiris where the driver is
x-runtime:
  driver: my_component.driver:MyExtractorDriver
  requirements:
    imports:
      - my_component
    packages:
      - my-component-osiris
  min_osiris_version: 0.5.0
  max_osiris_version: 0.9.99

# LLM hints for pipeline generation
llmHints:
  promptGuidance: |
    Use my.extractor to extract data from my data source.
    Requires connection_url and api_key.
  commonPatterns:
    - pattern: basic_extraction
      description: Extract entire table without filters

limits:
  maxRows: 1000000
  maxSizeMB: 5120
  maxDurationSeconds: 3600
EOF
```

### Step 4: Create Package __init__.py

```python
# src/my_component/__init__.py
"""My component for Osiris."""

from pathlib import Path
import yaml

__version__ = "0.1.0"
__all__ = ["load_spec"]


def load_spec() -> dict:
    """Load component specification.

    This function is called by Osiris at runtime via the entry point.
    It must return a complete specification dictionary.

    Returns:
        Component specification dict

    Raises:
        FileNotFoundError: If spec.yaml not found
        yaml.YAMLError: If spec is malformed
    """
    spec_path = Path(__file__).parent / "spec.yaml"

    if not spec_path.exists():
        raise FileNotFoundError(f"Spec not found: {spec_path}")

    with open(spec_path) as f:
        spec = yaml.safe_load(f)

    if not spec:
        raise ValueError("Empty spec file")

    # Validate required fields
    required = ["name", "version", "modes", "configSchema"]
    missing = [k for k in required if k not in spec]
    if missing:
        raise ValueError(f"Missing required fields: {missing}")

    return spec
```

### Step 5: Create Driver Implementation

```python
# src/my_component/driver.py
"""Driver implementation for my component."""

import logging
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)


class MyExtractorDriver:
    """Extracts data from my data source."""

    def run(
        self,
        *,
        step_id: str,
        config: dict,
        inputs: dict | None = None,
        ctx: Any = None,
    ) -> dict:
        """Execute extraction.

        Args:
            step_id: Step identifier in pipeline
            config: Configuration dict with connection_url, api_key, table
            inputs: Not used for extractors
            ctx: Execution context (can emit metrics)

        Returns:
            {"df": DataFrame} with extracted data

        Raises:
            ValueError: If config is invalid
            Exception: If extraction fails
        """
        # Validate required config
        connection_url = config.get("connection_url")
        api_key = config.get("api_key")
        table = config.get("table")

        if not all([connection_url, api_key, table]):
            raise ValueError(f"Step {step_id}: missing required config fields")

        try:
            logger.info(f"Extracting {table} from {connection_url}")

            # TODO: Implement actual extraction logic
            # This is a placeholder that creates empty DataFrame
            df = pd.DataFrame()

            # Emit metrics if context available
            if ctx:
                ctx.emit_metric("rows_extracted", len(df))

            return {"df": df}

        except Exception as e:
            logger.error(f"Extraction failed: {e}")
            raise
```

### Step 6: Create Tests

```python
# tests/conftest.py
"""Shared test fixtures."""

import pytest


@pytest.fixture
def sample_config():
    """Sample configuration for testing."""
    return {
        "connection_url": "http://localhost:8000",
        "api_key": "test-key-12345",
        "table": "users"
    }
```

```python
# tests/test_driver.py
"""Driver unit tests."""

import pytest
from my_component.driver import MyExtractorDriver


@pytest.fixture
def driver():
    return MyExtractorDriver()


def test_driver_requires_config(driver, sample_config):
    """Driver should reject incomplete config."""
    incomplete_config = {"connection_url": "http://localhost"}

    with pytest.raises(ValueError, match="missing required config"):
        driver.run(step_id="test", config=incomplete_config)


def test_driver_extracts_data(driver, sample_config):
    """Driver should extract data (mock test)."""
    # This will fail until you implement the extraction logic
    result = driver.run(step_id="test", config=sample_config)

    assert "df" in result
    assert hasattr(result["df"], "shape")
```

```python
# tests/test_spec.py
"""Specification validation tests."""

from my_component import load_spec


def test_spec_loads():
    """Spec should load without errors."""
    spec = load_spec()
    assert spec is not None


def test_spec_has_required_fields():
    """Spec should have all required fields."""
    spec = load_spec()

    required = ["name", "version", "modes", "configSchema"]
    for field in required:
        assert field in spec, f"Missing {field}"


def test_spec_name_format():
    """Spec name should be family.role format."""
    spec = load_spec()
    name = spec["name"]

    parts = name.split(".")
    assert len(parts) == 2, f"Name should be 'family.role', got '{name}'"
```

### Step 7: Create Documentation

```markdown
# my-component-osiris

My component for Osiris ETL pipeline generator.

## Installation

```bash
pip install my-component-osiris
```

## Usage

### In Osiris Pipeline (OML)

```yaml
steps:
  - name: extract_data
    type: my.extractor
    config:
      connection_url: http://api.example.com
      api_key: ${MY_API_KEY}
      table: users
```

### Configuration

- `connection_url`: URL or endpoint of your data source
- `api_key`: Authentication key (will be masked in logs)
- `table`: Table or resource name to extract

## Requirements

- Python 3.11+
- osiris-pipeline >= 0.5.0

## Development

```bash
git clone https://github.com/your-org/my-component-osiris.git
cd my-component-osiris

# Install with dev dependencies
pip install -e ".[dev]"

# Run tests
pytest tests/

# Format code
black src/
ruff check --fix src/
```

## License

Apache-2.0
```

### Step 8: Setup Testing Environment

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install package in editable mode with dev deps
pip install -e ".[dev]"

# Run tests
pytest tests/ -v

# Test coverage
pytest tests/ --cov=src/my_component
```

### Step 9: Build and Test Locally

```bash
# Build package
pip install build
python -m build

# Test the built package
pip uninstall -y my-component-osiris
pip install dist/my_component_osiris-0.1.0-py3-none-any.whl

# Verify component is discoverable
python -c "from my_component import load_spec; print(load_spec()['name'])"
```

### Step 10: Publish to PyPI

```bash
# Install publishing tools
pip install twine

# Build distributions
python -m build

# Test upload first (TestPyPI)
twine upload --repository testpypi dist/*

# Verify test installation
pip install --index-url https://test.pypi.org/simple/ my-component-osiris==0.1.0
python -c "from my_component import load_spec; print(load_spec())"

# Production upload
twine upload dist/*

# Verify production installation
pip install my-component-osiris
```

## Common Issues & Solutions

### Issue: "ModuleNotFoundError: No module named 'my_component'"

**Solution**: Ensure package is installed in editable mode:
```bash
pip install -e .
```

### Issue: "spec.yaml not found"

**Solution**: Ensure `spec.yaml` is in `src/my_component/` and configured in `pyproject.toml`:
```toml
[tool.setuptools.package-data]
my_component = ["spec.yaml"]
```

### Issue: "Entry point not found"

**Solution**: Reinstall package after modifying `pyproject.toml`:
```bash
pip install -e . --force-reinstall
```

### Issue: "Spec validation fails"

**Solution**: Validate spec format:
```bash
# Check YAML syntax
python -c "import yaml; yaml.safe_load(open('src/my_component/spec.yaml'))"

# Validate against schema (requires osiris installed)
python -c "
from my_component import load_spec
from jsonschema import validate
from osiris.components.registry import ComponentRegistry

spec = load_spec()
registry = ComponentRegistry()
schema = registry._schema
validate(instance=spec, schema=schema)
print('Valid!')
"
```

## Testing with E2B

To verify your component works in E2B sandbox:

```python
# tests/test_e2b.py
import pytest
import sys
import importlib
from pathlib import Path


@pytest.mark.integration
def test_driver_in_sandbox(tmp_path):
    """Test driver in isolated sandbox (E2B simulation)."""
    import shutil

    # Create sandbox directory
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()

    # Copy driver to sandbox
    import my_component
    src_dir = Path(my_component.__file__).parent
    for file in src_dir.glob("*.py"):
        shutil.copy(file, sandbox / file.name)
    shutil.copy(src_dir / "spec.yaml", sandbox / "spec.yaml")

    # Test import from sandbox
    original_path = sys.path.copy()
    try:
        sys.path.insert(0, str(sandbox))

        # Clear any cached imports
        for mod in list(sys.modules.keys()):
            if mod.startswith("my_component"):
                del sys.modules[mod]

        # Import from sandbox
        spec_module = importlib.import_module("my_component")

        # Verify it works
        spec = spec_module.load_spec()
        assert spec["name"] == "my.extractor"

        # Instantiate driver
        driver_class = getattr(spec_module, "MyExtractorDriver")
        driver = driver_class()
        assert hasattr(driver, "run")

    finally:
        sys.path = original_path
```

## Release Checklist

Before publishing:

- [ ] All tests pass: `pytest tests/`
- [ ] Code formatted: `black src/` and `ruff check --fix src/`
- [ ] Spec validates: `python -c "from my_component import load_spec; load_spec()"`
- [ ] Version updated in `pyproject.toml` and `spec.yaml`
- [ ] CHANGELOG.md updated
- [ ] README.md complete with examples
- [ ] No hardcoded secrets or credentials
- [ ] License file present
- [ ] Git tag created: `git tag v0.1.0`

## Getting Help

- **Osiris Documentation**: https://github.com/keboola/osiris
- **Component Development Guide**: docs/developer-guide/ai/START-HERE.md
- **ADR-0024 (Component Packaging)**: docs/adr/0024-component-packaging.md
- **Component Spec Schema**: components/spec.schema.json

## Contributing

See CONTRIBUTING.md for guidelines on contributing back to this component.

## License

Apache-2.0
