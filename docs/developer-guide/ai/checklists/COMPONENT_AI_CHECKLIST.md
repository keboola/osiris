# Osiris Component AI Compliance Checklist

**Purpose**: Machine-verifiable rules for automated validation by CI systems and AI agents.

**Date**: 2025-09-30
**Audience**: CI pipelines, automated validators, AI development agents
**Status**: Production-ready

---

## Introduction

This document provides strict, machine-verifiable rules for Osiris component development. Each rule follows the format:

- **Rule ID**: Stable identifier (e.g., `SPEC-001`)
- **Statement**: MUST/SHOULD/MAY requirement (RFC 2119)
- **Grounding**: File path + section reference
- **Test Hint**: Command or test file that validates it
- **Failure Message**: Template for friendly error output

**Usage**:
- **CI Systems**: Validate PRs against these rules
- **AI Agents**: Generate code compliant with these rules
- **Developers**: Reference for compliance requirements

**Companion Document**: [`COMPONENT_DEVELOPER_AUDIT.md`](COMPONENT_DEVELOPER_AUDIT.md) (human-friendly guide)

---

## Domain: Spec Completeness & Schema Conformance

### SPEC-001: Required Fields Present
**Statement**: Component spec MUST contain `name`, `version`, `modes`, `capabilities`, `configSchema`.
**Grounding**: `components/spec.schema.json` (required array)
**Test**: `osiris components validate <name> --level basic`
**Failure**: `❌ Missing required field: <field>. Component specs must include: name, version, modes, capabilities, configSchema.`

### SPEC-002: Name Pattern Valid
**Statement**: `name` MUST match pattern `^[a-z0-9_.-]+$`.
**Grounding**: `components/spec.schema.json:properties.name.pattern`
**Test**: JSON Schema validation
**Failure**: `❌ Invalid component name '<name>'. Use lowercase letters, numbers, dots, dashes, underscores only. Example: 'mysql.extractor'`

### SPEC-003: Semantic Version Valid
**Statement**: `version` MUST follow semantic versioning (major.minor.patch).
**Grounding**: `components/spec.schema.json:properties.version.pattern`
**Test**: Regex match `^\d+\.\d+\.\d+$`
**Failure**: `❌ Invalid version '<version>'. Expected format: major.minor.patch (e.g., 1.0.0). See https://semver.org/`

### SPEC-004: Modes Non-Empty
**Statement**: `modes` array MUST contain at least one valid mode.
**Grounding**: `components/spec.schema.json:properties.modes.minItems`
**Test**: Array length > 0, all items in enum
**Failure**: `❌ At least one mode required. Valid modes: extract, write, transform, discover, analyze, stream. Example: modes: [extract, discover]`

### SPEC-005: Capabilities Object Present
**Statement**: `capabilities` MUST be an object with boolean values.
**Grounding**: `components/spec.schema.json:properties.capabilities`
**Test**: Type check + all values boolean
**Failure**: `❌ Capabilities must be an object with boolean values. Example: capabilities: {discover: true, streaming: false}`

### SPEC-006: ConfigSchema Valid JSON Schema
**Statement**: `configSchema` MUST be a valid JSON Schema Draft 2020-12.
**Grounding**: `docs/reference/components-spec.md:72-91`, `osiris/components/registry.py:282-286`
**Test**: `Draft202012Validator.check_schema(config_schema)`
**Failure**: `❌ Invalid configSchema: <error>. Ensure it follows JSON Schema Draft 2020-12 specification. See https://json-schema.org/draft/2020-12/json-schema-validation.html`

### SPEC-007: Examples Validate Against ConfigSchema
**Statement**: All `examples[].config` MUST validate against `configSchema`.
**Grounding**: `osiris/components/registry.py:289-310`
**Test**: `osiris components validate <name> --level enhanced`
**Failure**: `❌ Example <n> config invalid: <error>. Fix the example or update configSchema.`

### SPEC-008: Secrets Use JSON Pointers
**Statement**: All `secrets` array entries MUST be valid JSON Pointers starting with `/`.
**Grounding**: `docs/reference/components-spec.md:95-112`
**Test**: Regex match `^/` + path exists in configSchema
**Failure**: `❌ Secret path '<path>' must start with '/' (JSON Pointer format). Example: '/password' for top-level field, '/connection/password' for nested field.`

