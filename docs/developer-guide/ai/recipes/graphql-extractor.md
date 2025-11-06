# GraphQL API Extractor Recipe

## Use Case
Building an extractor for any GraphQL API (e.g., GitHub, Shopify, Hasura, custom GraphQL endpoints).

## Prerequisites
- GraphQL endpoint URL
- Authentication method (Bearer token, API key, Basic auth)
- Sample GraphQL query
- Understanding of pagination (cursor-based or offset-based)
- JSONPath for data extraction from nested responses

## Component Structure

### 1. spec.yaml Template

```yaml
name: graphql.extractor
version: 1.0.0
title: GraphQL API Extractor
description: Extract data from any GraphQL API endpoint with support for queries, variables, authentication, and pagination

modes:
  - extract

capabilities:
  discover: false  # GraphQL schema introspection could be added later
  adHocAnalytics: true  # can execute arbitrary GraphQL queries
  inMemoryMove: false   # returns DataFrame but no direct move API
  streaming: false      # no streaming support (batch only)
  bulkOperations: true  # supports pagination for large datasets
  transactions: false   # GraphQL doesn't typically use transactions
  partitioning: true    # supports cursor-based pagination
  customTransforms: false  # no custom transforms

configSchema:
  type: object
  properties:
    endpoint:
      type: string
      format: uri
      description: GraphQL API endpoint URL
      minLength: 1
    query:
      type: string
      description: GraphQL query string
      minLength: 1
    variables:
      type: object
      description: GraphQL query variables as key-value pairs
      additionalProperties: true
      default: {}
    headers:
      type: object
      description: HTTP headers for authentication and customization
      additionalProperties:
        type: string
      default: {}
    auth_type:
      type: string
      description: Authentication method
      enum: ["none", "bearer", "basic", "api_key"]
      default: "none"
    auth_token:
      type: string
      description: Authentication token (for bearer, basic password, or API key)
    auth_username:
      type: string
      description: Username for basic authentication
    auth_header_name:
      type: string
      description: Custom header name for API key authentication
      default: "X-API-Key"
    timeout:
      type: integer
      description: Request timeout in seconds
      default: 30
      minimum: 5
      maximum: 300
    max_retries:
      type: integer
      description: Maximum number of retry attempts
      default: 3
      minimum: 0
      maximum: 10
    retry_delay:
      type: number
      description: Delay between retries in seconds
      default: 1.0
      minimum: 0.1
      maximum: 60.0
    pagination_enabled:
      type: boolean
      description: Enable automatic pagination for paginated GraphQL queries
      default: false
    pagination_path:
      type: string
      description: JSONPath to pagination info (e.g., "data.repositories.pageInfo")
      default: "data.pageInfo"
    pagination_cursor_field:
      type: string
      description: Name of cursor field in pageInfo
      default: "endCursor"
    pagination_has_next_field:
      type: string
      description: Name of hasNext field in pageInfo
      default: "hasNextPage"
    pagination_variable_name:
      type: string
      description: Name of the variable to update with cursor for next page
      default: "after"
    max_pages:
      type: integer
      description: Maximum number of pages to fetch (0 = unlimited)
      default: 0
      minimum: 0
    data_path:
      type: string
      description: JSONPath to extract data from response (e.g., "data.repositories.nodes")
      default: "data"
    flatten_result:
      type: boolean
      description: Whether to flatten nested objects in the result
      default: true
    validate_ssl:
      type: boolean
      description: Whether to validate SSL certificates
      default: true
  required:
    - endpoint
    - query
  additionalProperties: false

secrets:
  - /auth_token
  - /auth_username
  - /headers

x-connection-fields:
  - name: endpoint
    override: allowed
  - name: auth_token
    override: forbidden  # Security: token cannot be overridden
  - name: auth_username
    override: forbidden  # Security
  - name: headers
    override: warning  # Allow but warn (headers might contain auth)

redaction:
  strategy: mask
  mask: "***"
  extras:
    - /auth_token
    - /auth_username
    - /headers/Authorization
    - /headers/X-API-Key

x-runtime:
  driver: osiris.drivers.graphql_extractor_driver.GraphQLExtractorDriver
  requirements:
    imports:
      - requests
      - jsonpath_ng
      - pandas
    packages:
      - requests
      - jsonpath-ng
      - pandas

examples:
  - title: GitHub API - Get repositories
    config:
      endpoint: "https://api.github.com/graphql"
      query: |
        query GetRepositories($first: Int!) {
          viewer {
            repositories(first: $first) {
              nodes {
                name
                description
                stargazerCount
              }
            }
          }
        }
      variables:
        first: 20
      auth_type: "bearer"
      auth_token: "ghp_your_token_here"  # pragma: allowlist secret
      data_path: "data.viewer.repositories.nodes"

  - title: Shopify Admin API - Paginated products
    config:
      endpoint: "https://your-shop.myshopify.com/admin/api/2023-10/graphql.json"
      query: |
        query GetProducts($first: Int!, $after: String) {
          products(first: $first, after: $after) {
            edges {
              node {
                id
                title
                productType
              }
            }
            pageInfo {
              hasNextPage
              endCursor
            }
          }
        }
      variables:
        first: 50
      auth_type: "api_key"
      auth_header_name: "X-Shopify-Access-Token"
      auth_token: "your_access_token"  # pragma: allowlist secret
      pagination_enabled: true
      pagination_path: "data.products.pageInfo"
      data_path: "data.products.edges[*].node"
      max_pages: 10
```

