# LLM Contract: Connectors

**Purpose**: AI patterns for connection resolution and healthcheck implementation.

**Audience**: AI agents, LLMs generating connector code

---

## Connector vs Component

**Clarification**: Connector ≠ Component

- **Connector**: Connection management, authentication, client initialization
- **Component**: What/How/Where - spec + driver + connector

**Example**:
```
mysql.extractor (Component) = spec.yaml + driver.py + mysql_connector.py
                                                        ^^^^^^^^^^^^^^^^
                                                        This is the connector
```

---

## Connection Resolution Flow

```
Pipeline YAML         osiris_connections.yaml         Driver
     |                        |                          |
     | @mysql.default         |                          |
     +----------------------->|                          |
                              | Resolve alias            |
                              | Substitute env vars      |
                              | Create connection dict   |
                              +------------------------->|
                                                         | Use resolved_connection
                                                         | Execute query
```

---

## Connection Files

### CONN-001: Connection File Location

**Statement**: Connections MUST be defined in `osiris_connections.yaml` at project root.

**Format**:
```yaml
version: 1
connections:
  <family>:
    <alias>:
      <connection_fields>
```

**Example**:
```yaml
version: 1
connections:
  mysql:
    default:
      host: localhost
      port: 3306
      database: mydb
      user: admin
      password: ${MYSQL_PASSWORD}
    production:
      host: prod-db.example.com
      port: 3306
      database: prod_db
      user: readonly
      password: ${MYSQL_PROD_PASSWORD}
```

---

### CONN-002: Environment Variable Substitution

**Statement**: Secrets SHOULD use environment variable substitution.

**Syntax**: `${VAR_NAME}`

**Example**:
```yaml
connections:
  shopify:
    main:
      shop_domain: mystore.myshopify.com
      access_token: ${SHOPIFY_ACCESS_TOKEN}
      api_version: "2024-01"
```

**Resolution**:
```python
import os

def resolve_env_vars(value: str) -> str:
    """Resolve ${VAR_NAME} patterns."""
    import re
    pattern = r'\$\{([^}]+)\}'
    def replacer(match):
        var_name = match.group(1)
        return os.environ.get(var_name, "")
    return re.sub(pattern, replacer, value)
```

---

### CONN-003: Default Connection

**Statement**: One connection per family SHOULD be marked as `default: true`.

**Purpose**: Allow omitting alias in pipeline YAML

**Example**:
```yaml
connections:
  mysql:
    default:
      host: localhost
      default: true  # This is the default connection
    production:
      host: prod-db.example.com
```

**Pipeline Usage**:
```yaml
steps:
  - id: extract_users
    driver: mysql.extractor
    config:
      connection: "@mysql"  # Uses default connection
```

---

## Connection Resolution

### CONN-004: Alias Pattern

**Statement**: Connection aliases MUST follow `@<family>.<alias>` pattern.

**Pattern**: `^@[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$`

**Examples**:
```yaml
# ✓ Correct
connection: "@mysql.default"
connection: "@shopify.main"
connection: "@supabase.prod"

# ✗ Wrong
connection: "mysql.default"     # Missing @
connection: "@MySQL.Default"    # Capital letters
connection: "@mysql-default"    # Wrong separator
```

---

### CONN-005: Resolution Timing

**Statement**: Runner MUST resolve connections BEFORE calling driver.

**Flow**:
```python
# Runner (osiris/core/runner.py)
def execute_step(step: dict) -> None:
    config = step["config"]

    # 1. Resolve connection alias
    if "connection" in config:
        alias = config["connection"]  # e.g., "@mysql.default"
        resolved = resolve_connection(alias)
        config["resolved_connection"] = resolved

    # 2. Call driver (driver receives resolved_connection)
    driver.run(step_id=step["id"], config=config, inputs={}, ctx=ctx)
```

**Driver MUST NOT resolve connections**:
```python
# ❌ WRONG: Driver resolves connection
def run(self, *, step_id, config, inputs, ctx):
    alias = config["connection"]
    conn = resolve_connection(alias)  # Driver should NOT do this

# ✓ CORRECT: Driver uses resolved_connection
def run(self, *, step_id, config, inputs, ctx):
    conn_info = config.get("resolved_connection", {})
    client = self._create_client(conn_info)
```

