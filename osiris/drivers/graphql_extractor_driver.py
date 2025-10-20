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
            # Nested try block to ensure session cleanup even on exceptions
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

                if ctx and hasattr(ctx, "log_event"):
                    ctx.log_event(
                        "extraction.complete", {"rows": rows_read, "pages": pages_fetched, "requests": requests_made}
                    )

                return {"df": df}

            finally:
                # ALWAYS close session, even on exception
                if self.session:
                    self.session.close()
                    self.session = None

        except requests.exceptions.RequestException as e:
            error_msg = f"GraphQL API request failed: {str(e)}"
            logger.error(f"Step {step_id}: {error_msg}")
            if ctx and hasattr(ctx, "log_event"):
                ctx.log_event("extraction.error", {"error": error_msg})
            # Session already closed in inner finally block
            raise RuntimeError(error_msg) from e

        except Exception as e:
            error_msg = f"GraphQL extraction failed: {type(e).__name__}: {str(e)}"
            logger.error(f"Step {step_id}: {error_msg}")
            if ctx and hasattr(ctx, "log_event"):
                ctx.log_event("extraction.error", {"error": error_msg})
            # Session already closed in inner finally block
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
            password = config.get("auth_token")  # Using auth_token as password for basic auth
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
        if ctx and hasattr(ctx, "log_event"):
            ctx.log_event("extraction.query", {"variables": variables})

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

                if ctx and hasattr(ctx, "log_event"):
                    ctx.log_event(
                        "extraction.response",
                        {"status_code": response.status_code, "response_size": len(response.content)},
                    )

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
        max_pages = config.get("max_pages", 0)  # 0 means unlimited

        # Start with initial variables
        current_variables = config.get("variables", {}).copy()
        has_next_page = True

        logger.info(f"Step {step_id}: Starting paginated GraphQL extraction (max_pages={max_pages or 'unlimited'})")

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

            if ctx and hasattr(ctx, "log_event"):
                ctx.log_event(
                    "extraction.page",
                    {
                        "page": pages_fetched,
                        "cursor": current_variables.get(cursor_variable),
                        "data_count": len(page_data) if isinstance(page_data, list) else 1,
                    },
                )

            # Get pagination info for next page
            try:
                # Execute the query again to get the full response for pagination info
                temp_config_for_pagination = config.copy()
                temp_config_for_pagination["variables"] = current_variables
                temp_config_for_pagination["data_path"] = ""  # Get full response

                # Re-execute to get pagination info (this is a limitation - ideally we'd cache the response)
                payload = {"query": query, "variables": current_variables}

                response = self.session.post(
                    endpoint, json=payload, timeout=config.get("timeout", 30), verify=config.get("validate_ssl", True)
                )
                response.raise_for_status()
                response_data = response.json()

                # Extract pagination info
                pagination_info = self._extract_data_from_response(response_data, pagination_path)

                if not pagination_info:
                    logger.info(f"Step {step_id}: No pagination info found at path '{pagination_path}', stopping")
                    break

                has_next_page = pagination_info.get(has_next_field, False)
                next_cursor = pagination_info.get(cursor_field)

                if has_next_page and next_cursor:
                    current_variables[cursor_variable] = next_cursor
                    logger.info(f"Step {step_id}: Fetching next page with cursor: {next_cursor}")
                else:
                    logger.info(f"Step {step_id}: Reached end of pages (hasNext={has_next_page}, cursor={next_cursor})")
                    break

            except Exception as e:
                logger.warning(f"Step {step_id}: Failed to get pagination info, stopping pagination: {e}")
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

    def doctor(self, config: dict) -> dict:
        """Health check for GraphQL API connectivity."""
        results = {"status": "healthy", "checks": {}}

        endpoint = config.get("endpoint")
        if not endpoint:
            results["status"] = "unhealthy"
            results["checks"]["endpoint"] = "missing endpoint configuration"
            return results

        try:
            # Test basic connectivity with introspection query
            session = self._create_session(config)

            # Simple introspection query to test connection
            introspection_query = """
            query IntrospectionQuery {
              __schema {
                queryType {
                  name
                }
              }
            }
            """

            response = session.post(
                endpoint,
                json={"query": introspection_query},
                timeout=config.get("timeout", 30),
                verify=config.get("validate_ssl", True),
            )

            if response.status_code == 200:
                response_data = response.json()
                if "errors" in response_data:
                    results["checks"]["connection"] = f"GraphQL errors: {response_data['errors']}"
                    if any("introspection" in str(error).lower() for error in response_data["errors"]):
                        # Introspection might be disabled, but connection works
                        results["checks"]["connection"] = "passed (introspection disabled)"
                    else:
                        results["status"] = "unhealthy"
                else:
                    results["checks"]["connection"] = "passed"
            else:
                results["status"] = "unhealthy"
                results["checks"]["connection"] = f"HTTP {response.status_code}: {response.text}"

            session.close()

        except requests.exceptions.SSLError as e:
            results["status"] = "unhealthy"
            results["checks"]["connection"] = f"SSL error: {e}"
        except requests.exceptions.Timeout as e:
            results["status"] = "unhealthy"
            results["checks"]["connection"] = f"timeout: {e}"
        except requests.exceptions.ConnectionError as e:
            results["status"] = "unhealthy"
            results["checks"]["connection"] = f"connection error: {e}"
        except Exception as e:
            results["status"] = "unhealthy"
            results["checks"]["connection"] = f"unexpected error: {e}"

        # Check authentication if configured
        auth_type = config.get("auth_type", "none")
        if auth_type != "none":
            auth_token = config.get("auth_token")
            if not auth_token:
                results["status"] = "unhealthy"
                results["checks"]["authentication"] = f"missing auth_token for {auth_type} authentication"
            else:
                results["checks"]["authentication"] = f"{auth_type} authentication configured"

        return results
