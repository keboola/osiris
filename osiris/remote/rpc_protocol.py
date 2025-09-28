"""JSON-RPC Protocol for E2B Transparent Proxy.

This module defines the message protocol between the host orchestrator
and the ProxyWorker running inside the E2B sandbox.
"""

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class CommandType(str, Enum):
    """Command types sent from host to worker."""

    PREPARE = "prepare"
    EXEC_STEP = "exec_step"
    CLEANUP = "cleanup"
    PING = "ping"


class ResponseStatus(str, Enum):
    """Response status from worker."""

    READY = "ready"
    COMPLETE = "complete"
    CLEANED = "cleaned"
    PONG = "pong"
    ERROR = "error"


class MessageType(str, Enum):
    """Message types from worker to host."""

    RESPONSE = "response"
    EVENT = "event"
    METRIC = "metric"
    ERROR = "error"


# Request Messages (Host → Worker)


class PrepareCommand(BaseModel):
    """Initialize session in the sandbox."""

    cmd: Literal[CommandType.PREPARE] = Field(default=CommandType.PREPARE)
    session_id: str = Field(..., description="Session ID from host")
    manifest: dict[str, Any] = Field(..., description="Compiled manifest data")
    log_level: str | None = Field("INFO", description="Logging level")
    install_deps: bool | None = Field(False, description="Auto-install missing dependencies")


class ExecStepCommand(BaseModel):
    """Execute a pipeline step."""

    cmd: Literal[CommandType.EXEC_STEP] = Field(default=CommandType.EXEC_STEP)
    step_id: str = Field(..., description="Step identifier")
    driver: str = Field(..., description="Driver name (e.g., 'mysql.extractor')")
    config: dict[str, Any] | None = Field(None, description="Step configuration (deprecated, use cfg_path)")
    cfg_path: str | None = Field(None, description="Path to config file (file-only contract)")
    inputs: dict[str, Any] | None = Field(None, description="Symbolic input references or actual data")


class CleanupCommand(BaseModel):
    """Finalize session and cleanup resources."""

    cmd: Literal[CommandType.CLEANUP] = Field(default=CommandType.CLEANUP)


class PingCommand(BaseModel):
    """Health check command."""

    cmd: Literal[CommandType.PING] = Field(default=CommandType.PING)
    data: str | None = Field(None, description="Optional echo data")


# Response Messages (Worker → Host)


class PrepareResponse(BaseModel):
    """Response to prepare command."""

    status: Literal[ResponseStatus.READY] = Field(default=ResponseStatus.READY)
    session_id: str = Field(..., description="Confirmed session ID")
    session_dir: str = Field(..., description="Working directory path")
    drivers_loaded: list[str] = Field(..., description="List of loaded drivers")


class ExecStepResponse(BaseModel):
    """Response to exec_step command."""

    status: Literal[ResponseStatus.COMPLETE] = Field(default=ResponseStatus.COMPLETE)
    step_id: str = Field(..., description="Executed step ID")
    rows_processed: int | None = Field(None, description="Number of rows processed")
    outputs: dict[str, Any] | None = Field(None, description="Output data for downstream steps")
    duration_ms: float | None = Field(None, description="Execution duration in milliseconds")
    error: str | None = Field(None, description="Error message if step failed")
    error_type: str | None = Field(None, description="Exception class name")
    traceback: str | None = Field(None, description="Full stack trace")


class CleanupResponse(BaseModel):
    """Response to cleanup command."""

    status: Literal[ResponseStatus.CLEANED] = Field(default=ResponseStatus.CLEANED)
    session_id: str = Field(..., description="Cleaned session ID")
    steps_executed: int = Field(..., description="Total steps executed")
    total_rows: int | None = Field(None, description="Total rows processed")


class PingResponse(BaseModel):
    """Response to ping command."""

    status: Literal[ResponseStatus.PONG] = Field(default=ResponseStatus.PONG)
    timestamp: float = Field(..., description="Response timestamp")
    echo: str | None = Field(None, description="Echoed data")


class ErrorResponse(BaseModel):
    """Error response for any failed command."""

    status: Literal[ResponseStatus.ERROR] = Field(default=ResponseStatus.ERROR)
    error: str = Field(..., description="Error message")
    traceback: str | None = Field(None, description="Stack trace if available")


# Streaming Messages (Worker → Host)


class EventMessage(BaseModel):
    """Event streamed from worker."""

    type: Literal[MessageType.EVENT] = Field(default=MessageType.EVENT)
    name: str = Field(..., description="Event name")
    timestamp: float = Field(..., description="Event timestamp")
    data: dict[str, Any] = Field(default_factory=dict, description="Event data")


class MetricMessage(BaseModel):
    """Metric streamed from worker."""

    type: Literal[MessageType.METRIC] = Field(default=MessageType.METRIC)
    name: str = Field(..., description="Metric name")
    value: Any = Field(..., description="Metric value")
    timestamp: float = Field(..., description="Metric timestamp")
    tags: dict[str, str] | None = Field(None, description="Optional metric tags")


class ErrorMessage(BaseModel):
    """Error streamed from worker."""

    type: Literal[MessageType.ERROR] = Field(default=MessageType.ERROR)
    error: str = Field(..., description="Error message")
    timestamp: float = Field(..., description="Error timestamp")
    context: dict[str, Any] | None = Field(None, description="Error context")


# Helper functions for message parsing


def parse_command(data: dict[str, Any]) -> BaseModel:
    """Parse a command from JSON data.

    Args:
        data: Raw JSON dictionary

    Returns:
        Parsed command model

    Raises:
        ValueError: If command type is unknown or data is invalid
    """
    cmd_type = data.get("cmd")

    if cmd_type == CommandType.PREPARE:
        return PrepareCommand(**data)
    elif cmd_type == CommandType.EXEC_STEP:
        return ExecStepCommand(**data)
    elif cmd_type == CommandType.CLEANUP:
        return CleanupCommand(**data)
    elif cmd_type == CommandType.PING:
        return PingCommand(**data)
    else:
        raise ValueError(f"Unknown command type: {cmd_type}")


def parse_message(data: dict[str, Any]) -> BaseModel:
    """Parse a message from worker.

    Args:
        data: Raw JSON dictionary

    Returns:
        Parsed message model

    Raises:
        ValueError: If message type is unknown or data is invalid
    """
    # Check if it's a response (has 'status' field)
    if "status" in data:
        status = data.get("status")

        if status == ResponseStatus.READY:
            return PrepareResponse(**data)
        elif status == ResponseStatus.COMPLETE:
            return ExecStepResponse(**data)
        elif status == ResponseStatus.CLEANED:
            return CleanupResponse(**data)
        elif status == ResponseStatus.PONG:
            return PingResponse(**data)
        elif status == ResponseStatus.ERROR:
            return ErrorResponse(**data)
        else:
            raise ValueError(f"Unknown response status: {status}")

    # Otherwise it's a streaming message
    msg_type = data.get("type")

    if msg_type == MessageType.EVENT:
        return EventMessage(**data)
    elif msg_type == MessageType.METRIC:
        return MetricMessage(**data)
    elif msg_type == MessageType.ERROR:
        return ErrorMessage(**data)
    else:
        raise ValueError(f"Unknown message type: {msg_type}")
