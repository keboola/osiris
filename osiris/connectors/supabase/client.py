# # Copyright (c) 2025 Osiris Project
# #
# # Licensed under the Apache License, Version 2.0 (the "License");
# # you may not use this file except in compliance with the License.
# # You may obtain a copy of the License at
# #
# #     http://www.apache.org/licenses/LICENSE-2.0
# #
# # Unless required by applicable law or agreed to in writing, software
# # distributed under the License is distributed on an "AS IS" BASIS,
# # WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# # See the License for the specific language governing permissions and
# # limitations under the License.

"""Shared Supabase client for connection management."""

import logging
from typing import Any

from supabase import Client, create_client

logger = logging.getLogger(__name__)


class SupabaseClient:
    """Shared Supabase client for auth, session, and retries."""

    def __init__(self, config: dict[str, Any]):
        """Initialize Supabase client configuration.

        Args:
            config: Connection configuration with keys:
                - url: Supabase project URL (or SUPABASE_URL env var)
                - key: Supabase anon key (or SUPABASE_KEY env var)
                - schema: Database schema (default: public)
                - timeout: Request timeout in seconds (default: 30)
                - retries: Number of retries (default: 3)
        """
        self.config = config
        self.client: Client | None = None
        self._initialized = False

        # Get credentials from config only (no ENV fallback for runtime)
        # Support both direct URL and project ID approaches
        self.url = config.get("url")
        if not self.url:
            project_id = config.get("project_id")
            if project_id:
                self.url = f"https://{project_id}.supabase.co"

        # Support various key field names for compatibility
        self.key = config.get("service_role_key") or config.get("anon_key") or config.get("key")
        self.schema = config.get("schema", "public")
        self.timeout = config.get("timeout", 30)
        self.retries = config.get("retries", 3)

        if not self.url or not self.key:
            raise ValueError("Supabase URL and key are required (config or env vars)")

    async def connect(self) -> Client:
        """Connect to Supabase and return client."""
        if self._initialized and self.client:
            return self.client

        try:
            # Create Supabase client in thread pool (sync SDK operation)
            import asyncio  # noqa: PLC0415  # Lazy import for async operations

            self.client = await asyncio.to_thread(create_client, self.url, self.key)
            self._initialized = True
            logger.info("Connected to Supabase project")
            return self.client

        except Exception as e:
            logger.error(f"Failed to connect to Supabase: {e}")
            raise

    def connect_sync(self) -> Client:
        """Synchronous wrapper for async connect().

        Returns:
            Connected Supabase client

        Raises:
            RuntimeError: If called from within an async context
        """
        import asyncio  # noqa: PLC0415

        try:
            # Try to get the running loop
            try:
                asyncio.get_running_loop()
                # We're in an async context - this shouldn't happen in normal usage
                raise RuntimeError("connect_sync() called from async context. Use 'await connect()' instead.")
            except RuntimeError:
                # No running loop - good, we can create one
                pass

            # Run the async connect in a new event loop
            return asyncio.run(self.connect())

        except Exception as e:
            logger.error(f"Failed to connect to Supabase (sync): {e}")
            raise

    def __enter__(self) -> Client:
        """Synchronous context manager entry.

        Returns:
            Connected Supabase client
        """
        return self.connect_sync()

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Synchronous context manager exit.

        Args:
            exc_type: Exception type if an exception occurred
            exc_val: Exception value if an exception occurred
            exc_tb: Exception traceback if an exception occurred
        """
        # Supabase client doesn't need explicit cleanup
        # Just clear the reference
        self.client = None
        self._initialized = False

    async def disconnect(self) -> None:
        """Close Supabase connection."""
        # Supabase client doesn't need explicit disconnect
        self.client = None
        self._initialized = False
        logger.debug("Supabase connection closed")

    async def __aenter__(self) -> Client:
        """Async context manager entry."""
        return await self.connect()

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        # Supabase client doesn't need explicit cleanup
        pass

    def is_connected(self) -> bool:
        """Check if client is connected."""
        return self._initialized and self.client is not None

    def doctor(self, connection: dict, timeout: float = 2.0) -> tuple[bool, dict]:
        """Health check for Supabase connection.

        Args:
            connection: Connection configuration dict
            timeout: Maximum time to wait for connection (seconds)

        Returns:
            Tuple of (ok: bool, details: dict) where details contains:
                - latency_ms: Connection latency in milliseconds
                - category: Error category (auth/network/permission/timeout/unknown)
                - message: Redacted error message
        """
        import time

        import requests

        start_time = time.time()

        try:
            # Get URL and key
            url = connection.get("url")
            if not url and connection.get("project_id"):
                url = f"https://{connection['project_id']}.supabase.co"

            key = connection.get("service_role_key") or connection.get("anon_key") or connection.get("key")

            if not url or not key:
                return False, {
                    "latency_ms": 0,
                    "category": "config",
                    "message": "Missing required URL or key",
                }

            # Try health endpoint first (public, fastest)
            health_url = f"{url}/auth/v1/health"

            try:
                response = requests.get(health_url, timeout=timeout)
                if response.status_code == 200:
                    latency_ms = (time.time() - start_time) * 1000
                    return True, {
                        "latency_ms": round(latency_ms, 2),
                        "message": "Connection successful",
                    }
            except requests.RequestException:
                pass  # Try fallback

            # Fallback: REST API base with auth
            try:
                rest_url = f"{url}/rest/v1/"
                headers = {"apikey": key, "Authorization": f"Bearer {key}"}
                response = requests.head(rest_url, headers=headers, timeout=timeout)
                if 200 <= response.status_code < 300:
                    latency_ms = (time.time() - start_time) * 1000
                    return True, {
                        "latency_ms": round(latency_ms, 2),
                        "message": "Connection successful",
                    }
                elif response.status_code == 401:
                    latency_ms = (time.time() - start_time) * 1000
                    return False, {
                        "latency_ms": round(latency_ms, 2),
                        "category": "auth",
                        "message": "Authentication failed",
                    }
                else:
                    latency_ms = (time.time() - start_time) * 1000
                    return False, {
                        "latency_ms": round(latency_ms, 2),
                        "category": "network",
                        "message": f"HTTP {response.status_code}",
                    }
            except requests.Timeout:
                latency_ms = (time.time() - start_time) * 1000
                return False, {
                    "latency_ms": round(latency_ms, 2),
                    "category": "timeout",
                    "message": "Connection timeout",
                }
            except requests.ConnectionError:
                latency_ms = (time.time() - start_time) * 1000
                return False, {
                    "latency_ms": round(latency_ms, 2),
                    "category": "network",
                    "message": "Cannot connect to server",
                }

        except Exception:
            latency_ms = (time.time() - start_time) * 1000
            return False, {
                "latency_ms": round(latency_ms, 2),
                "category": "unknown",
                "message": "Connection test failed",
            }
