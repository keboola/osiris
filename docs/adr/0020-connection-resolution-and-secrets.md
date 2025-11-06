# ADR 0020: Connection Resolution and Secrets

## Status
Accepted

## Context

OML v0.1.0 must remain secret-free to ensure pipelines can be safely shared, version-controlled, and reviewed. Currently, credentials live in `.env` files, making it difficult to manage multiple database connections and requiring direct environment variable references in code. We need a clean separation between non-secret connection metadata (hostnames, ports, database names) and actual secrets (passwords, API keys), while maintaining deterministic resolution for compile/run/chat operations.

Key requirements:
- OML files must never contain secrets
- Support multiple connections per connector family (e.g., multiple MySQL databases)
- Provide clear default selection when connection isn't specified
- Enable better onboarding and developer experience
- Maintain backward compatibility with existing `.env` approach

## Decision

Introduce an external connections configuration file (`osiris_connections.yaml`) for non-secret connection metadata, while secrets remain in `.env` and are referenced via `${ENV_VAR}` substitution.

### Connection Alias Model

Connections are organized by connector family with named aliases:

```yaml
connections:
  <family>:
    <alias>:
      default: true|false  # optional; at most one true per family
      # ... non-secret fields ...
      secret_field: ${ENV_VAR}
```

### Default Selection Precedence

When OML doesn't specify a connection, the system follows this precedence:
1. Alias with `default: true`
2. Alias named `default`
3. Fail with a friendly error listing available aliases

### OML Reference Syntax

Optional explicit connection reference in OML:
```yaml
config:
  connection: "@<family>.<alias>"  # e.g., "@mysql.db_movies", "@supabase.main"
```

If omitted, default selection precedence applies.

### Chat Integration

- **At INTENT_CAPTURED**: LLM may be informed about available families/aliases (names only) to make a single bounded choice if ambiguous
- **After DISCOVERY**: Still no open questions; use discovered connection context

## Details

### File Format

**Location**: `osiris_connections.yaml` (project root, alongside `osiris.yaml`)

**Example Structure**:
```yaml
version: 1
connections:
  mysql:
    db_movies:
      default: true
      host: test-api-to-mysql.cjtmwuzxk8bh.us-east-1.rds.amazonaws.com
      port: 3306
      database: padak
      user: admin
      password: ${MYSQL_PASSWORD}
    db_analytics:
      host: mysql-db2.internal
      port: 3306
      database: analytics
      user: svc_analytics
      password: ${MYSQL_ANALYTICS_PASSWORD}
  supabase:
    main:
      default: true
      url: https://nedklmkgzjsyvqfxbmve.supabase.com
      service_role_key: ${SUPABASE_SERVICE_ROLE_KEY}
    staging:
      url: https://staging.supabase.com
      service_role_key: ${SUPABASE_STAGING_KEY}
  duckdb:
    local:
      default: true
      path: ./data/local.duckdb
```

### Resolver API

**Module**: `osiris/core/config.py`

**Key Functions**:
```python
def load_connections_yaml() -> dict:
    """Load connections config with ${VAR} substitution from environment."""
    
def resolve_connection(family: str, alias: Optional[str] = None) -> dict:
    """
    Resolve connection by family and optional alias.
    - If alias provided: return specific connection
    - If alias is None: apply default selection precedence
    - Parse values like "@family.alias" format
    Returns resolved dict with secrets substituted.
    """
```

### Runner Integration

Components receive fully resolved connection dictionaries:
- `mysql.extractor` and `supabase.writer` no longer read env directly
- Runner calls `resolve_connection()` before component instantiation
- Components receive clean dict with all values resolved

### CLI Commands (M1c Minimal)

**List Connections**:
```bash
osiris connections list
```
Output:
```
MySQL Connections:
  * db_movies (default) - padak@test-api-to-mysql.cjtmwuzxk8bh.us-east-1.rds.amazonaws.com:3306
    └─ Environment: MYSQL_PASSWORD [✓ Set]
  * db_analytics - svc_analytics@mysql-db2.internal:3306/analytics
    └─ Environment: MYSQL_ANALYTICS_PASSWORD [✗ Missing]

Supabase Connections:
  * main (default) - https://nedklmkgzjsyvqfxbmve.supabase.com
    └─ Environment: SUPABASE_SERVICE_ROLE_KEY [✓ Set]
```

**Test Connections**:
```bash
osiris connections doctor
```
- MySQL: Execute `SELECT 1`
- Supabase: Minimal ping or simple insert/select
- DuckDB: Check file exists/writable
- Results mockable in tests

### CLI Commands (M1d Future)

**Add Connection Wizard**:
```bash
osiris connections add mysql --alias prod --set-default
```
- Interactive wizard reading component spec
- Separates secrets from non-secrets
- Writes to `osiris_connections.yaml` (never writes secret values)
- Guides user to set environment variables

### Security & Redaction

**Redaction Rules**:
- Automatic masking for fields matching: `password`, `key`, `token`, `secret`, `credential`
- Session logs replace secrets with `***REDACTED***`
- Prompt dumps never include actual secret values
- CLI output shows only whether env vars are set, not values

