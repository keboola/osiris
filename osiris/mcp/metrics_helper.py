"""
Helper utilities for adding metrics to MCP tool responses.

Provides a standardized way to add correlation_id, duration_ms, bytes_in, and bytes_out
to all tool responses as required by Phase 2.1 of the MCP metrics implementation.
"""

import json
import time
from typing import Any


def calculate_bytes(data: Any) -> int:
    """
    Calculate the size of data in bytes.

    Args:
        data: Data to measure (dict, str, list, etc.)

    Returns:
        Size in bytes
    """
    if data is None:
        return 0
    if isinstance(data, (str, bytes)):
        return len(data.encode() if isinstance(data, str) else data)
    return len(json.dumps(data, default=str))


def add_metrics(
    response: dict[str, Any], correlation_id: str, start_time: float, request_args: dict[str, Any]
) -> dict[str, Any]:
    """
    Add metrics fields to a tool response.

    This function adds the required metrics fields in a _meta dictionary:
    - correlation_id: Unique identifier for request tracing
    - duration_ms: Time taken to process the request
    - bytes_in: Size of the request parameters
    - bytes_out: Size of the response payload

    Args:
        response: The original response dictionary
        correlation_id: Correlation ID from audit logger
        start_time: Start time from time.time()
        request_args: Original request arguments

    Returns:
        Response with metrics fields added in _meta dict
    """
    # Calculate metrics
    duration_ms = int((time.time() - start_time) * 1000)
    bytes_in = calculate_bytes(request_args)
    bytes_out = calculate_bytes(response)

    # Merge with existing _meta if present (from CLI responses)
    existing_meta = response.get("_meta", {})

    # Add/override metrics in _meta dict
    response["_meta"] = {
        **existing_meta,
        "correlation_id": correlation_id,
        "duration_ms": duration_ms,
        "bytes_in": bytes_in,
        "bytes_out": bytes_out,
    }

    return response
