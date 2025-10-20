"""Driver interface and registry for runtime execution."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
import hashlib
import importlib
import logging
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


@dataclass
class DriverRegistrationSummary:
    """Summary of driver registry population from component specifications."""

    registered: dict[str, str] = field(default_factory=dict)
    skipped: dict[str, str] = field(default_factory=dict)
    errors: dict[str, str] = field(default_factory=dict)
    metadata: dict[str, dict[str, Any]] = field(default_factory=dict)
    fingerprint: str | None = None

    def compute_fingerprint(self) -> str | None:
        """Compute a stable fingerprint of registered drivers for parity checks."""
        if not self.registered:
            self.fingerprint = None
            return self.fingerprint

        payload = "|".join(f"{component}:{driver}" for component, driver in sorted(self.registered.items()))
        self.fingerprint = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        return self.fingerprint


class DriverRegistry:
    """Registry for driver implementations."""

    def __init__(self):
        self._drivers: dict[str, Callable[[], Driver]] = {}
        self._metadata: dict[str, dict[str, Any]] = {}
        self._loaded_specs: Mapping[str, dict[str, Any]] | None = None

    def load_specs(self, component_registry: Any | None = None) -> Mapping[str, dict[str, Any]]:
        """Load component specifications destined for driver registration.

        Args:
            component_registry: Optional ComponentRegistry-like object. When omitted the
                default ComponentRegistry is instantiated.

        Returns:
            Mapping of component name to loaded specification.
        """

        if component_registry is None:
            from osiris.components.registry import ComponentRegistry

            component_registry = ComponentRegistry()

        specs = component_registry.load_specs()
        self._loaded_specs = specs
        return specs

    def register(self, name: str, factory: Callable[[], Driver], *, info: dict[str, Any] | None = None) -> None:
        """Register a driver factory.

        Args:
            name: Driver name (e.g., "mysql.extractor")
            factory: Callable that returns a Driver instance
            info: Optional metadata describing the driver (module, class, etc.)
        """
        logger.debug(f"Registering driver: {name}")
        self._drivers[name] = factory
        if info is not None:
            self._metadata[name] = info
        else:
            self._metadata.setdefault(name, {})

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

    def get_metadata(self, name: str) -> dict[str, Any]:
        """Return metadata for a registered driver."""
        return dict(self._metadata.get(name, {}))

    def populate_from_component_specs(  # noqa: PLR0915
        self,
        specs: Mapping[str, dict[str, Any]],
        *,
        modes: set[str] | None = None,
        allow: set[str] | None = None,
        deny: set[str] | None = None,
        verify_import: bool = False,
        strict: bool = False,
        on_success: Callable[[str, str], None] | None = None,
        on_error: Callable[[str, str, Exception], None] | None = None,
    ) -> DriverRegistrationSummary:
        """Populate the registry using component specifications.

        Args:
            specs: Mapping of component name to specification dictionary
            modes: Optional set of modes to include (component modes intersection)
            allow: Optional set of component or driver identifiers to allow
            deny: Optional set of component or driver identifiers to exclude
            verify_import: If True, import the module immediately to surface dependency errors
            strict: If True, skip registration on import errors
            on_success: Optional callback invoked on successful registration (component, driver)
            on_error: Optional callback invoked when driver import verification fails

        Returns:
            DriverRegistrationSummary with details of registration outcome
        """

        summary = DriverRegistrationSummary()
        allowed_modes = set(modes) if modes else None
        allow = set(allow or [])
        deny = set(deny or [])

        for component_name, spec in specs.items():
            runtime_cfg = spec.get("x-runtime", {}) or {}
            driver_path = runtime_cfg.get("driver")

            if not driver_path:
                summary.skipped[component_name] = "missing x-runtime.driver"
                continue

            spec_modes = set(spec.get("modes", []))
            if allowed_modes and allowed_modes.isdisjoint(spec_modes):
                summary.skipped[component_name] = "mode filtered"
                continue

            if allow and component_name not in allow and driver_path not in allow:
                summary.skipped[component_name] = "not allowlisted"
                continue

            if deny and (component_name in deny or driver_path in deny):
                summary.skipped[component_name] = "denylisted"
                continue

            try:
                module_path, class_name = driver_path.rsplit(".", 1)
            except ValueError as exc:  # malformed driver path
                message = f"invalid driver path '{driver_path}'"
                summary.errors[component_name] = message
                if on_error:
                    on_error(component_name, driver_path, exc)
                if strict:
                    continue
                else:
                    # Skip registration because we cannot construct a factory
                    continue

            info = {
                "driver_path": driver_path,
                "module": module_path,
                "class": class_name,
            }

            import_problem: Exception | None = None
            if verify_import:
                try:
                    module = importlib.import_module(module_path)
                    getattr(module, class_name)
                except Exception as exc:  # noqa: BLE001 - want to surface any import issue
                    import_problem = exc
                    summary.errors[component_name] = f"{type(exc).__name__}: {exc}"
                    if on_error:
                        on_error(component_name, driver_path, exc)
                    if strict:
                        continue

            def factory(mp: str = module_path, cn: str = class_name) -> Driver:
                module = importlib.import_module(mp)
                driver_class = getattr(module, cn)
                return driver_class()

            self.register(component_name, factory, info=info)
            summary.registered[component_name] = driver_path
            summary.metadata[component_name] = info

            if import_problem is None and on_success:
                on_success(component_name, driver_path)

        summary.compute_fingerprint()
        return summary

    def validate_imports(self, instantiate: bool = False) -> dict[str, Exception | None]:
        """Validate that registered drivers can be imported (and optionally instantiated).

        Args:
            instantiate: If True, instantiate each driver factory to catch runtime errors

        Returns:
            Mapping of driver name to Exception (if failure) or None (if success)
        """

        results: dict[str, Exception | None] = {}
        for name, factory in self._drivers.items():
            metadata = self._metadata.get(name, {})
            module_path = metadata.get("module")
            class_name = metadata.get("class")
            try:
                if instantiate:
                    factory()
                elif module_path and class_name:
                    module = importlib.import_module(module_path)
                    getattr(module, class_name)
                else:
                    # Fall back to invoking factory to ensure import coverage
                    factory()
                results[name] = None
            except Exception as exc:  # noqa: BLE001 - propagate any failure for diagnostics
                results[name] = exc

        return results
