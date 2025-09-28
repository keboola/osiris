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

"""MySQL extractor for reading operations."""

import logging
import re
from typing import Any

import pandas as pd
from sqlalchemy import inspect, text
from sqlalchemy.exc import SQLAlchemyError

from ...core.interfaces import IExtractor, TableInfo
from .client import MySQLClient

logger = logging.getLogger(__name__)


class MySQLExtractor(IExtractor):
    """MySQL extractor for data discovery and extraction."""

    def __init__(self, config: dict[str, Any]):
        """Initialize MySQL extractor.

        Args:
            config: Connection configuration (passed to MySQLClient)
        """
        self.config = config
        self.base_client = MySQLClient(config)
        self.engine = None
        self.inspector = None
        self._initialized = False

    async def connect(self) -> None:
        """Establish connection to MySQL."""
        if self._initialized:
            return

        self.engine = await self.base_client.connect()
        self.inspector = inspect(self.engine)
        self._initialized = True

    async def disconnect(self) -> None:
        """Close MySQL connection."""
        await self.base_client.disconnect()
        self.engine = None
        self.inspector = None
        self._initialized = False

    async def list_tables(self) -> list[str]:
        """List all tables in the database."""
        if not self._initialized:
            await self.connect()

        return self.inspector.get_table_names()

    async def get_table_info(self, table_name: str) -> TableInfo:
        """Get information about a table including sample data.

        Args:
            table_name: Name of the table

        Returns:
            TableInfo with schema and sample data
        """
        if not self._initialized:
            await self.connect()

        try:
            # Validate table name
            if not self._validate_identifier(table_name):
                raise ValueError(f"Invalid table name: {table_name}")

            # Get columns
            columns = self.inspector.get_columns(table_name)
            column_names = [col["name"] for col in columns]
            column_types = {col["name"]: str(col["type"]) for col in columns}

            # Get primary key
            pk_constraint = self.inspector.get_pk_constraint(table_name)
            primary_keys = pk_constraint.get("constrained_columns", [])

            # Get row count
            with self.engine.connect() as conn:
                result = conn.execute(text(f"SELECT COUNT(*) FROM `{table_name}`"))  # nosec B608
                row_count = result.scalar()

            # Get sample data (10 rows for MVP)
            sample_query = f"SELECT * FROM `{table_name}` LIMIT 10"  # nosec B608
            sample_df = pd.read_sql(sample_query, self.engine)

            # Convert to list of dicts for easier processing
            sample_data = sample_df.to_dict("records")

            return TableInfo(
                name=table_name,
                columns=column_names,
                column_types=column_types,
                primary_keys=primary_keys,
                row_count=row_count,
                sample_data=sample_data,
            )

        except Exception as e:
            logger.error(f"Failed to get info for table {table_name}: {e}")
            raise

    async def execute_query(self, query: str) -> pd.DataFrame:
        """Execute a SQL query and return results as DataFrame.

        Args:
            query: SQL query to execute

        Returns:
            Query results as pandas DataFrame
        """
        if not self._initialized:
            await self.connect()

        try:
            df = pd.read_sql(query, self.engine)
            return df
        except SQLAlchemyError as e:
            logger.error(f"Failed to execute query: {e}")
            raise

    async def sample_table(self, table_name: str, size: int = 10) -> pd.DataFrame:
        """Get sample data from a table.

        Args:
            table_name: Name of the table
            size: Number of rows to sample

        Returns:
            Sample data as DataFrame
        """
        if not self._validate_identifier(table_name):
            raise ValueError(f"Invalid table name: {table_name}")

        query = f"SELECT * FROM `{table_name}` LIMIT {size}"  # nosec B608
        return await self.execute_query(query)

    def _validate_identifier(self, identifier: str) -> bool:
        """Validate MySQL identifier (table/column name).

        Args:
            identifier: Identifier to validate

        Returns:
            True if valid, False otherwise
        """
        # Allow alphanumeric, underscore, dollar sign
        return bool(re.fullmatch(r"[A-Za-z0-9_$]+", str(identifier)))
