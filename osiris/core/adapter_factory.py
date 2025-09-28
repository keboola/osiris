"""Factory for creating execution adapters based on target."""

from typing import Any

from .execution_adapter import ExecutionAdapter


def get_execution_adapter(target: str, config: dict[str, Any] | None = None) -> ExecutionAdapter:
    """Get an execution adapter based on target.

    Args:
        target: Execution target ("local" or "e2b")
        config: Optional configuration for the adapter

    Returns:
        ExecutionAdapter instance

    Raises:
        ValueError: If target is unknown or dependencies are missing
    """
    config = config or {}

    if target == "local":
        from ..runtime.local_adapter import LocalAdapter

        return LocalAdapter(**config)

    elif target == "e2b":
        try:
            from ..remote.e2b_transparent_proxy import E2BTransparentProxy

            return E2BTransparentProxy(config)
        except ImportError as e:
            raise ValueError(f"E2B adapter not available. Install E2B dependencies: {e}") from e

    else:
        raise ValueError(f"Unknown execution target: {target}. Valid options: 'local', 'e2b'")
