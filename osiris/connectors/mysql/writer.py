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

"""MySQL writer for loading operations."""

import logging
from typing import Any

import pandas as pd
from sqlalchemy import text

from ...core.interfaces import ILoader
from .client import MySQLClient

logger = logging.getLogger(__name__)


class MySQLWriter(ILoader):
    """MySQL writer for data loading operations."""

    def __init__(self, config: dict[str, Any]):
        """Initialize MySQL writer.

        Args:
            config: Connection configuration with additional keys:
                - batch_size: Number of rows per batch (default: 1000)
                - mode: Default write mode (append/replace/upsert)
        """
        self.config = config
        self.base_client = MySQLClient(config)
        self.engine = None
        self._initialized = False

        # Writer-specific config
        self.batch_size = config.get("batch_size", 1000)
        self.default_mode = config.get("mode", "append")

    async def connect(self) -> None:
        """Establish connection to MySQL."""
        if self._initialized:
            return

        self.engine = await self.base_client.connect()
        self._initialized = True

    async def disconnect(self) -> None:
        """Close MySQL connection."""
        await self.base_client.disconnect()
        self.engine = None
        self._initialized = False

    async def insert_data(self, table_name: str, data: list[dict[str, Any]]) -> bool:
        """Insert data into a MySQL table.

        Args:
            table_name: Name of the table
            data: List of dictionaries to insert

        Returns:
            True if successful
        """
        if not self._initialized:
            await self.connect()

        if not data:
            logger.info("No data to insert")
            return True

        try:
            # Convert to DataFrame for easy bulk insertion
            df = pd.DataFrame(data)

            # Insert data using pandas to_sql
            df.to_sql(
                name=table_name,
                con=self.engine,
                if_exists="append",
                index=False,
                chunksize=self.batch_size,
            )

            logger.info(f"Successfully inserted {len(data)} rows into {table_name}")
            return True

        except Exception as e:
            logger.error(f"Failed to insert data into {table_name}: {e}")
            raise

    async def upsert_data(self, table_name: str, data: list[dict[str, Any]], conflict_keys: list[str] = None) -> bool:
        """Upsert data (insert or update on conflict).

        Uses MySQL's ON DUPLICATE KEY UPDATE syntax.

        Args:
            table_name: Name of the table
            data: List of dictionaries to upsert
            conflict_keys: Keys to check for conflicts (defaults to primary keys)

        Returns:
            True if successful
        """
        if not self._initialized:
            await self.connect()

        if not data:
            logger.info("No data to upsert")
            return True

        try:
            # For MySQL upsert, we use INSERT ... ON DUPLICATE KEY UPDATE
            # This requires knowing the table structure

            # Get column names from first row
            columns = list(data[0].keys())
            column_list = ", ".join(f"`{col}`" for col in columns)

            # Create placeholders
            placeholders = ", ".join(["%s"] * len(columns))

            # Create update clause (exclude primary keys if specified)
            update_columns = [col for col in columns if col not in (conflict_keys or [])]
            if not update_columns:
                # If no update columns, just insert (ignore duplicates)
                update_clause = f"`{columns[0]}` = VALUES(`{columns[0]}`)"
            else:
                update_clause = ", ".join(f"`{col}` = VALUES(`{col}`)" for col in update_columns)

            # Build query
            query = f"""
                INSERT INTO `{table_name}` ({column_list})
                VALUES ({placeholders})
                ON DUPLICATE KEY UPDATE {update_clause}
            """  # nosec B608

            # Execute in batches
            with self.engine.connect() as conn:
                for i in range(0, len(data), self.batch_size):
                    batch = data[i : i + self.batch_size]

                    # Convert batch to list of tuples
                    values = []
                    for row in batch:
                        values.append(tuple(row[col] for col in columns))

                    # Execute batch
                    conn.execute(text(query), values)
                    logger.debug(f"Upserted batch {i // self.batch_size + 1} ({len(batch)} rows)")

                conn.commit()

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
            # First, delete all existing data
            logger.warning(f"Deleting all data from {table_name}")
            with self.engine.connect() as conn:
                conn.execute(text(f"DELETE FROM `{table_name}`"))  # nosec B608
                conn.commit()

            # Then insert new data
            if data:
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
            # Build SET clause
            set_clause = ", ".join(f"`{key}` = :{key}" for key in updates)

            # Build WHERE clause
            where_clause = " AND ".join(f"`{key}` = :filter_{key}" for key in filters)

            # Build query
            query = f"UPDATE `{table_name}` SET {set_clause} WHERE {where_clause}"  # nosec B608

            # Prepare parameters
            params = {}
            params.update(updates)
            for key, value in filters.items():
                params[f"filter_{key}"] = value

            # Execute query
            with self.engine.connect() as conn:
                result = conn.execute(text(query), params)
                conn.commit()
                rows_affected = result.rowcount

            logger.info(f"Updated {rows_affected} rows in {table_name}")
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
            # Build WHERE clause
            where_clause = " AND ".join(f"`{key}` = :{key}" for key in filters)

            # Build query
            query = f"DELETE FROM `{table_name}` WHERE {where_clause}"  # nosec B608

            # Execute query
            with self.engine.connect() as conn:
                result = conn.execute(text(query), filters)
                conn.commit()
                rows_affected = result.rowcount

            logger.info(f"Deleted {rows_affected} rows from {table_name}")
            return True

        except Exception as e:
            logger.error(f"Failed to delete data from {table_name}: {e}")
            raise

    async def load_dataframe(self, table_name: str, df: pd.DataFrame, mode: str = None) -> bool:
        """Load a pandas DataFrame into a MySQL table.

        Args:
            table_name: Name of the table
            df: DataFrame to load
            mode: "append", "replace", or "upsert" (default: use config)

        Returns:
            True if successful
        """
        if not self._initialized:
            await self.connect()

        mode = mode or self.default_mode

        try:
            # Convert DataFrame to list of dicts
            data = df.to_dict("records")

            if mode == "replace":
                return await self.replace_table(table_name, data)
            elif mode == "upsert":
                return await self.upsert_data(table_name, data)
            else:  # append
                return await self.insert_data(table_name, data)

        except Exception as e:
            logger.error(f"Failed to load DataFrame into {table_name}: {e}")
            raise

    async def create_table(self, table_name: str, schema: dict[str, str]) -> bool:
        """Create a new table with given schema.

        Args:
            table_name: Name of the table to create
            schema: Column definitions {"column_name": "data_type"}

        Returns:
            True if successful
        """
        if not self._initialized:
            await self.connect()

        try:
            # Build column definitions
            column_defs = []
            for col_name, col_type in schema.items():
                column_defs.append(f"`{col_name}` {col_type}")

            # Create table query
            query = f"""
                CREATE TABLE IF NOT EXISTS `{table_name}` (
                    {", ".join(column_defs)}
                )
            """

            # Execute query
            with self.engine.connect() as conn:
                conn.execute(text(query))
                conn.commit()

            logger.info(f"Created table {table_name}")
            return True

        except Exception as e:
            logger.error(f"Failed to create table {table_name}: {e}")
            raise

    async def execute_sql(self, sql: str, params: dict[str, Any] = None) -> bool:
        """Execute custom SQL statement.

        Args:
            sql: SQL statement to execute
            params: Parameters for the SQL statement

        Returns:
            True if successful
        """
        if not self._initialized:
            await self.connect()

        try:
            with self.engine.connect() as conn:
                result = conn.execute(text(sql), params or {})
                conn.commit()

                if result.rowcount is not None:
                    logger.info(f"SQL executed, {result.rowcount} rows affected")
                else:
                    logger.info("SQL executed successfully")

                return True

        except Exception as e:
            logger.error(f"Failed to execute SQL: {e}")
            raise
