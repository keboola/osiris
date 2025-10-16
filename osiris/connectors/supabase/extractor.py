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

"""Supabase data extractor for reading operations."""

import logging
from typing import Any

import pandas as pd

from ...core.interfaces import IExtractor, TableInfo
from .client import SupabaseClient

logger = logging.getLogger(__name__)


class SupabaseExtractor(IExtractor):
    """Supabase extractor for data discovery and extraction."""

    def __init__(self, config: dict[str, Any]):
        """Initialize Supabase extractor.

        Args:
            config: Connection configuration (passed to SupabaseClient)
        """
        self.config = config
        self.base_client = SupabaseClient(config)
        self.client = None
        self._initialized = False

    async def connect(self) -> None:
        """Establish connection to Supabase."""
        if self._initialized:
            return

        self.client = await self.base_client.connect()
        self._initialized = True

    async def disconnect(self) -> None:
        """Close Supabase connection."""
        await self.base_client.disconnect()
        self.client = None
        self._initialized = False

    async def list_tables(self) -> list[str]:
        """List all available tables.

        Note: Automatically discovers tables using one of:
        1. PostgreSQL information_schema (if pg_dsn provided)
        2. Custom RPC function in Supabase
        3. Configuration with known table names

        Returns:
            List of table names
        """
        if not self._initialized:
            await self.connect()

        # Option 1: Try PostgreSQL information_schema if pg_dsn is available
        pg_dsn = self.config.get("pg_dsn")
        if pg_dsn:
            try:
                import asyncio  # noqa: PLC0415  # Lazy import for async operations

                tables = await asyncio.to_thread(self._discover_tables_via_postgres, pg_dsn)
                if tables:
                    logger.info(f"Discovered {len(tables)} tables via PostgreSQL")
                    return tables
            except Exception as e:
                logger.debug(f"PostgreSQL table discovery failed: {e}")  # nosec B110

        # Option 2: Try custom RPC if available
        try:
            import asyncio  # noqa: PLC0415  # Lazy import for async operations

            # Execute sync Supabase call in thread pool
            response = await asyncio.to_thread(lambda: self.client.rpc("list_tables", {}).execute())
            if response.data:
                return [t["table_name"] for t in response.data]
        except Exception as e:
            logger.debug(f"RPC list_tables not available: {e}")  # nosec B110

        # Option 3: Use configured tables
        configured_tables = self.config.get("tables", [])
        if configured_tables:
            logger.info(f"Using configured tables: {configured_tables}")
            return configured_tables

        # Option 4: Fallback message
        logger.warning(
            "Cannot auto-discover tables. Either:\n"
            "1. Add 'pg_dsn' to connection config for automatic discovery\n"
            "2. Create an RPC function 'list_tables' in Supabase\n"
            "3. Provide 'tables' list in config"
        )
        return []

    def _discover_tables_via_postgres(self, pg_dsn: str) -> list[str]:
        """Discover tables using PostgreSQL information_schema.

        Args:
            pg_dsn: PostgreSQL connection string

        Returns:
            List of table names
        """
        try:
            import psycopg2  # noqa: PLC0415  # Lazy import for PostgreSQL

            # Connect to PostgreSQL
            conn = psycopg2.connect(pg_dsn)
            cursor = conn.cursor()

            # Query information_schema for tables in public schema
            schema = self.config.get("schema", "public")
            cursor.execute(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = %s
                AND table_type = 'BASE TABLE'
                ORDER BY table_name
                """,
                (schema,),
            )

            tables = [row[0] for row in cursor.fetchall()]

            cursor.close()
            conn.close()

            return tables

        except ImportError:
            logger.warning(
                "psycopg2 not installed - cannot use PostgreSQL discovery. Install with: pip install psycopg2-binary"
            )  # noqa: E501
            return []
        except Exception as e:
            logger.error(f"Failed to discover tables via PostgreSQL: {e}")
            return []

    async def get_table_info(self, table_name: str) -> TableInfo:
        """Get schema and sample data for a table.

        Args:
            table_name: Name of the table

        Returns:
            TableInfo with schema and sample data
        """
        if not self._initialized:
            await self.connect()

        try:
            import asyncio  # noqa: PLC0415  # Lazy import for async operations

            # Get sample data (run sync Supabase call in thread pool)
            response = await asyncio.to_thread(lambda: self.client.table(table_name).select("*").limit(10).execute())
            sample_data = response.data

            # Get total count (with proper count query)
            count_response = await asyncio.to_thread(
                lambda: self.client.table(table_name).select("*", count="exact", head=True).execute()
            )
            row_count = count_response.count if hasattr(count_response, "count") else len(sample_data)

            # Infer schema from sample data
            columns = []
            column_types = {}
            primary_keys = []

            if sample_data:
                # Get column names from first row
                first_row = sample_data[0]
                columns = list(first_row.keys())

                # Infer types from Python types
                for col in columns:
                    value = first_row.get(col)
                    column_types[col] = self._infer_type(value)

                # Assume 'id' is primary key (Supabase convention)
                if "id" in columns:
                    primary_keys = ["id"]

            return TableInfo(
                name=table_name,
                columns=columns,
                column_types=column_types,
                primary_keys=primary_keys,
                row_count=row_count,
                sample_data=sample_data,
            )

        except Exception as e:
            logger.error(f"Failed to get info for table {table_name}: {e}")
            raise

    async def execute_query(self, _query: str) -> pd.DataFrame:
        """Execute a query using Supabase's query builder.

        Note: This is limited to Supabase's query API.
        For raw SQL, create an RPC function in Supabase.

        Args:
            query: Not used directly - would need parsing

        Returns:
            Query results as DataFrame
        """
        if not self._initialized:
            await self.connect()

        # For MVP, we don't support raw SQL
        # Users should use sample_table or get_table_info
        raise NotImplementedError(
            "Raw SQL queries require RPC functions in Supabase. " "Use sample_table() or get_table_info() instead."
        )

    async def sample_table(self, table_name: str, size: int = 10) -> pd.DataFrame:
        """Get sample data from a table.

        Args:
            table_name: Name of the table
            size: Number of rows to sample

        Returns:
            Sample data as DataFrame
        """
        if not self._initialized:
            await self.connect()

        try:
            import asyncio  # noqa: PLC0415  # Lazy import for async operations

            # Execute sync Supabase call in thread pool
            response = await asyncio.to_thread(lambda: self.client.table(table_name).select("*").limit(size).execute())
            return pd.DataFrame(response.data)
        except Exception as e:
            logger.error(f"Failed to sample table {table_name}: {e}")
            raise

    async def get_filtered_data(self, table_name: str, filters: dict[str, Any], limit: int = None) -> pd.DataFrame:
        """Get filtered data from a table.

        Args:
            table_name: Name of the table
            filters: Dictionary of column filters
            limit: Maximum rows to return

        Returns:
            Filtered data as DataFrame
        """
        if not self._initialized:
            await self.connect()

        try:
            import asyncio  # noqa: PLC0415  # Lazy import for async operations

            query = self.client.table(table_name).select("*")

            # Apply filters
            for key, value in filters.items():
                query = query.eq(key, value)

            # Apply limit if specified
            if limit:
                query = query.limit(limit)

            # Execute sync Supabase call in thread pool
            response = await asyncio.to_thread(query.execute)
            return pd.DataFrame(response.data)

        except Exception as e:
            logger.error(f"Failed to get filtered data from {table_name}: {e}")
            raise

    def _infer_type(self, value: Any) -> str:
        """Infer SQL type from Python value."""
        if value is None:
            return "unknown"
        elif isinstance(value, bool):
            return "boolean"
        elif isinstance(value, int):
            return "integer"
        elif isinstance(value, float):
            return "float"
        elif isinstance(value, str):
            return "text"
        elif isinstance(value, dict):
            return "jsonb"
        elif isinstance(value, list):
            return "array"
        else:
            return type(value).__name__