---

### CONN-006: Resolved Connection Structure

**Statement**: `resolved_connection` MUST be dict with all connection fields.

**Structure**:
```python
resolved_connection = {
    "family": "mysql",
    "alias": "default",
    "host": "localhost",
    "port": 3306,
    "database": "mydb",
    "user": "admin",
    "password": "secret123"  # pragma: allowlist secret
}
```

**Driver Access**:
```python
def run(self, *, step_id, config, inputs, ctx):
    conn = config.get("resolved_connection", {})
    if not conn:
        raise ValueError(f"Step {step_id}: 'resolved_connection' is required")

    host = conn.get("host")
    port = conn.get("port", 3306)
    database = conn.get("database")
```

---

## Connection Validation

### CONN-007: Required Fields

**Statement**: Driver MUST validate required connection fields.

**Implementation**:
```python
def run(self, *, step_id, config, inputs, ctx):
    conn = config.get("resolved_connection", {})
    if not conn:
        raise ValueError(f"Step {step_id}: 'resolved_connection' is required")

    # Validate required fields
    required = ["host", "database", "user", "password"]
    for field in required:
        if not conn.get(field):
            raise ValueError(f"Step {step_id}: connection field '{field}' is required")
```

---

### CONN-008: Type Validation

**Statement**: Driver SHOULD validate connection field types.

**Implementation**:
```python
def _validate_connection(self, conn: dict) -> None:
    """Validate connection field types."""
    if not isinstance(conn.get("port"), int):
        raise TypeError(f"Connection field 'port' must be integer, got {type(conn.get('port'))}")

    if not isinstance(conn.get("host"), str):
        raise TypeError(f"Connection field 'host' must be string, got {type(conn.get('host'))}")
```

---

## Healthcheck (Doctor)

### CONN-009: Doctor Signature

**Statement**: `doctor()` MUST follow standard signature.

**Signature**:
```python
def doctor(self, connection: dict, timeout: float = 2.0) -> tuple[bool, dict]:
    """Test connection health.

    Args:
        connection: Resolved connection dict
        timeout: Maximum seconds to wait

    Returns:
        (ok, details) where details = {
            "latency_ms": float | None,
            "category": "auth"|"network"|"permission"|"timeout"|"ok"|"unknown",
            "message": str  # Non-sensitive, redacted
        }
    """
```

---

### CONN-010: Error Categories

**Statement**: `doctor()` MUST use standard error categories.

**Categories**:
- `auth` - Authentication failure (401, invalid credentials)
- `network` - Network/connection error
- `permission` - Authorization failure (403)
- `timeout` - Request timeout
- `ok` - Successful connection
- `unknown` - Uncategorized error

**Implementation**:
```python
def doctor(self, connection: dict, timeout: float = 2.0) -> tuple[bool, dict]:
    try:
        start = time.time()
        client = self._create_client(connection)
        client.ping(timeout=timeout)
        latency = (time.time() - start) * 1000

        return True, {
            "latency_ms": round(latency, 2),
            "category": "ok",
            "message": "Connection successful"
        }

    except AuthenticationError:
        return False, {
            "latency_ms": None,
            "category": "auth",
            "message": "Invalid credentials"
        }

    except PermissionError:
        return False, {
            "latency_ms": None,
            "category": "permission",
            "message": "Access denied"
        }

    except socket.timeout:
        return False, {
            "latency_ms": None,
            "category": "timeout",
            "message": f"Timed out after {timeout}s"
        }

    except (socket.error, ConnectionError) as e:
        return False, {
            "latency_ms": None,
            "category": "network",
            "message": f"Network error: {type(e).__name__}"
        }

    except Exception as e:
        return False, {
            "latency_ms": None,
            "category": "unknown",
            "message": f"Error: {type(e).__name__}"
        }
```

---

### CONN-011: Redaction-Safe Output

**Statement**: `doctor()` output MUST NOT contain secrets.

