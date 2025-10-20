"""
Audit logging for Osiris MCP server.

Tracks all tool invocations for observability and compliance.
"""

import asyncio
from datetime import UTC, datetime
import json
import logging
from pathlib import Path
import time
from typing import Any

logger = logging.getLogger(__name__)


class AuditLogger:
    """Audit logger for MCP tool invocations."""

    def __init__(self, log_dir: Path | None = None):
        """
        Initialize the audit logger.

        Args:
            log_dir: Directory for audit logs (from MCPFilesystemConfig, required)
        """
        if log_dir is None:
            raise ValueError("log_dir is required (no Path.home() usage allowed)")
        self.log_dir = log_dir
        self.log_dir.mkdir(parents=True, exist_ok=True)

        # Create audit log file with daily rotation
        today = datetime.now(UTC).strftime("%Y%m%d")
        self.log_file = self.log_dir / f"mcp_audit_{today}.jsonl"

        # Session tracking
        self.session_id = self._generate_session_id()
        self.tool_call_counter = 0

        # Create lock for concurrent write protection
        self._write_lock = asyncio.Lock()

    def _generate_session_id(self) -> str:
        """Generate a unique session ID."""
        import uuid  # noqa: PLC0415  # Lazy import for performance

        return f"mcp_{uuid.uuid4().hex[:12]}"

    def make_correlation_id(self) -> str:
        """Generate a correlation ID with mcp_ prefix."""
        self.tool_call_counter += 1
        return f"mcp_{self.session_id}_{self.tool_call_counter}"

    async def log_tool_call(
        self,
        tool: str = None,
        params_bytes: int = None,
        correlation_id: str = None,
        # Support old test API
        tool_name: str = None,
        arguments: dict[str, Any] = None,
    ) -> str:
        """
        Log a tool invocation.

        Args:
            tool: Name of the tool being called
            params_bytes: Size of parameters in bytes
            correlation_id: Correlation ID for tracing
            tool_name: (test compat) Tool name
            arguments: (test compat) Arguments

        Returns:
            Correlation ID (for test compat)
        """
        # Handle test compatibility
        if tool_name:
            tool = tool_name
        if arguments is not None and params_bytes is None:
            params_bytes = len(json.dumps(arguments))
        if not correlation_id:
            correlation_id = self.make_correlation_id()

        # Create audit event (with test-expected fields)
        event = {
            "event": "tool_call",
            "event_type": "tool_call_started",  # Test expects this
            "tool": tool,
            "tool_name": tool,  # Test expects this
            "correlation_id": correlation_id,
            "bytes_in": params_bytes or 0,
            "arguments": arguments or {},  # Test expects this
        }

        # Write to audit log
        await self._write_event(event)

        # Also log to standard logger
        logger.info(f"Tool call: {tool} (correlation_id={correlation_id})")

        return correlation_id

    async def log_tool_result(
        self,
        tool: str = None,
        duration_ms: int = None,
        result_bytes: int = None,
        correlation_id: str = None,
        # Test compat
        event_id: str = None,
        success: bool = None,
        payload_bytes: int = None,
        result: Any = None,
    ) -> None:
        """
        Log the result of a tool invocation.

        Args:
            tool: Tool name
            duration_ms: Duration in milliseconds
            result_bytes: Size of the response payload
            correlation_id: Correlation ID for tracing
        """
        # Handle test compat
        if event_id:
            correlation_id = event_id
        if payload_bytes is not None:
            result_bytes = payload_bytes

        event = {
            "event": "tool_result",
            "event_type": "tool_call_completed",  # Test expects this
            "tool": tool or "unknown",
            "correlation_id": correlation_id or "",
            "duration_ms": duration_ms or 0,
            "bytes_out": result_bytes or 0,
            "result": result,  # Test expects this
        }

        await self._write_event(event)

    async def log_tool_error(
        self,
        tool: str = None,
        duration_ms: int = None,
        error_code: str = None,
        correlation_id: str = None,
        # Test compat
        event_id: str = None,
        error: str = None,
    ) -> None:
        """
        Log a tool error.

        Args:
            tool: Tool name
            duration_ms: Duration in milliseconds
            error_code: Error code
            correlation_id: Correlation ID for tracing
        """
        # Handle test compat
        if event_id:
            correlation_id = event_id
        if error and not error_code:
            error_code = "ERROR"

        event = {
            "event": "tool_error",
            "event_type": "tool_call_failed",  # Test expects this
            "tool": tool or "unknown",
            "correlation_id": correlation_id or "",
            "duration_ms": duration_ms or 0,
            "error_code": error_code or "UNKNOWN",
            "error": error,  # Test expects this
        }

        await self._write_event(event)

    async def log_resource_access(self, resource_uri: str, operation: str, success: bool):
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
            "timestamp": datetime.now(UTC).isoformat(),
            "timestamp_ms": int(time.time() * 1000),
            "resource_uri": resource_uri,
            "operation": operation,
            "status": "ok" if success else "error",
        }

        await self._write_event(event)

    def _sanitize_arguments(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """
        Sanitize arguments to remove sensitive data using spec-aware masking.

        Args:
            arguments: Original arguments

        Returns:
            Sanitized arguments
        """
        from osiris.cli.helpers.connection_helpers import (  # noqa: PLC0415  # Lazy import
            mask_connection_for_display,
        )

        # Use spec-aware masking from shared helpers
        return mask_connection_for_display(arguments)

    async def _write_event(self, event: dict[str, Any]):
        """Write an event to the audit log."""
        try:
            # Append to JSONL file
            async with self._write_lock:
                with open(self.log_file, "a") as f:
                    f.write(json.dumps(event) + "\n")
        except Exception as e:
            logger.error(f"Failed to write audit event: {e}")

    def get_session_summary(self) -> dict[str, Any]:
        """Get a summary of the current session."""
        return {"session_id": self.session_id, "tool_calls": self.tool_call_counter, "audit_file": str(self.log_file)}
