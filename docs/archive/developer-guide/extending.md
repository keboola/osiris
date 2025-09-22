# Osiris Pipeline - Extension & Contribution Guide

## How to Contribute

TODO: Comprehensive contribution guide:

### Getting Started
TODO: Initial setup for contributors:
1. Fork the repository
2. Set up development environment
3. Read architecture documentation
4. Join community channels
5. Find good first issues

### Development Setup
```bash
# TODO: Complete setup instructions
# Clone your fork
git clone https://github.com/YOUR_USERNAME/osiris_pipeline.git
cd osiris_pipeline

# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install in development mode
pip install -e ".[dev]"

# Install pre-commit hooks
make pre-commit-install

# Run tests to verify setup
make test
```

### Contribution Process
TODO: Step-by-step contribution workflow:

1. **Find an Issue**
   - Check GitHub issues
   - Look for "good first issue" label
   - Discuss in issue comments

2. **Create Feature Branch**
   ```bash
   git checkout -b feature/your-feature-name
   ```

3. **Make Changes**
   - Follow coding standards
   - Add tests
   - Update documentation

4. **Test Locally**
   ```bash
   make test
   make lint
   make type-check
   ```

5. **Submit PR**
   - Clear description
   - Link related issues
   - Include test results

### Code Style
TODO: Coding standards:
- Python: Black formatting, type hints
- YAML: 2-space indentation
- Markdown: CommonMark specification
- Commit messages: Conventional Commits

### Testing Requirements
TODO: Test coverage expectations:
- Unit tests for new features
- Integration tests for pipelines
- >80% code coverage
- Performance benchmarks for critical paths

## Adding New Adapters

TODO: Complete guide for adapter development:

### Adapter Architecture
```python
# TODO: Adapter development template
from osiris.core.execution_adapter import ExecutionAdapter
from typing import Dict, Any

class MyCustomAdapter(ExecutionAdapter):
    """
    Custom adapter for [Platform/Service Name]

    This adapter enables Osiris to execute pipelines on [platform].
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize adapter with platform-specific configuration

        Args:
            config: Platform configuration including credentials
        """
        self.config = config
        self._validate_config()
        self._initialize_client()

    def _validate_config(self):
        """Validate required configuration parameters"""
        required = ["api_key", "endpoint"]
        for field in required:
            if field not in self.config:
                raise ValueError(f"Missing required config: {field}")

    def _initialize_client(self):
        """Initialize platform client/SDK"""
        # TODO: Platform-specific initialization
        pass

    def prepare(self, manifest: dict, context: ExecutionContext) -> PreparedRun:
        """
        Prepare execution environment on platform

        Steps:
        1. Validate manifest compatibility
        2. Create execution environment
        3. Upload dependencies
        4. Prepare configuration
        """
        # TODO: Implementation
        pass

    def execute(self, prepared: PreparedRun, context: ExecutionContext) -> None:
        """
        Execute pipeline on platform

        Steps:
        1. Submit job to platform
        2. Monitor execution progress
        3. Stream events back
        4. Handle errors
        """
        # TODO: Implementation
        pass

    def collect(self, prepared: PreparedRun, context: ExecutionContext) -> dict:
        """
        Collect results from platform

        Steps:
        1. Download artifacts
        2. Collect metrics
        3. Generate summary
        4. Cleanup resources
        """
        # TODO: Implementation
        pass
```

### Adapter Registration
```python
# In osiris/core/adapter_factory.py
from osiris.adapters.my_custom_adapter import MyCustomAdapter

class AdapterFactory:
    _adapters = {
        "local": LocalAdapter,
        "e2b": E2BTransparentProxy,
        "my_custom": MyCustomAdapter  # Add your adapter
    }

    @classmethod
    def register(cls, name: str, adapter_class: type):
        """Register new adapter"""
        cls._adapters[name] = adapter_class
```