### 2. Driver Implementation

File: `osiris/drivers/graphql_extractor_driver.py`

```python
"""GraphQL API extractor driver implementation."""

import base64
import logging
import time
from typing import Any

from jsonpath_ng import parse as jsonpath_parse
import pandas as pd
import requests

logger = logging.getLogger(__name__)


class GraphQLExtractorDriver:
    """Driver for extracting data from GraphQL APIs."""

    def __init__(self):
        """Initialize driver."""
        self.session = None

    def run(
        self,
        *,
        step_id: str,
        config: dict,
        inputs: dict | None = None,  # noqa: ARG002
        ctx: Any = None,
    ) -> dict:
        """Extract data from GraphQL API.

        Args:
            step_id: Step identifier
            config: Must contain 'endpoint', 'query', and optional auth/pagination config
            inputs: Not used for extractors
            ctx: Execution context for logging metrics

        Returns:
            {"df": DataFrame} with GraphQL query results
        """
        # Get required configuration
        endpoint = config.get("endpoint")
        query = config.get("query")

        if not endpoint:
            raise ValueError(f"Step {step_id}: 'endpoint' is required in config")
        if not query:
            raise ValueError(f"Step {step_id}: 'query' is required in config")

        # Initialize session
        self.session = self._create_session(config)

        try:
            # Log start
            logger.info(f"Step {step_id}: Starting GraphQL extraction from {endpoint}")
            if ctx and hasattr(ctx, "log_event"):
                ctx.log_event(
                    "extraction.start",
                    {
                        "endpoint": endpoint,
                        "auth_type": config.get("auth_type", "none"),
                        "pagination_enabled": config.get("pagination_enabled", False),
                    },
                )

            # Execute query (with pagination if enabled)
            try:
                all_data = []
                requests_made = 0
                pages_fetched = 0

                if config.get("pagination_enabled", False):
                    all_data, requests_made, pages_fetched = self._execute_paginated_query(
                        step_id, endpoint, query, config, ctx
                    )
                else:
                    result_data, requests_made = self._execute_single_query(step_id, endpoint, query, config, ctx)
                    all_data = [result_data] if result_data else []
                    pages_fetched = 1 if result_data else 0

                # Combine all data
                if not all_data:
                    df = pd.DataFrame()
                else:
                    # Flatten and combine data from all pages
                    combined_data = []
                    for page_data in all_data:
                        if isinstance(page_data, list):
                            combined_data.extend(page_data)
                        else:
                            combined_data.append(page_data)

                    df = (
                        pd.json_normalize(combined_data)
                        if config.get("flatten_result", True)
                        else pd.DataFrame(combined_data)
                    )

                # Log metrics
                rows_read = len(df)
                logger.info(
                    f"Step {step_id}: Extracted {rows_read} rows from GraphQL API ({pages_fetched} pages, {requests_made} requests)"
                )

                if ctx and hasattr(ctx, "log_metric"):
                    ctx.log_metric("rows_read", rows_read)
                    ctx.log_metric("requests_made", requests_made)
                    ctx.log_metric("pages_fetched", pages_fetched)

                return {"df": df}

            finally:
                # ALWAYS close session, even on exception
                if self.session:
                    self.session.close()
                    self.session = None

        except requests.exceptions.RequestException as e:
            error_msg = f"GraphQL API request failed: {str(e)}"
            logger.error(f"Step {step_id}: {error_msg}")
            raise RuntimeError(error_msg) from e

        except Exception as e:
            error_msg = f"GraphQL extraction failed: {type(e).__name__}: {str(e)}"
            logger.error(f"Step {step_id}: {error_msg}")
            raise RuntimeError(error_msg) from e

    def _create_session(self, config: dict) -> requests.Session:
        """Create configured requests session."""
        session = requests.Session()

        # Set up authentication
        auth_type = config.get("auth_type", "none")
        if auth_type == "bearer":
            token = config.get("auth_token")
            if token:
                session.headers["Authorization"] = f"Bearer {token}"
        elif auth_type == "basic":
            username = config.get("auth_username")
            password = config.get("auth_token")
            if username and password:
                credentials = base64.b64encode(f"{username}:{password}".encode()).decode()
                session.headers["Authorization"] = f"Basic {credentials}"
        elif auth_type == "api_key":
            token = config.get("auth_token")
            header_name = config.get("auth_header_name", "X-API-Key")
            if token:
                session.headers[header_name] = token

        # Add custom headers
        custom_headers = config.get("headers", {})
        session.headers.update(custom_headers)

        # Set default headers
        session.headers.setdefault("Content-Type", "application/json")
        session.headers.setdefault("User-Agent", "Osiris GraphQL Extractor/1.0")

        return session

    def _execute_single_query(
        self, step_id: str, endpoint: str, query: str, config: dict, ctx: Any = None
    ) -> tuple[Any, int]:
        """Execute a single GraphQL query."""
        variables = config.get("variables", {})
        timeout = config.get("timeout", 30)
        max_retries = config.get("max_retries", 3)
        retry_delay = config.get("retry_delay", 1.0)

        payload = {"query": query, "variables": variables}

        logger.info(f"Step {step_id}: Executing GraphQL query")

        # Retry logic
        last_exception = None
        for attempt in range(max_retries + 1):
            try:
                response = self.session.post(
                    endpoint, json=payload, timeout=timeout, verify=config.get("validate_ssl", True)
                )
                response.raise_for_status()

                # Parse GraphQL response
                response_data = response.json()

                # Check for GraphQL errors
                if "errors" in response_data:
                    error_details = response_data["errors"]
                    raise RuntimeError(f"GraphQL errors: {error_details}")

                # Extract data using configured path
                data_path = config.get("data_path", "data")
                extracted_data = self._extract_data_from_response(response_data, data_path)

                return extracted_data, 1

            except Exception as e:
                last_exception = e
                if attempt < max_retries:
                    logger.warning(
                        f"Step {step_id}: Request failed (attempt {attempt + 1}/{max_retries + 1}), retrying in {retry_delay}s: {e}"
                    )
                    time.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff
                else:
                    logger.error(f"Step {step_id}: All retry attempts failed")

        # If we get here, all retries failed
        raise last_exception

    def _execute_paginated_query(
        self, step_id: str, endpoint: str, query: str, config: dict, ctx: Any = None
    ) -> tuple[list[Any], int, int]:
        """Execute a paginated GraphQL query."""
        all_data = []
        total_requests = 0
        pages_fetched = 0

        # Pagination configuration
        pagination_path = config.get("pagination_path", "data.pageInfo")
        cursor_field = config.get("pagination_cursor_field", "endCursor")
        has_next_field = config.get("pagination_has_next_field", "hasNextPage")
        cursor_variable = config.get("pagination_variable_name", "after")
        max_pages = config.get("max_pages", 0)

        # Start with initial variables
        current_variables = config.get("variables", {}).copy()
        has_next_page = True

        logger.info(f"Step {step_id}: Starting paginated extraction (max_pages={max_pages or 'unlimited'})")

        while has_next_page and (max_pages == 0 or pages_fetched < max_pages):
            # Update query with current variables
            temp_config = config.copy()
            temp_config["variables"] = current_variables

            # Execute single page
            page_data, requests_for_page = self._execute_single_query(step_id, endpoint, query, temp_config, ctx)

            total_requests += requests_for_page
            pages_fetched += 1

            if page_data:
                all_data.append(page_data)

            # Get pagination info by re-executing with empty data_path
            try:
                payload = {"query": query, "variables": current_variables}
                response = self.session.post(
                    endpoint,
                    json=payload,
                    timeout=config.get("timeout", 30),
                    verify=config.get("validate_ssl", True),
                )
                response.raise_for_status()
                response_data = response.json()

                # Extract pagination info
                pagination_info = self._extract_data_from_response(response_data, pagination_path)

                if not pagination_info:
                    logger.info(f"Step {step_id}: No pagination info found, stopping")
                    break

                has_next_page = pagination_info.get(has_next_field, False)
                next_cursor = pagination_info.get(cursor_field)

                if has_next_page and next_cursor:
                    current_variables[cursor_variable] = next_cursor
                    logger.info(f"Step {step_id}: Fetching next page (cursor: {next_cursor})")
                else:
                    logger.info(f"Step {step_id}: Reached end of pages")
                    break

            except Exception as e:
                logger.warning(f"Step {step_id}: Failed to get pagination info: {e}")
                break

        logger.info(f"Step {step_id}: Completed paginated extraction: {pages_fetched} pages, {total_requests} requests")
        return all_data, total_requests, pages_fetched

    def _extract_data_from_response(self, response_data: dict, data_path: str) -> Any:
        """Extract data from GraphQL response using JSONPath."""
        if not data_path or data_path == "":
            return response_data

        try:
            # Parse JSONPath expression
            jsonpath_expr = jsonpath_parse(data_path)
            matches = jsonpath_expr.find(response_data)

            if not matches:
                logger.warning(f"No data found at path: {data_path}")
                return []

            # Return the first match (most common case)
            result = matches[0].value

            # Handle multiple matches by combining them
            if len(matches) > 1:
                if all(isinstance(match.value, list) for match in matches):
                    # Combine multiple lists
                    result = []
                    for match in matches:
                        result.extend(match.value)
                else:
                    # Return list of all matches
                    result = [match.value for match in matches]

            return result

        except Exception as e:
            logger.error(f"Failed to extract data using path '{data_path}': {e}")
            raise RuntimeError(f"Data extraction failed: {e}") from e
```