### SPEC-009: Redaction Extras Use JSON Pointers
**Statement**: All `redaction.extras` entries MUST be valid JSON Pointers.
**Grounding**: `docs/reference/components-spec.md:117-127`, `osiris/components/registry.py:356-367`
**Test**: `osiris components validate <name> --level strict`
**Failure**: `❌ Redaction path '<path>' doesn't reference a valid config field. Check that the path exists in configSchema properties.`

### SPEC-010: LLM Input Aliases Match ConfigSchema
**Statement**: All keys in `llmHints.inputAliases` MUST match `configSchema.properties`.
**Grounding**: `osiris/components/registry.py:371-387`
**Test**: `osiris components validate <name> --level strict`
**Failure**: `❌ Input alias '<key>' doesn't match any config field. Valid fields: <list>. Remove the alias or add the field to configSchema.`

---

## Domain: Capabilities and Mode Flags

### CAP-001: Discover Capability Consistency
**Statement**: If `modes` includes `"discover"`, `capabilities.discover` MUST be `true`.
**Grounding**: ADR-0007, logical consistency
**Test**: `modes.includes("discover") => capabilities.discover === true`
**Failure**: `❌ Component declares 'discover' mode but capabilities.discover is false. Set capabilities.discover: true.`

### CAP-002: Mode-Specific I/O Contracts
**Statement**: Extractors (mode: extract) MUST return `{"df": DataFrame}`. Writers (mode: write) MUST accept `inputs: {"df": DataFrame}` and return `{}`.
**Grounding**: `osiris/core/driver.py:30-31`, ADR-0012
**Test**: Runtime contract validation (not compile-time)
**Failure**: `❌ Extractor must return {"df": DataFrame}, got <type>. Check driver.run() return value.`

### CAP-003: Deprecated Load Mode
**Statement**: Use `"write"` mode instead of `"load"`. `"load"` is deprecated.
**Grounding**: ADR-0012 Amendment 1, `docs/adr/0012-separate-extractors-and-writers.md:60-75`
**Test**: Check if `modes` includes `"load"`
**Failure**: `⚠️  Mode 'load' is deprecated. Use 'write' instead. Support for 'load' will be removed in v2.0. See ADR-0012.`

### CAP-004: Streaming Not Yet Supported
**Statement**: Components MUST NOT declare `capabilities.streaming: true` in M1.
**Grounding**: ADR-0022, deferred to M2
**Test**: Check `capabilities.streaming === true`
**Failure**: `❌ Streaming capability not supported in M1. Set capabilities.streaming: false. See ADR-0022 for M2 roadmap.`

---

## Domain: Discovery Behavior & Caching

### DISC-001: Discovery Mode Declared
**Statement**: If component supports discovery, it MUST declare `modes: ["discover"]`.
**Grounding**: ADR-0002, `docs/reference/components-spec.md:49`
**Test**: `"discover" in spec["modes"]` when `capabilities.discover === true`
**Failure**: `❌ Component capability 'discover: true' requires mode 'discover' in modes array. Add 'discover' to modes.`

### DISC-002: Discovery Output Deterministic
**Statement**: Discovery output MUST be sorted (tables, columns) and deterministic.
**Grounding**: ADR-0002 (fingerprinting requirements)
**Test**: Run discovery twice, compare outputs
**Failure**: `❌ Discovery output is non-deterministic. Ensure tables and columns are sorted lexically. Use sorted() on lists.`

### DISC-003: Discovery Cache Fingerprint
**Statement**: Discovery results SHOULD include a fingerprint (SHA-256) for cache invalidation.
**Grounding**: ADR-0002
**Test**: Check for `fingerprint` key in discovery output
**Failure**: `⚠️  No fingerprint in discovery output. Cache invalidation will rely on TTL only. Consider adding SHA-256 hash of schema.`

---

## Domain: Connections Fields & Doctor Validation

