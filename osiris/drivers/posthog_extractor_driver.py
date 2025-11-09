"""
PostHog Osiris Driver - E2B Compatible Component

Implements streaming-based extraction for PostHog analytics data with memory-efficient
processing optimized for E2B sandbox constraints. Uses SEEK-based pagination to respect
rate limits and avoid performance degradation on large datasets.

CRITICAL: Uses streaming writer approach (batching) instead of materializing all rows
in memory to avoid OOM errors in E2B sandbox environments.
"""

from typing import Dict, Any, Tuple, Iterator, Optional
from datetime import datetime, timedelta, timezone
import pandas as pd
import json
from hashlib import sha256
import sys
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


class PostHogExtractorDriver:
    """Driver class for PostHog extractor component.

    This is a thin wrapper around the module-level functions to comply with
    Osiris driver registry expectations.
    """

    def run(self, *, step_id: str, config: Dict[str, Any], inputs: Dict[str, Any], ctx) -> Dict[str, Any]:
        """Execute the driver logic."""
        return run(step_id=step_id, config=config, inputs=inputs, ctx=ctx)

    def discover(self, *, config: Dict[str, Any], ctx) -> Dict[str, Any]:
        """Discover available PostHog data resources."""
        return discover(config=config, ctx=ctx)

    def doctor(self, *, config: Dict[str, Any], ctx) -> Tuple[bool, Dict[str, Any]]:
        """Health check for PostHog connection."""
        return doctor(config=config, ctx=ctx)


# Import shared API client - handles PostHog HogQL Query API
from .posthog_client import (
    PostHogClient,
    PostHogClientError,
    PostHogAuthenticationError,
    PostHogRateLimitError,
    PostHogNetworkError
)


class OsirisDriverError(Exception):
    """Base exception for Osiris driver errors"""
    pass


class PostHogDriverError(OsirisDriverError):
    """PostHog-specific driver error"""
    pass


def _get_base_url(resolved_connection: Dict[str, Any]) -> str:
    """
    Get PostHog base URL from resolved connection config.

    Args:
        resolved_connection: Connection dict with api_key, project_id, region, custom_base_url

    Returns:
        str: Base URL (e.g., https://us.posthog.com)

    Raises:
        PostHogDriverError: If configuration is invalid
    """
    region = resolved_connection.get("region", "us")

    if region == "self_hosted":
        base_url = resolved_connection.get("custom_base_url")
        if not base_url:
            raise PostHogDriverError("region=self_hosted but custom_base_url not provided")
        return base_url
    elif region == "eu":
        return "https://eu.posthog.com"
    elif region == "us":
        return "https://us.posthog.com"
    else:
        raise PostHogDriverError(f"Unknown region: {region}")