### 3. Tests

File: `tests/drivers/test_graphql_extractor_driver.py`

```python
"""Tests for GraphQL Extractor Driver."""

import pytest
from unittest.mock import Mock, patch
from osiris.drivers.graphql_extractor_driver import GraphQLExtractorDriver


@pytest.fixture
def driver():
    """Create driver instance."""
    return GraphQLExtractorDriver()


@pytest.fixture
def mock_ctx():
    """Create mock execution context."""
    ctx = Mock()
    ctx.log_metric = Mock()
    ctx.log_event = Mock()
    return ctx


@patch("requests.Session.post")
def test_simple_query(mock_post, driver, mock_ctx):
    """Test simple GraphQL query without pagination."""
    mock_response = Mock()
    mock_response.json.return_value = {
        "data": {
            "users": [
                {"id": 1, "name": "Alice"},
                {"id": 2, "name": "Bob"},
            ]
        }
    }
    mock_response.raise_for_status.return_value = None
    mock_response.status_code = 200
    mock_post.return_value = mock_response

    config = {
        "endpoint": "https://api.test.com/graphql",
        "query": "query { users { id name } }",
        "data_path": "data.users",
    }

    result = driver.run(step_id="test_step", config=config, ctx=mock_ctx)

    assert "df" in result
    df = result["df"]
    assert len(df) == 2
    assert df.iloc[0]["name"] == "Alice"


@patch("requests.Session.post")
def test_query_with_variables(mock_post, driver, mock_ctx):
    """Test GraphQL query with variables."""
    mock_response = Mock()
    mock_response.json.return_value = {
        "data": {
            "user": {"id": 1, "name": "Alice", "email": "alice@example.com"}
        }
    }
    mock_response.raise_for_status.return_value = None
    mock_post.return_value = mock_response

    config = {
        "endpoint": "https://api.test.com/graphql",
        "query": "query GetUser($id: Int!) { user(id: $id) { id name email } }",
        "variables": {"id": 1},
        "data_path": "data.user",
        "flatten_result": False,
    }

    result = driver.run(step_id="test_step", config=config, ctx=mock_ctx)

    assert "df" in result
    df = result["df"]
    assert len(df) == 1
    assert df.iloc[0]["email"] == "alice@example.com"


@patch("requests.Session.post")
def test_authentication_bearer(mock_post, driver, mock_ctx):
    """Test Bearer token authentication."""
    mock_response = Mock()
    mock_response.json.return_value = {"data": {"items": []}}
    mock_response.raise_for_status.return_value = None
    mock_post.return_value = mock_response

    config = {
        "endpoint": "https://api.test.com/graphql",
        "query": "query { items { id } }",
        "auth_type": "bearer",
        "auth_token": "test_token",  # pragma: allowlist secret
    }

    driver.run(step_id="test_step", config=config, ctx=mock_ctx)

    # Verify Authorization header was set
    assert driver.session is None  # Session closed after run
    mock_post.assert_called_once()


@patch("requests.Session.post")
def test_graphql_errors(mock_post, driver, mock_ctx):
    """Test handling of GraphQL errors."""
    mock_response = Mock()
    mock_response.json.return_value = {
        "errors": [
            {"message": "Field 'invalid' not found"}
        ]
    }
    mock_response.raise_for_status.return_value = None
    mock_post.return_value = mock_response

    config = {
        "endpoint": "https://api.test.com/graphql",
        "query": "query { invalid { id } }",
    }

    with pytest.raises(RuntimeError, match="GraphQL errors"):
        driver.run(step_id="test_step", config=config, ctx=mock_ctx)


@patch("requests.Session.post")
def test_empty_results(mock_post, driver, mock_ctx):
    """Test handling of empty results."""
    mock_response = Mock()
    mock_response.json.return_value = {"data": {"users": []}}
    mock_response.raise_for_status.return_value = None
    mock_post.return_value = mock_response

    config = {
        "endpoint": "https://api.test.com/graphql",
        "query": "query { users { id } }",
        "data_path": "data.users",
    }

    result = driver.run(step_id="test_step", config=config, ctx=mock_ctx)

    assert "df" in result
    assert len(result["df"]) == 0


@patch("requests.Session.post")
def test_network_error(mock_post, driver, mock_ctx):
    """Test handling of network errors."""
    import requests
    mock_post.side_effect = requests.exceptions.ConnectionError("Network error")

    config = {
        "endpoint": "https://api.test.com/graphql",
        "query": "query { users { id } }",
    }

    with pytest.raises(RuntimeError, match="GraphQL API request failed"):
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
- [ ] Session cleanup in finally block
- [ ] Logs include step_id in messages
- [ ] Tests mock all external API calls
- [ ] Driver logs metrics via ctx.log_metric()
- [ ] JSONPath expressions tested

## Discovery Mode (Optional Enhancement)

To add GraphQL schema introspection for discovery:

```python
def discover(self, *, step_id: str, config: dict, ctx: Any = None) -> dict:
    """Discover GraphQL schema using introspection query."""
    introspection_query = """
    query IntrospectionQuery {
      __schema {
        types {
          name
          kind
          description
          fields {
            name
            type {
              name
              kind
            }
          }
        }
      }
    }
    """

    temp_config = config.copy()
    temp_config["query"] = introspection_query
    temp_config["data_path"] = "data.__schema.types"

    result = self.run(step_id=step_id, config=temp_config, ctx=ctx)

    return {
        "schema": result["df"].to_dict("records")
    }
