# Cursor Pagination Pattern

## When to Use
- API returns `next_cursor`, `next_token`, or similar in response
- Common in modern APIs (GraphQL, Twitter, Stripe, Shopify, etc.)
- Better performance than offset for large datasets
- Prevents duplicate records when data changes during pagination

## Pattern Implementation

### Response Structure

Typical cursor-based API response:
```json
{
  "data": [
    {"id": 1, "name": "Record 1"},
    {"id": 2, "name": "Record 2"}
  ],
  "pagination": {
    "next_cursor": "abc123xyz",
    "has_more": true
  }
}
```

### Basic Driver Code

```python
def extract(self, *, endpoint: str, api_key: str, page_size: int = 100):
    """Extract data with cursor pagination."""
    cursor = None
    page = 0

    while True:
        # Build request params
        params = {"limit": page_size}
        if cursor:
            params["cursor"] = cursor

        # Make API call
        headers = {"Authorization": f"Bearer {api_key}"}
        response = self.session.get(endpoint, params=params, headers=headers)
        response.raise_for_status()
        data = response.json()

        # Extract items
        items = data.get("data", [])
        if not items:
            logger.info(f"No more data. Total pages: {page}")
            break

        # Yield records
        for item in items:
            yield item

        # Log progress
        self.context.log_metric(
            "records_extracted",
            len(items),
            tags={"page": page + 1}
        )

        # Get next cursor
        pagination = data.get("pagination", {})
        cursor = pagination.get("next_cursor")

        # Stop if no more pages
        if not cursor or not pagination.get("has_more", False):
            logger.info(f"Reached last page. Total pages: {page + 1}")
            break

        page += 1
```

### Edge Cases

#### 1. Empty First Page
```python
items = data.get("data", [])
if not items:
    logger.info("No data available")
    return  # Don't try to paginate
```

#### 2. Cursor But No Data
```python
if cursor and not items:
    logger.warning("API returned cursor but no data - possible bug")
    break
```

#### 3. Rate Limiting
```python
import time

if response.status_code == 429:
    retry_after = int(response.headers.get("Retry-After", 60))
    logger.info(f"Rate limited. Waiting {retry_after}s")
    time.sleep(retry_after)
    continue  # Retry same page
```

#### 4. Network Errors with Retry
```python
import time
from requests.exceptions import RequestException

max_retries = 3
retry_delay = 5

for attempt in range(max_retries):
    try:
        response = self.session.get(url, params=params, headers=headers)
        response.raise_for_status()
        break
    except RequestException as e:
        if attempt < max_retries - 1:
            logger.warning(f"Request failed (attempt {attempt + 1}/{max_retries}): {e}")
            time.sleep(retry_delay)
        else:
            logger.error(f"Request failed after {max_retries} attempts")
            raise
```

## Complete Working Example

```python
"""Example: Cursor pagination with robust error handling."""

import logging
import time
from typing import Any, Iterator
import requests
from requests.exceptions import RequestException

from osiris.core.driver_context import DriverContext

logger = logging.getLogger(__name__)


class CursorPaginatedExtractor:
    """Extractor with cursor pagination and error handling."""

    def __init__(self, *, context: DriverContext):
        """Initialize driver with context."""
        self.context = context
        self.session = requests.Session()

    def extract(
        self,
        *,
        base_url: str,
        endpoint: str,
        api_key: str,
        page_size: int = 100,
        max_retries: int = 3,
    ) -> Iterator[dict[str, Any]]:
        """
        Extract data with cursor pagination.

        Args:
            base_url: API base URL
            endpoint: API endpoint path
            api_key: API authentication key
            page_size: Records per page
            max_retries: Max retry attempts per request

        Yields:
            Records from the API
        """
        url = f"{base_url}{endpoint}"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        cursor = None
        page = 0
        total_records = 0

        while True:
            # Build params
            params = {"limit": page_size}
            if cursor:
                params["cursor"] = cursor

            # Retry logic
            for attempt in range(max_retries):
                try:
                    logger.info(f"Fetching page {page + 1} (cursor: {cursor or 'initial'})")
                    response = self.session.get(url, params=params, headers=headers, timeout=30)

                    # Handle rate limiting
                    if response.status_code == 429:
                        retry_after = int(response.headers.get("Retry-After", 60))
                        logger.warning(f"Rate limited. Waiting {retry_after}s")
                        time.sleep(retry_after)
                        continue

                    response.raise_for_status()
                    break

                except RequestException as e:
                    if attempt < max_retries - 1:
                        delay = 2**attempt  # Exponential backoff
                        logger.warning(
                            f"Request failed (attempt {attempt + 1}/{max_retries}): {e}. "
                            f"Retrying in {delay}s"
                        )
                        time.sleep(delay)
                    else:
                        logger.error(f"Request failed after {max_retries} attempts")
                        raise

            # Parse response
            data = response.json()
            items = data.get("data", [])

            # Handle empty page
            if not items:
                logger.info(f"No more data. Total: {total_records} records across {page} pages")
                break

            # Yield records
            for item in items:
                yield item
                total_records += 1

            # Log metrics
            self.context.log_metric(
                "records_extracted",
                len(items),
                tags={"endpoint": endpoint, "page": page + 1},
            )

            # Get next cursor
            pagination = data.get("pagination", {})
            next_cursor = pagination.get("next_cursor")
            has_more = pagination.get("has_more", False)

            # Check termination
            if not next_cursor or not has_more:
                logger.info(f"Reached last page. Total: {total_records} records across {page + 1} pages")
                break

            # Warn if cursor didn't change (infinite loop protection)
            if next_cursor == cursor:
                logger.error("Cursor didn't change - stopping to prevent infinite loop")
                break

            cursor = next_cursor
            page += 1
```

