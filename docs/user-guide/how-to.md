# Osiris Pipeline - How-To Guide

## Building a Pipeline

TODO: Comprehensive pipeline building guide:

### Understanding Pipeline Components
TODO: Explain each component type:
- Extractors (data sources)
- Transformers (data processing)
- Writers (data destinations)
- Connections (credentials & config)

### Using Conversational Mode
TODO: Best practices for chat:
```bash
osiris chat

# TODO: Document conversation strategies:
# - Be specific about data needs
# - Provide table names when known
# - Specify transformation logic clearly
# - Review AI suggestions carefully
```

### Manual OML Creation
TODO: Guide for writing OML directly:
```yaml
# TODO: Complete OML template with annotations
oml_version: "0.1.0"
name: "example_pipeline"
steps:
  - id: "extract_1"
    component: "mysql.extractor"
    mode: "read"
    config:
      # TODO: Explain each config option
      connection: "@mysql.primary"
      query: "SELECT * FROM customers"
```

### Pipeline Patterns
TODO: Document common patterns:
- Single source to destination
- Multiple sources with joins
- Fan-out (one source, multiple destinations)
- Incremental loads
- CDC (Change Data Capture) - future

## Validating OML

TODO: Validation procedures:

### Syntax Validation
```bash
osiris oml validate pipeline.oml

# TODO: Explain validation checks:
# - Schema compliance
# - Required fields
# - Forbidden keys
# - Connection references
```

### Connection Validation
```bash
osiris connections doctor

# TODO: Show output format
# TODO: Explain health checks
```

### Dry Run Validation
```bash
osiris run pipeline.oml --dry-run

# TODO: Explain what dry run checks:
# - Connection resolution
# - Driver availability
# - Configuration validity
```

## Compiling

TODO: Compilation deep dive:

### Basic Compilation
```bash
osiris compile pipeline.oml

# TODO: Explain output:
# - Manifest location
# - Fingerprint generation
# - Resolved configurations
```

### Compilation Options
```bash
# Output to specific directory
osiris compile pipeline.oml --output ./compiled/

# Include debug information
osiris compile pipeline.oml --debug

# TODO: Document all flags
```

### Understanding Manifests
TODO: Explain manifest structure:
```yaml
# TODO: Annotated manifest example
version: "1.0"
fingerprint: "sha256:..."
steps:
  - id: "extract_1"
    driver: "mysql.extractor"
    config:
      # Resolved configuration
```

## Running

TODO: Execution guide:

### Local Execution
```bash
# Run OML directly
osiris run pipeline.oml

# Run compiled manifest
osiris run compiled/manifest.yaml

# TODO: Explain execution phases:
# 1. Prepare
# 2. Execute
# 3. Collect artifacts
```

### E2B Cloud Execution
```bash
# Basic E2B run
osiris run pipeline.oml --e2b

# With resource specifications
osiris run pipeline.oml --e2b --cpu 4 --memory-gb 8

# With timeout
osiris run pipeline.oml --e2b --timeout 3600

# TODO: Document E2B advantages:
# - Isolation
# - Scalability
# - No local dependencies
```

### Passing Secrets
TODO: Secret management:
```bash
# Via environment
export MYSQL_PASSWORD="secret"
osiris run pipeline.oml

# Via .env file
echo "MYSQL_PASSWORD=secret" > .env
osiris run pipeline.oml

# For E2B
osiris run pipeline.oml --e2b --e2b-env KEY=value
```

### Monitoring Execution
TODO: Real-time monitoring:
```bash
# Watch logs in real-time
tail -f logs/run_*/events.jsonl | jq

# TODO: Add monitoring patterns
# TODO: Explain event types
```

## Debugging

TODO: Debugging strategies:

### Reading Logs
```bash
# View session logs
osiris logs show --session <id>

# Generate interactive HTML report
osiris logs html --session <id> --open

# Filter events
osiris logs show --session <id> --filter "error"

# TODO: Document log structure
```

The HTML report provides comprehensive execution analysis with metrics, events timeline, and artifact inspection.

### Common Errors
TODO: Troubleshooting guide:

#### Connection Errors
```
# Error: Connection refused
# TODO: Diagnosis steps
# TODO: Resolution options
```

#### Data Errors
```
# Error: Column not found
# TODO: Schema inspection
# TODO: Query debugging
```

#### Memory Errors
```
# Error: Out of memory
# TODO: Data sampling
# TODO: Streaming options (future)
```

### Debug Mode
```bash
# Enable verbose logging
osiris run pipeline.oml --verbose

# Enable debug mode
osiris run pipeline.oml --debug

# TODO: Explain debug output
```

### Performance Analysis
TODO: Performance troubleshooting:
```bash
# View metrics
osiris logs show --session <id> --metrics

# TODO: Explain metrics:
# - rows_read
# - rows_written
# - execution_time
# - memory_usage
```

## Advanced Topics

TODO: Link to advanced guides:

### Custom Components
- [Developer Guide](../developer-guide/components.md)
- Creating custom extractors
- Creating custom writers

### Pipeline Orchestration
- Scheduling with cron (future)
- Integration with Airflow (future)
- Integration with Prefect (future)

### Data Quality
- Adding validation steps
- Data profiling
- Anomaly detection (future)

### Optimization
- Query optimization
- Batch size tuning
- Parallel execution (future)

## Best Practices

TODO: Add best practices:

### Pipeline Design
- Keep pipelines simple and focused
- Use meaningful step IDs
- Document complex queries
- Version control OML files

### Security
- Never hardcode secrets
- Use connection aliases
- Rotate credentials regularly
- Audit pipeline access

### Performance
- Filter data at source
- Use appropriate batch sizes
- Monitor resource usage
- Consider E2B for large datasets

### Maintenance
- Regular connection health checks
- Log rotation policies
- Artifact cleanup
- Documentation updates
