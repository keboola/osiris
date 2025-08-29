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
import os
from typing import Any, Dict, Optional

from supabase import Client, create_client

logger = logging.getLogger(__name__)


class SupabaseClient:
    """Shared Supabase client for auth, session, and retries."""

    def __init__(self, config: Dict[str, Any]):
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
        self.client: Optional[Client] = None
        self._initialized = False

        # Get credentials from config or environment
        # Support both direct URL and project ID approaches
        self.url = config.get("url") or os.environ.get("SUPABASE_URL")
        if not self.url:
            project_id = config.get("project_id") or os.environ.get("SUPABASE_PROJECT_ID")
            if project_id:
                self.url = f"https://{project_id}.supabase.co"

        self.key = (
            config.get("key")
            or os.environ.get("SUPABASE_ANON_PUBLIC_KEY")
            or os.environ.get("SUPABASE_KEY")  # Legacy support
        )
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
            # Create Supabase client
            self.client = create_client(self.url, self.key)
            self._initialized = True
            logger.info("Connected to Supabase project")
            return self.client

        except Exception as e:
            logger.error(f"Failed to connect to Supabase: {e}")
            raise

    async def disconnect(self) -> None:
        """Close Supabase connection."""
        # Supabase client doesn't need explicit disconnect
        self.client = None
        self._initialized = False
        logger.debug("Supabase connection closed")

    def is_connected(self) -> bool:
        """Check if client is connected."""
        return self._initialized and self.client is not None
