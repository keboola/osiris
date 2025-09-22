# ADR-0027: Run Export Context for AI

## Status
Partially Accepted

## Context

Current HTML logs browser provides rich visualization for human operators but is not AI-friendly. As organizations increasingly use AI assistants to analyze pipeline runs, debug issues, and optimize performance, we need more than just raw logs - we need a context-rich digest that provides complete understanding in a way that AI models can easily consume and reason about.

This is not merely a plain text export of existing logs. The problem requires enriched context:
- AI models need schemas to understand data structure and relationships
- Configuration context must include explanatory metadata about what each setting means
- Connection details need semantic annotations explaining their purpose
- Execution flow requires narrative context to understand causality
- Metrics need baseline comparisons to identify anomalies

Organizations want to:
- Use AI to analyze failed runs and suggest fixes
- Generate automatic run summaries and reports
- Compare runs to identify performance regressions
- Train models on historical run patterns
- Enable ChatGPT/Claude to debug production issues

## Decision

Introduce an AI-optimized context bundle that goes beyond simple log export to provide a comprehensive, enriched digest of pipeline execution. This bundle will be a single text file containing not just what happened, but WHY it happened, with schemas, configuration context, and explanatory metadata that enables AI models to perfectly understand the run.

### Bundle Structure
```
================================================================================
OSIRIS RUN BUNDLE
================================================================================
Session ID: run_1234567890
Pipeline: customer_etl_pipeline
Status: completed | failed | partial
Start Time: 2024-01-15T10:00:00Z
End Time: 2024-01-15T10:05:00Z
Duration: 5m 0s
Environment: local | e2b

================================================================================
MANIFEST
================================================================================
# This is the compiled pipeline definition
# TODO: Include full manifest with inline comments explaining each section

================================================================================
CONFIGURATION WITH CONTEXT
================================================================================
# Step configurations with semantic explanations
# Each config includes metadata explaining its purpose and impact

Step: extract_customers
Component: mysql.extractor
Configuration:
  connection: [REDACTED mysql.primary connection details]
    # Context: Primary read-replica database for customer data
    # Purpose: Low-latency access to production customer records
    # SLA: 99.9% availability, <100ms query response
  query: |
    SELECT * FROM customers
    WHERE created_at > '2024-01-01'
    # Context: Incremental extraction pattern
    # Business Rule: Only process customers created this year
    # Expected Volume: ~1,500 rows based on historical patterns
  # Connection resolved from osiris_connections.yaml alias "mysql.primary"
  # Password loaded from environment variable MYSQL_PASSWORD
  # Component Capability: Supports batch extraction up to 10M rows

================================================================================
SCHEMAS
================================================================================
# Data schemas discovered or validated during execution
# TODO: Include table schemas, column types, row counts

Table: customers
Columns:
  - id: INTEGER (primary key)
  - name: VARCHAR(255)
  - email: VARCHAR(255) (unique)
  - created_at: TIMESTAMP
Row Count: 1,543

================================================================================
EXECUTION TIMELINE
================================================================================
# Chronological sequence of events
# TODO: Include key events with timestamps and context

10:00:00 [START] Pipeline execution started
10:00:01 [PREPARE] Loading drivers and resolving connections
10:00:02 [DISCOVERY] Discovering schema for table 'customers'
10:00:03 [STEP_START] extract_customers: Beginning extraction
10:00:15 [METRICS] extract_customers: Read 1,543 rows in 12s
10:00:15 [STEP_COMPLETE] extract_customers: Success
10:00:16 [STEP_START] write_to_csv: Writing data to filesystem
10:00:18 [METRICS] write_to_csv: Wrote 1,543 rows to customers.csv
10:00:18 [STEP_COMPLETE] write_to_csv: Success
10:00:19 [COMPLETE] Pipeline completed successfully

================================================================================
METRICS SUMMARY
================================================================================
# Aggregated metrics for analysis
# TODO: Include all metrics with explanations

Total Rows Read: 1,543
Total Rows Written: 1,543
Total Execution Time: 5m 0s
Memory Peak Usage: 245 MB
E2B Overhead: N/A (local execution)

Per-Step Metrics:
- extract_customers:
    rows_read: 1,543
    execution_time_ms: 12,000
    memory_usage_mb: 125

- write_to_csv:
    rows_written: 1,543
    execution_time_ms: 2,000
    file_size_bytes: 125,432

================================================================================
ARTIFACTS
================================================================================
# Files generated during execution
# TODO: List artifacts with sizes and checksums

artifacts/extract_customers/
  - metadata.json (543 bytes)

artifacts/write_to_csv/
  - customers.csv (125,432 bytes, sha256:abc123...)
  - write_summary.json (234 bytes)

================================================================================
ERRORS AND WARNINGS
================================================================================
# Any errors or warnings encountered
# TODO: Include full error context with suggestions

[No errors in this run]

Example error format:
ERROR [mysql.extractor] Step 'extract_1' failed: Connection timeout
  Context: Attempting to connect to mysql.primary (host: db.example.com:3306)
  Suggestion: Check network connectivity and firewall rules
  Stack trace: [included if available]

================================================================================
AI ANALYSIS HINTS
================================================================================
# Context to help AI understand this run
# TODO: Include relevant hints

- This pipeline extracts customer data from MySQL and writes to CSV
- The extraction uses a date filter to get recent customers only
- CSV output is sorted by customer ID for consistency
- This appears to be a daily batch job based on the schedule
- Performance is within normal range (compare with previous runs)
- No schema changes detected since last run

================================================================================
END OF BUNDLE
================================================================================
Generated: 2024-01-15T10:06:00Z
Osiris Version: 2.0.0
Bundle Format: 1.0
```

