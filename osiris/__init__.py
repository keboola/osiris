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

"""Osiris MVP - Conversational ETL pipeline generator."""

import tomllib
from pathlib import Path

_project_root = Path(__file__).parent.parent
_pyproject = _project_root / "pyproject.toml"

try:
    __version__ = tomllib.loads(_pyproject.read_text())["project"]["version"]
except Exception:
    __version__ = "0.5.4"  # Fallback for installed package

__author__ = "Osiris Team"
__description__ = "LLM-first conversational ETL pipeline generator"

# Database connectors
from .connectors import MySQLExtractor, MySQLWriter, SupabaseExtractor, SupabaseWriter
from .core.discovery import ExtractorFactory, ProgressiveDiscovery, WriterFactory

# Core interfaces
from .core.interfaces import (
    IDiscovery,
    IExtractor,
    ILoader,
    IStateStore,
    ITransformer,
)

# Core implementations
from .core.state_store import SQLiteStateStore

__all__ = [
    # Interfaces
    "IStateStore",
    "IDiscovery",
    "IExtractor",
    "ILoader",
    "ITransformer",
    # Implementations
    "SQLiteStateStore",
    "ProgressiveDiscovery",
    "ExtractorFactory",
    "WriterFactory",
    # Connectors
    "MySQLExtractor",
    "MySQLWriter",
    "SupabaseExtractor",
    "SupabaseWriter",
]