## Testing

```python
"""Tests for cursor pagination."""

import pytest
from unittest.mock import Mock, patch
from osiris.drivers.cursor_paginated_extractor import CursorPaginatedExtractor
from osiris.core.driver_context import DriverContext


@pytest.fixture
def driver():
    """Create driver instance."""
    context = Mock(spec=DriverContext)
    return CursorPaginatedExtractor(context=context)


@patch("requests.Session.get")
def test_cursor_pagination_multiple_pages(mock_get, driver):
    """Test cursor pagination across multiple pages."""
    # Page 1
    page1 = Mock()
    page1.status_code = 200
    page1.json.return_value = {
        "data": [{"id": 1}, {"id": 2}],
        "pagination": {"next_cursor": "cursor_page_2", "has_more": True},
    }
    page1.raise_for_status.return_value = None

    # Page 2
    page2 = Mock()
    page2.status_code = 200
    page2.json.return_value = {
        "data": [{"id": 3}, {"id": 4}],
        "pagination": {"next_cursor": "cursor_page_3", "has_more": True},
    }
    page2.raise_for_status.return_value = None

    # Page 3 (last page)
    page3 = Mock()
    page3.status_code = 200
    page3.json.return_value = {
        "data": [{"id": 5}],
        "pagination": {"next_cursor": None, "has_more": False},
    }
    page3.raise_for_status.return_value = None

    mock_get.side_effect = [page1, page2, page3]

    results = list(
        driver.extract(
            base_url="https://api.test.com",
            endpoint="/items",
            api_key="test_key",  # pragma: allowlist secret
        )
    )

    assert len(results) == 5
    assert results[0]["id"] == 1
    assert results[4]["id"] == 5
    assert mock_get.call_count == 3


@patch("requests.Session.get")
def test_cursor_pagination_empty_first_page(mock_get, driver):
    """Test handling of empty first page."""
    page1 = Mock()
    page1.status_code = 200
    page1.json.return_value = {
        "data": [],
        "pagination": {},
    }
    page1.raise_for_status.return_value = None
    mock_get.return_value = page1

    results = list(
        driver.extract(
            base_url="https://api.test.com",
            endpoint="/empty",
            api_key="test_key",  # pragma: allowlist secret
        )
    )

    assert len(results) == 0
    assert mock_get.call_count == 1


@patch("requests.Session.get")
def test_cursor_pagination_rate_limit_retry(mock_get, driver):
    """Test rate limit handling."""
    # First call: rate limited
    rate_limited = Mock()
    rate_limited.status_code = 429
    rate_limited.headers = {"Retry-After": "1"}

    # Second call: success
    success = Mock()
    success.status_code = 200
    success.json.return_value = {
        "data": [{"id": 1}],
        "pagination": {"next_cursor": None, "has_more": False},
    }
    success.raise_for_status.return_value = None

    mock_get.side_effect = [rate_limited, success]

    results = list(
        driver.extract(
            base_url="https://api.test.com",
            endpoint="/items",
            api_key="test_key",  # pragma: allowlist secret
        )
    )

    assert len(results) == 1
    assert mock_get.call_count == 2


@patch("requests.Session.get")
def test_cursor_pagination_network_error_retry(mock_get, driver):
    """Test network error retry logic."""
    import requests

    # First two calls fail
    error = requests.exceptions.ConnectionError("Network error")

    # Third call succeeds
    success = Mock()
    success.status_code = 200
    success.json.return_value = {
        "data": [{"id": 1}],
        "pagination": {"next_cursor": None, "has_more": False},
    }
    success.raise_for_status.return_value = None

    mock_get.side_effect = [error, error, success]

    results = list(
        driver.extract(
            base_url="https://api.test.com",
            endpoint="/items",
            api_key="test_key",  # pragma: allowlist secret
        )
    )

    assert len(results) == 1
    assert mock_get.call_count == 3


@patch("requests.Session.get")
def test_cursor_infinite_loop_protection(mock_get, driver):
    """Test protection against infinite loops with unchanging cursor."""
    page1 = Mock()
    page1.status_code = 200
    page1.json.return_value = {
        "data": [{"id": 1}],
        "pagination": {"next_cursor": "same_cursor", "has_more": True},
    }
    page1.raise_for_status.return_value = None

    page2 = Mock()
    page2.status_code = 200
    page2.json.return_value = {
        "data": [{"id": 2}],
        "pagination": {"next_cursor": "same_cursor", "has_more": True},  # Same cursor!
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

    # Should stop after detecting cursor didn't change
    assert len(results) == 2
    assert mock_get.call_count == 2
```

