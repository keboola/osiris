# Osiris Pipeline - Component Development Guide

## Component Lifecycle

Components in Osiris follow a well-defined lifecycle from discovery to execution. For database components, the discovery phase is particularly important - see [discovery.md](./discovery.md) for details on schema discovery contracts.

### 1. Discovery Phase
How components support schema exploration:
- Filesystem scanning in `components/` directory
- Spec.yaml parsing and validation
- Registry population at startup
- Component availability in chat context

### 2. Compilation Phase
TODO: Component role in compilation:
- OML component reference resolution
- Configuration validation against schema
- Connection resolution and merging
- Manifest generation with driver mapping

### 3. Execution Phase
TODO: Runtime component behavior:
- Driver instantiation
- Configuration injection
- Input/output data flow
- Metric emission
- Error handling

### 4. Cleanup Phase
TODO: Post-execution cleanup:
- Resource deallocation
- Connection closing
- Artifact finalization
- Status reporting

## Capabilities

TODO: Component capability system:

### Capability Declaration
```yaml
# In spec.yaml
capabilities:
  modes:
    - read    # Can extract data
    - write   # Can write data
    - transform  # Can transform data

  features:
    - streaming  # Supports streaming IO (future)
    - batch     # Supports batch processing
    - incremental  # Supports incremental loads

  doctor:  # Health check capability
    enabled: true
    checks:
      - connection
      - permissions
      - schema
```

### Standard Capabilities
TODO: Document standard capabilities:

#### Data Operations
- `read`: Extract data from source
- `write`: Write data to destination
- `transform`: Modify data in-flight

#### Processing Modes
- `batch`: Process data in batches
- `streaming`: Stream processing (future)
- `incremental`: Delta processing

#### Health Checks
- `doctor`: Diagnostic capability
- `validate`: Configuration validation
- `test`: Self-test capability

### Custom Capabilities
TODO: How to define custom capabilities:
```yaml
# Example custom capability
capabilities:
  custom:
    encryption: true
    compression: ["gzip", "snappy"]
    partitioning: ["date", "hash"]
```

## Spec.json

TODO: Complete spec.yaml documentation:

### Schema Structure
```yaml
# Complete annotated spec.yaml
name: "mysql.extractor"
version: "1.0.0"
description: "Extracts data from MySQL databases"
author: "Osiris Team"
tags: ["database", "sql", "extraction"]

# Configuration schema (JSON Schema)
config_schema:
  type: object
  required: ["query"]
  properties:
    query:
      type: string
      description: "SQL query to execute"
    batch_size:
      type: integer
      default: 1000
      minimum: 1
      maximum: 100000

# Capabilities declaration
capabilities:
  modes: ["read"]
  features: ["batch"]
  doctor:
    enabled: true

# Secrets specification
secrets:
  fields:
    - path: "/connection/password"
      description: "Database password"
      required: true
      env_var: "MYSQL_PASSWORD"

# Output schema
output_schema:
  type: object
  properties:
    df:
      type: "DataFrame"
      description: "Extracted data as DataFrame"

# Examples for LLM
examples:
  - description: "Extract all customers"
    config:
      query: "SELECT * FROM customers"

  - description: "Extract with filtering"
    config:
      query: |
        SELECT * FROM orders
        WHERE created_at > '2024-01-01'
        LIMIT 1000

# TODO: Add more sections:
# - dependencies
# - performance hints
# - compatibility matrix
```

### Validation Rules
TODO: Spec validation requirements:
- Required fields: name, version, config_schema
- Semantic versioning for version
- Valid JSON Schema for config_schema
- Unique component names in registry

### Schema Evolution
TODO: Versioning and compatibility:
- Backward compatibility requirements
- Migration strategies
- Deprecation process
- Version selection

## Registry

TODO: Component registry system:

### Registry Architecture
```python
# TODO: Registry interface
class ComponentRegistry:
    def register(self, spec: ComponentSpec) -> None:
        """Register a component"""

    def get(self, name: str) -> ComponentSpec:
        """Get component by name"""

    def list(self) -> List[ComponentSpec]:
        """List all components"""

    def validate(self, name: str, config: dict) -> ValidationResult:
        """Validate component config"""
```

