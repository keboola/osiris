# Connections & Doctor Contract

**Purpose**: Machine-verifiable connection and healthcheck requirements.

**Scope**: All components using connections

---

## MUST Rules: Connection Resolution

### CONN-001: Use Resolved Connection

**Statement**: Driver MUST read from `config["resolved_connection"]`, NOT environment.

**Correct**:
```python
conn_info = config.get("resolved_connection", {})
api_key = conn_info.get("api_key")
```

**Wrong**:
```python
import os
api_key = os.environ.get("API_KEY")  # ❌ Don't do this
```

**Failure**: `❌ Driver reads from environment instead of resolved_connection`

---

### CONN-002: Validate Required Fields

**Statement**: Driver MUST validate required connection fields.

**Implementation**:
```python
conn_info = config.get("resolved_connection", {})
if not conn_info:
    raise ValueError(f"Step {step_id}: 'resolved_connection' is required")

required = ["api_key", "base_url"]
for field in required:
    if not conn_info.get(field):
        raise ValueError(f"Step {step_id}: connection field '{field}' is required")
```

---

## SHOULD Rules: Doctor Implementation

### DOC-001: Implement doctor()

**Statement**: Components SHOULD implement `doctor()` for healthchecks.

**Signature**:
```python
def doctor(self, connection: dict, timeout: float = 2.0) -> tuple[bool, dict]:
    """Test connection health."""
```

**Return Structure**:
```python
return ok, {
    "latency_ms": float | None,
    "category": "auth"|"network"|"permission"|"timeout"|"ok"|"unknown",
    "message": str  # Non-sensitive, redacted
}
```

---

### DOC-002: Error Categories

**Statement**: `doctor()` MUST use standard error categories.

**Categories**:
- `auth` - Authentication failure (401, invalid credentials)
- `network` - Network/connection error
- `permission` - Authorization failure (403)
- `timeout` - Request timeout
- `ok` - Successful connection
- `unknown` - Uncategorized error

**Example**:
```python
try:
    response = requests.get(health_url, timeout=timeout)
    response.raise_for_status()
    return True, {"latency_ms": 50, "category": "ok", "message": "Connected"}
except requests.exceptions.HTTPError as e:
    if e.response.status_code == 401:
        return False, {"latency_ms": None, "category": "auth", "message": "Invalid credentials"}
    elif e.response.status_code == 403:
        return False, {"latency_ms": None, "category": "permission", "message": "Access denied"}
except requests.exceptions.Timeout:
    return False, {"latency_ms": None, "category": "timeout", "message": "Timed out"}
except requests.exceptions.ConnectionError as e:
    return False, {"latency_ms": None, "category": "network", "message": str(e)}
```

---

### DOC-003: Redaction-Safe Output

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

---

## CLI Commands

### Test All Connections

```bash
osiris connections doctor --json
```

**Output**:
```json
{
  "connections": [
    {
      "family": "mysql",
      "alias": "default",
      "ok": true,
      "latency_ms": 12.5,
      "category": "ok",
      "message": "Connection successful"
    },
    {
      "family": "shopify",
      "alias": "main",
      "ok": false,
      "latency_ms": null,
      "category": "auth",
      "message": "Invalid access token"
    }
  ]
}
```

---

### Test Specific Connection

```bash
osiris connections doctor --family mysql --alias default --json
```

**Output**:
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

## Connection File Format

**File**: `osiris_connections.yaml`

```yaml
version: 1
connections:
  mysql:
    default:
      host: localhost
      port: 3306
      database: mydb
      user: admin
      password: ${MYSQL_PASSWORD}  # Env var substitution

  shopify:
    main:
      shop_domain: mystore.myshopify.com
      access_token: ${SHOPIFY_TOKEN}
      api_version: "2024-01"
      default: true  # Use when no alias specified
```

---

## Validation Checklist

- [ ] Driver reads from `config["resolved_connection"]`
- [ ] Driver validates required connection fields
- [ ] Component spec declares `capabilities.doctor: true` if `doctor()` implemented
- [ ] `doctor()` returns `tuple[bool, dict]`
- [ ] `doctor()` timeout defaults to 2.0 seconds
- [ ] Error categories use standard values
- [ ] `doctor()` output contains no secrets
- [ ] CLI command works: `osiris connections doctor --json`

---

## See Also

- **Overview**: `../llms/overview.md`
- **Connector Contract**: `../llms/connectors.md`
- **Full Checklist**: `COMPONENT_AI_CHECKLIST.md`
