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

"""Supabase data writer for loading operations."""

from datetime import datetime
from decimal import Decimal
import logging
from typing import Any

import numpy as np
import pandas as pd

from ...core.interfaces import ILoader
from .client import SupabaseClient

logger = logging.getLogger(__name__)


class SupabaseWriter(ILoader):
    """Supabase writer for data loading operations."""

    def __init__(self, config: dict[str, Any]):
        """Initialize Supabase writer.

        Args:
            config: Connection configuration with additional keys:
                - batch_size: Number of rows per batch (default: 1000)
                - mode: Default write mode (append/replace/upsert)
                - conflict_keys: Default conflict resolution keys
                - auto_create_table: Create table if it doesn't exist (default: False)
        """
        self.config = config
        self.base_client = SupabaseClient(config)
        self.client = None
        self._initialized = False

        # Writer-specific config
        self.batch_size = config.get("batch_size", 100)
        self.write_mode = config.get("write_mode", "append")
        self.primary_key = config.get("primary_key", [])
        self.create_if_missing = config.get("create_if_missing", False)

    def _serialize_data(self, data: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Convert pandas/numpy types to JSON-serializable types.

        Args:
            data: List of dictionaries containing data

        Returns:
            List of dictionaries with serialized data
        """
        serialized_data = []

        for record in data:
            serialized_record = {}
            for key, value in record.items():
                # Handle pandas Timestamp and numpy datetime64
                if pd.isna(value):
                    serialized_record[key] = None
                elif isinstance(value, pd.Timestamp | np.datetime64):
                    # Convert to ISO format string
                    if pd.isna(value):
                        serialized_record[key] = None
                    else:
                        serialized_record[key] = pd.Timestamp(value).isoformat()
                elif isinstance(value, datetime):
                    serialized_record[key] = value.isoformat()
                elif isinstance(value, np.integer | np.int64 | np.int32):
                    serialized_record[key] = int(value)
                elif isinstance(value, np.floating | np.float64 | np.float32 | Decimal):
                    serialized_record[key] = float(value)
                elif isinstance(value, np.bool_):
                    serialized_record[key] = bool(value)
                else:
                    serialized_record[key] = value

            serialized_data.append(serialized_record)

        return serialized_data

    def _mysql_to_postgres_type(self, mysql_type: str, value: Any = None) -> str:
        """Map MySQL types to PostgreSQL types.

        Args:
            mysql_type: MySQL type name (optional, inferred if not provided)
            value: Sample value to infer type from

        Returns:
            PostgreSQL type string
        """
        # Type mapping MySQL -> PostgreSQL
        type_map = {
            # Integer types
            "TINYINT": "SMALLINT",  # MySQL TINYINT(1) -> BOOLEAN handled separately
            "SMALLINT": "SMALLINT",
            "MEDIUMINT": "INTEGER",
            "INT": "INTEGER",
            "INTEGER": "INTEGER",
            "BIGINT": "BIGINT",
            # Decimal types
            "DECIMAL": "NUMERIC",
            "NUMERIC": "NUMERIC",
            "FLOAT": "REAL",
            "DOUBLE": "DOUBLE PRECISION",
            # Date/Time types
            "DATE": "DATE",
            "TIME": "TIME",
            "DATETIME": "TIMESTAMP",
            "TIMESTAMP": "TIMESTAMPTZ",
            "YEAR": "SMALLINT",
            # String types
            "CHAR": "CHAR",
            "VARCHAR": "VARCHAR",
            "TEXT": "TEXT",
            "TINYTEXT": "TEXT",
            "MEDIUMTEXT": "TEXT",
            "LONGTEXT": "TEXT",
            # Binary types
            "BINARY": "BYTEA",
            "VARBINARY": "BYTEA",
            "BLOB": "BYTEA",
            "TINYBLOB": "BYTEA",
            "MEDIUMBLOB": "BYTEA",
            "LONGBLOB": "BYTEA",
            # JSON
            "JSON": "JSONB",
        }

        # If we have a MySQL type string, use it
        if mysql_type:
            mysql_upper = mysql_type.upper().split("(")[0]  # Remove size specifier
            if mysql_upper in type_map:
                # Special case: TINYINT(1) is typically boolean
                if mysql_upper == "TINYINT" and "(1)" in mysql_type.upper():
                    return "BOOLEAN"
                return type_map[mysql_upper]

        # Fallback to inference from value
        return self._infer_sql_type(value)

    def _infer_sql_type(self, value: Any) -> str:
        """Infer PostgreSQL type from a Python value.

        Args:
            value: Sample value to infer type from

        Returns:
            PostgreSQL type string
        """
        if value is None or pd.isna(value):
            return "TEXT"  # Default for null values
        elif isinstance(value, bool) or (isinstance(value, int | np.integer) and value in (0, 1)):
            return "BOOLEAN"
        elif isinstance(value, int | np.integer):
            # Choose appropriate integer type based on value
            if -32768 <= value <= 32767:
                return "SMALLINT"
            elif -2147483648 <= value <= 2147483647:
                return "INTEGER"
            else:
                return "BIGINT"
        elif isinstance(value, float | np.floating | Decimal):
            return "DOUBLE PRECISION"
        elif isinstance(value, datetime | pd.Timestamp | np.datetime64):
            return "TIMESTAMPTZ"
        elif isinstance(value, str):
            # Use TEXT for strings, which is more flexible than VARCHAR
            return "TEXT"
        else:
            return "TEXT"  # Default fallback

    def _infer_table_schema(self, data: list[dict[str, Any]]) -> dict[str, str]:
        """Infer table schema from sample data.

        Args:
            data: List of dictionaries containing sample data

        Returns:
            Dictionary mapping column names to SQL types
        """
        if not data:
            return {}

        schema = {}

        # Sample the first few records to infer types
        sample_size = min(10, len(data))
        sample_records = data[:sample_size]

        # Get all column names from all records
        all_columns = set()
        for record in sample_records:
            all_columns.update(record.keys())

        # Infer type for each column
        for column in all_columns:
            column_types = []

            # Look at non-null values to infer type
            for record in sample_records:
                if column in record and record[column] is not None and not pd.isna(record[column]):
                    column_types.append(self._infer_sql_type(record[column]))

            if column_types:
                # Use the most common type, or the first one if all are different
                from collections import Counter

                type_counts = Counter(column_types)
                schema[column] = type_counts.most_common(1)[0][0]
            else:
                schema[column] = "TEXT"  # Default for all-null columns

        return schema

    async def _table_exists(self, table_name: str) -> bool:
        """Check if a table exists in Supabase.

        Args:
            table_name: Name of the table to check

        Returns:
            True if table exists
        """
        try:
            import asyncio  # noqa: PLC0415  # Lazy import for async operations

            # Try to query the table with limit 0 to check existence
            await asyncio.to_thread(lambda: self.client.table(table_name).select("*").limit(0).execute())
            return True
        except Exception as e:
            # If we get a "table not found" error, the table doesn't exist
            if "PGRST205" in str(e) or "not found" in str(e).lower():
                return False
            # For other errors, re-raise
            raise

    async def _create_table_if_not_exists(self, table_name: str, data: list[dict[str, Any]]) -> bool:
        """Create table if it doesn't exist and auto_create_table is enabled.

        Args:
            table_name: Name of the table to create
            data: Sample data to infer schema from

        Returns:
            True if table was created or already exists
        """
        if not self.create_if_missing:
            return False

        # Check if table already exists
        if await self._table_exists(table_name):
            return True

        # Infer schema from data
        schema = self._infer_table_schema(data)
        if not schema:
            logger.warning(f"Cannot infer schema for table {table_name} - no data provided")
            return False

        # Build CREATE TABLE SQL
        column_definitions = []
        for column_name, sql_type in schema.items():
            # Escape column names with double quotes for PostgreSQL
            column_definitions.append(f'"{column_name}" {sql_type}')

        columns_part = ",\n  ".join(column_definitions)
        create_sql = f'CREATE TABLE "{table_name}" (\n  {columns_part}\n);'

        # Since we can't directly create tables via Supabase client,
        # we'll log the SQL and let the user create it manually
        logger.warning(f"Table '{table_name}' does not exist")
        logger.info("AUTO-CREATE TABLE ENABLED: Please create the table manually using this SQL:")
        logger.info("=" * 60)
        logger.info(create_sql)
        logger.info("=" * 60)
        logger.info("You can run this SQL in your Supabase SQL Editor at:")
        logger.info("https://supabase.com/dashboard/project/YOUR_PROJECT_ID/sql")
        logger.info(f"Inferred schema: {schema}")

        return False

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

    async def insert_data(self, table_name: str, data: list[dict[str, Any]]) -> bool:
        """Insert data into a table.

        Args:
            table_name: Name of the table
            data: List of dictionaries to insert

        Returns:
            True if successful
        """
        if not self._initialized:
            await self.connect()

        try:
            # Serialize data to handle pandas/numpy types
            serialized_data = self._serialize_data(data)

            # Try to create table if it doesn't exist and auto_create_table is enabled
            if self.create_if_missing:
                await self._create_table_if_not_exists(table_name, serialized_data)

            # Process in batches for large datasets
            import asyncio  # noqa: PLC0415  # Lazy import for async operations

            for i in range(0, len(serialized_data), self.batch_size):
                batch = serialized_data[i : i + self.batch_size]
                # Execute sync Supabase call in thread pool (bind batch variable to avoid B023)
                await asyncio.to_thread(lambda b=batch: self.client.table(table_name).insert(b).execute())
                logger.debug(f"Inserted batch {i // self.batch_size + 1} ({len(batch)} rows)")

            logger.info(f"Successfully inserted {len(data)} rows into {table_name}")
            return True

        except Exception as e:
            # Check if it's a "table not found" error and create_if_missing is enabled
            if "PGRST205" in str(e) and self.create_if_missing:
                logger.error(f"Failed to insert data into {table_name}: {e}")
                logger.info(
                    "Table creation was attempted but failed. Please create the table manually using the SQL provided above."
                )
            else:
                logger.error(f"Failed to insert data into {table_name}: {e}")
            raise

    async def upsert_data(
        self, table_name: str, data: list[dict[str, Any]], primary_key: str | list[str] = None
    ) -> bool:
        """Upsert data (insert or update on conflict).

        Args:
            table_name: Name of the table
            data: List of dictionaries to upsert
            primary_key: Column(s) for conflict resolution (required for upsert)

        Returns:
            True if successful

        Raises:
            ValueError: If primary_key not specified for upsert operation
        """
        if not self._initialized:
            await self.connect()

        primary_key = primary_key or self.primary_key

        # Validate primary_key is provided for upsert
        if not primary_key:
            raise ValueError(
                "primary_key must be specified for upsert operation. "
                "Specify the column(s) that uniquely identify each row."
            )

        # Normalize to list
        if isinstance(primary_key, str):
            primary_key = [primary_key]

        try:
            # Serialize data to handle pandas/numpy types
            serialized_data = self._serialize_data(data)

            # Try to create table if it doesn't exist and auto_create_table is enabled
            if self.create_if_missing:
                await self._create_table_if_not_exists(table_name, serialized_data)

            # Process in batches
            import asyncio  # noqa: PLC0415  # Lazy import for async operations

            for i in range(0, len(serialized_data), self.batch_size):
                batch = serialized_data[i : i + self.batch_size]

                # Supabase upsert handles conflicts based on table's primary key
                # Log which columns are being used for conflict resolution
                logger.debug(f"Upserting with primary_key: {primary_key}")
                # Execute sync Supabase call in thread pool (bind batch variable to avoid B023)
                await asyncio.to_thread(lambda b=batch: self.client.table(table_name).upsert(b).execute())
                logger.debug(f"Upserted batch {i // self.batch_size + 1} ({len(batch)} rows)")

            logger.info(f"Successfully upserted {len(data)} rows into {table_name}")
            return True

        except Exception as e:
            logger.error(f"Failed to upsert data into {table_name}: {e}")
            raise

    async def replace_table(self, table_name: str, data: list[dict[str, Any]]) -> bool:
        """Replace entire table contents.

        WARNING: This deletes all existing data!

        Args:
            table_name: Name of the table
            data: New data for the table

        Returns:
            True if successful
        """
        if not self._initialized:
            await self.connect()

        try:
            import asyncio  # noqa: PLC0415  # Lazy import for async operations

            # Delete all existing data (be very careful!)
            logger.warning(f"Deleting all data from {table_name}")
            # Trick to delete all rows (execute sync call in thread pool)
            await asyncio.to_thread(lambda: self.client.table(table_name).delete().neq("id", -999999).execute())

            # Insert new data
            await self.insert_data(table_name, data)

            logger.info(f"Successfully replaced {table_name} with {len(data)} rows")
            return True

        except Exception as e:
            logger.error(f"Failed to replace table {table_name}: {e}")
            raise

    async def update_data(self, table_name: str, updates: dict[str, Any], filters: dict[str, Any]) -> bool:
        """Update specific rows in a table.

        Args:
            table_name: Name of the table
            updates: Dictionary of column updates
            filters: Dictionary of filters to identify rows

        Returns:
            True if successful
        """
        if not self._initialized:
            await self.connect()

        try:
            import asyncio  # noqa: PLC0415  # Lazy import for async operations

            query = self.client.table(table_name).update(updates)

            # Apply filters
            for key, value in filters.items():
                query = query.eq(key, value)

            # Execute sync Supabase call in thread pool
            await asyncio.to_thread(query.execute)
            logger.info(f"Updated rows in {table_name} where {filters}")
            return True

        except Exception as e:
            logger.error(f"Failed to update data in {table_name}: {e}")
            raise

    async def delete_data(self, table_name: str, filters: dict[str, Any]) -> bool:
        """Delete specific rows from a table.

        Args:
            table_name: Name of the table
            filters: Dictionary of filters to identify rows

        Returns:
            True if successful
        """
        if not self._initialized:
            await self.connect()

        try:
            import asyncio  # noqa: PLC0415  # Lazy import for async operations

            query = self.client.table(table_name).delete()

            # Apply filters
            for key, value in filters.items():
                query = query.eq(key, value)

            # Execute sync Supabase call in thread pool
            await asyncio.to_thread(query.execute)
            logger.info(f"Deleted rows from {table_name} where {filters}")
            return True

        except Exception as e:
            logger.error(f"Failed to delete data from {table_name}: {e}")
            raise

    async def load_dataframe(
        self,
        table_name: str,
        df: pd.DataFrame,
        write_mode: str = None,
        primary_key: str | list[str] = None,
    ) -> bool:
        """Load a pandas DataFrame into a Supabase table.

        Args:
            table_name: Name of the table
            df: DataFrame to load
            write_mode: "append", "replace", or "upsert" (default: use config)
            primary_key: Column(s) for upsert conflict resolution

        Returns:
            True if successful
        """
        if not self._initialized:
            await self.connect()

        write_mode = write_mode or self.write_mode

        try:
            # Convert DataFrame to list of dicts
            data = df.to_dict("records")

            if write_mode == "replace":
                return await self.replace_table(table_name, data)
            elif write_mode == "upsert":
                return await self.upsert_data(table_name, data, primary_key)
            else:  # append
                return await self.insert_data(table_name, data)

        except Exception as e:
            logger.error(f"Failed to load DataFrame into {table_name}: {e}")
            raise

    async def create_table(self, table_name: str, schema: dict[str, str]) -> bool:
        """Create a new table with given schema.

        Note: This requires admin access or an RPC function in Supabase.

        Args:
            table_name: Name of the table to create
            schema: Column definitions

        Returns:
            True if successful
        """
        # Table creation typically requires admin access
        # or a custom RPC function in Supabase
        raise NotImplementedError(
            "Table creation requires admin access or custom RPC function. "
            "Please create tables through Supabase dashboard or SQL editor."
        )
