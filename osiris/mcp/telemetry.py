"""
Telemetry module for Osiris MCP server.

Emits structured telemetry events for observability and monitoring.
"""

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class TelemetryEmitter:
    """Emits telemetry events for MCP operations."""

    def __init__(self, enabled: bool = True, output_dir: Optional[Path] = None):
        """
        Initialize telemetry emitter.

        Args:
            enabled: Whether telemetry is enabled
            output_dir: Directory for telemetry output (defaults to .osiris_telemetry/)
        """
        self.enabled = enabled
        self.output_dir = output_dir or Path.home() / ".osiris_telemetry"

        if self.enabled:
            self.output_dir.mkdir(parents=True, exist_ok=True)
            # Create daily telemetry file
            today = datetime.now(timezone.utc).strftime("%Y%m%d")
            self.telemetry_file = self.output_dir / f"mcp_telemetry_{today}.jsonl"

        # Session tracking
        self.session_id = self._generate_session_id()
        self.metrics = {
            "tool_calls": 0,
            "total_bytes_in": 0,
            "total_bytes_out": 0,
            "total_duration_ms": 0,
            "errors": 0
        }

    def _generate_session_id(self) -> str:
        """Generate a unique session ID."""
        import uuid
        return f"tel_{uuid.uuid4().hex[:12]}"

    def emit_tool_call(
        self,
        tool: str,
        status: str,
        duration_ms: int,
        bytes_in: int,
        bytes_out: int,
        error: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
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

        # Update metrics
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
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "timestamp_ms": int(time.time() * 1000),
            "tool": tool,
            "status": status,
            "duration_ms": duration_ms,
            "bytes_in": bytes_in,
            "bytes_out": bytes_out
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
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "timestamp_ms": int(time.time() * 1000),
            "version": version,
            "protocol_version": protocol_version
        }

        try:
            with open(self.telemetry_file, "a") as f:
                f.write(json.dumps(event) + "\n")
        except Exception as e:
            logger.error(f"Failed to write server start event: {e}")

    def emit_server_stop(self, reason: Optional[str] = None):
        """
        Emit server stop event with session summary.

        Args:
            reason: Reason for stopping (e.g., "shutdown", "error")
        """
        if not self.enabled:
            return

        event = {
            "event": "server_stop",
            "session_id": self.session_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "timestamp_ms": int(time.time() * 1000),
            "reason": reason or "normal",
            "metrics": self.metrics
        }

        try:
            with open(self.telemetry_file, "a") as f:
                f.write(json.dumps(event) + "\n")
        except Exception as e:
            logger.error(f"Failed to write server stop event: {e}")

    def emit_handshake(self, duration_ms: int, success: bool, client_info: Optional[Dict[str, Any]] = None):
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
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "timestamp_ms": int(time.time() * 1000),
            "duration_ms": duration_ms,
            "success": success
        }

        if client_info:
            event["client_info"] = client_info

        try:
            with open(self.telemetry_file, "a") as f:
                f.write(json.dumps(event) + "\n")
        except Exception as e:
            logger.error(f"Failed to write handshake event: {e}")

    def get_session_summary(self) -> Dict[str, Any]:
        """Get summary of current telemetry session."""
        return {
            "session_id": self.session_id,
            "metrics": self.metrics,
            "telemetry_file": str(self.telemetry_file) if self.enabled else None,
            "enabled": self.enabled
        }


# Global telemetry instance (can be configured at startup)
_telemetry: Optional[TelemetryEmitter] = None


def get_telemetry() -> Optional[TelemetryEmitter]:
    """Get the global telemetry instance."""
    return _telemetry


def init_telemetry(enabled: bool = True, output_dir: Optional[Path] = None) -> TelemetryEmitter:
    """
    Initialize global telemetry.

    Args:
        enabled: Whether to enable telemetry
        output_dir: Directory for telemetry output

    Returns:
        Telemetry emitter instance
    """
    global _telemetry
    _telemetry = TelemetryEmitter(enabled, output_dir)
    return _telemetry