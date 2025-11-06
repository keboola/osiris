# Pagination Selector

## Decision Tree

**START: How does the API paginate results?**

### Question 1: Does API use page number + page size?

**YES** → Offset pagination
- **Parameters**: `page=1`, `per_page=100` (or `limit`/`offset`)
- **Reference**: `recipes/pagination-offset.md`
- **Examples**: `/users?page=2&per_page=50`

**Pros**:
- Simple to understand and implement
- Supports random access to pages
- Easy to calculate total pages

**Cons**:
- Performance degrades with deep pages
- Issues with concurrent insertions/deletions
- Database must scan/skip rows

**NO** → Continue to Question 2

---

### Question 2: Does API use cursor/token from previous response?

**YES** → Cursor pagination
- **Parameters**: `cursor=abc123`, `next_token=xyz`, `after=id:123`
- **Reference**: `recipes/pagination-cursor.md`
- **Example**: GraphQL extractor uses cursor

**Common patterns**:
```json
{
  "data": [...],
  "pagination": {
    "next_cursor": "eyJpZCI6MTIzfQ==",
    "has_more": true
  }
}
```

**Pros**:
- Consistent performance regardless of depth
- Handles insertions/deletions gracefully
- Efficient database queries

**Cons**:
- No random access to pages
- Cannot jump to specific page
- Cursor must be opaque/encoded

**NO** → Continue to Question 3

---

### Question 3: Does API use "next" URL in response?

**YES** → Link-based pagination
- **Header**: `Link: <url>; rel="next"`
- **Body**: `{"next": "https://api.example.com/users?page=2"}`
- **Pattern**: Follow URL until null/empty

**Header example**:
```
Link: <https://api.example.com/users?page=2>; rel="next",
      <https://api.example.com/users?page=10>; rel="last"
```

**Body example**:
```json
{
  "data": [...],
  "links": {
    "next": "https://api.example.com/users?cursor=abc",
    "prev": "https://api.example.com/users?cursor=xyz"
  }
}
```

**Reference**: `recipes/pagination-link.md`

**Pros**:
- API controls pagination logic
- No need to construct URLs
- Works with any pagination strategy

**Cons**:
- Must parse headers or response
- URL structure may change
- No page count information

**NO** → Continue to Question 4

---

### Question 4: Does API return all results at once?

**YES** → No pagination needed
- **Pattern**: Single request returns all data
- **Consideration**: Ensure data fits in memory

**Use case**:
- Small datasets (< 1000 records)
- Lookup tables
- Configuration data

**Implementation**:
```python
response = requests.get(url)
data = response.json()
return data["items"]
```

**NO** → Check API documentation (unclear pagination pattern)

---

## Implementation Patterns

### Offset Pagination

```python
def extract_with_offset(url: str, per_page: int = 100):
    """Extract data using page number pagination."""
    page = 1

    while True:
        response = requests.get(
            url,
            params={"page": page, "per_page": per_page}
        )
        data = response.json()

        if not data["items"]:
            break

        yield from data["items"]

        # Check if we've reached the end
        if len(data["items"]) < per_page:
            break

        page += 1
```

**Deterministic variant** (required for discovery mode):
```python
def extract_with_offset_deterministic(url: str, order_by: str = "id"):
    """Extract with stable ordering for discovery."""
    params = {
        "page": 1,
        "per_page": 100,
        "sort": order_by,
        "order": "asc"
    }

    while True:
        response = requests.get(url, params=params)
        data = response.json()

        if not data["items"]:
            break

        yield from data["items"]
        params["page"] += 1
```

---

### Cursor Pagination

```python
def extract_with_cursor(url: str):
    """Extract data using cursor-based pagination."""
    cursor = None

    while True:
        params = {}
        if cursor:
            params["cursor"] = cursor

        response = requests.get(url, params=params)
        data = response.json()

        if not data["items"]:
            break

        yield from data["items"]

        # Get next cursor
        cursor = data.get("pagination", {}).get("next_cursor")
        if not cursor:
            break
```

**GraphQL variant**:
```python
def extract_with_graphql_cursor(endpoint: str, query: str):
    """Extract using GraphQL cursor pagination."""
    cursor = None

    while True:
        variables = {"cursor": cursor} if cursor else {}

        response = requests.post(
            endpoint,
            json={"query": query, "variables": variables}
        )
        data = response.json()

        edges = data["data"]["users"]["edges"]
        if not edges:
            break

        for edge in edges:
            yield edge["node"]

        page_info = data["data"]["users"]["pageInfo"]
        if not page_info["hasNextPage"]:
            break

        cursor = page_info["endCursor"]
```

---

### Link-based Pagination

