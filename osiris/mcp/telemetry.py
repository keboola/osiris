"""
Telemetry module for Osiris MCP server.

Emits structured telemetry events for observability and monitoring.
"""

from datetime import UTC, datetime
import json
import logging
from pathlib import Path
import threading
import time
from typing import Any

logger = logging.getLogger(__name__)

# Payload truncation limits (2-4 KB)
MAX_PAYLOAD_PREVIEW_BYTES = 4096
MIN_PAYLOAD_PREVIEW_BYTES = 2048


class TelemetryEmitter:
    """Emits telemetry events for MCP operations."""

    def __init__(self, enabled: bool = True, output_dir: Path | None = None):
        """
        Initialize telemetry emitter.

        Args:
            enabled: Whether telemetry is enabled
            output_dir: Directory for telemetry output (from MCPFilesystemConfig)
        """
        self.enabled = enabled
        if output_dir is None:
            raise ValueError("output_dir is required (no Path.home() usage allowed)")
        self.output_dir = output_dir
        self._metrics_lock = threading.Lock()

        if self.enabled:
            self.output_dir.mkdir(parents=True, exist_ok=True)
            # Create daily telemetry file
            today = datetime.now(UTC).strftime("%Y%m%d")
            self.telemetry_file = self.output_dir / f"mcp_telemetry_{today}.jsonl"

        # Session tracking
        self.session_id = self._generate_session_id()
        self.metrics = {"tool_calls": 0, "total_bytes_in": 0, "total_bytes_out": 0, "total_duration_ms": 0, "errors": 0}

    def _generate_session_id(self) -> str:
        """Generate a unique session ID."""
        import uuid  # noqa: PLC0415  # Lazy import for performance

        return f"tel_{uuid.uuid4().hex[:12]}"

    def _truncate_payload(self, payload: Any) -> str:
        """
        Truncate payload to 2-4 KB for telemetry storage.

        Args:
            payload: Payload to truncate (any JSON-serializable type)

        Returns:
            Truncated JSON string representation
        """
        try:
            # Convert to JSON string
            payload_str = json.dumps(payload)
            payload_bytes = len(payload_str.encode("utf-8"))

            # If within limits, return as-is
            if payload_bytes <= MAX_PAYLOAD_PREVIEW_BYTES:
                return payload_str

            # Truncate to minimum size
            truncated = payload_str[:MIN_PAYLOAD_PREVIEW_BYTES]
            return f"{truncated}... [TRUNCATED: {payload_bytes} bytes total]"
        except Exception as e:
            logger.warning(f"Failed to truncate payload: {e}")
            return "[PAYLOAD TRUNCATION FAILED]"

    def _redact_secrets(self, data: Any) -> Any:
        """
        Redact secrets from data using spec-aware helper.

        Args:
            data: Data to redact (dict, list, or primitive)

        Returns:
            Copy of data with secrets redacted
        """
        from osiris.cli.helpers.connection_helpers import (  # noqa: PLC0415  # Lazy import
            mask_connection_for_display,
        )

        if isinstance(data, dict):
            # Use spec-aware masking for dict data
            return mask_connection_for_display(data)
        elif isinstance(data, list):
            return [self._redact_secrets(item) for item in data]
        else:
            # Primitives pass through
            return data

    def emit_tool_call(
        self,
        tool: str,
        status: str,
        duration_ms: int,
        bytes_in: int,
        bytes_out: int,
        error: str | None = None,
        metadata: dict[str, Any] | None = None,
    ):
        """
        Emit a tool call telemetry event.

        Args:
            tool: Tool name that was called
            status: Status of the call (ok/error)
            duration_ms: Duration in milliseconds
            bytes_in: Input payload size in bytes
            bytes_out: Output payload size in bytes
            error: Error message if status is error
            metadata: Additional metadata
        """
        if not self.enabled:
            return

        # Update metrics (protected by lock to prevent race conditions)
        with self._metrics_lock:
            self.metrics["tool_calls"] += 1
            self.metrics["total_bytes_in"] += bytes_in
            self.metrics["total_bytes_out"] += bytes_out
            self.metrics["total_duration_ms"] += duration_ms
            if status == "error":
                self.metrics["errors"] += 1

        # Create event
        event = {
            "event": "tool_call",
            "session_id": self.session_id,
            "timestamp": datetime.now(UTC).isoformat(),
            "timestamp_ms": int(time.time() * 1000),
            "tool": tool,
            "status": status,
            "duration_ms": duration_ms,
            "bytes_in": bytes_in,
            "bytes_out": bytes_out,
        }

        if error:
            event["error"] = error

        if metadata:
            event["metadata"] = metadata

        # Write to telemetry file
        try:
            with open(self.telemetry_file, "a") as f:
                f.write(json.dumps(event) + "\n")
        except Exception as e:
            logger.error(f"Failed to write telemetry event: {e}")

        # Also log to standard logger at debug level
        logger.debug(f"Telemetry: {tool} - {status} ({duration_ms}ms, {bytes_in}B in, {bytes_out}B out)")

    def emit_server_start(self, version: str, protocol_version: str):
        """
        Emit server start event.

        Args:
            version: Server version
            protocol_version: MCP protocol version
        """
        if not self.enabled:
            return

        event = {
            "event": "server_start",
            "session_id": self.session_id,
            "timestamp": datetime.now(UTC).isoformat(),
            "timestamp_ms": int(time.time() * 1000),
            "version": version,
            "protocol_version": protocol_version,
        }

        try:
            with open(self.telemetry_file, "a") as f:
                f.write(json.dumps(event) + "\n")
        except Exception as e:
            logger.error(f"Failed to write server start event: {e}")

    def emit_server_stop(self, reason: str | None = None):
        """
        Emit server stop event with session summary.

        Args:
            reason: Reason for stopping (e.g., "shutdown", "error")
        """
        if not self.enabled:
            return

        with self._metrics_lock:
            metrics_copy = self.metrics.copy()

        event = {
            "event": "server_stop",
            "session_id": self.session_id,
            "timestamp": datetime.now(UTC).isoformat(),
            "timestamp_ms": int(time.time() * 1000),
            "reason": reason or "normal",
            "metrics": metrics_copy,
        }

        try:
            with open(self.telemetry_file, "a") as f:
                f.write(json.dumps(event) + "\n")
        except Exception as e:
            logger.error(f"Failed to write server stop event: {e}")

    def emit_handshake(self, duration_ms: int, success: bool, client_info: dict[str, Any] | None = None):
        """
        Emit handshake event.

        Args:
            duration_ms: Handshake duration in milliseconds
            success: Whether handshake succeeded
            client_info: Client information from handshake
        """
        if not self.enabled:
            return

        event = {
            "event": "handshake",
            "session_id": self.session_id,
            "timestamp": datetime.now(UTC).isoformat(),
            "timestamp_ms": int(time.time() * 1000),
            "duration_ms": duration_ms,
            "success": success,
        }

        if client_info:
            event["client_info"] = client_info

        try:
            with open(self.telemetry_file, "a") as f:
                f.write(json.dumps(event) + "\n")
        except Exception as e:
            logger.error(f"Failed to write handshake event: {e}")

    def get_session_summary(self) -> dict[str, Any]:
        """Get summary of current telemetry session."""
        with self._metrics_lock:
            metrics_copy = self.metrics.copy()
        return {
            "session_id": self.session_id,
            "metrics": metrics_copy,
            "telemetry_file": str(self.telemetry_file) if self.enabled else None,
            "enabled": self.enabled,
        }


# Global telemetry instance (can be configured at startup)
_telemetry: TelemetryEmitter | None = None
_telemetry_lock = threading.Lock()


def get_telemetry() -> TelemetryEmitter | None:
    """Get the global telemetry instance."""
    return _telemetry


def init_telemetry(enabled: bool = True, output_dir: Path | None = None) -> TelemetryEmitter:
    """
    Initialize global telemetry.

    Args:
        enabled: Whether to enable telemetry
        output_dir: Directory for telemetry output (required, no Path.home() fallback)

    Returns:
        Telemetry emitter instance
    """
    global _telemetry
    with _telemetry_lock:
        if _telemetry is None:
            if output_dir is None:
                raise ValueError("output_dir is required for telemetry initialization")
            _telemetry = TelemetryEmitter(enabled, output_dir)
    return _telemetry