### CONN-001: Resolved Connection Expected
**Statement**: Driver MUST read connection details from `config["resolved_connection"]`, NOT from environment.
**Grounding**: ADR-0020, `osiris/drivers/mysql_extractor_driver.py:40-42`
**Test**: Code inspection or runtime assertion
**Failure**: `❌ Driver must use config["resolved_connection"], not os.environ or direct env reads. The runner resolves connections before calling driver.run().`

### CONN-002: Required Connection Fields
**Statement**: Component spec MUST declare all required connection fields in `configSchema.required`.
**Grounding**: `docs/reference/components-spec.md:526-532`
**Test**: Check `spec.configSchema.required` includes connection fields
**Failure**: `❌ Connection field '<field>' is required but not declared in configSchema.required array. Add it to the required list.`

### CONN-003: Doctor Return Type
**Statement**: If implementing `doctor()`, return type MUST be `tuple[bool, dict]` with keys: `latency_ms`, `category`, `message`.
**Grounding**: ADR-0021, `docs/adr/0021-component-health-check-capability.md:13-23`
**Test**: Type check + key presence
**Failure**: `❌ doctor() must return (bool, dict) with keys: latency_ms, category, message. Example: return True, {"latency_ms": 50, "category": "ok", "message": "Connected"}`

### CONN-004: Doctor Error Categories
**Statement**: `doctor()` `category` MUST be one of: `"auth"`, `"network"`, `"permission"`, `"timeout"`, `"unknown"`.
**Grounding**: `docs/reference/events_and_metrics_schema.md:46`, ADR-0021
**Test**: Enum validation
**Failure**: `❌ Invalid doctor category '<category>'. Must be one of: auth, network, permission, timeout, unknown.`

---

## Domain: Logging/Metrics/Events Contract

### LOG-001: Required Metrics Emitted
**Statement**: Extractors MUST emit `rows_read` metric. Writers MUST emit `rows_written`. Processors MUST emit `rows_processed`.
**Grounding**: `docs/reference/events_and_metrics_schema.md:86-93`, `components/mysql.extractor/spec.yaml:203-205`
**Test**: Check `ctx.log_metric()` calls in driver code
**Failure**: `❌ <Component type> must emit '<metric>' metric via ctx.log_metric(). Example: ctx.log_metric("rows_read", len(df), tags={"step": step_id})`

### LOG-002: Metric Units Consistent
**Statement**: All metrics MUST specify correct units: `rows`, `ms`, `bytes`, `seconds`, `files`, `code`.
**Grounding**: `docs/reference/events_and_metrics_schema.md:74`
**Test**: Check `unit` parameter in `ctx.log_metric()` calls
**Failure**: `⚠️  Metric '<metric>' missing unit. Expected: <unit>. Example: ctx.log_metric("rows_read", count, unit="rows")`

### LOG-003: Metric Tags Include Step ID
**Statement**: All step-level metrics MUST include `tags={"step": step_id}`.
**Grounding**: `docs/reference/events_and_metrics_schema.md:76`, line 83
**Test**: Check `tags` parameter in `ctx.log_metric()` calls
**Failure**: `❌ Metric '<metric>' must include step_id in tags. Example: tags={"step": step_id}`

### LOG-004: Logging Policy Declared
**Statement**: Component spec SHOULD declare `loggingPolicy` with `metricsToCapture` listing expected metrics.
**Grounding**: `components/mysql.extractor/spec.yaml:192-205`
**Test**: Check presence of `loggingPolicy.metricsToCapture`
**Failure**: `⚠️  No loggingPolicy declared. Add metricsToCapture: [rows_read, duration_ms, bytes_processed] to help users understand expected telemetry.`

### LOG-005: Event Names Standardized
**Statement**: Event names MUST follow pattern `<category>.<action>` (e.g., `extraction.start`, `write.complete`).
**Grounding**: `docs/reference/events_and_metrics_schema.md:198-206`
**Test**: Regex match event names
**Failure**: `⚠️  Event name '<event>' doesn't follow pattern '<category>.<action>'. Use patterns like: extraction.start, write.complete, discovery.tables`

### LOG-006: Sensitive Paths Redacted
**Statement**: All paths listed in `loggingPolicy.sensitivePaths` MUST also appear in `secrets` or `redaction.extras`.
**Grounding**: `components/mysql.extractor/spec.yaml:193-196`, ADR-0009
**Test**: Cross-reference arrays
**Failure**: `❌ Sensitive path '<path>' in loggingPolicy not declared in secrets or redaction.extras. Add it to secrets array for proper masking.`

