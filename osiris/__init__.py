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

from pathlib import Path
import tomllib

_project_root = Path(__file__).parent.parent
_pyproject = _project_root / "pyproject.toml"

try:
    # Development mode: read from pyproject.toml
    __version__ = tomllib.loads(_pyproject.read_text())["project"]["version"]
except Exception:
    # Production mode: read from installed package metadata
    try:
        from importlib.metadata import version

        __version__ = version("osiris-pipeline")
    except Exception:
        # Last resort fallback (should never happen in normal usage)
        __version__ = "unknown"

__author__ = "Osiris Team"
__description__ = "LLM-first conversational ETL pipeline generator"

# Database connectors
from .connectors import MySQLExtractor, MySQLWriter, SupabaseExtractor, SupabaseWriter  # noqa: E402
from .core.discovery import ExtractorFactory, ProgressiveDiscovery, WriterFactory  # noqa: E402

# Core interfaces
from .core.interfaces import (  # noqa: E402
    IDiscovery,
    IExtractor,
    ILoader,
    IStateStore,
    ITransformer,
)

# Core implementations
from .core.state_store import SQLiteStateStore  # noqa: E402

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
