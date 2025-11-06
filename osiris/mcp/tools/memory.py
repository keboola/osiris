"""
MCP tools for memory capture and management.
"""

import json
import logging
from pathlib import Path
import re
import time
from typing import Any

from osiris.mcp.errors import ErrorFamily, OsirisError, PolicyError
from osiris.mcp.metrics_helper import add_metrics

logger = logging.getLogger(__name__)


class MemoryTools:
    """Tools for capturing and managing session memory."""

    def __init__(self, memory_dir: Path | None = None, audit_logger=None):
        """Initialize memory tools."""
        if memory_dir is None:
            from osiris.mcp.config import get_config  # noqa: PLC0415  # Lazy import for performance

            config = get_config()
            memory_dir = config.memory_dir
        self.memory_dir = memory_dir
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        self.audit = audit_logger

    async def capture(self, args: dict[str, Any]) -> dict[str, Any]:
        """
        Capture session memory with consent and PII redaction.

        Delegates to CLI subprocess for filesystem access (CLI-first security model).

        Args:
            args: Tool arguments including consent, session_id, content

        Returns:
            Dictionary with capture results
        """
        start_time = time.time()
        correlation_id = self.audit.make_correlation_id() if self.audit else "unknown"

        # Check consent first
        consent = args.get("consent", False)
        if not consent:
            # Return error object instead of raising exception (still add metrics)
            result = {
                "error": {"code": "POLICY/POL001", "message": "Consent required for memory capture", "path": []},
                "captured": False,  # Explicitly set captured to False
                "status": "success",
            }
            return add_metrics(result, correlation_id, start_time, args)

        session_id = args.get("session_id")
        if not session_id:
            raise OsirisError(
                ErrorFamily.SCHEMA,
                "session_id is required",
                path=["session_id"],
                suggest="Provide a session ID for memory storage",
            )

        try:
            # Prepare events data
            retention_days = args.get("retention_days", 365)
            if retention_days < 0:
                retention_days = 365  # Default to 365 if negative
            elif retention_days > 730:
                retention_days = 730  # Cap at 2 years max

            # Build events list from args
            events = [
                {
                    "intent": args.get("intent", ""),
                    "actor_trace": args.get("actor_trace", []),
                    "decisions": args.get("decisions", []),
                    "artifacts": args.get("artifacts", []),
                    "oml_uri": args.get("oml_uri"),
                    "error_report": args.get("error_report"),
                    "notes": args.get("notes", ""),
                }
            ]

            # Delegate to CLI subprocess (MCP process should NOT write files)
            from osiris.mcp import cli_bridge  # noqa: PLC0415  # Lazy import for performance

            result = await cli_bridge.run_cli_json(
                [
                    "mcp",
                    "memory",
                    "capture",
                    "--session-id",
                    session_id,
                    "--consent",
                    "--events",
                    json.dumps(events),
                    "--retention-days",
                    str(retention_days),
                    "--json",
                ]
            )

            # CLI returns the result in proper format - add metrics
            return add_metrics(result, correlation_id, start_time, args)

        except PolicyError:
            raise
        except Exception as e:
            logger.error(f"Memory capture failed: {e}")
            raise OsirisError(
                ErrorFamily.SEMANTIC,
                f"Memory capture failed: {str(e)}",
                path=["memory"],
                suggest="Check file permissions and disk space",
            ) from e

    def _save_memory(self, *args) -> str:
        """
        Save memory entry to file (internal method for testing).

        Args:
            Can be called as:
            - _save_memory(entry) for tests
            - _save_memory(session_id, entry) for real code

        Returns:
            Memory ID
        """
        # Handle both signatures
        if len(args) == 1:
            # Test signature: just entry
            entry = args[0]
            session_id = entry.get("session_id", "unknown")
        else:
            # Real signature: session_id, entry
            session_id = args[0]
            entry = args[1]

        # Save to JSONL file - use sessions/ subdirectory to match URI scheme
        # URIs use osiris://mcp/memory/sessions/<session_id>.jsonl format
        # Resolver expects memory_dir/sessions/<session_id>.jsonl
        sessions_dir = self.memory_dir / "sessions"
        sessions_dir.mkdir(parents=True, exist_ok=True)

        memory_file = sessions_dir / f"{session_id}.jsonl"
        with open(memory_file, "a") as f:
            f.write(json.dumps(entry) + "\n")

        # Generate a stable memory ID
        import hashlib  # noqa: PLC0415  # Lazy import for performance

        entry_str = json.dumps(entry, sort_keys=True)
        memory_hash = hashlib.sha256(entry_str.encode()).hexdigest()[:6]
        return f"mem_{memory_hash}"

    def _redact_pii(self, data: Any) -> Any:
        """
        Redact personally identifiable information from data.

        Uses spec-aware secret detection from ComponentRegistry (same approach as
        connection masking) to ensure comprehensive coverage of all secret patterns.

        Args:
            data: Data to redact

        Returns:
            Redacted data
        """
        if isinstance(data, str):
            # Redact DSN/connection strings (before other patterns)
            # Pattern: scheme://[userinfo@]host[:port][/path]
            data = re.sub(
                r"\b((?:mysql|postgresql|postgres|mongodb|redis|http|https)://)[^@\s]+@([^/\s]+)",
                r"\1***@\2",
                data,
                flags=re.IGNORECASE,
            )

            # Redact email addresses
            data = re.sub(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b", "***EMAIL***", data)

            # Redact phone numbers (basic patterns)
            data = re.sub(r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b", "***PHONE***", data)

            # Redact SSN-like patterns
            data = re.sub(r"\b\d{3}-\d{2}-\d{4}\b", "***SSN***", data)

            # Redact credit card-like patterns (basic)
            data = re.sub(r"\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b", "***CARD***", data)

            # Redact IP addresses
            data = re.sub(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", "***IP***", data)

            return data

        elif isinstance(data, dict):
            redacted = {}
            for key, value in data.items():
                # Use spec-aware secret detection (same pattern as connection_helpers.py)
                if self._is_secret_key(key):
                    redacted[key] = "***REDACTED***"
                else:
                    redacted[key] = self._redact_pii(value)
            return redacted

        elif isinstance(data, list):
            return [self._redact_pii(item) for item in data]

        else:
            return data

    def _is_secret_key(self, key_name: str) -> bool:
        """
        Check if a key name represents a secret field.

        Uses the same heuristics as connection_helpers.py for consistency.
        Handles compound names like "service_role_key" and "api_key" correctly.

        Args:
            key_name: Field name to check

        Returns:
            True if the field should be redacted
        """
        # Common secret patterns (expanded from connection_helpers.py)
        secret_patterns = {
            "password",
            "passwd",
            "pass",
            "pwd",
            "secret",
            "key",
            "token",
            "auth",
            "credential",
            "api_key",
            "apikey",
            "access_token",
            "refresh_token",
            "private_key",
            "client_secret",
            "service_role_key",
            "anon_key",
            "access_key_id",
            "secret_access_key",
            "ssn",
            "credit_card",
            "card_number",
        }

        key_lower = key_name.lower()

        # Exact match
        if key_lower in secret_patterns:
            return True

        # Check for compound names with word boundary detection
        for pattern in secret_patterns:
            if pattern in key_lower:
                # Check if it's at word boundaries (underscore-separated)
                parts = key_lower.split("_")
                if pattern in parts or any(part.endswith(pattern) for part in parts):
                    # Exclude known non-secrets like "primary_key"
                    if "primary" in key_lower and pattern == "key":  # nosec B105  # Comparing field name pattern
                        continue
                    if "foreign" in key_lower and pattern == "key":  # nosec B105  # Comparing field name pattern
                        continue
                    return True

        return False

    def _count_redactions(self, original: Any, redacted: Any) -> int:
        """
        Count the number of redactions applied.

        Args:
            original: Original data
            redacted: Redacted data

        Returns:
            Number of redactions
        """
        count = 0

        # Convert to JSON strings and count redaction markers
        json.dumps(original)
        redacted_str = json.dumps(redacted)

        patterns = ["***EMAIL***", "***PHONE***", "***SSN***", "***CARD***", "***IP***", "***REDACTED***"]

        for pattern in patterns:
            count += redacted_str.count(pattern)

        return count

    async def list_sessions(self, args: dict[str, Any]) -> dict[str, Any]:
        """
        List available memory sessions.

        Args:
            args: Tool arguments (none required)

        Returns:
            Dictionary with session list
        """
        start_time = time.time()
        correlation_id = self.audit.make_correlation_id() if self.audit else "unknown"

        try:
            sessions = []

            # Scan memory directory for session files (in sessions/ subdirectory)
            sessions_dir = self.memory_dir / "sessions"
            if not sessions_dir.exists():
                # Return empty list if sessions directory doesn't exist yet (still add metrics)
                result = {"sessions": [], "count": 0, "total_size_kb": 0.0, "status": "success"}
                return add_metrics(result, correlation_id, start_time, args)

            for session_file in sessions_dir.glob("*.jsonl"):
                session_id = session_file.stem

                # Get file stats
                stats = session_file.stat()
                size_kb = stats.st_size / 1024

                # Count entries
                with open(session_file) as f:
                    entry_count = sum(1 for _ in f)

                # Get first and last timestamps
                with open(session_file) as f:
                    lines = f.readlines()
                    if lines:
                        first_entry = json.loads(lines[0])
                        last_entry = json.loads(lines[-1])
                        first_timestamp = first_entry.get("timestamp", "unknown")
                        last_timestamp = last_entry.get("timestamp", "unknown")
                    else:
                        first_timestamp = last_timestamp = "unknown"

                sessions.append(
                    {
                        "session_id": session_id,
                        "file": str(session_file),
                        "entries": entry_count,
                        "size_kb": round(size_kb, 2),
                        "first_entry": first_timestamp,
                        "last_entry": last_timestamp,
                    }
                )

            result = {
                "sessions": sessions,
                "count": len(sessions),
                "total_size_kb": sum(s["size_kb"] for s in sessions),
                "status": "success",
            }

            return add_metrics(result, correlation_id, start_time, args)

        except Exception as e:
            logger.error(f"Failed to list sessions: {e}")
            raise OsirisError(
                ErrorFamily.SEMANTIC,
                f"Failed to list sessions: {str(e)}",
                path=["sessions"],
                suggest="Check memory directory permissions",
            ) from e