---

## Domain: Driver Interface and Lifecycle

### DRIVER-001: Driver Protocol Implemented
**Statement**: Driver class MUST implement `run(*, step_id, config, inputs, ctx) -> dict`.
**Grounding**: `osiris/core/driver.py:13-37`
**Test**: Duck typing check or Protocol validation
**Failure**: `❌ Driver must implement run(*, step_id: str, config: dict, inputs: dict | None, ctx: Any) -> dict method. Check signature matches Driver protocol.`

### DRIVER-002: Keyword-Only Arguments
**Statement**: All `run()` parameters MUST be keyword-only (use `*` separator).
**Grounding**: `osiris/core/driver.py:20`
**Test**: AST inspection or runtime check
**Failure**: `❌ Driver run() parameters must be keyword-only. Use: def run(*, step_id, config, inputs, ctx)`

### DRIVER-003: Input Immutability
**Statement**: Driver MUST NOT mutate `inputs` dict or DataFrames within it.
**Grounding**: `osiris/core/driver.py:34`
**Test**: Runtime check or static analysis
**Failure**: `❌ Driver mutated inputs. Create copies if modifications needed: df_copy = inputs["df"].copy()`

### DRIVER-004: Resource Cleanup
**Statement**: Driver SHOULD clean up resources (connections, file handles) in `finally` block.
**Grounding**: `osiris/drivers/mysql_extractor_driver.py:97-98`, best practice
**Test**: Code inspection for `try/finally`
**Failure**: `⚠️  No finally block for resource cleanup. Add finally: engine.dispose() or equivalent to prevent resource leaks.`

### DRIVER-005: Context Null Check
**Statement**: Driver MUST check `if ctx and hasattr(ctx, "log_metric")` before calling `ctx.log_metric()`.
**Grounding**: `osiris/drivers/mysql_extractor_driver.py:74-75`
**Test**: Code inspection
**Failure**: `❌ Must check ctx availability before calling ctx.log_metric(). Use: if ctx and hasattr(ctx, "log_metric"): ctx.log_metric(...)`

### DRIVER-006: Error Re-raising
**Statement**: Driver SHOULD catch specific exceptions, add context, and re-raise as `RuntimeError`.
**Grounding**: `osiris/drivers/mysql_extractor_driver.py:79-95`
**Test**: Code inspection for exception handling
**Failure**: `⚠️  No exception handling. Catch specific exceptions and re-raise with context for better error messages. Example: except ConnectionError as e: raise RuntimeError(f"Failed: {e}") from e`

---

## Domain: Healthcheck Availability and Semantics

### HEALTH-001: Doctor Capability Declared
**Statement**: If driver implements `doctor()` method, spec MUST have `capabilities.doctor: true`.
**Grounding**: ADR-0021
**Test**: Cross-reference spec and driver code
**Failure**: `❌ Driver implements doctor() but spec has capabilities.doctor: false. Set capabilities.doctor: true in spec.yaml.`

### HEALTH-002: Doctor Timeout Default
**Statement**: `doctor()` timeout parameter MUST default to 2.0 seconds.
**Grounding**: ADR-0021, `docs/adr/0021-component-health-check-capability.md:13`
**Test**: Check method signature
**Failure**: `❌ doctor() timeout default must be 2.0 seconds. Use: def doctor(self, connection: dict, timeout: float = 2.0)`

### HEALTH-003: Doctor Redaction-Safe
**Statement**: `doctor()` return dict MUST NOT contain secrets (passwords, keys).
**Grounding**: ADR-0021, `docs/adr/0021-component-health-check-capability.md:19-22`
**Test**: Runtime check for redacted patterns
**Failure**: `❌ doctor() returned unredacted secret in message field. Ensure all sensitive data is masked before returning.`

---

## Domain: Packaging/Registration

