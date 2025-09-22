# ADR-0032: Runtime Parameters and Environment Profiles

## Status
Proposed

## Context
Pipelines need to accept runtime parameters for configuration without modifying the OML file. Additionally, different environments (dev/staging/prod) require different configurations. Currently, there's no standardized way to pass external parameters or manage environment-specific settings.

## Problem
- No way to pass runtime parameters (e.g., date ranges, filters) to pipelines
- Environment-specific configuration requires separate OML files
- External orchestrators cannot pass correlation IDs or trace context
- Testing requires modifying production OML files

## Constraints
- Secrets must never appear in OML or compiled manifests
- Parameters must be validated at compile time
- Must support traceability across distributed systems
- Configuration precedence must be deterministic

## Decision
Extend OML with parameters, profiles, and metadata sections:

### 1. Parameter Declaration
```yaml
params:
  since_date:
    type: string
    default: "2024-01-01"
    description: "Start date for incremental load"

  batch_size:
    type: integer
    default: 1000
    min: 100
    max: 10000

  environment:
    type: string
    enum: ["dev", "staging", "prod"]
    default: "dev"
```

### 2. Environment Profiles
```yaml
profiles:
  dev:
    params:
      batch_size: 100
      since_date: "2024-06-01"
    config:
      log_level: debug

  prod:
    params:
      batch_size: 5000
      since_date: "2024-01-01"
    config:
      log_level: warning
```

### 3. External Metadata
```yaml
metadata:
  run_id: null  # Accepts external run ID for correlation
  external:
    parent_run_id: null
    traceparent: null  # W3C Trace Context
    correlation_id: null
```

### 4. Parameter Binding in Steps
```yaml
steps:
  - id: extract-data
    component: mysql.extractor
    config:
      query: |
        SELECT * FROM orders
        WHERE created_at >= '${params.since_date}'
        LIMIT ${params.batch_size}
```

## Parameter Resolution Precedence
1. CLI arguments: `--param since_date=2024-07-01`
2. Environment variables: `OSIRIS_PARAM_SINCE_DATE=2024-07-01`
3. Selected profile values
4. Default values in parameter declaration

## Compilation Process
1. Load OML with parameter declarations
2. Apply precedence rules to resolve all parameters
3. Validate parameter types and constraints
4. Replace all `${params.*}` placeholders with resolved values
5. Generate `effective_config.json` with frozen parameter values
6. Produce deterministic manifest with no placeholders

## CLI Interface
```bash
# Compile with parameters
osiris compile pipeline.yaml \
  --profile prod \
  --param since_date=2024-08-01 \
  --run-id abc123

# Run with external correlation
osiris run manifest.yaml \
  --run-id abc123 \
  --trace-parent "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
```

## Alternatives Considered
1. **Runtime templating**: Resolve parameters during execution (rejected: loses determinism)
2. **External config files only**: Separate YAML/JSON for parameters (rejected: splits configuration)
3. **Environment variables only**: No OML declaration (rejected: no validation/documentation)

## Consequences
### Positive
- Clean separation of configuration from logic
- Environment-specific settings without OML duplication
- External orchestrator integration via run_id/trace context
- Type-safe parameter validation

### Negative
- Additional compilation complexity
- More validation rules to maintain
- Potential for parameter explosion

## Implementation Notes
- Compiler validates all parameters before manifest generation
- Effective config stored alongside manifest for audit
- Sensitive parameters marked in schema, redacted in logs
- Run ID propagated to all events and metrics

## Security Considerations
- Parameters with `sensitive: true` are masked in logs
- Secrets remain in external stores, only references in OML
- Compiled manifests never contain actual secret values

## Status Tracking
- M1c: Basic parameter support with CLI/env override
- M2: Full profile support
- M3: Integration with external trace context