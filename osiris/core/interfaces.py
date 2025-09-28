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

"""
Core interfaces for Osiris v2.

These minimal interfaces enable:
1. Easy testing with mocks
2. Swappable implementations
3. Clear component boundaries
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


# Data structures
@dataclass
class TableInfo:
    """Basic table information."""

    name: str
    columns: list[str]  # Column names
    column_types: dict[str, str]  # {"column_name": "type"}
    primary_keys: list[str]
    row_count: int
    sample_data: list[dict[str, Any]]  # Sample data rows


@dataclass
class Pipeline:
    """Generated pipeline specification."""

    name: str
    yaml_content: str
    estimated_runtime: float  # seconds
    tables_used: list[str]


# Core interfaces (MVP - only 3 essential ones)
class IStateStore(ABC):
    """Manages conversation state."""

    @abstractmethod
    def set(self, key: str, value: Any) -> None:
        """Store a value."""
        pass

    @abstractmethod
    def get(self, key: str, default: Any = None) -> Any:
        """Retrieve a value."""
        pass

    @abstractmethod
    def clear(self) -> None:
        """Clear all state."""
        pass


class IDiscovery(ABC):
    """Discovers data sources and schemas."""

    @abstractmethod
    async def list_tables(self) -> list[str]:
        """List available tables."""
        pass

    @abstractmethod
    async def get_table_info(self, table: str, sample_size: int = 10) -> TableInfo:
        """Get table schema and sample data."""
        pass


# Extended interfaces (for post-MVP extensibility)
class IConnector(ABC):
    """Base connector interface for all data sources."""

    @abstractmethod
    async def connect(self) -> None:
        """Establish connection."""
        pass

    @abstractmethod
    async def disconnect(self) -> None:
        """Close connection."""
        pass


class IExtractor(IConnector):
    """Data extraction interface for reading from sources."""

    @abstractmethod
    async def list_tables(self) -> list[str]:
        """List available tables."""
        pass

    @abstractmethod
    async def get_table_info(self, table_name: str) -> TableInfo:
        """Get schema and sample data for a table."""
        pass

    @abstractmethod
    async def execute_query(self, query: str) -> Any:
        """Execute a query and return results."""
        pass

    @abstractmethod
    async def sample_table(self, table_name: str, size: int = 10) -> Any:
        """Get sample data from a table."""
        pass


class ITransformer(ABC):
    """Data transformation engine interface."""

    @abstractmethod
    async def validate_sql(self, sql: str) -> bool:
        """Validate SQL syntax."""
        pass

    @abstractmethod
    async def execute_transform(self, sql: str, inputs: dict[str, Any]) -> Any:
        """Execute transformation."""
        pass


class ILoader(ABC):
    """Data loading interface for writing to destinations."""

    @abstractmethod
    async def connect(self) -> None:
        """Establish connection to destination."""
        pass

    @abstractmethod
    async def disconnect(self) -> None:
        """Close connection to destination."""
        pass

    @abstractmethod
    async def insert_data(self, table_name: str, data: list[dict[str, Any]]) -> bool:
        """Insert data into a table."""
        pass

    @abstractmethod
    async def upsert_data(self, table_name: str, data: list[dict[str, Any]], conflict_keys: list[str] = None) -> bool:
        """Upsert data (insert or update on conflict)."""
        pass

    @abstractmethod
    async def replace_table(self, table_name: str, data: list[dict[str, Any]]) -> bool:
        """Replace entire table contents."""
        pass