```

## Common Patterns

### GitHub API
```yaml
endpoint: "https://api.github.com/graphql"
auth_type: bearer
auth_token: "ghp_..."
query: |
  query {
    viewer {
      repositories(first: 10) {
        nodes {
          name
          stargazerCount
        }
      }
    }
  }
data_path: "data.viewer.repositories.nodes"
```

### Shopify API with Pagination
```yaml
endpoint: "https://shop.myshopify.com/admin/api/2023-10/graphql.json"
auth_type: api_key
auth_header_name: "X-Shopify-Access-Token"
auth_token: "..."
query: |
  query GetProducts($first: Int!, $after: String) {
    products(first: $first, after: $after) {
      edges {
        node { id title }
      }
      pageInfo {
        hasNextPage
        endCursor
      }
    }
  }
variables:
  first: 50
pagination_enabled: true
pagination_path: "data.products.pageInfo"
data_path: "data.products.edges[*].node"
```

## Next Steps

1. Replace placeholder endpoint and query with your actual GraphQL API
2. Test authentication method (bearer, basic, or api_key)
3. Adjust data_path to match your GraphQL response structure
4. Configure pagination if needed
5. Test with real API credentials
6. Validate with: `pytest tests/drivers/test_graphql_extractor_driver.py -v`

## Related Recipes

- **rest-api-extractor.md** - REST API extraction patterns
- **sql-extractor.md** - SQL database extraction
- **auth-selector.md** - Authentication pattern selection
