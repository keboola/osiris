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

"""Progressive discovery system for Osiris v2 MVP.

Discovers database schemas progressively: 10 → 100 → 1000 rows as needed.
"""

import asyncio
import json
import logging
import time
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from ..connectors.mysql import MySQLExtractor, MySQLWriter
from ..connectors.supabase import SupabaseExtractor, SupabaseWriter
from ..core.interfaces import IDiscovery, IExtractor, ILoader, TableInfo

logger = logging.getLogger(__name__)


class DateTimeEncoder(json.JSONEncoder):
    """Custom JSON encoder that handles datetime objects and pandas Timestamps."""

    def default(self, obj):
        if isinstance(obj, (pd.Timestamp, datetime, date)):
            return obj.isoformat()
        elif pd.isna(obj):  # Handle pandas NaN/NaT values
            return None
        return super().default(obj)


class ProgressiveDiscovery(IDiscovery):
    """Progressive discovery that samples data incrementally."""

    def __init__(self, extractor: IExtractor, cache_dir: str = ".osiris_cache"):
        """Initialize discovery with an extractor.

        Args:
            extractor: Database extractor to use
            cache_dir: Directory for caching schemas
        """
        self.extractor = extractor
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)
        self.cache_ttl = 3600  # 1 hour TTL

        # Discovery state
        self.discovered_tables: Dict[str, TableInfo] = {}
        self.sample_sizes = [10, 100, 1000]  # Progressive sampling
        self.current_sample_level = 0

    async def list_tables(self) -> List[str]:
        """List all available tables in the database.

        Returns:
            List of table names
        """
        # Check cache first
        cached = self._get_cached_tables()
        if cached:
            logger.info(f"Using cached table list ({len(cached)} tables)")
            return cached

        # Discover tables
        tables = await self.extractor.list_tables()

        # Cache the result
        self._cache_tables(tables)

        logger.info(f"Discovered {len(tables)} tables")
        return tables

    async def get_table_info(self, table_name: str) -> TableInfo:
        """Get detailed information about a table.

        This uses progressive sampling - starts with 10 rows,
        can expand to 100 or 1000 if needed.

        Args:
            table_name: Name of the table

        Returns:
            TableInfo with schema and sample data
        """
        # Check if we already have this table discovered
        if table_name in self.discovered_tables:
            return self.discovered_tables[table_name]

        # Check cache
        cached = self._get_cached_table_info(table_name)
        if cached:
            logger.info(f"Using cached info for table {table_name}")
            self.discovered_tables[table_name] = cached
            return cached

        # Discover table info with initial sample
        logger.info(f"Discovering table {table_name} with {self.sample_sizes[0]} rows")
        table_info = await self.extractor.get_table_info(table_name)

        # Cache and store
        self._cache_table_info(table_name, table_info)
        self.discovered_tables[table_name] = table_info

        return table_info

    async def discover_all_tables(self, max_tables: int = 10) -> Dict[str, TableInfo]:
        """Discover all tables with basic sampling.

        Args:
            max_tables: Maximum number of tables to discover (for MVP)

        Returns:
            Dictionary of table names to TableInfo
        """
        tables = await self.list_tables()

        # Limit for MVP
        tables = tables[:max_tables]

        # Discover tables in parallel
        logger.info(f"Discovering {len(tables)} tables in parallel")

        tasks = []
        for table in tables:
            tasks.append(self.get_table_info(table))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        discovered = {}
        for table, result in zip(tables, results):
            if isinstance(result, Exception):
                logger.warning(f"Failed to discover table {table}: {result}")
            else:
                discovered[table] = result

        logger.info(f"Successfully discovered {len(discovered)} tables")
        return discovered

    async def expand_sample(self, table_name: str) -> TableInfo:
        """Expand the sample size for a table.

        This is called when we need more data to understand patterns.

        Args:
            table_name: Name of the table

        Returns:
            Updated TableInfo with larger sample
        """
        if self.current_sample_level >= len(self.sample_sizes) - 1:
            logger.info(f"Already at maximum sample size for {table_name}")
            return self.discovered_tables.get(table_name)

        self.current_sample_level += 1
        new_size = self.sample_sizes[self.current_sample_level]

        logger.info(f"Expanding sample for {table_name} to {new_size} rows")

        # Get larger sample
        sample_df = await self.extractor.sample_table(table_name, new_size)
        sample_data = sample_df.to_dict("records")

        # Update table info
        if table_name in self.discovered_tables:
            self.discovered_tables[table_name].sample_data = sample_data
            # Update cache
            self._cache_table_info(table_name, self.discovered_tables[table_name])

        return self.discovered_tables.get(table_name)

    async def search_tables(self, keywords: List[str]) -> List[Tuple[str, float]]:
        """Search for tables matching keywords.

        Args:
            keywords: Keywords to search for

        Returns:
            List of (table_name, relevance_score) tuples
        """
        tables = await self.list_tables()

        results = []
        for table in tables:
            # Simple keyword matching for MVP
            score = 0.0
            table_lower = table.lower()

            for keyword in keywords:
                keyword_lower = keyword.lower()
                if keyword_lower == table_lower:
                    score += 1.0  # Exact match
                elif keyword_lower in table_lower:
                    score += 0.5  # Partial match
                elif table_lower in keyword_lower:
                    score += 0.3  # Reverse partial

            if score > 0:
                results.append((table, score))

        # Sort by relevance
        results.sort(key=lambda x: x[1], reverse=True)

        return results

    # Cache management methods

    def _get_cache_path(self, key: str) -> Path:
        """Get cache file path for a key."""
        return self.cache_dir / f"{key}.json"

    def _is_cache_valid(self, path: Path) -> bool:
        """Check if cache file is still valid."""
        if not path.exists():
            return False

        # Check age
        age = time.time() - path.stat().st_mtime
        return age < self.cache_ttl

    def _get_cached_tables(self) -> Optional[List[str]]:
        """Get cached table list if valid."""
        path = self._get_cache_path("tables_list")

        if self._is_cache_valid(path):
            try:
                with open(path) as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load cache: {e}")

        return None

    def _cache_tables(self, tables: List[str]) -> None:
        """Cache table list."""
        path = self._get_cache_path("tables_list")

        try:
            with open(path, "w") as f:
                json.dump(tables, f, cls=DateTimeEncoder)
        except Exception as e:
            logger.warning(f"Failed to cache tables: {e}")

    def _get_cached_table_info(self, table_name: str) -> Optional[TableInfo]:
        """Get cached table info if valid."""
        path = self._get_cache_path(f"table_{table_name}")

        if self._is_cache_valid(path):
            try:
                with open(path) as f:
                    data = json.load(f)
                    return TableInfo(**data)
            except Exception as e:
                logger.warning(f"Failed to load cache for {table_name}: {e}")

        return None

    def _cache_table_info(self, table_name: str, info: TableInfo) -> None:
        """Cache table info."""
        path = self._get_cache_path(f"table_{table_name}")

        try:
            # Convert to dict for JSON serialization
            data = {
                "name": info.name,
                "columns": info.columns,
                "column_types": info.column_types,
                "primary_keys": info.primary_keys,
                "row_count": info.row_count,
                "sample_data": info.sample_data,
            }

            with open(path, "w") as f:
                json.dump(data, f, cls=DateTimeEncoder)
        except Exception as e:
            logger.warning(f"Failed to cache info for {table_name}: {e}")

    def clear_cache(self) -> None:
        """Clear all cached data."""
        for cache_file in self.cache_dir.glob("*.json"):
            try:
                cache_file.unlink()
            except Exception as e:
                logger.warning(f"Failed to delete cache file {cache_file}: {e}")

        logger.info("Cache cleared")


