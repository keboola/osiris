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
from typing import Any
import requests

logger = logging.getLogger(__name__)


class MyServiceExtractorDriver:
    """Extract data from MyService REST API with cursor pagination."""

    def __init__(self):
        """Initialize driver."""
        self.session = requests.Session()

    def run(
        self,
        *,
        step_id: str,
        config: dict,
        inputs: dict | None = None,  # noqa: ARG002
        ctx: Any = None,
    ) -> dict:
        """
        Extract data from MyService API.

        Args:
            step_id: Step identifier
            config: Configuration containing base_url, endpoint, api_key, etc.
            inputs: Not used for extractors
            ctx: Execution context for logging metrics

        Returns:
            {"df": DataFrame} with extracted data
        """
        # Extract config values
        base_url = config.get("base_url", "https://api.myservice.com")
        endpoint = config.get("endpoint")
        api_key = config.get("api_key")
        query = config.get("query")
        page_size = config.get("page_size", 100)

        if not endpoint:
            raise ValueError(f"Step {step_id}: 'endpoint' is required in config")
        if not api_key:
            raise ValueError(f"Step {step_id}: 'api_key' is required in config")

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
        all_records = []

        try:
            while True:
                # Add cursor if present
                if cursor:
                    params["cursor"] = cursor

                # Make request
                logger.info(f"Step {step_id}: Fetching page {page + 1} from {endpoint}")
                response = self.session.get(url, headers=headers, params=params)
                response.raise_for_status()

                data = response.json()
                items = data.get("data", [])

                if not items:
                    logger.info(f"Step {step_id}: No more data. Extracted {page} pages.")
                    break

                # Collect records
                all_records.extend(items)

                # Log metrics
                if ctx and hasattr(ctx, "log_metric"):
                    ctx.log_metric(
                        "records_extracted",
                        len(items),
                        tags={"endpoint": endpoint, "page": page + 1},
                    )

                # Check for next page
                cursor = data.get("pagination", {}).get("next_cursor")
                if not cursor:
                    logger.info(f"Step {step_id}: Reached last page. Total pages: {page + 1}")
                    break

                page += 1

            # Convert to DataFrame
            import pandas as pd  # noqa: PLC0415

            df = pd.DataFrame(all_records)

            # Log final metrics
            rows_read = len(df)
            logger.info(f"Step {step_id}: Extracted {rows_read} rows from {endpoint}")

            if ctx and hasattr(ctx, "log_metric"):
                ctx.log_metric("rows_read", rows_read)

            return {"df": df}

        except requests.exceptions.RequestException as e:
            error_msg = f"API request failed: {str(e)}"
            logger.error(f"Step {step_id}: {error_msg}")
            raise RuntimeError(error_msg) from e

        except Exception as e:
            error_msg = f"Extraction failed: {type(e).__name__}: {str(e)}"
            logger.error(f"Step {step_id}: {error_msg}")
            raise RuntimeError(error_msg) from e

        finally:
            if self.session:
                self.session.close()

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
    """Create driver instance."""
    return MyServiceExtractorDriver()


@pytest.fixture
def mock_ctx():
    """Create mock execution context."""
    ctx = Mock()
    ctx.log_metric = Mock()
    return ctx


@patch("requests.Session.get")
def test_extract_single_page(mock_get, driver, mock_ctx):
    """Test extraction with single page of results."""
    mock_response = Mock()
    mock_response.json.return_value = {
        "data": [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}],
        "pagination": {"next_cursor": None},
    }
    mock_response.raise_for_status.return_value = None
    mock_get.return_value = mock_response

    config = {
        "base_url": "https://api.test.com",
        "endpoint": "/customers",
        "api_key": "test_key",  # pragma: allowlist secret
        "page_size": 100,
    }

    result = driver.run(step_id="test_step", config=config, ctx=mock_ctx)

    assert "df" in result
    df = result["df"]
    assert len(df) == 2
    assert df.iloc[0]["name"] == "Alice"
    assert df.iloc[1]["name"] == "Bob"


@patch("requests.Session.get")
def test_extract_multiple_pages(mock_get, driver, mock_ctx):
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

    config = {
        "base_url": "https://api.test.com",
        "endpoint": "/items",
        "api_key": "test_key",  # pragma: allowlist secret
    }

    result = driver.run(step_id="test_step", config=config, ctx=mock_ctx)

    assert "df" in result
    df = result["df"]
    assert len(df) == 4
    assert df.iloc[0]["id"] == 1
    assert df.iloc[3]["id"] == 4


@patch("requests.Session.get")
def test_extract_empty_results(mock_get, driver, mock_ctx):
    """Test extraction with no results."""
    mock_response = Mock()
    mock_response.json.return_value = {
        "data": [],
        "pagination": {},
    }
    mock_response.raise_for_status.return_value = None
    mock_get.return_value = mock_response

    config = {
        "base_url": "https://api.test.com",
        "endpoint": "/empty",
        "api_key": "test_key",  # pragma: allowlist secret
    }

    result = driver.run(step_id="test_step", config=config, ctx=mock_ctx)

    assert "df" in result
    assert len(result["df"]) == 0


@patch("requests.Session.get")
def test_extract_with_query_filter(mock_get, driver, mock_ctx):
    """Test extraction with query parameter."""
    mock_response = Mock()
    mock_response.json.return_value = {
        "data": [{"id": 1, "status": "active"}],
        "pagination": {},
    }
    mock_response.raise_for_status.return_value = None
    mock_get.return_value = mock_response

    config = {
        "base_url": "https://api.test.com",
        "endpoint": "/users",
        "api_key": "test_key",  # pragma: allowlist secret
        "query": "status=active",
    }

    result = driver.run(step_id="test_step", config=config, ctx=mock_ctx)

    assert "df" in result
    df = result["df"]
    assert len(df) == 1
    mock_get.assert_called_once()
    call_args = mock_get.call_args
    assert call_args[1]["params"]["filter"] == "status=active"


@patch("requests.Session.get")
def test_error_handling(mock_get, driver, mock_ctx):
    """Test error handling with network failure."""
    import requests

    mock_get.side_effect = requests.exceptions.ConnectionError("Network error")

    config = {
        "base_url": "https://api.test.com",
        "endpoint": "/test",
        "api_key": "test_key",  # pragma: allowlist secret
    }

    with pytest.raises(RuntimeError, match="API request failed"):
        driver.run(step_id="test_step", config=config, ctx=mock_ctx)
```

## Validation Checklist

Before committing:
- [ ] spec.yaml validates against schema
- [ ] All secrets declared in `secrets` array
- [ ] x-connection-fields has override policies
- [ ] Driver uses run() method with step_id, config, inputs, ctx
- [ ] Driver returns {"df": DataFrame}
- [ ] Tests include secret suppressions (`# pragma: allowlist secret`)
- [ ] Error handling wraps exceptions with RuntimeError
- [ ] Pagination handles empty results
- [ ] Logs include step_id in messages
- [ ] Tests mock all external API calls
- [ ] Driver logs metrics via ctx.log_metric()

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
