# REST API Extractor Recipe

## Use Case
Building an extractor for any REST API (e.g., Shopify, Stripe, GitHub).

## Prerequisites
- API documentation URL
- Authentication method (Bearer token, API key, OAuth)
- Pagination strategy (cursor, offset, page-based)
- Base URL and endpoint paths

## Component Structure

### 1. spec.yaml Template

```yaml
name: myservice.extractor
version: 1.0.0
family: myservice
type: extractor
description: Extract data from MyService REST API

capabilities:
  modes: ["extract"]
  discovery: false
  healthcheck: true

configSchema:
  type: object
  properties:
    base_url:
      type: string
      description: API base URL
      default: "https://api.myservice.com"
    endpoint:
      type: string
      description: API endpoint path (e.g., /v1/customers)
    query:
      type: string
      description: Optional query parameters
    api_key:
      type: string
      description: API authentication key
    page_size:
      type: integer
      description: Number of records per page
      default: 100
  required: ["endpoint", "api_key"]
  additionalProperties: false

secrets:
  - /config/api_key

x-connection-fields:
  - name: base_url
    override: allowed
  - name: api_key
    override: forbidden

x-runtime:
  driver: osiris.drivers.myservice_extractor_driver.MyServiceExtractorDriver

examples:
  - name: Extract customers
    config:
      connection: "@myservice.production"
      endpoint: "/v1/customers"
      page_size: 100
```

### 2. Driver Implementation

File: `osiris/drivers/myservice_extractor_driver.py`

```python
"""MyService REST API Extractor Driver."""

import logging
from typing import Any, Iterator
import requests

from osiris.core.driver_context import DriverContext

logger = logging.getLogger(__name__)


class MyServiceExtractorDriver:
    """Extract data from MyService REST API with cursor pagination."""

    def __init__(self, *, context: DriverContext):
        """Initialize driver with context."""
        self.context = context
        self.session = requests.Session()

    def extract(
        self,
        *,
        base_url: str = "https://api.myservice.com",
        endpoint: str,
        api_key: str,
        query: str | None = None,
        page_size: int = 100,
    ) -> Iterator[dict[str, Any]]:
        """
        Extract data from MyService API.

        Args:
            base_url: API base URL
            endpoint: API endpoint path
            api_key: API authentication key
            query: Optional query filter
            page_size: Records per page

        Yields:
            Records from the API
        """
        # Set auth headers
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        # Build initial URL
        url = f"{base_url}{endpoint}"
        params = {"limit": page_size}
        if query:
            params["filter"] = query

        cursor = None
        page = 0

        while True:
            # Add cursor if present
            if cursor:
                params["cursor"] = cursor

            # Make request
            logger.info(f"Fetching page {page + 1} from {endpoint}")
            response = self.session.get(url, headers=headers, params=params)
            response.raise_for_status()

            data = response.json()
            items = data.get("data", [])

            if not items:
                logger.info(f"No more data. Extracted {page} pages.")
                break

            # Yield records
            for item in items:
                yield item

            # Log metrics
            self.context.log_metric(
                "records_extracted",
                len(items),
                tags={"endpoint": endpoint, "page": page + 1},
            )

            # Check for next page
            cursor = data.get("pagination", {}).get("next_cursor")
            if not cursor:
                logger.info(f"Reached last page. Total pages: {page + 1}")
                break

            page += 1

    def healthcheck(self, *, base_url: str, api_key: str) -> dict[str, Any]:
        """
        Check API connectivity and auth.

        Args:
            base_url: API base URL
            api_key: API authentication key

        Returns:
            Health check result
        """
        url = f"{base_url}/health"
        headers = {"Authorization": f"Bearer {api_key}"}

        try:
            response = self.session.get(url, headers=headers, timeout=5)
            response.raise_for_status()
            return {
                "status": "healthy",
                "latency_ms": response.elapsed.total_seconds() * 1000,
            }
        except requests.exceptions.RequestException as e:
            return {
                "status": "unhealthy",
                "error": str(e),
                "category": "network",
            }
```

### 3. Tests

File: `tests/drivers/test_myservice_extractor_driver.py`