### PKG-001: x-runtime Driver Path Valid
**Statement**: `x-runtime.driver` MUST be importable Python path: `<module>.<class>`.
**Grounding**: `osiris/core/driver.py:165-175`, `components/mysql.extractor/spec.yaml:214`
**Test**: `importlib.import_module(module); getattr(module, class)`
**Failure**: `❌ Cannot import driver: <x-runtime.driver>. Ensure module and class exist. Example: osiris.drivers.mysql_extractor_driver.MySQLExtractorDriver`

### PKG-002: Driver Class Name Convention
**Statement**: Driver class name SHOULD follow pattern `<Family><Role>Driver`.
**Grounding**: ADR-0012, convention in codebase
**Test**: Check class name matches pattern
**Failure**: `⚠️  Driver class '<class>' doesn't follow naming convention. Expected: <Family><Role>Driver (e.g., MySQLExtractorDriver)`

### PKG-003: Driver File Name Convention
**Statement**: Driver file SHOULD be named `<family>_<role>_driver.py`.
**Grounding**: ADR-0012, codebase pattern
**Test**: Check file name
**Failure**: `⚠️  Driver file '<file>' doesn't follow naming convention. Expected: <family>_<role>_driver.py (e.g., mysql_extractor_driver.py)`

### PKG-004: Semver for Breaking Changes
**Statement**: Increment major version when making incompatible config schema changes.
**Grounding**: Semantic versioning convention
**Test**: Manual changelog review
**Failure**: `⚠️  Config schema changed incompatibly but version is not a major bump. Increment major version (e.g., 1.0.0 → 2.0.0).`

### PKG-005: Component ID Matches Spec Name
**Statement**: Component registry ID MUST match `spec.yaml` `name` field.
**Grounding**: `osiris/components/registry.py:113`
**Test**: Compare directory name to `spec.name`
**Failure**: `❌ Component directory '<dir>' doesn't match spec.name '<name>'. Rename directory to match spec.name.`

---

## Domain: Resilience/Retry Adherence

### RETRY-001: Exponential Backoff for Transients
**Statement**: Drivers SHOULD implement exponential backoff for transient failures (network, rate limit).
**Grounding**: ADR-0033 (Proposed), best practice
**Test**: Code inspection for retry logic
**Failure**: `⚠️  No retry logic for transient failures. Consider exponential backoff for network errors. See ADR-0033.`

### RETRY-002: Max 3 Retry Attempts
**Statement**: If implementing retries, limit to 3 attempts with initial delay 1s, max delay 30s.
**Grounding**: ADR-0033, `docs/adr/0033-resilience-retry-policies.md:128-143`
**Test**: Check retry parameters
**Failure**: `⚠️  Retry max_attempts should be ≤3. Found: <n>. Excessive retries can delay error reporting.`

### RETRY-003: No Retry on Permanent Errors
**Statement**: MUST NOT retry on permanent errors: syntax, permissions, validation.
**Grounding**: ADR-0033, `docs/adr/0033-resilience-retry-policies.md:90-94`
**Test**: Check error classification logic
**Failure**: `❌ Retrying permanent error '<error>'. Only retry transient failures (network, timeout). Skip retries for auth, syntax, validation errors.`

---

## Domain: Determinism Requirements

### DET-001: Sorted JSON Keys
**Statement**: All JSON outputs (artifacts, configs) MUST have sorted keys for determinism.
**Grounding**: ADR-0015, AIOP requirements
**Test**: `json.dumps(obj, sort_keys=True)`
**Failure**: `❌ JSON output has unsorted keys. Use sort_keys=True for determinism. Example: json.dumps(data, sort_keys=True)`

### DET-002: ISO 8601 Timestamps
**Statement**: All timestamps MUST be ISO 8601 UTC format: `YYYY-MM-DDTHH:MM:SS.sssZ`.
**Grounding**: ADR-0027, `docs/reference/events_and_metrics_schema.md:8`
**Test**: Regex match timestamp format
**Failure**: `❌ Timestamp '<ts>' not ISO 8601 UTC. Expected format: 2025-09-30T12:00:00.000Z. Use: datetime.utcnow().isoformat() + "Z"`