**Implementation**:
- Extend `osiris/core/secrets_masking.py`
- Apply to all logging, stdout, and debug output
- Connection resolution logs show alias names, not resolved values

### Component-Level Override Policies (x-connection-fields)

Components can declare which fields are provided by connections and control whether they can be overridden in pipeline step configs using the `x-connection-fields` specification field.

**Purpose**: Prevents accidental credential leakage while allowing infrastructure fields to be overridden for testing.

**Override Policies**:
- `allowed`: Step config can override (e.g., host, port for testing)
- `forbidden`: Step config cannot override (e.g., password, api_key for security)
- `warning`: Step config can override but emits warning (e.g., headers that might contain auth)

**Example Component Spec**:
```yaml
name: mysql.extractor
x-connection-fields:
  - name: host
    override: allowed      # Can use different host for testing
  - name: password
    override: forbidden    # Security: cannot override password
```

**Validation Behavior**:
- Validator checks override policies when connection reference used
- Forbidden overrides cause validation errors
- Warning overrides emit warnings but allow execution

**See Also**: [x-connection-fields Specification](../reference/x-connection-fields.md) for full documentation.

### Testing Strategy

**Unit Tests**:
- Environment variable substitution (`${VAR}` → value)
- Default precedence logic (default flag, "default" name, error)
- Parsing "@family.alias" syntax
- Missing environment variable handling

**Integration Tests**:
- Runner passes resolved dicts to components
- Components receive correct connection parameters
- Secrets never appear in logs or error messages

**CLI Tests**:
- `connections list` masks secrets correctly
- `connections doctor` handles connection failures gracefully
- Mock connection testing for CI/CD environments

## Consequences

### Positive

- **Cleaner OML**: No secrets or connection details in pipeline definitions
- **Safer Secret Handling**: Clear separation between secrets and configuration
- **Multi-Connection Support**: Easy to manage multiple databases per family
- **Predictable Defaults**: Clear precedence rules for connection selection
- **Better Developer Experience**: Visual connection status, testing tools
- **Shareable Configurations**: `osiris_connections.yaml` can be committed (without secrets)

### Negative

- **Additional Configuration File**: One more file to manage
- **Learning Curve**: Users must understand connections YAML + `.env` split
- **Migration Effort**: Existing projects need to create connections file
- **Potential Confusion**: Two places for configuration (connections vs. osiris.yaml)

## Alternatives Considered

### 1. Keep Everything in Environment Variables
- **Pros**: Simple, familiar, single source
- **Cons**: Hard to share/review, poor multi-connection support, verbose OML
- **Rejected**: Poor developer experience for multiple connections

### 2. Embed Connections in OML
- **Pros**: Self-contained pipelines
- **Cons**: Secrets in version control, duplication across pipelines
- **Rejected**: Critical security risk

### 3. Use External Secret Management (Vault, AWS Secrets Manager)
- **Pros**: Enterprise-grade security
- **Cons**: Complex setup, external dependencies
- **Deferred**: Good for future enhancement, too complex for MVP

### 4. Connection Strings
- **Pros**: Compact, industry standard
- **Cons**: Harder to parse, mix secrets with config
- **Rejected**: Doesn't solve the separation problem

## Migration Path

1. **Backward Compatible**: If no `osiris_connections.yaml` exists, fall back to current `.env` approach
2. **Migration Tool** (future): `osiris migrate connections` to generate from existing `.env`
3. **Documentation**: Clear migration guide with examples

## References

- ADR 0019: Chat State Machine and OML Synthesis - Connection selection during chat
- ADR 0009: Secrets Handling Strategy - Overall secrets approach
- Issue #M1c: Connection resolution requirements
- `osiris/core/config.py` - Implementation location
- `osiris/core/secrets_masking.py` - Redaction implementation
- [x-connection-fields Specification](../reference/x-connection-fields.md) - Component-level override policies for connection fields

## Notes on Milestone M1

**Implementation Status**: Fully implemented in Milestone M1.

The connection resolution and secrets management system has been implemented in:
- **Core implementation**: `osiris/core/config.py` - Contains `load_connections_yaml()` and `resolve_connection()` functions with ${ENV_VAR} substitution
- **Environment loading**: `osiris/core/env_loader.py` - Unified environment loading system ensuring consistent behavior across all commands
- **CLI commands**: `osiris/cli/connections_cmd.py` - Implementation of `osiris connections list` and `osiris connections doctor` commands
- **Runtime integration**: Connection resolution integrated into runner, components receive resolved connection dicts

Key features delivered:
- External `osiris_connections.yaml` for non-secret connection metadata
- Environment variable substitution for secrets using `${ENV_VAR}` syntax
- Connection alias model with family-based organization
- Default selection precedence: `default:true` → alias named "default" → error
- Optional OML reference syntax: `config.connection: "@family.alias"`
- CLI commands: `osiris connections list` (shows aliases with masked secrets)
- CLI commands: `osiris connections doctor` (tests connectivity)
- Complete separation of secrets from pipeline definitions
- Runtime connection resolution with per-step events
- Automatic redaction of sensitive fields in logs and outputs

Note: The connection wizard (`osiris connections add`) was deferred to M1d as planned.