**Correct**:
```python
return False, {
    "category": "auth",
    "message": "Invalid token"  # ✓ Generic message
}
```

**Wrong**:
```python
return False, {
    "message": f"Token {api_key} is invalid"  # ❌ Leaks secret
}
```

**DSN Redaction**:
```python
# ✓ Correct
message = "Failed to connect to mysql://***@localhost/mydb"

# ❌ Wrong
message = f"Failed to connect to mysql://{user}:{password}@{host}/{db}"
```

---

### CONN-012: Latency Measurement

**Statement**: `doctor()` SHOULD measure connection latency.

**Implementation**:
```python
import time

def doctor(self, connection: dict, timeout: float = 2.0) -> tuple[bool, dict]:
    start = time.time()
    try:
        # Perform health check
        response = requests.get(health_url, timeout=timeout)
        response.raise_for_status()

        latency_ms = (time.time() - start) * 1000
        return True, {
            "latency_ms": round(latency_ms, 2),
            "category": "ok",
            "message": "Connected"
        }
    except Exception as e:
        return False, {
            "latency_ms": None,
            "category": classify_error(e),
            "message": str(e)
        }
```

---

## Connection Pooling

### CONN-013: Connection Reuse

**Statement**: Connectors SHOULD reuse connections within a session.

**Anti-Pattern**:
```python
# ❌ Wrong: Create new connection for each query
def run(self, *, step_id, config, inputs, ctx):
    conn = self._create_connection(config["resolved_connection"])
    result = conn.execute(query)
    conn.close()
```

**Correct Pattern**:
```python
# ✓ Correct: Reuse connection from context
def run(self, *, step_id, config, inputs, ctx):
    conn = self._get_or_create_connection(config["resolved_connection"])
    result = conn.execute(query)
    # Connection stays open for future steps

def _get_or_create_connection(self, conn_info: dict):
    """Get existing connection or create new one."""
    cache_key = self._make_cache_key(conn_info)
    if cache_key not in self._connection_cache:
        self._connection_cache[cache_key] = self._create_connection(conn_info)
    return self._connection_cache[cache_key]
```

---

### CONN-014: Connection Cleanup

**Statement**: Connectors MUST close connections on session end.

**Implementation**:
```python
class MySQLConnector:
    def __init__(self):
        self._connection_cache = {}

    def close_all(self):
        """Close all cached connections."""
        for conn in self._connection_cache.values():
            try:
                conn.close()
            except Exception:
                pass
        self._connection_cache.clear()

# Runner cleanup
def cleanup_session():
    for connector in active_connectors:
        connector.close_all()
```

---

## Client Initialization

### CONN-015: Client Factory Pattern

**Statement**: Connectors SHOULD use factory pattern for client creation.

**Implementation**:
```python
class ShopifyConnector:
    @staticmethod
    def create_client(connection: dict):
        """Create Shopify API client from connection info."""
        shop_domain = connection.get("shop_domain")
        access_token = connection.get("access_token")
        api_version = connection.get("api_version", "2024-01")

        if not shop_domain or not access_token:
            raise ValueError("shop_domain and access_token are required")

        return shopify.GraphQL(
            shop_url=f"https://{shop_domain}/admin/api/{api_version}/graphql.json",
            headers={"X-Shopify-Access-Token": access_token}
        )
```

---

### CONN-016: Connection String Building

**Statement**: Use DSN-style connection strings for JDBC/ODBC-like connectors.

**Pattern**:
```python
def build_dsn(conn: dict) -> str:
    """Build MySQL DSN."""
    host = conn.get("host", "localhost")
    port = conn.get("port", 3306)
    database = conn.get("database")
    user = conn.get("user")
    password = conn.get("password")

    # Build DSN
    dsn = f"mysql://{user}:{password}@{host}:{port}/{database}"
    return dsn
```

**Redacted Version (for logging)**:
```python
def build_dsn_redacted(conn: dict) -> str:
    """Build redacted DSN for logging."""
    host = conn.get("host", "localhost")
    port = conn.get("port", 3306)
    database = conn.get("database")

    return f"mysql://***@{host}:{port}/{database}"
```

---

## SSL/TLS Configuration

