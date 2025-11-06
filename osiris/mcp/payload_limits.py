"""
Payload limit enforcement for Osiris MCP server.

Provides utilities for checking and enforcing payload size limits.
"""

import json
from typing import Any

from osiris.mcp.config import get_config
from osiris.mcp.errors import ErrorFamily, OsirisError


class PayloadLimitError(OsirisError):
    """Error raised when payload exceeds size limits."""

    def __init__(self, actual_size: int, limit: int, context: str = "payload"):
        """
        Initialize payload limit error.

        Args:
            actual_size: Actual payload size in bytes
            limit: Limit in bytes
            context: Context of the limit (e.g., "request", "response")
        """
        self.actual_size = actual_size
        self.limit = limit
        message = (
            f"{context.capitalize()} size ({self._format_bytes(actual_size)}) "
            f"exceeds limit ({self._format_bytes(limit)})"
        )
        super().__init__(
            ErrorFamily.POLICY,
            message,
            path=[context, "size"],
            suggest=f"Reduce {context} size or request data in smaller chunks",
        )

    @staticmethod
    def _format_bytes(size: int) -> str:
        """Format byte size in human-readable format."""
        for unit in ["B", "KB", "MB", "GB"]:
            if size < 1024.0:
                return f"{size:.1f}{unit}"
            size /= 1024.0
        return f"{size:.1f}TB"


class PayloadLimiter:
    """Enforces payload size limits."""

    def __init__(self, limit_bytes: int = None):
        """
        Initialize payload limiter.

        Args:
            limit_bytes: Maximum payload size in bytes (defaults to config)
        """
        config = get_config()
        self.limit_bytes = limit_bytes or config.payload_limit_bytes

    def check_size(self, data: Any, context: str = "payload") -> int:
        """
        Check if data size is within limits.

        Args:
            data: Data to check (will be serialized to JSON)
            context: Context for error messages

        Returns:
            Size of data in bytes

        Raises:
            PayloadLimitError: If data exceeds size limit
        """
        # Calculate size
        size = self.calculate_size(data)

        # Check against limit
        if size > self.limit_bytes:
            raise PayloadLimitError(size, self.limit_bytes, context)

        return size

    def calculate_size(self, data: Any) -> int:
        """
        Calculate size of data when serialized to JSON.

        Args:
            data: Data to measure

        Returns:
            Size in bytes
        """
        if isinstance(data, str):
            return len(data.encode("utf-8"))
        elif isinstance(data, bytes):
            return len(data)
        elif isinstance(data, (dict, list)):
            # Serialize to JSON and measure
            json_str = json.dumps(data, separators=(",", ":"))
            return len(json_str.encode("utf-8"))
        else:
            # Try to convert to string and measure
            str_data = str(data)
            return len(str_data.encode("utf-8"))

    def truncate_if_needed(self, data: str | dict | list, context: str = "data") -> tuple[Any, bool]:
        """
        Truncate data if it exceeds limits.

        Args:
            data: Data to potentially truncate
            context: Context for truncation

        Returns:
            Tuple of (data, was_truncated)
        """
        size = self.calculate_size(data)

        if size <= self.limit_bytes:
            return data, False

        # Truncation strategy depends on data type
        if isinstance(data, str):
            # Truncate string
            max_chars = self.limit_bytes // 4  # Conservative estimate for UTF-8
            truncated = data[:max_chars]
            truncated += f"\n\n[Truncated: {PayloadLimitError._format_bytes(size)} > {PayloadLimitError._format_bytes(self.limit_bytes)}]"
            return truncated, True

        elif isinstance(data, list):
            # Truncate list by removing items
            truncated = []
            current_size = 2  # For "[]"

            for item in data:
                item_size = self.calculate_size(item) + 1  # +1 for comma
                if current_size + item_size > self.limit_bytes * 0.9:  # Leave 10% buffer
                    truncated.append(
                        {
                            "__truncated__": True,
                            "remaining_items": len(data) - len(truncated),
                            "total_size": PayloadLimitError._format_bytes(size),
                        }
                    )
                    break
                truncated.append(item)
                current_size += item_size

            return truncated, True

        elif isinstance(data, dict):
            # Truncate dict by removing keys
            truncated = {}
            current_size = 2  # For "{}"
            keys = list(data.keys())

            for key in keys:
                key_size = len(json.dumps(key)) + 1  # +1 for colon
                value_size = self.calculate_size(data[key]) + 1  # +1 for comma
                item_size = key_size + value_size

                if current_size + item_size > self.limit_bytes * 0.9:  # Leave 10% buffer
                    truncated["__truncated__"] = {
                        "remaining_keys": len(keys) - len(truncated),
                        "total_size": PayloadLimitError._format_bytes(size),
                    }
                    break
                truncated[key] = data[key]
                current_size += item_size

            return truncated, True

        else:
            # For other types, convert to string and truncate
            str_data = str(data)
            return self.truncate_if_needed(str_data, context)

    def check_request(self, request: dict[str, Any]) -> int:
        """
        Check if request payload is within limits.

        Args:
            request: Request payload

        Returns:
            Size of request in bytes

        Raises:
            PayloadLimitError: If request exceeds size limit
        """
        return self.check_size(request, "request")

    def check_response(self, response: Any) -> int:
        """
        Check if response payload is within limits.

        Args:
            response: Response payload

        Returns:
            Size of response in bytes

        Raises:
            PayloadLimitError: If response exceeds size limit
        """
        return self.check_size(response, "response")


# Global payload limiter instance
_limiter: PayloadLimiter = None


def get_limiter() -> PayloadLimiter:
    """Get the global payload limiter instance."""
    global _limiter
    if _limiter is None:
        _limiter = PayloadLimiter()
    return _limiter


def init_limiter(limit_bytes: int = None) -> PayloadLimiter:
    """
    Initialize global payload limiter.

    Args:
        limit_bytes: Maximum payload size in bytes

    Returns:
        PayloadLimiter instance
    """
    global _limiter
    _limiter = PayloadLimiter(limit_bytes)
    return _limiter
