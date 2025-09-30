# Osiris LLM Contract: Overview

**Purpose**: Core principles for AI-generated Osiris code.

**Audience**: AI agents, LLMs generating Osiris components

---

## Core Principles

### 1. Determinism

**Rule**: Same inputs MUST produce identical outputs.

**Why**: Enables AIOP delta analysis, cache validity, reproducible debugging.

**Implementation**:
```python
# CORRECT: Sorted keys
import json
data = {"z": 1, "a": 2}
json.dumps(data, sort_keys=True)  # → '{"a": 2, "z": 1}'

# WRONG: Unsorted keys
json.dumps(data)  # → '{"z": 1, "a": 2}' (order may vary)
```

**Validation**:
```bash
# Run twice, compare outputs
osiris run pipeline.yaml --out run1/
osiris run pipeline.yaml --out run2/
diff -r run1/ run2/  # Should be identical
```

---

### 2. Fingerprints

**Rule**: Use SHA-256 for all fingerprints.

**Why**: Security, collision resistance, standardization.

**Implementation**:
```python
import hashlib

def compute_fingerprint(data: str) -> str:
    """Compute SHA-256 fingerprint."""
    return hashlib.sha256(data.encode("utf-8")).hexdigest()

# Example: Discovery cache fingerprint
discovery_data = json.dumps(discovery_result, sort_keys=True)
fingerprint = compute_fingerprint(discovery_data)
```

**Usage**:
- Discovery cache invalidation
- Manifest integrity checking
- Driver registry parity verification

---

### 3. Timestamps

**Rule**: All timestamps MUST be ISO 8601 UTC.

**Format**: `YYYY-MM-DDTHH:MM:SS.sssZ`

**Implementation**:
```python
from datetime import datetime, timezone

# CORRECT: ISO 8601 UTC
timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
# → "2025-09-30T12:00:00.000Z"

# WRONG: Local time or non-ISO format
datetime.now().isoformat()  # No timezone
str(datetime.now())         # Not ISO 8601
```

---

### 4. Evidence IDs

**Rule**: Stable, structured identifiers for all artifacts.

**Pattern**: `ev.<type>.<step_id>.<name>.<timestamp_ms>`

**Types**: `artifact`, `event`, `metric`, `log`

**Implementation**:
```python
def generate_evidence_id(
    type: str,
    step_id: str,
    name: str,
    timestamp_ms: int
) -> str:
    """Generate stable evidence ID."""
    return f"ev.{type}.{step_id}.{name}.{timestamp_ms}"

# Example
evidence_id = generate_evidence_id(
    type="artifact",
    step_id="extract_users",
    name="config",
    timestamp_ms=1735000000000
)
# → "ev.artifact.extract_users.config.1735000000000"
```

---

### 5. Machine-Readable Outputs

**Rule**: All outputs MUST be parseable without heuristics.

**Formats**:
- **Events**: JSON Lines (`.jsonl`)
- **Metrics**: JSON Lines with schema
- **Configs**: JSON or YAML (sorted keys)
- **Errors**: Structured with `category`, `message`, `fix_hint`

**Example Event**:
```json
{
  "ts": "2025-09-30T12:00:00.000Z",
  "session": "run_1735000000000",
  "event": "step_complete",
  "step_id": "extract_users",
  "rows_processed": 1000,
  "duration_ms": 1500
}
```

**Example Metric**:
```json
{
  "ts": "2025-09-30T12:00:00.000Z",
  "session": "run_1735000000000",
  "metric": "rows_read",
  "value": 1000,
  "unit": "rows",
  "tags": {"step": "extract_users"}
}
```

---

### 6. Secret Redaction

**Rule**: Secrets MUST be redacted before any output.

**Detection**: Use component spec `secrets` field (JSON Pointers).

**Implementation**:
```python
from osiris.core.secrets_masking import mask_secrets

def write_artifact(config: dict, secrets_paths: list[str]) -> None:
    """Write config artifact with secrets masked."""
    masked_config = mask_secrets(config, secrets_paths)
    with open("artifact.json", "w") as f:
        json.dump(masked_config, f, sort_keys=True)
```

**Pattern Matching**:
```python
SECRET_PATTERNS = [
    r"password",
    r"token",
    r"key",
    r"secret",
    r"credential",
]
```

---

### 7. Error Taxonomy

**Rule**: Categorize errors for retry/abort decisions.

**Categories**:
- `auth` - Authentication failure (no retry)
- `network` - Network issue (retry with backoff)
- `permission` - Authorization failure (no retry)
- `timeout` - Request timeout (retry with backoff)
- `validation` - Input validation error (no retry)
- `unknown` - Uncategorized error (no retry)

**Implementation**:
```python
def classify_error(exception: Exception) -> str:
    """Classify error for retry logic."""
    if isinstance(exception, AuthenticationError):
        return "auth"
    elif isinstance(exception, requests.exceptions.Timeout):
        return "timeout"
    elif isinstance(exception, requests.exceptions.ConnectionError):
        return "network"
    elif isinstance(exception, PermissionError):
        return "permission"
    elif isinstance(exception, ValueError):
        return "validation"
    else:
        return "unknown"
```

---

### 8. Healthcheck Contract

**Rule**: `doctor()` output MUST be machine-readable dict.

**Schema**:
```python
def doctor(connection: dict, timeout: float = 2.0) -> tuple[bool, dict]:
    """Return (ok, details)."""
    return ok, {
        "latency_ms": float | None,
        "category": "auth"|"network"|"permission"|"timeout"|"ok"|"unknown",
        "message": str  # Non-sensitive, redacted
    }
```

**CLI Output Format**:
```json
{
  "family": "mysql",
  "alias": "default",
  "ok": true,
  "latency_ms": 50.0,
  "category": "ok",
  "message": "Connection successful"
}
```

---

## AI Agent Checklist

Before generating code, verify:

- [ ] Outputs are deterministic (sorted keys, stable IDs)
- [ ] Timestamps use ISO 8601 UTC
- [ ] Fingerprints use SHA-256
- [ ] Evidence IDs follow pattern
- [ ] Events/metrics match schemas
- [ ] Secrets are redacted
- [ ] Errors are categorized
- [ ] Healthcheck returns structured dict

---

## Validation Commands

```bash
# Validate determinism
osiris run pipeline.yaml --out run1/
osiris run pipeline.yaml --out run2/
diff run1/events.jsonl run2/events.jsonl  # Should match

# Validate event schema
cat logs/run_XXX/events.jsonl | jq -c '.' | \
  python -m jsonschema -i /dev/stdin schemas/events.schema.json

# Validate metric schema
cat logs/run_XXX/metrics.jsonl | jq -c '.' | \
  python -m jsonschema -i /dev/stdin schemas/metrics.schema.json

# Check for secrets
grep -i "password\|token\|key" logs/run_XXX/**/*.json
# Should return no matches (all redacted)
```

---

## See Also

- **Component Contract**: `llms/components.md`
- **Driver Contract**: `llms/drivers.md`
- **Connector Contract**: `llms/connectors.md`
- **Full Checklist**: `../checklists/COMPONENT_AI_CHECKLIST.md`
