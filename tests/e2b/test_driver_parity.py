"""Tests to ensure driver registration parity between local and E2B contexts."""

from osiris.components.registry import ComponentRegistry
from osiris.core.driver import DriverRegistry


def test_driver_registry_parity_across_environments():
    """Driver sets derived from ComponentRegistry should match for local and remote runners."""

    registry = ComponentRegistry()
    specs = registry.load_specs()

    local_registry = DriverRegistry()
    local_summary = local_registry.populate_from_component_specs(specs)

    remote_registry = DriverRegistry()
    remote_summary = remote_registry.populate_from_component_specs(
        specs,
        modes={"extract", "transform", "write", "read"},
    )

    assert set(local_summary.registered.keys()) == set(remote_summary.registered.keys())
    assert local_summary.fingerprint == remote_summary.fingerprint
