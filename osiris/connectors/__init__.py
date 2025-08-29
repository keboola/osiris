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

"""Database connectors for Osiris v2."""

from .mysql import MySQLExtractor, MySQLWriter
from .supabase import SupabaseExtractor, SupabaseWriter


class ConnectorRegistry:
    """Registry of available database connectors."""

    def __init__(self):
        self.connectors = {
            "mysql": {
                "extractor": MySQLExtractor,
                "writer": MySQLWriter,
                "description": "MySQL database connector",
            },
            "supabase": {
                "extractor": SupabaseExtractor,
                "writer": SupabaseWriter,
                "description": "Supabase (PostgreSQL) cloud connector",
            },
        }

    def list(self) -> list[str]:
        """List available connector names."""
        return list(self.connectors.keys())

    def get_connector_info(self, name: str) -> dict:
        """Get connector information."""
        return self.connectors.get(name, {})

    def get_extractor(self, name: str):
        """Get extractor class for connector."""
        connector = self.connectors.get(name)
        return connector["extractor"] if connector else None

    def get_writer(self, name: str):
        """Get writer class for connector."""
        connector = self.connectors.get(name)
        return connector["writer"] if connector else None


__all__ = [
    "MySQLExtractor",
    "MySQLWriter",
    "SupabaseExtractor",
    "SupabaseWriter",
    "ConnectorRegistry",
]
