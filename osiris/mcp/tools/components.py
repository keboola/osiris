"""
MCP tools for component management.
"""

import logging
import time
from typing import Any

from osiris.mcp.errors import ErrorFamily, OsirisError
from osiris.mcp.metrics_helper import add_metrics

logger = logging.getLogger(__name__)


class ComponentsTools:
    """Tools for managing pipeline components."""

    def __init__(self, audit_logger=None):
        """Initialize components tools."""
        self._registry = None
        self.audit = audit_logger

    def _get_registry(self):
        """Get or create component registry."""
        if self._registry is None:
            try:
                from osiris.components.registry import ComponentRegistry  # noqa: PLC0415  # Lazy import

                self._registry = ComponentRegistry()
            except Exception as e:
                logger.error(f"Failed to initialize component registry: {e}")
                raise OsirisError(
                    ErrorFamily.SEMANTIC,
                    f"Failed to initialize component registry: {str(e)}",
                    path=["registry"],
                    suggest="Check component specs directory",
                ) from e
        return self._registry

    async def list(self, args: dict[str, Any]) -> dict[str, Any]:
        """
        List available pipeline components.

        Args:
            args: Tool arguments (none required)

        Returns:
            Dictionary with component information
        """
        start_time = time.time()
        correlation_id = self.audit.make_correlation_id() if self.audit else "unknown"

        try:
            registry = self._get_registry()

            # Load component specs
            specs = registry.load_specs()

            # Format components for response
            components = []
            for name, spec in specs.items():
                component = {
                    "name": name,
                    "version": spec.get("version", "1.0.0"),
                    "description": spec.get("description", ""),
                    "tags": spec.get("tags", []),
                    "capabilities": spec.get("capabilities", {}),
                }

                # Add schema information
                if "config_schema" in spec:
                    schema = spec["config_schema"]
                    component["required_fields"] = schema.get("required", [])
                    component["optional_fields"] = [
                        k for k in schema.get("properties", {}) if k not in schema.get("required", [])
                    ]

                # Add examples if available
                if "examples" in spec:
                    component["examples"] = [
                        {"description": ex.get("description", ""), "config": ex.get("config", {})}
                        for ex in spec["examples"][:2]  # Limit to 2 examples
                    ]

                components.append(component)

            # Group by capability
            extractors = [c for c in components if "extractor" in c["name"]]
            writers = [c for c in components if "writer" in c["name"]]
            processors = [c for c in components if "processor" in c["name"]]
            others = [c for c in components if c not in extractors + writers + processors]

            result = {
                "components": {"extractors": extractors, "writers": writers, "processors": processors, "other": others},
                "total_count": len(components),
                "status": "success",
            }

            return add_metrics(result, correlation_id, start_time, args)

        except Exception as e:
            logger.error(f"Error listing components: {e}")
            raise OsirisError(
                ErrorFamily.SEMANTIC,
                f"Failed to list components: {str(e)}",
                path=["components"],
                suggest="Check component specs directory",
            ) from e