### Implementation Details

TODO: Complete implementation specifications:

1. **CLI Command**
   ```bash
   osiris logs bundle --session <id> [--output <file>]
   osiris logs bundle --last  # Bundle most recent run
   ```

2. **Size Limits**
   - Maximum bundle size: 5MB (configurable)
   - Truncation strategy for large artifacts
   - Compression option for archival

3. **Redaction Rules**
   - All passwords replaced with [REDACTED]
   - API keys replaced with [REDACTED API_KEY]
   - Connection strings sanitized
   - PII detection and masking (future)

4. **Format Versioning**
   - Bundle format version in header
   - Backward compatibility for parsers
   - Migration tools for format changes

5. **AI Optimization**
   - Clear section delimiters
   - Explanatory comments throughout
   - Consistent formatting
   - Machine-parseable timestamps
   - Error messages with actionable suggestions

## Consequences

### Positive
- **AI-Friendly**: Single text file with complete context enables AI analysis
- **Debugging**: Comprehensive information for troubleshooting
- **Portability**: Text format works everywhere, easy to share
- **Versioning**: Can track bundle format evolution
- **Compliance**: Consistent secret redaction for security

### Negative
- **Size**: Bundle files can be large for complex pipelines
- **Redundancy**: Some information duplicated from other logs
- **Maintenance**: Another format to maintain and document
- **Performance**: Bundle generation adds overhead

### Neutral
- **Format Evolution**: Will need to evolve based on AI model feedback
- **Integration**: Third-party tools will need to understand format
- **Storage**: Organizations need to manage bundle retention

## Implementation Plan

TODO: Implementation phases:

### Phase 1: MVP (Week 1)
- Basic bundle generation
- Core sections (manifest, config, metrics)
- CLI command implementation
- Secret redaction

### Phase 2: Enhanced Context (Week 2)
- Schema information
- Execution timeline
- AI analysis hints
- Error context enhancement

### Phase 3: Optimization (Week 3)
- Size optimization
- Compression support
- Format validation
- Documentation

### Phase 4: Integration (Week 4)
- AI model testing
- Feedback incorporation
- Performance tuning
- Release

## References
- Issue #XXX: AI-friendly log format request
- ADR-0003: Session-scoped logging (related)
- Claude/ChatGPT best practices for context
- JSONL vs TXT format analysis

## Notes on Milestone M1

**Implementation Status**: Partially implemented in Milestone M1. Integration postponed to Milestone M2.

The context builder foundation has been implemented, but the run export feature described in this ADR has not been fully integrated:
- **Context builder implemented**: `osiris/prompts/build_context.py` - Builds minimal component context for LLM consumption
- **JSON schema defined**: `osiris/prompts/context.schema.json` - Schema for context format with strict validation
- **CLI command exists**: `osiris prompts build-context` - Generates component context with caching and fingerprinting

What has NOT been implemented:
- **Run bundle generation**: The `osiris logs bundle` command does not exist
- **AI-optimized run export**: No integration between run logs and AI context
- **Enhanced context sections**: Timeline, metrics summary, AI hints not implemented
- **Chat integration**: Context builder not fully integrated into chat command workflow

Current state:
- The context builder successfully generates a minimal (~330 token) JSON representation of component capabilities
- It includes SHA-256 fingerprinting and disk caching for efficiency
- NO-SECRETS guarantee implemented with comprehensive secret filtering
- Session-aware logging with structured events

The full run export context for AI feature is postponed to Milestone M2 for implementation alongside other AI enhancement features.