### DET-003: Stable Evidence IDs
**Statement**: Artifact and evidence IDs MUST follow pattern: `ev.<type>.<step_id>.<name>.<timestamp_ms>`.
**Grounding**: ADR-0027
**Test**: Regex match evidence ID format
**Failure**: `❌ Evidence ID '<id>' doesn't match pattern: ev.<type>.<step_id>.<name>.<timestamp_ms>. Example: ev.artifact.extract_users.config.1735000000000`

---

## Domain: LLM/AI Compliance

### AI-001: LLM Hints Provided
**Statement**: Component spec SHOULD include `llmHints` section with `promptGuidance` and `inputAliases`.
**Grounding**: `docs/reference/components-spec.md:137-152`, `components/mysql.extractor/spec.yaml:159-191`
**Test**: Check presence of `llmHints` section
**Failure**: `⚠️  No llmHints provided. Add llmHints section to help LLM-driven pipeline generation understand component usage.`

### AI-002: Input Aliases Comprehensive
**Statement**: `llmHints.inputAliases` SHOULD map common field name variations to canonical names.
**Grounding**: `components/mysql.extractor/spec.yaml:160-176`
**Test**: Check `inputAliases` coverage
**Failure**: `⚠️  Limited input aliases. Add common variations (e.g., host: [hostname, server], user: [username, login]) to improve LLM understanding.`

### AI-003: YAML Snippets Provided
**Statement**: `llmHints.yamlSnippets` SHOULD include common OML patterns.
**Grounding**: `components/mysql.extractor/spec.yaml:181-185`
**Test**: Check presence of `yamlSnippets`
**Failure**: `⚠️  No YAML snippets provided. Add yamlSnippets to show LLMs how to use component in OML pipelines.`

### AI-004: Examples Include OML Snippets
**Statement**: Each example SHOULD include `omlSnippet` field showing pipeline usage.
**Grounding**: `docs/reference/components-spec.md:93-94`
**Test**: Check examples for `omlSnippet` field
**Failure**: `⚠️  Example missing omlSnippet. Add omlSnippet to show complete pipeline context for LLM training.`

### AI-005: AIOP Artifact Determinism
**Statement**: Artifacts created by driver MUST be deterministic (sorted keys, stable IDs, no timestamps in content).
**Grounding**: ADR-0027 (AIOP requirements)
**Test**: Run twice, compare artifact contents
**Failure**: `❌ Artifacts are non-deterministic. Ensure JSON keys sorted, use stable IDs, avoid embedding timestamps in artifact content.`

### AI-006: AIOP Secret Redaction
**Statement**: Artifacts MUST NOT contain unredacted secrets. Redact before writing to disk.
**Grounding**: ADR-0027, `osiris/core/secrets_masking.py`
**Test**: Scan artifacts for secret patterns
**Failure**: `❌ Artifact contains unredacted secret: <pattern>. Use secrets_masking module to redact before writing artifacts.`

### AI-007: Machine-Parsable Errors
**Statement**: Error messages SHOULD be structured JSON when possible, not just strings.
**Grounding**: `osiris/components/error_mapper.py`, best practice for LLM consumption
**Test**: Check error handling for structured output
**Failure**: `⚠️  Errors are plain strings. Consider structured errors with category, message, fix_hint for better LLM/UI consumption.`

### AI-008: Healthcheck Machine-Readable
**Statement**: `doctor()` output MUST be machine-parsable dict, not human-readable string.
**Grounding**: ADR-0021, designed for automated processing
**Test**: Check `doctor()` return structure
**Failure**: `❌ doctor() must return structured dict, not string. Use: {"latency_ms": 50, "category": "ok", "message": "..."}`

### AI-009: Discovery Output Schema Stable
**Statement**: Discovery output schema MUST remain stable across versions for cache compatibility.
**Grounding**: ADR-0002 (discovery cache)
**Test**: Schema comparison across versions
**Failure**: `⚠️  Discovery output schema changed. Increment major version and document schema migration for cache invalidation.`

### AI-010: Fingerprints Use SHA-256
**Statement**: All fingerprints (discovery cache, manifests) MUST use SHA-256, not MD5 or SHA-1.
**Grounding**: Security best practice, ADR-0015
**Test**: Check hash algorithm usage
**Failure**: `❌ Use SHA-256 for fingerprints, not <algorithm>. Import: import hashlib; hashlib.sha256(data.encode()).hexdigest()`

