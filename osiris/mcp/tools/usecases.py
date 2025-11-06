"""
MCP tools for OML use case management.
"""

import builtins
import logging
from pathlib import Path
import time
from typing import Any

import yaml

from osiris.mcp.errors import ErrorFamily, OsirisError
from osiris.mcp.metrics_helper import add_metrics

logger = logging.getLogger(__name__)


class UsecasesTools:
    """Tools for managing OML use case templates."""

    def __init__(self, usecases_dir: Path | None = None, audit_logger=None):
        """Initialize usecases tools."""
        self.usecases_dir = usecases_dir or Path(__file__).parent.parent / "data" / "usecases"
        self.audit = audit_logger

    async def list(self, args: dict[str, Any]) -> dict[str, Any]:
        """
        List available OML use case templates.

        Args:
            args: Tool arguments (none required)

        Returns:
            Dictionary with use case information
        """
        start_time = time.time()
        correlation_id = self.audit.make_correlation_id() if self.audit else "unknown"

        try:
            # Load use cases catalog
            usecases = self._load_usecases_catalog()

            # Format for response
            formatted_usecases = []
            for usecase in usecases:
                formatted = {
                    "id": usecase.get("id", "unknown"),
                    "name": usecase.get("name", ""),
                    "description": usecase.get("description", ""),
                    "category": usecase.get("category", "general"),
                    "tags": usecase.get("tags", []),
                    "difficulty": usecase.get("difficulty", "medium"),
                    "snippet_uri": f"osiris://mcp/usecases/{usecase.get('id', 'unknown')}.yaml",
                }

                # Add requirements if present
                if "requirements" in usecase:
                    formatted["requirements"] = usecase["requirements"]

                # Add example config if present
                if "example" in usecase:
                    formatted["example"] = usecase["example"]

                formatted_usecases.append(formatted)

            # Group by category
            categories = {}
            for usecase in formatted_usecases:
                category = usecase["category"]
                if category not in categories:
                    categories[category] = []
                categories[category].append(usecase)

            result = {
                "usecases": formatted_usecases,
                "by_category": categories,
                "total_count": len(formatted_usecases),
                "categories": list(categories.keys()),
                "status": "success",
            }

            return add_metrics(result, correlation_id, start_time, args)

        except Exception as e:
            logger.error(f"Failed to list use cases: {e}")
            raise OsirisError(
                ErrorFamily.SEMANTIC,
                f"Failed to list use cases: {str(e)}",
                path=["usecases"],
                suggest="Check use cases catalog file",
            ) from e

    def _load_usecases_catalog(self) -> builtins.list[dict[str, Any]]:
        """Load the use cases catalog."""
        # For now, return a hardcoded catalog
        # In production, this would load from osiris/mcp/data/usecases/catalog.yaml
        return [
            {
                "id": "mysql_to_csv",
                "name": "MySQL to CSV Export",
                "description": "Extract data from MySQL and save as CSV files",
                "category": "data_export",
                "tags": ["mysql", "csv", "export", "etl"],
                "difficulty": "easy",
                "requirements": {"connections": ["mysql"], "components": ["mysql.extractor", "filesystem.csv_writer"]},
                "example": {
                    "version": "0.1.0",
                    "name": "mysql_export",
                    "description": "Export MySQL tables to CSV",
                    "steps": [
                        {
                            "id": "extract",
                            "component": "mysql.extractor",
                            "config": {"connection": "@mysql.default", "query": "SELECT * FROM users"},
                        },
                        {
                            "id": "save",
                            "component": "filesystem.csv_writer",
                            "config": {"path": "output/users.csv"},
                            "depends_on": ["extract"],
                        },
                    ],
                },
            },
            {
                "id": "mysql_to_supabase",
                "name": "MySQL to Supabase Migration",
                "description": "Migrate data from MySQL to Supabase PostgreSQL",
                "category": "data_migration",
                "tags": ["mysql", "supabase", "postgresql", "migration"],
                "difficulty": "medium",
                "requirements": {
                    "connections": ["mysql", "supabase"],
                    "components": ["mysql.extractor", "supabase.writer"],
                },
                "example": {
                    "version": "0.1.0",
                    "name": "mysql_to_supabase",
                    "description": "Migrate MySQL data to Supabase",
                    "steps": [
                        {
                            "id": "extract-users",
                            "component": "mysql.extractor",
                            "config": {"connection": "@mysql.source", "query": "SELECT * FROM users"},
                        },
                        {
                            "id": "write-users",
                            "component": "supabase.writer",
                            "config": {"connection": "@supabase.target", "table": "users", "mode": "upsert"},
                            "depends_on": ["extract-users"],
                        },
                    ],
                },
            },
            {
                "id": "data_transformation",
                "name": "Data Transformation Pipeline",
                "description": "Extract, transform, and load data with DuckDB",
                "category": "etl",
                "tags": ["etl", "duckdb", "transformation", "analytics"],
                "difficulty": "medium",
                "requirements": {
                    "connections": ["mysql"],
                    "components": ["mysql.extractor", "duckdb.processor", "filesystem.csv_writer"],
                },
                "example": {
                    "version": "0.1.0",
                    "name": "transform_pipeline",
                    "description": "ETL pipeline with transformations",
                    "steps": [
                        {
                            "id": "extract",
                            "component": "mysql.extractor",
                            "config": {"connection": "@mysql.default", "query": "SELECT * FROM transactions"},
                        },
                        {
                            "id": "transform",
                            "component": "duckdb.processor",
                            "config": {
                                "query": """
                                    SELECT
                                        DATE_TRUNC('month', transaction_date) as month,
                                        customer_id,
                                        SUM(amount) as total_amount,
                                        COUNT(*) as transaction_count
                                    FROM df
                                    GROUP BY 1, 2
                                """
                            },
                            "depends_on": ["extract"],
                        },
                        {
                            "id": "save",
                            "component": "filesystem.csv_writer",
                            "config": {"path": "output/monthly_summary.csv"},
                            "depends_on": ["transform"],
                        },
                    ],
                },
            },
            {
                "id": "incremental_sync",
                "name": "Incremental Data Sync",
                "description": "Sync data incrementally based on timestamps",
                "category": "sync",
                "tags": ["sync", "incremental", "real-time"],
                "difficulty": "hard",
                "requirements": {
                    "connections": ["mysql", "supabase"],
                    "components": ["mysql.extractor", "duckdb.processor", "supabase.writer"],
                },
            },
            {
                "id": "data_validation",
                "name": "Data Quality Validation",
                "description": "Validate data quality before loading",
                "category": "quality",
                "tags": ["validation", "quality", "testing"],
                "difficulty": "medium",
                "requirements": {"connections": ["mysql"], "components": ["mysql.extractor", "duckdb.processor"]},
            },
        ]

    async def get_template(self, args: dict[str, Any]) -> dict[str, Any]:
        """
        Get a specific use case template.

        Args:
            args: Tool arguments including usecase_id

        Returns:
            Dictionary with template details
        """
        start_time = time.time()
        correlation_id = self.audit.make_correlation_id() if self.audit else "unknown"

        usecase_id = args.get("usecase_id")
        if not usecase_id:
            raise OsirisError(
                ErrorFamily.SCHEMA,
                "usecase_id is required",
                path=["usecase_id"],
                suggest="Provide a use case ID from the catalog",
            )

        try:
            # Load catalog and find the specific use case
            usecases = self._load_usecases_catalog()
            usecase = next((u for u in usecases if u.get("id") == usecase_id), None)

            if not usecase:
                raise OsirisError(
                    ErrorFamily.SEMANTIC,
                    f"Use case not found: {usecase_id}",
                    path=["usecase_id"],
                    suggest="Use osiris.usecases.list to see available use cases",
                )

            # Convert example to YAML if present
            oml_template = None
            if "example" in usecase:
                oml_template = yaml.dump(usecase["example"], default_flow_style=False)

            result = {
                "usecase": usecase,
                "oml_template": oml_template,
                "snippet_uri": f"osiris://mcp/usecases/{usecase_id}.yaml",
                "status": "success",
            }

            return add_metrics(result, correlation_id, start_time, args)

        except OsirisError:
            raise
        except Exception as e:
            logger.error(f"Failed to get template: {e}")
            raise OsirisError(
                ErrorFamily.SEMANTIC,
                f"Failed to get template: {str(e)}",
                path=["template"],
                suggest="Check use case ID",
            ) from e
