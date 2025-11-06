# Authentication Selector

## Decision Tree

**START: What authentication does the API require?**

### Question 1: Does API require OAuth 2.0?

**YES** → OAuth pattern
- **Secrets**: `client_id`, `client_secret`, (optional: `refresh_token`)
- **Flow**: Authorization Code or Client Credentials
- **Reference**: `recipes/auth-oauth2.md`
- **Example**: Future Shopify connector

**Implementation notes**:
- Token refresh logic required
- Store access_token with expiration
- Handle authorization callback

**NO** → Continue to Question 2

---

### Question 2: Does API use API key in header?

**YES** → API Key pattern
- **Secrets**: `api_key`
- **Header**: `X-API-Key`, `Authorization`, or custom header
- **Reference**: `recipes/auth-api-key.md`
- **Example**: Many REST APIs

**Common header names**:
- `X-API-Key: {api_key}`
- `Authorization: {api_key}`
- `X-Auth-Token: {api_key}`
- Custom: `X-Custom-Auth: {api_key}`

**NO** → Continue to Question 3

---

### Question 3: Does API use HTTP Basic Auth?

**YES** → Basic Auth pattern
- **Secrets**: `username`, `password`
- **Header**: `Authorization: Basic [base64(username:password)]`
- **Reference**: Built-in auth handling
- **Example**: Similar to mysql.extractor credentials

**Implementation**:
```python
import base64
credentials = f"{username}:{password}".encode()
auth_header = f"Basic {base64.b64encode(credentials).decode()}"
headers = {"Authorization": auth_header}
```

**NO** → Continue to Question 4

---

### Question 4: Does API use Bearer token?

**YES** → Bearer Token pattern
- **Secrets**: `token` or `access_token`
- **Header**: `Authorization: Bearer {token}`
- **Reference**: `recipes/auth-bearer.md`
- **Example**: GitHub API, many modern APIs

**Implementation**:
```python
headers = {"Authorization": f"Bearer {token}"}
```

**NO** → Continue to Question 5

---

### Question 5: No authentication required?

**YES** → Public API
- **Secrets**: `[]` (empty list in spec.yaml)
- **Headers**: Standard HTTP headers only
- **Example**: Public data APIs

**Implementation**:
```python
# No auth headers needed
response = requests.get(url, headers={"Accept": "application/json"})
```

**NO** → Contact team (unsupported authentication type)

---

## Security Configuration

### For ALL authentication types:

#### 1. Declare secrets in spec.yaml

```yaml
spec:
  secrets:
    - /config/api_key  # or relevant secret path
    - /config/password
```

#### 2. Set x-connection-fields

```yaml
x-connection-fields:
  - name: api_key
    override: forbidden  # Security fields always forbidden
    description: "API key for authentication"

  - name: base_url
    override: allowed  # Non-secret fields can be allowed
    description: "API base URL"
```

#### 3. Mask in logs

```python
from osiris.core.logging import mask_url

logger.info(f"Connecting to {mask_url(url)}")
logger.debug(f"Auth header: {mask_auth_header(header)}")
```

#### 4. Never log secrets

```python
# WRONG - logs secret
logger.info(f"Using API key: {api_key}")

# CORRECT - masks secret
logger.info(f"Using API key: {api_key[:4]}...")
logger.info("API key configured")
```

---

## Authentication Patterns

### OAuth 2.0 Flow

```python
class OAuth2Handler:
    def __init__(self, client_id: str, client_secret: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.access_token = None
        self.expires_at = None

    def get_token(self) -> str:
        if self.access_token and self.expires_at > time.time():
            return self.access_token

        # Refresh token
        response = requests.post(
            "https://oauth.example.com/token",
            data={
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            }
        )
        data = response.json()
        self.access_token = data["access_token"]
        self.expires_at = time.time() + data["expires_in"]
        return self.access_token

    def get_headers(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {self.get_token()}"}
```

### API Key Pattern

```python
class APIKeyHandler:
    def __init__(self, api_key: str, header_name: str = "X-API-Key"):
        self.api_key = api_key
        self.header_name = header_name

    def get_headers(self) -> Dict[str, str]:
        return {self.header_name: self.api_key}
```

### Bearer Token Pattern

```python
class BearerTokenHandler:
    def __init__(self, token: str):
        self.token = token

    def get_headers(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}
```

---

## Secret Management

### Environment Variables

```bash
# .env file (gitignored)
API_KEY=sk_live_abc123xyz
CLIENT_ID=app_id_12345
CLIENT_SECRET=secret_xyz789
```

### Connection Configuration

```yaml
# connection.yaml
connections:
  my_api:
    family: myapi.extractor
    config:
      base_url: "https://api.example.com/v1"
      api_key: ${API_KEY}  # Reference env var
```

### Runtime Access

```python
from osiris.core.config import Config

config = Config.load()
connection = config.get_connection("my_api")
api_key = connection["config"]["api_key"]  # Resolved from env
```

---

## Testing Authentication

### Unit Tests

```python
def test_api_key_auth():
    handler = APIKeyHandler(api_key="test_key")
    headers = handler.get_headers()
    assert headers["X-API-Key"] == "test_key"

def test_bearer_token_auth():
    handler = BearerTokenHandler(token="test_token")
    headers = handler.get_headers()
    assert headers["Authorization"] == "Bearer test_token"
```

### Integration Tests

```python
@pytest.mark.integration
def test_real_api_connection():
    # Skip if no credentials
    api_key = os.getenv("API_KEY")
    if not api_key:
        pytest.skip("API_KEY not set")

    handler = APIKeyHandler(api_key=api_key)
    response = requests.get(
        "https://api.example.com/v1/test",
        headers=handler.get_headers()
    )
    assert response.status_code == 200
```

---

## Common Pitfalls

### 1. Hardcoded Secrets

```python
# WRONG
api_key = "sk_live_abc123"

# CORRECT
api_key = os.getenv("API_KEY")
if not api_key:
    raise ValueError("API_KEY environment variable required")
```

### 2. Logging Secrets

```python
# WRONG
logger.info(f"Authenticated with key: {api_key}")

# CORRECT
logger.info("Authentication successful")
```

### 3. Exposing in Error Messages

```python
# WRONG
raise ValueError(f"Invalid API key: {api_key}")

# CORRECT
raise ValueError("Invalid API key (check credentials)")
```

---

## Next Steps

After choosing authentication method:

1. **Implement auth handler** in your driver
2. **Update spec.yaml** with secrets and x-connection-fields
3. **Add logging** with proper secret masking
4. **Proceed to**: `pagination-selector.md` (if REST API)
5. **Then**: `recipes/rest-api-extractor.md` (full implementation)

---

## Quick Reference

| Auth Type    | Secrets Required         | Header Format                |
|--------------|--------------------------|------------------------------|
| OAuth 2.0    | client_id, client_secret | Bearer {access_token}        |
| API Key      | api_key                  | X-API-Key: {key}             |
| Basic Auth   | username, password       | Basic {base64}               |
| Bearer Token | token                    | Bearer {token}               |
| Public API   | None                     | None                         |

---

**Document Version**: 1.0
**Last Updated**: 2025-10-26
**Related**: `api-type-selector.md`, `pagination-selector.md`, `../recipes/auth-*.md`