class ExtractorFactory:
    """Factory for creating database extractors."""

    @staticmethod
    def create_extractor(db_type: str, config: Dict[str, Any]) -> IExtractor:
        """Create an extractor based on database type.

        Args:
            db_type: Type of database ("mysql", "supabase")
            config: Connection configuration

        Returns:
            Configured extractor instance

        Raises:
            ValueError: If db_type is not supported
        """
        if db_type == "mysql":
            return MySQLExtractor(config)
        elif db_type == "supabase":
            return SupabaseExtractor(config)
        else:
            raise ValueError(f"Unsupported database type: {db_type}")


class WriterFactory:
    """Factory for creating database writers."""

    @staticmethod
    def create_writer(db_type: str, config: Dict[str, Any]) -> ILoader:
        """Create a writer based on database type.

        Args:
            db_type: Type of database ("mysql", "supabase")
            config: Connection configuration

        Returns:
            Configured writer instance

        Raises:
            ValueError: If db_type is not supported
        """
        if db_type == "mysql":
            return MySQLWriter(config)
        elif db_type == "supabase":
            return SupabaseWriter(config)
        else:
            raise ValueError(f"Unsupported database type: {db_type}")


async def discover_from_connection_strings(
    connection_strings: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Discover schemas from multiple connection strings.

    This is the main entry point for discovery in the MVP.

    Args:
        connection_strings: List of connection configs with "type" and connection params

    Returns:
        Dictionary with discovered schemas from all sources
    """
    discoveries = {}

    for conn_config in connection_strings:
        db_type = conn_config.get("type")
        name = conn_config.get("name", db_type)

        try:
            # Create extractor
            extractor = ExtractorFactory.create_extractor(db_type, conn_config)

            # Create discovery
            discovery = ProgressiveDiscovery(extractor)

            # Discover tables
            tables = await discovery.discover_all_tables(max_tables=10)

            discoveries[name] = {
                "type": db_type,
                "tables": {
                    table_name: {
                        "columns": info.columns,
                        "row_count": info.row_count,
                        "sample_rows": len(info.sample_data),
                        "primary_keys": info.primary_keys,
                    }
                    for table_name, info in tables.items()
                },
            }

            # Disconnect
            await extractor.disconnect()

        except Exception as e:
            logger.error(f"Failed to discover {name}: {e}")
            discoveries[name] = {"error": str(e)}

    return discoveries