```python
def extract_with_links(url: str):
    """Extract data following 'next' links."""
    next_url = url

    while next_url:
        response = requests.get(next_url)
        data = response.json()

        yield from data["items"]

        # Get next URL from response body
        next_url = data.get("links", {}).get("next")
```

**Header-based variant**:
```python
import requests

def extract_with_link_header(url: str):
    """Extract data using Link header."""
    next_url = url

    while next_url:
        response = requests.get(next_url)
        data = response.json()

        yield from data["items"]

        # Parse Link header
        link_header = response.headers.get("Link", "")
        next_url = parse_next_link(link_header)

def parse_next_link(link_header: str) -> str:
    """Parse 'next' URL from Link header."""
    import re
    match = re.search(r'<([^>]+)>;\s*rel="next"', link_header)
    return match.group(1) if match else None
```

---

## Determinism Requirements

For discovery mode (DISC-001), pagination must be deterministic:

### Offset Pagination
```python
# REQUIRED: Add stable sort order
params = {
    "page": page,
    "per_page": 100,
    "sort": "id",      # Stable field
    "order": "asc"     # Consistent direction
}
```

### Cursor Pagination
- API usually handles stability
- Cursor encodes position
- No additional sorting needed

### Link-based Pagination
- Follow order provided by API
- Trust API's pagination logic
- Document expected behavior

---

## Error Handling

### Rate Limiting

```python
import time

def extract_with_retry(url: str, max_retries: int = 3):
    """Extract with retry logic for rate limits."""
    retries = 0

    while retries < max_retries:
        try:
            response = requests.get(url)

            if response.status_code == 429:
                # Rate limited
                retry_after = int(response.headers.get("Retry-After", 60))
                logger.warning(f"Rate limited, waiting {retry_after}s")
                time.sleep(retry_after)
                retries += 1
                continue

            response.raise_for_status()
            return response.json()

        except requests.RequestException as e:
            logger.error(f"Request failed: {e}")
            retries += 1
            time.sleep(2 ** retries)  # Exponential backoff

    raise Exception("Max retries exceeded")
```

### Empty Pages

```python
def handle_empty_pages(data: Dict[str, Any]) -> bool:
    """Check if page is truly empty vs. end of data."""
    items = data.get("items", [])

    # Empty items list
    if not items:
        return True

    # Check total count if available
    total = data.get("total", 0)
    if total == 0:
        return True

    return False
```

---

## Performance Optimization

### Parallel Pagination

```python
from concurrent.futures import ThreadPoolExecutor

def extract_parallel_pages(url: str, total_pages: int):
    """Extract multiple pages in parallel (offset pagination only)."""
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = []

        for page in range(1, total_pages + 1):
            future = executor.submit(fetch_page, url, page)
            futures.append(future)

        for future in futures:
            yield from future.result()

def fetch_page(url: str, page: int):
    """Fetch single page."""
    response = requests.get(url, params={"page": page, "per_page": 100})
    return response.json()["items"]
```

**Warning**: Only use for offset pagination where order doesn't matter!

---

## Testing Pagination

### Unit Tests

```python
def test_offset_pagination():
    """Test offset pagination logic."""
    # Mock responses
    responses = [
        {"items": [1, 2, 3], "total": 5},
        {"items": [4, 5], "total": 5},
        {"items": [], "total": 5}
    ]

    # Test pagination
    all_items = list(extract_with_offset_mock(responses))
    assert all_items == [1, 2, 3, 4, 5]

def test_cursor_pagination():
    """Test cursor pagination logic."""
    responses = [
        {"items": [1, 2], "cursor": "abc"},
        {"items": [3, 4], "cursor": "def"},
        {"items": [], "cursor": None}
    ]

    all_items = list(extract_with_cursor_mock(responses))
    assert all_items == [1, 2, 3, 4]
```

---

## Next Steps

After choosing pagination strategy:

1. **Implement pagination** in your driver
2. **Add determinism** (sort order for offset, stable cursors)
3. **Handle errors** (rate limits, empty pages, timeouts)
4. **Add logging** for debugging pagination issues
5. **Proceed to**: `recipes/rest-api-extractor.md` (full implementation)

---

## Quick Reference

| Type   | Parameters              | Pros                    | Cons                  | Use Case              |
|--------|-------------------------|-------------------------|-----------------------|-----------------------|
| Offset | page, per_page          | Simple, random access   | Performance degrades  | Small datasets        |
| Cursor | cursor, next_token      | Consistent performance  | No random access      | Large datasets        |
| Link   | Follow next URL         | API-controlled          | Parse headers/body    | Flexible APIs         |
| None   | Single request          | Simplest                | Memory limits         | Small static data     |

---

**Document Version**: 1.0
**Last Updated**: 2025-10-26
**Related**: `api-type-selector.md`, `auth-selector.md`, `../recipes/pagination-*.md`
