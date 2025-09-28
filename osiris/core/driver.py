"""Driver interface and registry for runtime execution."""

import logging
from collections.abc import Callable
from typing import Any, Protocol

logger = logging.getLogger(__name__)


class Driver(Protocol):
    """Protocol for pipeline step drivers.

    Drivers are responsible for executing individual pipeline steps.
    They receive configuration and inputs, and return outputs.
    """

    def run(self, *, step_id: str, config: dict, inputs: dict | None = None, ctx: Any = None) -> dict:
        """Execute the driver logic.

        Args:
            step_id: Identifier of the step being executed
            config: Step configuration including resolved connections
            inputs: Input data from upstream steps (e.g., {"df": DataFrame})
            ctx: Execution context (logger, session info, etc.)

        Returns:
            Output data. For extractors/transforms: {"df": DataFrame}
            For writers: {} (empty dict)

        Notes:
            - Must not mutate inputs
            - Should emit metrics via ctx if provided
        """
        ...


class DriverRegistry:
    """Registry for driver implementations."""

    def __init__(self):
        self._drivers: dict[str, Callable[[], Driver]] = {}

    def register(self, name: str, factory: Callable[[], Driver]) -> None:
        """Register a driver factory.

        Args:
            name: Driver name (e.g., "mysql.extractor")
            factory: Callable that returns a Driver instance
        """
        logger.debug(f"Registering driver: {name}")
        self._drivers[name] = factory

    def get(self, name: str) -> Driver:
        """Get a driver instance by name.

        Args:
            name: Driver name

        Returns:
            Driver instance

        Raises:
            ValueError: If driver not found
        """
        if name not in self._drivers:
            available = ", ".join(sorted(self._drivers.keys()))
            raise ValueError(f"Driver '{name}' not registered. " f"Available drivers: {available or '(none)'}")

        factory = self._drivers[name]
        return factory()

    def list_drivers(self) -> list[str]:
        """List all registered driver names."""
        return sorted(self._drivers.keys())