---

## Validation Summary Table

| Domain | Rules | Critical (MUST) | Advisory (SHOULD) |
|--------|-------|-----------------|-------------------|
| Spec Completeness | 10 | 8 | 2 |
| Capabilities | 4 | 2 | 2 |
| Discovery | 3 | 1 | 2 |
| Connections | 4 | 4 | 0 |
| Logging/Metrics | 6 | 3 | 3 |
| Driver Interface | 6 | 3 | 3 |
| Healthcheck | 3 | 2 | 1 |
| Packaging | 5 | 2 | 3 |
| Resilience | 3 | 1 | 2 |
| Determinism | 3 | 3 | 0 |
| LLM/AI Compliance | 10 | 3 | 7 |
| **Total** | **57** | **32** | **25** |

---

## CI Integration

### Pre-Commit Hook

```bash
#!/bin/bash
# .git/hooks/pre-commit
# Validate changed component specs

for file in $(git diff --cached --name-only | grep 'components/.*/spec.yaml'); do
  component=$(basename $(dirname $file))
  echo "Validating $component..."
  osiris components validate $component --level strict || exit 1
done
```

### GitHub Actions

```yaml
# .github/workflows/validate-components.yml
name: Validate Components
on: [pull_request]
jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.10'
      - name: Install dependencies
        run: pip install -r requirements.txt
      - name: Validate all components
        run: |
          for dir in components/*/; do
            component=$(basename $dir)
            echo "Validating $component..."
            osiris components validate $component --level strict --json > /tmp/$component.json
            if [ $? -ne 0 ]; then
              cat /tmp/$component.json
              exit 1
            fi
          done
```

---

## Usage Examples

### For AI Agents

```python
# AI agent validating generated component
def validate_component(spec: dict) -> list[str]:
    """Validate component against AI checklist rules."""
    errors = []

    # SPEC-001: Required fields
    required = ["name", "version", "modes", "capabilities", "configSchema"]
    for field in required:
        if field not in spec:
            errors.append(f"SPEC-001: Missing required field: {field}")

    # SPEC-002: Name pattern
    if not re.match(r'^[a-z0-9_.-]+$', spec.get("name", "")):
        errors.append(f"SPEC-002: Invalid name pattern")

    # ... more rules

    return errors
```

### For CI Systems

```bash
# CI script validating PRs
#!/bin/bash
set -e

echo "Validating component specs..."
for spec in components/*/spec.yaml; do
  component=$(basename $(dirname $spec))

  # Run validation with JSON output
  result=$(osiris components validate $component --level strict --json)

  # Check result
  is_valid=$(echo $result | jq -r '.is_valid')
  if [ "$is_valid" != "true" ]; then
    echo "❌ $component failed validation"
    echo $result | jq '.errors'
    exit 1
  fi

  echo "✓ $component passed"
done

echo "All components valid ✓"
```

---

## Exemptions

Some rules may be waived in specific circumstances:

| Rule | Exemption Criteria | Approval Required |
|------|-------------------|-------------------|
| LOG-004 (loggingPolicy) | Legacy components pre-M1 | Tech lead |
| AI-001 (llmHints) | Internal-only components | None |
| RETRY-001 (backoff) | Simple read-only extractors | Code review |
| SPEC-010 (inputAliases) | Stable API components | None |

**Process**: Add `# EXEMPTION: <rule-id> - <reason>` comment in spec or code.

---

## Maintenance

This checklist must be updated when:
- New ADRs are accepted that affect component contracts
- JSON Schema version changes (currently Draft 2020-12)
- Driver protocol evolves
- AIOP requirements change

**Owner**: Core team
**Review Cycle**: Every milestone release

---

## See Also

- **Human Guide**: [`COMPONENT_DEVELOPER_AUDIT.md`](COMPONENT_DEVELOPER_AUDIT.md)
- **Core Concepts**: [`docs/developer-guide/CONCEPTS.md`](developer-guide/CONCEPTS.md)
- **Reference**: [`docs/reference/components-spec.md`](reference/components-spec.md)
- **ADRs**: [`docs/adr/`](adr/)

---

**Last Updated**: 2025-09-30