### CONN-017: SSL Support

**Statement**: Connectors SHOULD support SSL/TLS connections.

**Connection Schema**:
```yaml
connections:
  mysql:
    secure:
      host: prod-db.example.com
      port: 3306
      ssl: true
      ssl_ca: /path/to/ca.pem
      ssl_cert: /path/to/client-cert.pem
      ssl_key: /path/to/client-key.pem
```

**Client Initialization**:
```python
def create_client(connection: dict):
    ssl_config = None
    if connection.get("ssl"):
        ssl_config = {
            "ca": connection.get("ssl_ca"),
            "cert": connection.get("ssl_cert"),
            "key": connection.get("ssl_key")
        }

    return pymysql.connect(
        host=connection["host"],
        port=connection["port"],
        ssl=ssl_config
    )
```

---

## Retry Logic

### CONN-018: Retry on Transient Errors

**Statement**: Connectors SHOULD retry on transient network errors.

**Implementation**:
```python
import time

def connect_with_retry(conn_info: dict, max_retries: int = 3) -> Any:
    """Connect with exponential backoff."""
    for attempt in range(max_retries):
        try:
            return create_connection(conn_info)
        except (socket.timeout, ConnectionError) as e:
            if attempt == max_retries - 1:
                raise
            wait_time = 2 ** attempt  # Exponential backoff
            time.sleep(wait_time)
    raise RuntimeError("Failed to connect after retries")
```

---

### CONN-019: Non-Retryable Errors

**Statement**: Do NOT retry on auth or permission errors.

**Implementation**:
```python
def connect_with_retry(conn_info: dict, max_retries: int = 3) -> Any:
    for attempt in range(max_retries):
        try:
            return create_connection(conn_info)
        except AuthenticationError:
            # Don't retry auth errors
            raise
        except PermissionError:
            # Don't retry permission errors
            raise
        except (socket.timeout, ConnectionError):
            if attempt == max_retries - 1:
                raise
            time.sleep(2 ** attempt)
```

---

## Connection Testing

### CONN-020: CLI Doctor Command

**Statement**: Connectors MUST be testable via `osiris connections doctor`.

**Command**:
```bash
osiris connections doctor --family mysql --alias default --json
```

**Expected Output**:
```json
{
  "family": "mysql",
  "alias": "default",
  "ok": true,
  "latency_ms": 12.5,
  "category": "ok",
  "message": "Connection successful",
  "details": {
    "server_version": "8.0.35",
    "charset": "utf8mb4"
  }
}
```

---

### CONN-021: Connection Listing

**Statement**: All connections MUST be listable via `osiris connections list`.

**Command**:
```bash
osiris connections list --json
```

**Expected Output**:
```json
[
  {
    "family": "mysql",
    "alias": "default",
    "host": "localhost",
    "database": "mydb",
    "default": true
  },
  {
    "family": "shopify",
    "alias": "main",
    "shop_domain": "mystore.myshopify.com",
    "api_version": "2024-01"
  }
]
```

---

## Common Connection Patterns

### MySQL
```yaml
connections:
  mysql:
    default:
      host: localhost
      port: 3306
      database: mydb
      user: admin
      password: ${MYSQL_PASSWORD}
      charset: utf8mb4
      ssl: false
```

### PostgreSQL / Supabase
```yaml
connections:
  supabase:
    default:
      url: https://abc123.supabase.co
      service_role_key: ${SUPABASE_SERVICE_ROLE_KEY}
      api_version: v1
```

### Shopify
```yaml
connections:
  shopify:
    main:
      shop_domain: mystore.myshopify.com
      access_token: ${SHOPIFY_ACCESS_TOKEN}
      api_version: "2024-01"
```

### REST API
```yaml
connections:
  api:
    default:
      base_url: https://api.example.com/v1
      api_key: ${API_KEY}
      timeout: 30
```

---

## See Also

- **Overview**: `overview.md`
- **Driver Contract**: `drivers.md`
- **Connections & Doctor Contract**: `../checklists/connections_doctor_contract.md`
- **Full Checklist**: `../checklists/COMPONENT_AI_CHECKLIST.md`