### Registration Process
TODO: How components are registered:
1. Scan component directories
2. Load and parse spec.yaml
3. Validate against meta-schema
4. Register in memory
5. Build LLM context

### Registry Operations
TODO: Common registry operations:
```python
# Get component
spec = registry.get("mysql.extractor")

# Validate configuration
result = registry.validate("mysql.extractor", {
    "query": "SELECT * FROM users"
})

# List available components
components = registry.list()

# Filter by capability
extractors = registry.filter(capability="read")
```

### Registry Persistence (Future)
TODO: Planned registry persistence:
- Cache compiled registry
- Hot reload support
- Remote registry support
- Plugin discovery

## Examples

TODO: Complete component examples:

### Simple Extractor
```yaml
# components/simple/extractor/spec.yaml
name: "simple.extractor"
version: "1.0.0"
description: "Simple data extractor example"

config_schema:
  type: object
  required: ["source"]
  properties:
    source:
      type: string
      description: "Data source path"

capabilities:
  modes: ["read"]
```

```python
# components/simple/extractor/driver.py
from osiris.core.driver import Driver, DriverRegistry

class SimpleExtractorDriver(Driver):
    def run(self, step_id: str, config: dict, inputs: dict, ctx) -> dict:
        # TODO: Implementation
        source = config["source"]
        # Read data from source
        df = read_data(source)
        # Log metrics
        ctx.log_metric("rows_read", len(df))
        return {"df": df}

# Register driver
DriverRegistry.register("simple.extractor", SimpleExtractorDriver())
```

### Complex Writer
```yaml
# components/complex/writer/spec.yaml
name: "complex.writer"
version: "2.0.0"
description: "Advanced data writer with partitioning"

config_schema:
  type: object
  required: ["destination", "format"]
  properties:
    destination:
      type: string
    format:
      enum: ["parquet", "csv", "json"]
    partition_by:
      type: array
      items:
        type: string
    compression:
      enum: ["none", "gzip", "snappy"]

capabilities:
  modes: ["write"]
  features: ["batch", "partitioning"]
  custom:
    formats: ["parquet", "csv", "json"]
    compression: ["gzip", "snappy"]

secrets:
  fields:
    - path: "/connection/access_key"
      env_var: "AWS_ACCESS_KEY"
    - path: "/connection/secret_key"
      env_var: "AWS_SECRET_KEY"
```

### Transformer Component
```yaml
# components/transform/aggregator/spec.yaml
name: "transform.aggregator"
version: "1.0.0"
description: "Data aggregation transformer"

config_schema:
  type: object
  required: ["group_by", "aggregations"]
  properties:
    group_by:
      type: array
      items:
        type: string
    aggregations:
      type: object
      additionalProperties:
        enum: ["sum", "avg", "count", "min", "max"]

capabilities:
  modes: ["transform"]
  features: ["batch"]

input_schema:
  type: object
  required: ["df"]
  properties:
    df:
      type: "DataFrame"

output_schema:
  type: object
  properties:
    df:
      type: "DataFrame"
      description: "Aggregated DataFrame"
```

## Testing Components

TODO: Component testing guide:

### Unit Testing
```python
# TODO: Unit test example
def test_mysql_extractor():
    driver = MySQLExtractorDriver()
    config = {"query": "SELECT 1"}
    result = driver.run("test", config, {}, MockContext())
    assert "df" in result
```

### Integration Testing
```python
# TODO: Integration test example
def test_mysql_to_csv_pipeline():
    # Create pipeline
    # Run pipeline
    # Verify output
    pass
```

### Health Check Testing
```python
# TODO: Health check test
def test_component_doctor():
    result = driver.doctor(config)
    assert result.status == "healthy"
```

## Best Practices

TODO: Component development best practices:

### Design Principles
- Single responsibility per component
- Clear input/output contracts
- Comprehensive error handling
- Meaningful metric emission
- Security-first design

### Performance Guidelines
- Efficient resource usage
- Batch processing optimization
- Connection pooling
- Memory management
- Progress reporting

### Documentation Standards
- Complete spec.yaml
- Inline code documentation
- Usage examples
- Performance characteristics
- Troubleshooting guide

### Security Considerations
- Never log secrets
- Validate all inputs
- Sanitize SQL queries
- Use secure connections
- Follow OWASP guidelines