```python
"""Tests for MyService Extractor Driver."""

import pytest
from unittest.mock import Mock, patch
from osiris.drivers.myservice_extractor_driver import MyServiceExtractorDriver
from osiris.core.driver_context import DriverContext


@pytest.fixture
def driver():
    """Create driver instance with mocked context."""
    context = Mock(spec=DriverContext)
    return MyServiceExtractorDriver(context=context)


@patch("requests.Session.get")
def test_extract_single_page(mock_get, driver):
    """Test extraction with single page of results."""
    mock_response = Mock()
    mock_response.json.return_value = {
        "data": [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}],
        "pagination": {"next_cursor": None},
    }
    mock_response.raise_for_status.return_value = None
    mock_get.return_value = mock_response

    results = list(
        driver.extract(
            base_url="https://api.test.com",
            endpoint="/customers",
            api_key="test_key",  # pragma: allowlist secret
            page_size=100,
        )
    )

    assert len(results) == 2
    assert results[0]["name"] == "Alice"
    assert results[1]["name"] == "Bob"


@patch("requests.Session.get")
def test_extract_multiple_pages(mock_get, driver):
    """Test extraction with multiple pages."""
    # Page 1
    page1 = Mock()
    page1.json.return_value = {
        "data": [{"id": 1}, {"id": 2}],
        "pagination": {"next_cursor": "cursor_page_2"},
    }
    page1.raise_for_status.return_value = None

    # Page 2
    page2 = Mock()
    page2.json.return_value = {
        "data": [{"id": 3}, {"id": 4}],
        "pagination": {"next_cursor": None},
    }
    page2.raise_for_status.return_value = None

    mock_get.side_effect = [page1, page2]

    results = list(
        driver.extract(
            base_url="https://api.test.com",
            endpoint="/items",
            api_key="test_key",  # pragma: allowlist secret
        )
    )

    assert len(results) == 4
    assert results[0]["id"] == 1
    assert results[3]["id"] == 4


@patch("requests.Session.get")
def test_extract_empty_results(mock_get, driver):
    """Test extraction with no results."""
    mock_response = Mock()
    mock_response.json.return_value = {
        "data": [],
        "pagination": {},
    }
    mock_response.raise_for_status.return_value = None
    mock_get.return_value = mock_response

    results = list(
        driver.extract(
            base_url="https://api.test.com",
            endpoint="/empty",
            api_key="test_key",  # pragma: allowlist secret
        )
    )

    assert len(results) == 0


@patch("requests.Session.get")
def test_extract_with_query_filter(mock_get, driver):
    """Test extraction with query parameter."""
    mock_response = Mock()
    mock_response.json.return_value = {
        "data": [{"id": 1, "status": "active"}],
        "pagination": {},
    }
    mock_response.raise_for_status.return_value = None
    mock_get.return_value = mock_response

    results = list(
        driver.extract(
            base_url="https://api.test.com",
            endpoint="/users",
            api_key="test_key",  # pragma: allowlist secret
            query="status=active",
        )
    )

    assert len(results) == 1
    mock_get.assert_called_once()
    call_args = mock_get.call_args
    assert call_args[1]["params"]["filter"] == "status=active"


@patch("requests.Session.get")
def test_healthcheck_success(mock_get, driver):
    """Test successful health check."""
    mock_response = Mock()
    mock_response.raise_for_status.return_value = None
    mock_response.elapsed.total_seconds.return_value = 0.05
    mock_get.return_value = mock_response

    result = driver.healthcheck(
        base_url="https://api.test.com",
        api_key="test_key",  # pragma: allowlist secret
    )

    assert result["status"] == "healthy"
    assert result["latency_ms"] == 50


@patch("requests.Session.get")
def test_healthcheck_failure(mock_get, driver):
    """Test health check with network error."""
    import requests

    mock_get.side_effect = requests.exceptions.ConnectionError("Network error")

    result = driver.healthcheck(
        base_url="https://api.test.com",
        api_key="test_key",  # pragma: allowlist secret
    )

    assert result["status"] == "unhealthy"
    assert "Network error" in result["error"]
    assert result["category"] == "network"
```

## Validation Checklist

Before committing:
- [ ] spec.yaml validates against schema
- [ ] All secrets declared in `secrets` array
- [ ] x-connection-fields has override policies
- [ ] Driver uses keyword-only args (`*,`)
- [ ] Tests include secret suppressions (`# pragma: allowlist secret`)
- [ ] Healthcheck returns proper error categories
- [ ] Pagination handles empty results
- [ ] Logs use masked URLs
- [ ] Tests mock all external API calls
- [ ] Driver logs metrics via context

## Common Variations

### Authentication Methods

**API Key in Header:**
```python
headers = {"X-API-Key": api_key}
```

**Basic Auth:**
```python
from requests.auth import HTTPBasicAuth
response = self.session.get(url, auth=HTTPBasicAuth(username, password))
```

**OAuth Token:**
```python
headers = {"Authorization": f"Bearer {oauth_token}"}
```

### Pagination Strategies

**Offset-based:**
```python
offset = 0
while True:
    params = {"limit": page_size, "offset": offset}
    # ... fetch and yield ...
    offset += len(items)
```

**Page-based:**
```python
page = 1
while True:
    params = {"page": page, "per_page": page_size}
    # ... fetch and yield ...
    page += 1
```

## Next Steps

1. Replace "myservice" with your actual service name
2. Update authentication method if not Bearer token
3. Adjust pagination logic based on API docs
4. Add discovery mode if API supports schema introspection
5. Test with real API credentials
6. Validate with: `python -m pytest tests/drivers/test_myservice_extractor_driver.py -v`
7. Run from testing_env: `cd testing_env && python -m pytest ../tests/drivers/test_myservice_extractor_driver.py`

## Related Recipes

- **pagination-cursor.md** - Deep dive into cursor pagination
- **auth-selector.md** - Authentication pattern selection
- **error-handling.md** - Robust error handling patterns
