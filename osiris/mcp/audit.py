"""
Audit logging for Osiris MCP server.

Tracks all tool invocations for observability and compliance.
"""

import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

logger = logging.getLogger(__name__)


class AuditLogger:
    """Audit logger for MCP tool invocations."""

    def __init__(self, log_dir: Optional[Path] = None):
        """
        Initialize the audit logger.

        Args:
            log_dir: Directory for audit logs. Defaults to .osiris_audit/
        """
        self.log_dir = log_dir or Path.home() / ".osiris_audit"
        self.log_dir.mkdir(parents=True, exist_ok=True)

        # Create audit log file with daily rotation
        today = datetime.now(timezone.utc).strftime("%Y%m%d")
        self.log_file = self.log_dir / f"mcp_audit_{today}.jsonl"

        # Session tracking
        self.session_id = self._generate_session_id()
        self.tool_call_counter = 0

    def _generate_session_id(self) -> str:
        """Generate a unique session ID."""
        import uuid
        return f"mcp_{uuid.uuid4().hex[:12]}"

    async def log_tool_call(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        correlation_id: Optional[str] = None
    ) -> str:
        """
        Log a tool invocation.

        Args:
            tool_name: Name of the tool being called
            arguments: Tool arguments (will be sanitized)
            correlation_id: Optional correlation ID for tracing

        Returns:
            Event ID for this audit entry
        """
        self.tool_call_counter += 1

        # Generate event ID
        event_id = f"ev_{self.session_id}_{self.tool_call_counter}"

        # Sanitize arguments (remove sensitive data)
        sanitized_args = self._sanitize_arguments(arguments)

        # Create audit event
        event = {
            "event": "tool_call",
            "event_id": event_id,
            "session_id": self.session_id,
            "correlation_id": correlation_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "timestamp_ms": int(time.time() * 1000),
            "tool": tool_name,
            "arguments": sanitized_args,
            "call_number": self.tool_call_counter
        }

        # Write to audit log
        await self._write_event(event)

        # Also log to standard logger
        logger.info(f"Tool call: {tool_name} (event_id={event_id})")

        return event_id

    async def log_tool_result(
        self,
        event_id: str,
        success: bool,
        duration_ms: int,
        payload_bytes: int,
        error: Optional[str] = None
    ):
        """
        Log the result of a tool invocation.

        Args:
            event_id: Event ID from log_tool_call
            success: Whether the tool call succeeded
            duration_ms: Duration in milliseconds
            payload_bytes: Size of the response payload
            error: Error message if failed
        """
        event = {
            "event": "tool_result",
            "event_id": event_id,
            "session_id": self.session_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "timestamp_ms": int(time.time() * 1000),
            "status": "ok" if success else "error",
            "duration_ms": duration_ms,
            "payload_bytes": payload_bytes
        }

        if error:
            event["error"] = error

        await self._write_event(event)

    async def log_resource_access(
        self,
        resource_uri: str,
        operation: str,
        success: bool
    ):
        """
        Log resource access.

        Args:
            resource_uri: URI of the resource
            operation: Operation performed (read, write, etc.)
            success: Whether the operation succeeded
        """
        event = {
            "event": "resource_access",
            "session_id": self.session_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "timestamp_ms": int(time.time() * 1000),
            "resource_uri": resource_uri,
            "operation": operation,
            "status": "ok" if success else "error"
        }

        await self._write_event(event)

    def _sanitize_arguments(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        Sanitize arguments to remove sensitive data.

        Args:
            arguments: Original arguments

        Returns:
            Sanitized arguments
        """
        sanitized = {}

        for key, value in arguments.items():
            # Redact known sensitive fields
            if key in ["password", "secret", "token", "api_key", "private_key"]:
                sanitized[key] = "***REDACTED***"
            elif key == "connection_string" and isinstance(value, str):
                # Redact connection strings
                sanitized[key] = self._redact_connection_string(value)
            elif isinstance(value, dict):
                # Recursively sanitize nested dicts
                sanitized[key] = self._sanitize_arguments(value)
            elif isinstance(value, list):
                # Sanitize list items if they're dicts
                sanitized[key] = [
                    self._sanitize_arguments(item) if isinstance(item, dict) else item
                    for item in value
                ]
            else:
                sanitized[key] = value

        return sanitized

    def _redact_connection_string(self, conn_str: str) -> str:
        """
        Redact sensitive parts of a connection string.

        Args:
            conn_str: Original connection string

        Returns:
            Redacted connection string
        """
        import re

        # Pattern for DSN-style connection strings
        dsn_pattern = r"(.*://)(.*?)(@.*)"
        match = re.match(dsn_pattern, conn_str)

        if match:
            scheme = match.group(1)
            host_part = match.group(3)
            return f"{scheme}***{host_part}"

        # If not a DSN, return partially redacted
        if len(conn_str) > 10:
            return f"{conn_str[:5]}***{conn_str[-5:]}"

        return "***"

    async def _write_event(self, event: Dict[str, Any]):
        """Write an event to the audit log."""
        try:
            # Append to JSONL file
            async with asyncio.Lock():
                with open(self.log_file, "a") as f:
                    f.write(json.dumps(event) + "\n")
        except Exception as e:
            logger.error(f"Failed to write audit event: {e}")

    def get_session_summary(self) -> Dict[str, Any]:
        """Get a summary of the current session."""
        return {
            "session_id": self.session_id,
            "tool_calls": self.tool_call_counter,
            "audit_file": str(self.log_file)
        }