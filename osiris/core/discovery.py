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
from datetime import date, datetime
import json
import logging
from pathlib import Path
import time
from typing import Any
import uuid

import pandas as pd

from ..connectors.mysql import MySQLExtractor, MySQLWriter
from ..connectors.supabase import SupabaseExtractor, SupabaseWriter
from ..core.interfaces import IDiscovery, IExtractor, ILoader, TableInfo
from .cache_fingerprint import (
    CacheEntry,
    CacheFingerprint,
    create_cache_entry,
    create_cache_fingerprint,
    should_invalidate_cache,
)
from .secrets_masking import mask_sensitive_dict, safe_repr
from .session_logging import log_event, log_metric

logger = logging.getLogger(__name__)


class DateTimeEncoder(json.JSONEncoder):
    """Custom JSON encoder that handles datetime objects and pandas Timestamps."""

    def default(self, obj):
        if isinstance(obj, pd.Timestamp | datetime | date):
            return obj.isoformat()
        elif pd.isna(obj):  # Handle pandas NaN/NaT values
            return None
        return super().default(obj)


class ProgressiveDiscovery(IDiscovery):
    """Progressive discovery that samples data incrementally."""

    def __init__(
        self,
        extractor: IExtractor,
        cache_dir: str = ".osiris_cache",
        component_type: str = "generic.table",
        component_version: str = "0.1.0",
        connection_ref: str = "@default",
        session_id: str | None = None,
        ttl_seconds: int | None = None,
    ):
        """Initialize discovery with an extractor.

        Args:
            extractor: Database extractor to use
            cache_dir: Directory for caching schemas
            component_type: Type of component for fingerprinting
            component_version: Version of component spec
            connection_ref: Connection reference for fingerprinting
            session_id: Optional session ID for logging (auto-generated if None)
            ttl_seconds: Optional TTL override for cache entries
        """
        self.extractor = extractor
        self.cache_dir = Path(cache_dir)
        self.cache_ttl = ttl_seconds if ttl_seconds is not None else 3600  # 1 hour TTL default

        # Session tracking for structured logging
        self.session_id = session_id or f"discovery_{uuid.uuid4().hex[:8]}"

        # Try to create cache directory with graceful error handling
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            # If we can't create the cache directory, fall back to temp directory
            import tempfile

            fallback_dir = Path(tempfile.mkdtemp(prefix="osiris-cache-"))

            # Log structured cache error
            self._log_cache_event(
                "cache_error",
                kind="permission_denied",
                dir=str(cache_dir),
                fallback=str(fallback_dir),
            )

            self.cache_dir = fallback_dir
        except Exception as e:
            # For any other unexpected errors, fall back to temp directory
            import tempfile

            fallback_dir = Path(tempfile.mkdtemp(prefix="osiris-cache-"))

            # Log structured cache error
            self._log_cache_event(
                "cache_error",
                kind="unexpected_error",
                dir=str(cache_dir),
                error=str(e),
                fallback=str(fallback_dir),
            )

            self.cache_dir = fallback_dir

        # Component fingerprinting info
        self.component_type = component_type
        self.component_version = component_version
        self.connection_ref = connection_ref
        self.spec_schema: dict[str, Any] = {}  # Will be set by component registry

        # Test-only override for spec version (for testing cache invalidation)
        self._spec_version_override: str | None = None

        # Discovery state
        self.discovered_tables: dict[str, TableInfo] = {}
        self.sample_sizes = [10, 100, 1000]  # Progressive sampling
        self.current_sample_level = 0

    def set_spec_schema(self, spec_schema: dict[str, Any]) -> None:
        """Set the component spec schema for fingerprinting.

        Args:
            spec_schema: Component specification schema
        """
        self.spec_schema = spec_schema

    def set_spec_version_override(self, version_override: str) -> None:
        """Set spec version override for testing cache invalidation.

        WARNING: Test-only method. Do not use in production.

        Args:
            version_override: Version string to override component_version
        """
        self._spec_version_override = version_override

    def _get_effective_component_version(self) -> str:
        """Get the effective component version (with test override if set)."""
        return self._spec_version_override or self.component_version

    def _log_cache_event(self, event: str, **kwargs) -> None:
        """Log structured cache event with session context.

        Args:
            event: Event type (cache_lookup, cache_hit, cache_miss, cache_store, cache_error)
            **kwargs: Additional structured data to log
        """
        # Base context
        context = {
            "event": event,
            "session": self.session_id,
        }

        # Add provided data, masking sensitive fields
        for key, value in kwargs.items():
            if isinstance(value, dict):
                context[key] = safe_repr(mask_sensitive_dict(value))
            else:
                context[key] = value

        # Format as key=value pairs for easy grepping
        log_parts = []
        for key, value in context.items():
            if isinstance(value, str) and " " in value:
                log_parts.append(f'{key}="{value}"')
            else:
                log_parts.append(f"{key}={value}")

        log_message = " ".join(log_parts)

        # Log at appropriate level
        if event in ["cache_lookup", "cache_store"]:
            logger.debug(log_message)
        elif event in ["cache_hit", "cache_miss"]:
            logger.info(log_message)
        elif event == "cache_error":
            logger.warning(log_message)
        else:
            logger.info(log_message)

        # Also log to session-scoped structured events
        log_event(event, **kwargs)

    async def list_tables(self) -> list[str]:
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

    async def get_table_info(self, table_name: str, options: dict[str, Any] | None = None) -> TableInfo:
        """Get detailed information about a table.

        This uses progressive sampling - starts with 10 rows,
        can expand to 100 or 1000 if needed.

        Args:
            table_name: Name of the table
            options: Options for discovery (schema, columns, filters, etc.)

        Returns:
            TableInfo with schema and sample data
        """
        # Use empty options if none provided
        if options is None:
            options = {"table": table_name}
        elif "table" not in options:
            options["table"] = table_name

        # Create fingerprint for this request
        effective_version = self._get_effective_component_version()
        fingerprint = create_cache_fingerprint(
            component_type=self.component_type,
            component_version=effective_version,
            connection_ref=self.connection_ref,
            options=options,
            spec_schema=self.spec_schema,
        )

        # Log cache lookup
        self._log_cache_event(
            "cache_lookup",
            component_type=self.component_type,
            version=effective_version,
            conn=self.connection_ref,
            options_fp=fingerprint.options_fp[:8],
            spec_fp=fingerprint.spec_fp[:8],
            key=fingerprint.cache_key[:12],
        )

        # Check cache with fingerprint validation first (includes TTL check)
        cached_entry = self._get_cached_table_info_with_fingerprint(table_name)
        if cached_entry and not should_invalidate_cache(cached_entry, fingerprint):
            # Cache hit - log with structured format
            age_seconds = self._get_cache_age(cached_entry)
            self._log_cache_event(
                "cache_hit",
                key=fingerprint.cache_key[:12],
                age_s=age_seconds,
                ttl_s=cached_entry.ttl_seconds,
                options_fp=fingerprint.options_fp[:8],
                spec_fp=fingerprint.spec_fp[:8],
            )

            table_info = TableInfo(**cached_entry.payload)

            # Store in memory cache with fingerprint key for this session
            memory_cache_key = fingerprint.cache_key
            self.discovered_tables[memory_cache_key] = table_info
            return table_info
        elif cached_entry:
            # Cache exists but needs invalidation - determine reason
            if cached_entry.is_expired:
                age_seconds = self._get_cache_age(cached_entry)
                self._log_cache_event(
                    "cache_miss",
                    reason="ttl_expired",
                    key=fingerprint.cache_key[:12],
                    age_s=age_seconds,
                    ttl_s=cached_entry.ttl_seconds,
                    options_fp=fingerprint.options_fp[:8],
                    spec_fp=fingerprint.spec_fp[:8],
                )
            else:
                # Fingerprint mismatch - determine which component changed
                cached_fp = cached_entry.fingerprint
                reason = self._determine_cache_miss_reason(cached_fp, fingerprint)

                log_data = {
                    "reason": reason,
                    "key": fingerprint.cache_key[:12],
                    "spec_fp": fingerprint.spec_fp[:8],
                }

                # Add specific change details based on reason
                if reason == "options_changed":
                    log_data.update({"options_fp": f"old:{cached_fp.options_fp[:8]} new:{fingerprint.options_fp[:8]}"})
                elif reason == "spec_changed":
                    log_data.update({"options_fp": fingerprint.options_fp[:8]})
                elif reason == "component_changed":
                    log_data.update(
                        {
                            "options_fp": fingerprint.options_fp[:8],
                            "old_version": cached_fp.component_version,
                            "new_version": fingerprint.component_version,
                        }
                    )

                self._log_cache_event("cache_miss", **log_data)
        else:
            # No cached entry exists
            self._log_cache_event(
                "cache_miss",
                reason="no_cache",
                key=fingerprint.cache_key[:12],
                options_fp=fingerprint.options_fp[:8],
                spec_fp=fingerprint.spec_fp[:8],
            )

        # Check if we have it in memory cache (but only if disk cache was valid)
        # If disk cache was invalid (TTL expired, etc.), we don't use memory cache
        memory_cache_key = fingerprint.cache_key
        if cached_entry is None and memory_cache_key in self.discovered_tables:
            # Remove from memory cache since disk cache is invalid
            logger.debug(f"Removing stale memory cache for table {table_name}")
            del self.discovered_tables[memory_cache_key]

        # Cache is invalid or missing - discover table info
        logger.info(f"Discovering table {table_name} with {self.sample_sizes[0]} rows")

        # Time the extraction for metrics
        start_time = time.time()
        table_info = await self.extractor.get_table_info(table_name)
        extraction_time = time.time() - start_time

        # Log discovery metrics
        log_metric(
            "table_discovery_duration_ms",
            int(extraction_time * 1000),
            table=table_name,
            row_count=table_info.row_count,
            column_count=len(table_info.columns),
        )

        # Cache with fingerprint and store
        self._cache_table_info_with_fingerprint(table_name, table_info, fingerprint)
        self.discovered_tables[memory_cache_key] = table_info

        # Log cache storage
        self._log_cache_event(
            "cache_store",
            key=fingerprint.cache_key[:12],
            created_at=datetime.utcnow().isoformat() + "Z",
            ttl_s=self.cache_ttl,
            options_fp=fingerprint.options_fp[:8],
            spec_fp=fingerprint.spec_fp[:8],
        )

        return table_info

    async def discover_all_tables(self, max_tables: int = 10) -> dict[str, TableInfo]:
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
        for table, result in zip(tables, results, strict=False):
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

    async def search_tables(self, keywords: list[str]) -> list[tuple[str, float]]:
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

    def _get_cached_tables(self) -> list[str] | None:
        """Get cached table list if valid."""
        path = self._get_cache_path("tables_list")

        if self._is_cache_valid(path):
            try:
                with open(path) as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load cache: {e}")

        return None

    def _cache_tables(self, tables: list[str]) -> None:
        """Cache table list."""
        path = self._get_cache_path("tables_list")

        try:
            with open(path, "w") as f:
                json.dump(tables, f, cls=DateTimeEncoder)
        except Exception as e:
            logger.warning(f"Failed to cache tables: {e}")

    def _get_cached_table_info(self, table_name: str) -> TableInfo | None:
        """Get cached table info if valid (legacy method for backward compatibility)."""
        path = self._get_cache_path(f"table_{table_name}")

        if self._is_cache_valid(path):
            try:
                with open(path) as f:
                    data = json.load(f)
                    return TableInfo(**data)
            except Exception as e:
                logger.warning(f"Failed to load cache for {table_name}: {e}")

        return None

    def _get_cached_table_info_with_fingerprint(self, table_name: str) -> CacheEntry | None:
        """Get cached table info with fingerprint validation."""
        path = self._get_cache_path(f"table_{table_name}")

        if path.exists():
            try:
                with open(path) as f:
                    data = json.load(f)

                # Check if this is the new fingerprint format
                if "fingerprint" in data and "payload" in data:
                    fingerprint_data = data["fingerprint"]
                    fingerprint = CacheFingerprint(
                        component_type=fingerprint_data["component_type"],
                        component_version=fingerprint_data["component_version"],
                        connection_ref=fingerprint_data["connection_ref"],
                        options_fp=fingerprint_data["options_fp"],
                        spec_fp=fingerprint_data["spec_fp"],
                    )

                    cache_entry = CacheEntry(
                        key=data["key"],
                        created_at=data["created_at"],
                        ttl_seconds=data["ttl_seconds"],
                        fingerprint=fingerprint,
                        payload=data["payload"],
                    )
                    return cache_entry

            except Exception as e:
                logger.warning(f"Failed to load fingerprinted cache for {table_name}: {e}")

        return None

    def _cache_table_info(self, table_name: str, info: TableInfo) -> None:
        """Cache table info (legacy method for backward compatibility)."""
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

    def _get_cache_age(self, cache_entry: CacheEntry) -> int:
        """Get cache age in seconds."""
        import time

        created_timestamp = datetime.fromisoformat(cache_entry.created_at.replace("Z", "+00:00")).timestamp()
        return int(time.time() - created_timestamp)

    def _determine_cache_miss_reason(self, cached_fp: CacheFingerprint, current_fp: CacheFingerprint) -> str:
        """Determine the specific reason for cache miss between two fingerprints.

        Args:
            cached_fp: Cached fingerprint
            current_fp: Current request fingerprint

        Returns:
            Reason string: options_changed, spec_changed, or component_changed
        """
        # Check component-level changes first (type, version, connection)
        if (
            cached_fp.component_type != current_fp.component_type
            or cached_fp.component_version != current_fp.component_version
            or cached_fp.connection_ref != current_fp.connection_ref
        ):
            return "component_changed"

        # Check spec schema changes
        if cached_fp.spec_fp != current_fp.spec_fp:
            return "spec_changed"

        # Check options changes
        if cached_fp.options_fp != current_fp.options_fp:
            return "options_changed"

        # Shouldn't reach here if fingerprints actually differ
        return "unknown"

    def _cache_table_info_with_fingerprint(
        self, table_name: str, info: TableInfo, fingerprint: CacheFingerprint
    ) -> None:
        """Cache table info with fingerprint metadata."""
        path = self._get_cache_path(f"table_{table_name}")

        try:
            # Convert table info to dict for JSON serialization
            payload = {
                "name": info.name,
                "columns": info.columns,
                "column_types": info.column_types,
                "primary_keys": info.primary_keys,
                "row_count": info.row_count,
                "sample_data": info.sample_data,
            }

            # Create cache entry with fingerprint
            cache_entry = create_cache_entry(fingerprint, payload, self.cache_ttl)

            # Serialize cache entry
            data = {
                "key": cache_entry.key,
                "created_at": cache_entry.created_at,
                "ttl_seconds": cache_entry.ttl_seconds,
                "fingerprint": {
                    "component_type": fingerprint.component_type,
                    "component_version": fingerprint.component_version,
                    "connection_ref": fingerprint.connection_ref,
                    "options_fp": fingerprint.options_fp,
                    "spec_fp": fingerprint.spec_fp,
                },
                "payload": payload,
            }

            with open(path, "w") as f:
                json.dump(data, f, cls=DateTimeEncoder)

        except Exception as e:
            logger.warning(f"Failed to cache fingerprinted info for {table_name}: {e}")

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
    def create_extractor(db_type: str, config: dict[str, Any]) -> IExtractor:
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
    def create_writer(db_type: str, config: dict[str, Any]) -> ILoader:
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
    connection_strings: list[dict[str, Any]],
) -> dict[str, Any]:
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