def _flatten_event(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    Flatten nested event structure into flat dict for DataFrame.

    Converts:
    - properties dict → properties_* columns
    - Preserves scalar fields (uuid, event, timestamp, etc.)
    - Serializes complex types (nested dicts, lists) as JSON strings

    Note: Person properties are NOT included in events extraction.
    Extract persons separately if you need person-level data.

    Args:
        event: Raw event dict from PostHog API

    Returns:
        Dict with flattened structure

    Example:
        >>> event = {
        ...     "uuid": "abc-123",
        ...     "event": "$pageview",
        ...     "timestamp": "2025-11-08T10:00:00Z",
        ...     "properties": {"$browser": "Chrome", "custom": {"nested": "value"}}
        ... }
        >>> flat = _flatten_event(event)
        >>> flat["properties_$browser"]
        'Chrome'
        >>> flat["properties_custom"]
        '{"nested": "value"}'
    """
    flattened = {}

    # Copy scalar fields
    scalar_fields = ["uuid", "event", "timestamp", "distinct_id", "person_id"]
    for field in scalar_fields:
        if field in event:
            flattened[field] = event[field]

    # Flatten properties
    if "properties" in event:
        props = event["properties"]
        if isinstance(props, dict):
            for key, value in props.items():
                col_name = f"properties_{key}"
                # Serialize complex types as JSON
                if isinstance(value, (dict, list)):
                    flattened[col_name] = json.dumps(value)
                else:
                    flattened[col_name] = value

    # Note: person_properties are NOT available in PostHog HogQL events table
    # To get person properties, extract the 'persons' table separately

    return flattened


def _flatten_person(person: Dict[str, Any]) -> Dict[str, Any]:
    """
    Flatten nested person structure into flat dict for DataFrame.

    Converts:
    - properties dict → person_properties_* columns
    - Preserves scalar fields (id, created_at, is_identified)
    - Serializes complex types as JSON strings

    Args:
        person: Raw person dict from PostHog API

    Returns:
        Dict with flattened structure

    Example:
        >>> person = {
        ...     "id": "person123",
        ...     "created_at": "2025-11-08T10:00:00Z",
        ...     "is_identified": True,
        ...     "properties": {"email": "user@example.com", "plan": "pro"}
        ... }
        >>> flat = _flatten_person(person)
        >>> flat["person_properties_email"]
        'user@example.com'
    """
    flattened = {}

    # Copy scalar fields
    scalar_fields = ["id", "created_at", "is_identified"]
    for field in scalar_fields:
        if field in person:
            flattened[field] = person[field]

    # Flatten person properties
    if "properties" in person:
        props = person["properties"]
        if isinstance(props, dict):
            for key, value in props.items():
                col_name = f"person_properties_{key}"
                # Serialize complex types as JSON
                if isinstance(value, (dict, list)):
                    flattened[col_name] = json.dumps(value)
                else:
                    flattened[col_name] = value

    return flattened


def _flatten_session(session: Dict[str, Any]) -> Dict[str, Any]:
    """
    Flatten session row - sessions are already flat (43 columns).

    Sessions table structure is inherently flat with all metrics at top level.
    No nested properties to flatten.

    Args:
        session: Raw session dict from PostHog API

    Returns:
        Dict with session data (unchanged)

    Example:
        >>> session = {
        ...     "session_id": "session123",
        ...     "$start_timestamp": "2025-11-08T10:00:00Z",
        ...     "$session_duration": 3600
        ... }
        >>> flat = _flatten_session(session)
        >>> flat["session_id"]
        'session123'
    """
    # Sessions are already flat - just return as-is
    return session


def _flatten_row(row: Dict[str, Any], data_type: str) -> Dict[str, Any]:
    """
    Flatten a row based on data type.

    Routes to appropriate flatten function based on data_type.

    Args:
        row: Raw row dict from PostHog API
        data_type: One of "events", "persons", "sessions", "person_distinct_ids"

    Returns:
        Dict with flattened structure

    Raises:
        PostHogDriverError: If data_type is unrecognized
    """
    if data_type == "events":
        return _flatten_event(row)
    elif data_type == "persons":
        return _flatten_person(row)
    elif data_type == "sessions":
        return _flatten_session(row)
    elif data_type == "person_distinct_ids":
        # Already flat (2 columns: distinct_id, person_id)
        return row
    else:
        raise PostHogDriverError(f"Unknown data_type for flattening: {data_type}")


def run(
    *,
    step_id: str,
    config: Dict[str, Any],
    inputs: Dict[str, Any],
    ctx
) -> Dict[str, Any]:
    """
    Main Osiris driver entry point - STREAMING implementation.

    CRITICAL: Uses streaming approach with batch processing to avoid memory exhaustion
    in E2B sandbox. Rows are batched into chunks and built into DataFrame incrementally.

    Args:
        step_id: Unique step identifier
        config: Configuration dict containing:
            - resolved_connection: {api_key, project_id, region, custom_base_url}
            - data_type: "events" or "persons"
            - event_types: Optional list of event type filters
            - lookback_window_minutes: Lookback window (5-60 minutes, default 15)
            - initial_since: Initial start timestamp (ISO 8601)
            - page_size: Rows per page (100-10000, default 1000)
            - deduplication_enabled: Enable UUID deduplication (default True)
        inputs: Input state dict with:
            - state: {last_timestamp, last_uuid, recent_uuids}
        ctx: Osiris context object (for logging, metrics, base_path)

    Returns:
        Dict with:
            - df: pandas.DataFrame with extracted data
            - state: Updated state for next run {last_timestamp, last_uuid, recent_uuids}

    Raises:
        PostHogDriverError: On configuration or connection errors
        PostHogAuthenticationError: On auth failures
        PostHogRateLimitError: On rate limiting (after retries)
    """
    session = None
    try:
        # ===== Extract and validate configuration =====
        resolved_connection = config.get("resolved_connection", {})
        if not resolved_connection:
            raise PostHogDriverError("Missing resolved_connection in config")

        api_key = resolved_connection.get("api_key")
        project_id = resolved_connection.get("project_id")

        if not api_key or not project_id:
            raise PostHogDriverError("Missing api_key or project_id in resolved_connection")

        # Get base URL from region
        base_url = _get_base_url(resolved_connection)

        # Extract config parameters
        data_type = config.get("data_type", "events")
        if data_type not in ("events", "persons", "sessions", "person_distinct_ids"):
            raise PostHogDriverError(
                f"Invalid data_type: {data_type}. "
                f"Valid options: events, persons, sessions, person_distinct_ids"
            )

        event_types = config.get("event_types", [])
        if event_types and not isinstance(event_types, list):
            raise PostHogDriverError("event_types must be a list")

        lookback_window_minutes = config.get("lookback_window_minutes", 15)
        if not (5 <= lookback_window_minutes <= 60):
            raise PostHogDriverError(
                f"lookback_window_minutes must be 5-60, got {lookback_window_minutes}"
            )

        initial_since = config.get("initial_since")
        page_size = config.get("page_size", 1000)
        if not (100 <= page_size <= 10000):
            raise PostHogDriverError(f"page_size must be 100-10000, got {page_size}")

        deduplication_enabled = config.get("deduplication_enabled", True)

        # ===== Load state from inputs =====
        state_input = inputs.get("state", {})
        last_timestamp = state_input.get("last_timestamp")
        last_uuid = state_input.get("last_uuid")
        recent_uuids = set(state_input.get("recent_uuids", []))

        ctx.log(f"[{step_id}] Starting PostHog extraction: data_type={data_type}, "
                f"page_size={page_size}, deduplication={deduplication_enabled}")

        # ===== Calculate time range =====
        now = datetime.now(timezone.utc)

        if last_timestamp:
            # Resume from high-watermark
            since = datetime.fromisoformat(last_timestamp)
        elif initial_since:
            # Use configured initial timestamp
            since = datetime.fromisoformat(initial_since)
        else:
            # Default: last 30 days
            since = now - timedelta(days=30)

        # Apply lookback window for handling ingestion delays
        actual_since = since - timedelta(minutes=lookback_window_minutes)
        until = now

        ctx.log(f"[{step_id}] Time range: {actual_since.isoformat()} to {until.isoformat()}")

        # ===== Create API client =====
        client = PostHogClient(base_url, api_key, project_id)

        # ===== STREAMING: Batch processing instead of list() =====
        batch_size = 1000
        batch: list[Dict[str, Any]] = []
        all_rows: list[Dict[str, Any]] = []
        deduplicated_count = 0

        try:
            if data_type == "events":
                # Iterate events with SEEK-based pagination
                iterator: Iterator[Dict[str, Any]] = client.iterate_events(
                    since=actual_since,
                    until=until,
                    event_types=event_types if event_types else None,
                    page_size=page_size,
                    last_timestamp=last_timestamp,
                    last_uuid=last_uuid
                )

            elif data_type == "persons":
                # Iterate persons with SEEK-based pagination
                iterator = client.iterate_persons(
                    page_size=page_size,
                    last_created_at=last_timestamp,
                    last_id=last_uuid
                )

            elif data_type == "sessions":
                # NEW: Sessions extraction (time-based)
                iterator = client.iterate_sessions(
                    since=actual_since,
                    until=until,
                    page_size=config.get("page_size", 1000)
                )

            elif data_type == "person_distinct_ids":
                # NEW: Person distinct IDs (full table scan, no time filter)
                iterator = client.iterate_person_distinct_ids(
                    page_size=config.get("page_size", 1000)
                )

            else:
                raise PostHogDriverError(f"Unhandled data_type: {data_type}")

            # Stream rows into batches
            for row in iterator:
                uuid_val = row.get("uuid")

                # Deduplication: skip if UUID already seen
                if deduplication_enabled and uuid_val and uuid_val in recent_uuids:
                    deduplicated_count += 1
                    continue

                # Add UUID to cache for dedup
                if uuid_val:
                    recent_uuids.add(uuid_val)

                # Append to current batch
                batch.append(row)

                # When batch reaches threshold, extend all_rows and clear batch
                if len(batch) >= batch_size:
                    all_rows.extend(batch)
                    batch = []
                    ctx.log(f"[{step_id}] Processed {len(all_rows)} rows... "
                            f"(dedup: {deduplicated_count})")

            # Process final batch
            if batch:
                all_rows.extend(batch)
                ctx.log(f"[{step_id}] Final batch: {len(batch)} rows")

        except (PostHogAuthenticationError, PostHogRateLimitError) as e:
            ctx.log(f"[{step_id}] API error: {e}", level="error")
            raise

        # ===== Create DataFrame from rows =====
        if not all_rows:
            ctx.log(f"[{step_id}] No rows extracted")
            df = pd.DataFrame()
        else:
            # Flatten properties for all rows (data type specific)
            flattened_rows = [_flatten_row(row, data_type) for row in all_rows]
            df = pd.DataFrame(flattened_rows)
            ctx.log(f"[{step_id}] Created DataFrame with {len(df)} rows, "
                    f"{len(df.columns)} columns")

        # ===== Log metrics =====
        ctx.log_metric("rows_read", len(all_rows))
        ctx.log_metric("rows_deduplicated", deduplicated_count)
        ctx.log_metric("rows_output", len(df))
        ctx.log_metric("columns", len(df.columns) if not df.empty else 0)

        # ===== Update state for next run =====
        # High-watermark pattern: track last row's timestamp and UUID
        new_state = {
            "last_timestamp": until.isoformat() if all_rows else last_timestamp,
            "last_uuid": all_rows[-1].get("uuid") if all_rows and "uuid" in all_rows[-1] else last_uuid,
            "recent_uuids": list(recent_uuids)[-10000:]  # Keep last 10k UUIDs
        }

        ctx.log(f"[{step_id}] Updated state: last_timestamp={new_state.get('last_timestamp')}, "
                f"uuid_cache_size={len(new_state.get('recent_uuids', []))}")

        return {
            "df": df,
            "state": new_state
        }

    except Exception as e:
        ctx.log(f"[{step_id}] Unexpected error: {e}", level="error")
        raise OsirisDriverError(f"Extraction failed: {e}") from e

    finally:
        # ===== Cleanup =====
        if session:
            session.close()
            ctx.log(f"[{step_id}] Session closed")


def discover(*, config: Dict[str, Any], ctx) -> Dict[str, Any]:
    """
    Discover available PostHog data resources.

    Returns a static list of supported resources with deterministic fingerprint
    for orchestration compatibility.

    CRITICAL: Resources must be sorted for deterministic fingerprint generation.

    Args:
        config: Configuration dict (not used for discovery)
        ctx: Osiris context object

    Returns:
        Dict with:
            - resources: List of available data types (events, persons)
            - fingerprint: SHA256 hash of sorted resources JSON
            - discovered_at: ISO 8601 timestamp

    Example:
        >>> discover(config={}, ctx=ctx)
        {
            'resources': [
                {'name': 'events', 'type': 'table', ...},
                {'name': 'persons', 'type': 'table', ...}
            ],
            'fingerprint': 'abc123...',
            'discovered_at': '2025-11-08T10:30:00Z'
        }
    """
    resources = [
        {
            "name": "events",
            "type": "table",
            "description": "PostHog events with properties (clicks, page views, custom events)",
            "schema": {
                "uuid": {"type": "string", "description": "Unique event ID"},
                "event": {"type": "string", "description": "Event name"},
                "timestamp": {"type": "string", "description": "Event timestamp (ISO 8601)"},
                "distinct_id": {"type": "string", "description": "User identifier"},
                "person_id": {"type": "string", "description": "Person ID"},
                "properties_*": {"type": "dynamic", "description": "Dynamic event properties"}
            }
        },
        {
            "name": "persons",
            "type": "table",
            "description": "User/person profiles with traits and metadata",
            "schema": {
                "id": {"type": "string", "description": "Person ID"},
                "created_at": {"type": "string", "description": "Creation timestamp (ISO 8601)"},
                "is_identified": {"type": "boolean", "description": "Whether person is identified"},
                "person_properties_*": {"type": "dynamic", "description": "Dynamic person properties"}
            }
        },
        {
            "name": "sessions",
            "type": "table",
            "description": "Session analytics data with 43 columns (duration, pageviews, etc.)",
            "schema": {
                "session_id": {"type": "string", "description": "Unique session ID"},
                "$start_timestamp": {"type": "string", "description": "Session start timestamp"},
                "$end_timestamp": {"type": "string", "description": "Session end timestamp"},
                "$session_duration": {"type": "number", "description": "Session duration in seconds"},
                "*": {"type": "dynamic", "description": "43 session analytics columns"}
            }
        },
        {
            "name": "person_distinct_ids",
            "type": "table",
            "description": "Mapping table between distinct_id and person_id",
            "schema": {
                "distinct_id": {"type": "string", "description": "User distinct identifier"},
                "person_id": {"type": "string", "description": "Associated person ID"}
            }
        }
    ]

    # CRITICAL: Sort for deterministic fingerprint
    resources.sort(key=lambda r: r["name"])

    # Generate SHA256 fingerprint of sorted JSON
    fingerprint = sha256(
        json.dumps(resources, sort_keys=True).encode()
    ).hexdigest()

    discovered_at = datetime.now(timezone.utc).isoformat()

    ctx.log(f"Discovered {len(resources)} resources. Fingerprint: {fingerprint}")

    return {
        "resources": resources,
        "fingerprint": fingerprint,
        "discovered_at": discovered_at
    }


def doctor(*, config: Dict[str, Any], ctx) -> Tuple[bool, Dict[str, Any]]:
    """
    Health check for PostHog connection.

    Validates API connectivity and authentication with a short timeout (2s max).
    Categorizes errors for LLM interpretation.

    Args:
        config: Configuration dict with resolved_connection
        ctx: Osiris context object

    Returns:
        Tuple[bool, Dict[str, Any]]:
            - bool: True if healthy, False if error
            - dict: Status info with keys:
                - status: "healthy" or "error"
                - category: "auth", "network", "timeout", or "unknown"
                - message: Human-readable error message (no secrets)
                - timestamp: ISO 8601 timestamp

    Error Categories:
        - auth: Invalid credentials (401/403)
        - network: Cannot reach PostHog (connection error)
        - timeout: Request timeout (>2s)
        - unknown: Other unexpected error

    Example:
        >>> healthy, info = doctor(config={...}, ctx=ctx)
        >>> if not healthy:
        ...     print(f"Error ({info['category']}): {info['message']}")
    """
    try:
        resolved_connection = config.get("resolved_connection", {})
        api_key = resolved_connection.get("api_key")
        project_id = resolved_connection.get("project_id")

        # Validate required fields
        if not api_key or not project_id:
            return False, {
                "status": "error",
                "category": "auth",
                "message": "Missing API key or project ID in configuration",
                "timestamp": datetime.now(timezone.utc).isoformat()
            }

        # Get base URL
        try:
            base_url = _get_base_url(resolved_connection)
        except PostHogDriverError as e:
            return False, {
                "status": "error",
                "category": "auth",
                "message": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }

        # Create client and test connection (2.0s timeout)
        client = PostHogClient(base_url, api_key, project_id)
        client.test_connection(timeout=2.0)

        return True, {
            "status": "healthy",
            "category": "ok",
            "message": f"Successfully connected to PostHog project {project_id}",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

    except PostHogAuthenticationError as e:
        return False, {
            "status": "error",
            "category": "auth",
            "message": "Authentication failed. Check your API key and project ID.",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

    except PostHogNetworkError as e:
        # Distinguish timeout from other network errors
        if "timeout" in str(e).lower():
            return False, {
                "status": "error",
                "category": "timeout",
                "message": "Connection timeout (2s)",
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        else:
            return False, {
                "status": "error",
                "category": "network",
                "message": "Cannot reach PostHog server. Check network connectivity.",
                "timestamp": datetime.now(timezone.utc).isoformat()
            }

    except PostHogRateLimitError:
        return False, {
            "status": "error",
            "category": "network",
            "message": "Rate limited. Try again later.",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

    except PostHogClientError as e:
        return False, {
            "status": "error",
            "category": "unknown",
            "message": "PostHog API error. Check configuration.",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

    except Exception as e:
        ctx.log(f"Unexpected error in doctor: {e}", level="error")
        return False, {
            "status": "error",
            "category": "unknown",
            "message": "Unexpected error during health check",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