### Adapter Configuration
```yaml
# In osiris.yaml
adapters:
  my_custom:
    api_key: ${MY_CUSTOM_API_KEY}
    endpoint: https://api.platform.com
    default_resources:
      cpu: 4
      memory_gb: 8
```

### Testing Your Adapter
```python
# tests/adapters/test_my_custom_adapter.py
import pytest
from osiris.adapters.my_custom_adapter import MyCustomAdapter

class TestMyCustomAdapter:
    def test_prepare_phase(self):
        # TODO: Test preparation
        pass

    def test_execute_phase(self):
        # TODO: Test execution
        pass

    def test_collect_phase(self):
        # TODO: Test collection
        pass

    def test_error_handling(self):
        # TODO: Test error scenarios
        pass

    def test_parity_with_local(self):
        # TODO: Verify same results as LocalAdapter
        pass
```

### Documentation Requirements
TODO: Required documentation for new adapters:
- README in adapter directory
- Configuration examples
- Performance characteristics
- Limitations and constraints
- Troubleshooting guide

## Adding New Components

TODO: Complete component development guide:

### Component Structure
```
components/
└── my_component/
    ├── extractor/
    │   ├── spec.yaml      # Component specification
    │   ├── driver.py       # Driver implementation
    │   ├── __init__.py
    │   └── README.md       # Component documentation
    └── writer/
        ├── spec.yaml
        ├── driver.py
        ├── __init__.py
        └── README.md
```

### Creating Component Spec
```yaml
# components/my_component/extractor/spec.yaml
name: "my_component.extractor"
version: "1.0.0"
description: "Extract data from MyService"
author: "Your Name"
license: "Apache-2.0"

# Configuration schema
config_schema:
  type: object
  required: ["endpoint", "query"]
  properties:
    endpoint:
      type: string
      format: uri
      description: "API endpoint"
    query:
      type: string
      description: "Query specification"
    options:
      type: object
      properties:
        timeout:
          type: integer
          default: 30
        retry:
          type: integer
          default: 3

# Component capabilities
capabilities:
  modes: ["read"]
  features: ["batch", "streaming"]
  doctor:
    enabled: true
    checks: ["connection", "authentication", "permissions"]

# Secrets specification
secrets:
  fields:
    - path: "/connection/api_key"
      description: "API key for authentication"
      env_var: "MY_COMPONENT_API_KEY"
      required: true

# Output specification
output_schema:
  type: object
  properties:
    df:
      type: "DataFrame"
      description: "Extracted data"
    metadata:
      type: object
      description: "Extraction metadata"

# Examples for LLM
examples:
  - description: "Extract all records"
    config:
      endpoint: "https://api.example.com/v1"
      query: "SELECT * FROM data"

  - description: "Extract with filtering"
    config:
      endpoint: "https://api.example.com/v1"
      query: "SELECT * FROM data WHERE status='active'"
      options:
        timeout: 60
```

### Implementing Driver
```python
# components/my_component/extractor/driver.py
from osiris.core.driver import Driver
from typing import Dict, Any, Optional
import pandas as pd

class MyComponentExtractorDriver(Driver):
    """Driver for MyComponent data extraction"""

    def __init__(self):
        self.client = None

    def run(self, step_id: str, config: dict, inputs: dict, ctx) -> dict:
        """
        Execute extraction

        Args:
            step_id: Unique step identifier
            config: Resolved configuration
            inputs: Input data (usually empty for extractors)
            ctx: Execution context for metrics/logging

        Returns:
            Dictionary with extracted DataFrame
        """
        try:
            # Initialize client
            self._initialize_client(config)

            # Execute query
            ctx.log_event("extraction.start", {"query": config["query"]})
            data = self._execute_query(config["query"])

            # Convert to DataFrame
            df = pd.DataFrame(data)

            # Log metrics
            ctx.log_metric("rows_read", len(df))
            ctx.log_event("extraction.complete", {"rows": len(df)})

            return {"df": df}

        except Exception as e:
            ctx.log_event("extraction.error", {"error": str(e)})
            raise

    def doctor(self, config: dict) -> dict:
        """
        Health check implementation

        Returns:
            Health check results
        """
        results = {
            "status": "healthy",
            "checks": {}
        }

        # Check connection
        try:
            self._initialize_client(config)
            self.client.ping()
            results["checks"]["connection"] = "passed"
        except Exception as e:
            results["status"] = "unhealthy"
            results["checks"]["connection"] = f"failed: {e}"

        return results

    def _initialize_client(self, config: dict):
        """Initialize service client"""
        # TODO: Client initialization
        pass

    def _execute_query(self, query: str) -> list:
        """Execute query and return results"""
        # TODO: Query execution
        pass
```

