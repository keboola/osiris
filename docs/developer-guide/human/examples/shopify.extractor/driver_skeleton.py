"""Shopify Extractor Driver - Reference Implementation.

This driver demonstrates best practices for building Osiris extractors:
- Connection resolution and validation
- Pagination and rate limiting
- Error handling and retries
- Metric emission
- Discovery mode
"""

import logging
import time
from typing import Any

import pandas as pd
import requests

logger = logging.getLogger(__name__)


class ShopifyExtractorDriver:
    """Extract data from Shopify Admin API."""

    # API rate limits (Shopify: 2 req/sec for standard tier)
    RATE_LIMIT_DELAY = 0.5  # seconds between requests

    def run(
        self,
        *,
        step_id: str,
        config: dict,
        inputs: dict | None = None,
        ctx: Any = None,
    ) -> dict:
        """Execute extraction from Shopify.

        Args:
            step_id: Step identifier
            config: Configuration with resolved_connection
            inputs: Not used for extractors
            ctx: Execution context for metrics

        Returns:
            {"df": pandas.DataFrame} with extracted data
        """
        # 1. Validate configuration
        resource = config.get("resource")
        if not resource:
            raise ValueError(f"Step {step_id}: 'resource' is required")

        conn_info = config.get("resolved_connection", {})
        if not conn_info:
            raise ValueError(f"Step {step_id}: 'resolved_connection' is required")

        # 2. Extract connection details
        shop_domain = conn_info.get("shop_domain")
        access_token = conn_info.get("access_token")
        api_version = conn_info.get("api_version", "2024-01")

        if not shop_domain or not access_token:
            raise ValueError(f"Step {step_id}: shop_domain and access_token required")

        # 3. Build API client
        client = ShopifyAPIClient(
            shop_domain=shop_domain,
            access_token=access_token,
            api_version=api_version,
            rate_limit_delay=self.RATE_LIMIT_DELAY,
        )

        try:
            # 4. Extract data with pagination
            logger.info(f"Step {step_id}: Extracting {resource} from {shop_domain}")

            all_records = []
            since_id = config.get("since_id", 0)
            limit = config.get("limit", 250)
            api_calls = 0

            while True:
                # Fetch page
                response = client.get_resource(resource, since_id=since_id, limit=limit)
                records = response.get(resource, [])

                if not records:
                    break

                all_records.extend(records)
                api_calls += 1

                # Update pagination cursor
                last_id = records[-1].get("id")
                if last_id:
                    since_id = last_id
                else:
                    break

                # Check if we got fewer than limit (last page)
                if len(records) < limit:
                    break

                logger.debug(f"Step {step_id}: Fetched page, total records: {len(all_records)}")

            # 5. Convert to DataFrame
            df = pd.DataFrame(all_records)

            # 6. Emit metrics
            rows_read = len(df)
            logger.info(f"Step {step_id}: Read {rows_read} rows in {api_calls} API calls")

            if ctx and hasattr(ctx, "log_metric"):
                ctx.log_metric("rows_read", rows_read, unit="rows", tags={"step": step_id})
                ctx.log_metric("api_calls_made", api_calls, unit="calls", tags={"step": step_id})

            # 7. Return output
            return {"df": df}

        except requests.exceptions.HTTPError as e:
            error_msg = f"Shopify API error: {e.response.status_code} - {e.response.text}"
            logger.error(f"Step {step_id}: {error_msg}")
            raise RuntimeError(error_msg) from e

        except Exception as e:
            error_msg = f"Extraction failed: {type(e).__name__}: {str(e)}"
            logger.error(f"Step {step_id}: {error_msg}")
            raise RuntimeError(error_msg) from e


class ShopifyAPIClient:
    """Shopify Admin API client with rate limiting."""

    def __init__(
        self,
        shop_domain: str,
        access_token: str,
        api_version: str = "2024-01",
        rate_limit_delay: float = 0.5,
    ):
        """Initialize Shopify API client.

        Args:
            shop_domain: Shopify store domain (e.g., "mystore.myshopify.com")
            access_token: Admin API access token
            api_version: API version (e.g., "2024-01")
            rate_limit_delay: Delay between requests in seconds
        """
        self.shop_domain = shop_domain
        self.access_token = access_token
        self.api_version = api_version
        self.rate_limit_delay = rate_limit_delay
        self.base_url = f"https://{shop_domain}/admin/api/{api_version}"
        self.last_request_time = 0

    def get_resource(self, resource: str, since_id: int = 0, limit: int = 250) -> dict:
        """Fetch resource from Shopify API.

        Args:
            resource: Resource type (customers, orders, products, etc.)
            since_id: Return results after this ID
            limit: Maximum results per page

        Returns:
            API response dict

        Raises:
            requests.HTTPError: On API errors
        """
        # TODO: Implement rate limiting
        self._respect_rate_limit()

        # TODO: Build request
        url = f"{self.base_url}/{resource}.json"
        params = {"limit": limit}
        if since_id > 0:
            params["since_id"] = since_id

        headers = {
            "X-Shopify-Access-Token": self.access_token,
            "Content-Type": "application/json",
        }

        # TODO: Make request with retry
        response = requests.get(url, params=params, headers=headers, timeout=30)
        response.raise_for_status()

        return response.json()

    def _respect_rate_limit(self) -> None:
        """Enforce rate limiting between API calls."""
        elapsed = time.time() - self.last_request_time
        if elapsed < self.rate_limit_delay:
            time.sleep(self.rate_limit_delay - elapsed)
        self.last_request_time = time.time()

    def discover_resources(self) -> list[dict]:
        """Discover available resources (for discovery mode).

        Returns:
            List of resource metadata dicts

        TODO: Implement discovery logic
        - Query metafields endpoint
        - List available resources
        - Get schema for each resource
        """
        raise NotImplementedError("Discovery mode not yet implemented")

    def doctor(self, timeout: float = 2.0) -> tuple[bool, dict]:
        """Test connection health.

        Args:
            timeout: Request timeout in seconds

        Returns:
            (ok, details) tuple
        """
        try:
            start = time.time()
            url = f"{self.base_url}/shop.json"
            headers = {"X-Shopify-Access-Token": self.access_token}

            response = requests.get(url, headers=headers, timeout=timeout)
            response.raise_for_status()

            latency = (time.time() - start) * 1000

            return True, {
                "latency_ms": latency,
                "category": "ok",
                "message": "Connection successful",
            }

        except requests.exceptions.Timeout:
            return False, {
                "latency_ms": None,
                "category": "timeout",
                "message": "Request timed out",
            }

        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 401:
                category = "auth"
                message = "Invalid access token"
            elif e.response.status_code == 403:
                category = "permission"
                message = "Insufficient permissions"
            else:
                category = "unknown"
                message = f"HTTP {e.response.status_code}"

            return False, {
                "latency_ms": None,
                "category": category,
                "message": message,
            }

        except requests.exceptions.ConnectionError as e:
            return False, {
                "latency_ms": None,
                "category": "network",
                "message": str(e),
            }


# TODO: Implement backoff/retry logic
# TODO: Add connection pooling
# TODO: Implement discovery mode
# TODO: Add support for GraphQL API (bulk operations)
# TODO: Handle Shopify API versioning
