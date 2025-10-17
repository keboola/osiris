"""
MCP tools for guided OML authoring.
"""

import logging
import time
from typing import Any

from osiris.mcp.errors import ErrorFamily, OsirisError
from osiris.mcp.metrics_helper import add_metrics

logger = logging.getLogger(__name__)


class GuideTools:
    """Tools for providing guided next steps in OML authoring."""

    def __init__(self, audit_logger=None):
        """Initialize guide tools."""
        self.audit = audit_logger

    async def start(self, args: dict[str, Any]) -> dict[str, Any]:
        """
        Get guided next steps for OML authoring.

        Args:
            args: Tool arguments including intent, known_connections, flags

        Returns:
            Dictionary with guidance information
        """
        start_time = time.time()
        correlation_id = self.audit.make_correlation_id() if self.audit else "unknown"

        intent = args.get("intent", "")
        known_connections = args.get("known_connections", [])
        has_discovery = args.get("has_discovery", False)
        has_previous_oml = args.get("has_previous_oml", False)
        has_error_report = args.get("has_error_report", False)

        if not intent:
            # Return error object with suggested first step (still add metrics)
            result = {
                "error": {"code": "SCHEMA/OML020", "message": "intent is required", "path": ["intent"]},
                "next_steps": [{"tool": "connections.list", "params": {}}],
                "status": "success",  # Still success despite error structure
            }
            return add_metrics(result, correlation_id, start_time, args)

        try:
            # Determine the next logical step based on context
            next_step, objective, example = self._determine_next_step(
                intent, known_connections, has_discovery, has_previous_oml, has_error_report
            )

            # Get relevant references
            self._get_relevant_references(next_step)

            # Format next steps as array per spec
            next_steps = []
            if example and isinstance(example, dict):
                next_steps.append({"tool": example.get("tool", ""), "params": example.get("arguments", {})})

            # Add recommendations for backward compatibility
            recommendations = self._get_tips_for_step(next_step)

            result = {
                "objective": objective,
                "next_step": next_step,
                "next_steps": next_steps,
                "examples": {"minimal_request": example},
                "context": {
                    "has_connections": len(known_connections) > 0,
                    "has_discovery": has_discovery,
                    "has_previous_oml": has_previous_oml,
                    "has_error_report": has_error_report,
                },
                "recommendations": recommendations,
                "status": "success",
            }

            return add_metrics(result, correlation_id, start_time, args)

        except Exception as e:
            logger.error(f"Guide generation failed: {e}")
            raise OsirisError(
                ErrorFamily.SEMANTIC,
                f"Failed to generate guidance: {str(e)}",
                path=["guide"],
                suggest="Try providing more context about your goal",
            ) from e

    def _determine_next_step(
        self,
        intent: str,
        known_connections: list[str],
        has_discovery: bool,
        has_previous_oml: bool,
        has_error_report: bool,
    ) -> tuple[str, str, dict[str, Any]]:
        """
        Determine the next logical step based on current context.

        Args:
            intent: User's stated intent
            known_connections: List of known connection IDs
            has_discovery: Whether discovery has been performed
            has_previous_oml: Whether there's a previous OML draft
            has_error_report: Whether there's an error report

        Returns:
            Tuple of (next_step, objective, example)
        """
        # If there's an error report, suggest fixing it first
        if has_error_report and has_previous_oml:
            return (
                "validate_oml",
                "Fix validation errors in your OML pipeline",
                {
                    "tool": "osiris.validate_oml",
                    "arguments": {"oml_content": "# Your fixed OML content here", "strict": True},
                    "description": "Validate the fixed OML pipeline",
                },
            )

        # If no connections are known, list them first
        if not known_connections:
            return (
                "list_connections",
                "Discover available database connections",
                {
                    "tool": "osiris.connections.list",
                    "arguments": {},
                    "description": "List all configured database connections",
                },
            )

        # If connections are known but no discovery, suggest discovery
        if known_connections and not has_discovery:
            return (
                "run_discovery",
                "Explore database schema and sample data",
                {
                    "tool": "osiris.introspect_sources",
                    "arguments": {
                        "connection_id": known_connections[0] if known_connections else "@mysql.default",
                        "component_id": "mysql.extractor",
                        "samples": 5,
                    },
                    "description": "Discover database schema with sample data",
                },
            )

        # If discovery is done but no OML, suggest creating one
        if has_discovery and not has_previous_oml:
            return (
                "create_oml",
                "Create your first OML pipeline",
                {
                    "tool": "osiris.save_oml",
                    "arguments": {"oml_content": self._get_sample_oml(), "session_id": "session_001"},
                    "description": "Save your first OML pipeline draft",
                },
            )

        # If everything exists, suggest validation
        if has_previous_oml:
            return (
                "validate_oml",
                "Validate and refine your OML pipeline",
                {
                    "tool": "osiris.validate_oml",
                    "arguments": {"oml_content": "# Your OML content here", "strict": True},
                    "description": "Validate your OML pipeline",
                },
            )

        # Default: list components to explore options
        return (
            "list_components",
            "Explore available pipeline components",
            {
                "tool": "osiris.components.list",
                "arguments": {},
                "description": "List all available pipeline components",
            },
        )

    def _get_relevant_references(self, next_step: str) -> list[str]:
        """Get relevant resource URIs for the next step."""
        references_by_step = {
            "list_connections": ["osiris://mcp/prompts/oml_authoring_guide.md"],
            "run_discovery": ["osiris://mcp/prompts/oml_authoring_guide.md"],
            "create_oml": ["osiris://mcp/schemas/oml/v0.1.0.json", "osiris://mcp/usecases/catalog.yaml"],
            "validate_oml": ["osiris://mcp/schemas/oml/v0.1.0.json"],
            "list_components": ["osiris://mcp/prompts/oml_authoring_guide.md"],
        }

        return references_by_step.get(next_step, [])

    def _get_tips_for_step(self, next_step: str) -> list[str]:
        """Get helpful tips for the current step."""
        tips_by_step = {
            "list_connections": [
                "Connections are configured in osiris_connections.yaml",
                "Use connection references like @mysql.default in your OML",
                "Run 'osiris.connections.doctor' to diagnose connection issues",
            ],
            "run_discovery": [
                "Discovery results are cached for 24 hours",
                "Use samples parameter to fetch sample data",
                "Discovery helps understand database structure before writing queries",
            ],
            "create_oml": [
                "Start with a simple pipeline and iterate",
                "Each step needs a unique ID",
                "Use depends_on to control execution order",
            ],
            "validate_oml": [
                "Validation checks schema compliance and semantic correctness",
                "Fix errors before warnings",
                "Use strict=false for lenient validation during development",
            ],
            "list_components": [
                "Components are grouped by type: extractors, writers, processors",
                "Each component has a JSON schema for configuration",
                "Check component examples for usage patterns",
            ],
        }

        return tips_by_step.get(next_step, [])

    def _get_sample_oml(self) -> str:
        """Get a sample OML pipeline for demonstration."""
        return """version: 0.1.0
name: my_first_pipeline
description: Extract and transform data

steps:
  - id: extract-data
    component: mysql.extractor
    config:
      connection: @mysql.default
      query: "SELECT * FROM users LIMIT 100"

  - id: transform-data
    component: duckdb.processor
    config:
      query: "SELECT * FROM df WHERE active = true"
    depends_on: [extract-data]

  - id: save-results
    component: filesystem.csv_writer
    config:
      path: output/users.csv
    depends_on: [transform-data]
"""