## Determinism for Discovery

Cursor pagination is usually deterministic if:
- API returns stable cursor values
- Data doesn't change during pagination
- Cursor includes timestamp or snapshot ID

For discovery mode, log cursors for debugging:
```python
logger.debug(f"Page {page + 1} cursor: {cursor}")
```

## Common API Variations

| API | Cursor Field | Has More Field | Example |
|-----|-------------|----------------|---------|
| Stripe | `starting_after` | `has_more` | `{"has_more": true, "data": [...]}` |
| Twitter | `next_token` | Check if exists | `{"next_token": "abc", "data": [...]}` |
| GitHub GraphQL | `endCursor`, `hasNextPage` | `hasNextPage` | `{"pageInfo": {"endCursor": "xyz", "hasNextPage": true}}` |
| Shopify GraphQL | `endCursor` | `hasNextPage` | `{"pageInfo": {"hasNextPage": true, "endCursor": "abc"}}` |
| Facebook Graph | `next` (URL) | Check if exists | `{"paging": {"next": "https://..."}}` |

### Stripe Example
```python
cursor = None
while True:
    params = {"limit": page_size}
    if cursor:
        params["starting_after"] = cursor

    data = response.json()
    items = data.get("data", [])
    has_more = data.get("has_more", False)

    for item in items:
        yield item

    if not has_more:
        break

    # Use last item's ID as cursor
    cursor = items[-1]["id"]
```

### GraphQL Example
```python
cursor = None
while True:
    query = """
    query($cursor: String, $limit: Int!) {
      items(after: $cursor, first: $limit) {
        edges {
          node { id name }
        }
        pageInfo {
          endCursor
          hasNextPage
        }
      }
    }
    """
    variables = {"cursor": cursor, "limit": page_size}

    data = response.json()["data"]["items"]

    for edge in data["edges"]:
        yield edge["node"]

    page_info = data["pageInfo"]
    if not page_info["hasNextPage"]:
        break

    cursor = page_info["endCursor"]
```

## Best Practices

1. **Always log page numbers** - Helps debugging and monitoring
2. **Use exponential backoff** - `2**attempt` for retry delays
3. **Respect rate limits** - Check `Retry-After` header
4. **Validate cursor changes** - Prevent infinite loops
5. **Log total records** - Track extraction progress
6. **Handle empty pages** - First page might be empty
7. **Set timeouts** - Prevent hanging requests
8. **Mask secrets in logs** - Use `# pragma: allowlist secret` in tests

## Next Steps

- Copy this pattern into your driver's extract() method
- Adjust field names based on your API documentation
- Add rate limiting if API has limits (check docs for headers)
- Test with mock data (multiple pages, empty pages, errors)
- Run tests: `cd testing_env && python -m pytest ../tests/drivers/ -v -k cursor`

## Related Recipes

- **rest-api-extractor.md** - Complete REST API extractor template
- **error-handling.md** - Robust error handling patterns
- **rate-limiting.md** - Advanced rate limiting strategies
