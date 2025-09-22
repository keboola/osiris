# Osiris Developer Guide

## Overview

This guide is for developers extending, maintaining, or contributing to the Osiris Pipeline system. For user documentation, see the [User Guide](../user-guide/user-guide.md).

## Module Documentation

Osiris v0.2.0 is organized into distinct modules, each with specific responsibilities:

### Core Modules
- **[CLI Module](module-cli.md)** - Command-line interface using Rich framework
- **[Core Module](module-core.md)** - Business logic, LLM integration, and orchestration
- **[Components Module](module-components.md)** - Component registry and validation system

### Execution Modules
- **[Runtime Module](module-runtime.md)** - Local pipeline execution
- **[Remote Module (E2B)](module-remote.md)** - Cloud sandbox execution via E2B
- **[Drivers Module](module-drivers.md)** - Concrete data operation implementations

### Infrastructure Modules
- **[Connectors Module](module-connectors.md)** - Database connection management

## Using AI Assistants for Development

### The LLM Contract System

Osiris uses a **contract-based approach** for AI-assisted development. We provide machine-readable instructions that ensure AI assistants generate code that follows our architecture patterns.

### Contract Files

#### Main Contract
**[`llms.txt`](llms.txt)** - The primary contract file that **MUST be loaded first** for any development work. Contains:
- Repository structure and file organization
- Component contracts (OML, Driver, Adapter interfaces)
- Registration patterns and rules
- Critical coding instructions

#### Specialized Contracts
Load these IN ADDITION to the main contract for specific tasks:

- **[`llms-drivers.txt`](llms-drivers.txt)** - Driver development
  - Driver protocol implementation
  - Extractor/Writer/Transformer rules
  - Error handling patterns
  - SQL validation requirements

- **[`llms-cli.txt`](llms-cli.txt)** - CLI development
  - Rich console patterns
  - Command structure
  - Table formatting
  - Error messages and exit codes

- **[`llms-testing.txt`](llms-testing.txt)** - Test development
  - Test structure and fixtures
  - Mock patterns
  - Temporary directory usage
  - Secret handling with pragma comments

### How to Use

1. **Start a new development session**:
   ```bash
   # Load the contract into your AI assistant
   cat docs/developer-guide/llms.txt
   # Copy and paste into ChatGPT, Claude, or other AI assistant
   ```

2. **Tell the AI what you're building**:
   ```
   "Following the Osiris LLM contract I just shared, help me create a new
   PostgreSQL extractor driver that follows the same patterns as the MySQL extractor"
   ```

3. **The AI will generate code that**:
   - Follows the Driver protocol exactly
   - Uses proper registration patterns
   - Emits required metrics
   - Handles errors correctly
   - Matches existing code style

### Module-Specific Contracts (Future)

We're considering adding specialized LLM contracts for different modules:

```
developer-guide/
├── llms.txt                    # Main contract (current)
├── llms-drivers.txt            # Driver development contract (planned)
├── llms-adapters.txt           # Adapter development contract (planned)
├── llms-components.txt         # Component spec contract (planned)
└── llms-testing.txt            # Testing patterns contract (planned)
```

## Development Workflows

### Creating a New Driver

1. Load the LLM contract into your AI assistant
2. Review existing drivers in `osiris/drivers/` as examples
3. Follow the Driver protocol from `osiris/core/driver.py`
4. Register your driver in the appropriate module
5. Add tests following existing patterns

Example AI prompt:
```
"Create a new S3 writer driver that follows the Osiris driver protocol.
It should write DataFrames to S3 as Parquet files. Follow the same patterns
as filesystem_csv_writer_driver.py"
```

### Creating a New Adapter

1. Load the LLM contract
2. Implement the ExecutionAdapter ABC from `osiris/core/execution_adapter.py`
3. Follow the three-phase pattern: prepare() → execute() → collect()
4. Register in `osiris/core/adapter_factory.py`

Example AI prompt:
```
"Create a new Kubernetes adapter that runs pipeline steps as Jobs.
Follow the same interface as LocalAdapter and E2BTransparentProxy"
```

### Adding Component Specs

1. Create a `spec.yaml` following the format in `docs/reference/components-spec.md`
2. Include JSON Schema for configuration validation
3. Declare capabilities and modes
4. Add examples for LLM context generation

## Architecture Principles

When developing Osiris components, follow these principles:

1. **Contract-First**: Define clear interfaces before implementation
2. **LLM-Friendly**: Make code obvious with clear patterns
3. **Deterministic**: Same inputs must produce same outputs
4. **Observable**: Emit structured events and metrics
5. **Testable**: Pure functions where possible, clear side effects

## Key Interfaces

### Driver Protocol
```python
def run(self, step_id: str, config: dict, inputs: dict | None, ctx: Any) -> dict:
    """Execute a pipeline step"""
    # Validate configuration
    # Process inputs
    # Perform operation
    # Emit metrics via ctx
    # Return outputs
```

### Adapter Protocol
```python
class ExecutionAdapter(ABC):
    def prepare(self, manifest: dict, context: ExecutionContext) -> PreparedRun:
        """Prepare execution package"""

    def execute(self, prepared: PreparedRun, context: ExecutionContext) -> None:
        """Execute the pipeline"""

    def collect(self, prepared: PreparedRun, context: ExecutionContext) -> dict:
        """Collect results and artifacts"""
```

## Testing Guidelines

### Test Structure
```python
def test_component():
    # Arrange - Set up test data
    driver = ComponentDriver()
    config = {"required": "value"}
    ctx = MockContext()

    # Act - Execute operation
    result = driver.run("test_1", config, {}, ctx)

    # Assert - Verify behavior
    assert "df" in result
    assert ctx.metrics["rows_read"] > 0
```

### Test Coverage Requirements
- Unit tests for all drivers
- Integration tests for adapters
- End-to-end tests for critical paths
- Mock external dependencies
- Test error conditions

## Contributing

### Before Submitting Code

1. **Load the LLM contract** if using AI assistance
2. **Follow existing patterns** in the codebase
3. **Add tests** for new functionality
4. **Update documentation** as needed
5. **Run the test suite**: `make test`
6. **Format code**: `make format`
7. **Check types**: `make type-check`

### PR Guidelines

- Reference relevant ADRs
- Include test coverage
- Update CHANGELOG.md if applicable
- Ensure CI passes

## Common Development Tasks

### Running Tests
```bash
# Run all tests
make test

# Run specific test file
python -m pytest tests/test_driver.py

# Run with coverage
python -m pytest --cov=osiris tests/
```

### Local Development
```bash
# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install development dependencies
pip install -r requirements-dev.txt

# Run in development mode
cd testing_env
python ../osiris.py compile pipeline.yaml
python ../osiris.py run --last-compile --verbose
```

### Debugging
```bash
# Enable debug logging
export OSIRIS_LOG_LEVEL=DEBUG

# Run with verbose output
osiris run --last-compile --verbose

# Inspect session logs
osiris logs show --session run_XXX
```

## Resources

- [Architecture Documentation](../architecture.md)
- [ADRs](../adr/) - Architecture decision records
- [Component Specs](../reference/components-spec.md)
- [OML Format](../reference/pipeline-format.md)
- [Examples](../examples/) - Sample pipelines

## Getting Help

- Review existing code patterns in `osiris/`
- Check ADRs for design decisions
- Use the LLM contract for AI assistance
- Follow the test examples in `tests/`

---

**Remember**: Always load `llms.txt` into your AI assistant before starting development work. This ensures generated code follows Osiris patterns and contracts.