### Registering Driver
```python
# components/my_component/extractor/__init__.py
from osiris.core.driver import DriverRegistry
from .driver import MyComponentExtractorDriver

# Register driver on import
DriverRegistry.register("my_component.extractor", MyComponentExtractorDriver())
```

### Testing Component
```python
# tests/components/test_my_component.py
import pytest
from components.my_component.extractor.driver import MyComponentExtractorDriver

class TestMyComponentExtractor:
    def test_extraction(self):
        driver = MyComponentExtractorDriver()
        config = {
            "endpoint": "https://api.test.com",
            "query": "SELECT * FROM test"
        }
        result = driver.run("test_1", config, {}, MockContext())

        assert "df" in result
        assert len(result["df"]) > 0

    def test_doctor(self):
        driver = MyComponentExtractorDriver()
        config = {"endpoint": "https://api.test.com"}
        result = driver.doctor(config)

        assert result["status"] in ["healthy", "unhealthy"]
        assert "checks" in result
```

## OSS Workflow

TODO: Open source best practices:

### Branching Strategy
```
main                 # Stable releases
├── milestone-m2     # Current milestone work
├── feature/xyz      # Feature branches
└── hotfix/abc       # Critical fixes
```

### Release Process
TODO: Release workflow:
1. Complete milestone in feature branch
2. Update CHANGELOG.md
3. Bump version numbers
4. Create PR to main
5. Run full test suite
6. Merge and tag release
7. Create GitHub release
8. Update documentation

### Documentation Standards
TODO: Documentation requirements:
- All public APIs documented
- Examples for common use cases
- Architecture decision records (ADRs)
- Milestone documentation
- User guides and tutorials

### Community Guidelines
TODO: Community interaction:
- Code of Conduct
- Issue templates
- PR templates
- Discussion forums
- Community meetings

### Licensing
TODO: License information:
- Apache 2.0 license
- Contributor agreement
- Third-party licenses
- Patent grants

## Advanced Topics

### Plugin Architecture (Future)
TODO: Plugin system design:
```python
# Planned plugin interface
class OsirisPlugin:
    """Base class for Osiris plugins"""

    def register_components(self, registry):
        """Register plugin components"""
        pass

    def register_adapters(self, factory):
        """Register plugin adapters"""
        pass

    def register_commands(self, cli):
        """Register CLI commands"""
        pass
```

### Performance Optimization
TODO: Performance contribution guide:
- Profiling tools
- Benchmark suite
- Optimization strategies
- Memory management
- Caching layers

### Security Contributions
TODO: Security guidelines:
- Security review process
- Vulnerability reporting
- Security testing
- Compliance requirements
- Audit trails

## Resources

TODO: Helpful resources:

### Documentation
- [Architecture Overview](../overview.md)
- [Component Guide](components.md)
- [Adapter Guide](adapters.md)
- [API Reference](#) - TODO

### Tools
- Development setup scripts
- Testing utilities
- Debugging tools
- Performance profilers

### Community
- GitHub Discussions
- Discord server (future)
- Stack Overflow
- Blog posts

### Examples
- Example components
- Example adapters
- Example pipelines
- Tutorial notebooks
