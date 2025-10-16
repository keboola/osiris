"""CLI command for OML use case templates.

Provides example templates for common ETL patterns.
This is a minimal stub implementation for MCP Phase 1.
"""

import json

from rich.console import Console
from rich.table import Table

console = Console()


def list_usecases(category: str | None = None, json_output: bool = False):
    """List available OML use case templates.

    Args:
        category: Optional category filter (etl, migration, export, etc.)
        json_output: Whether to output JSON instead of rich formatting

    Returns:
        Exit code (0 for success, non-zero for errors)
    """
    # Stub implementation with example use cases
    usecases = [
        {
            "name": "mysql_to_supabase_etl",
            "category": "etl",
            "description": "Extract data from MySQL and load into Supabase",
            "components": ["mysql.extractor", "duckdb.processor", "supabase.writer"],
        },
        {
            "name": "csv_export",
            "category": "export",
            "description": "Export database table to CSV file",
            "components": ["mysql.extractor", "filesystem.csv_writer"],
        },
        {
            "name": "database_migration",
            "category": "migration",
            "description": "Migrate all tables from one database to another",
            "components": ["mysql.extractor", "supabase.writer"],
        },
        {
            "name": "api_to_database",
            "category": "etl",
            "description": "Extract from REST/GraphQL API and load to database",
            "components": ["graphql.extractor", "duckdb.processor", "supabase.writer"],
        },
    ]

    # Filter by category if provided
    if category:
        usecases = [uc for uc in usecases if uc["category"] == category]

    if json_output:
        result = {
            "status": "success",
            "category_filter": category,
            "usecases": usecases,
            "count": len(usecases),
        }
        print(json.dumps(result, indent=2))
    else:
        if not usecases:
            console.print(f"[yellow]No use cases found{f' for category: {category}' if category else ''}[/yellow]")
            return 0

        title = "OML Use Case Templates"
        if category:
            title += f" (Category: {category})"

        table = Table(title=title)
        table.add_column("Name", style="cyan")
        table.add_column("Category", style="yellow")
        table.add_column("Description", style="white")

        for uc in usecases:
            table.add_row(uc["name"], uc["category"], uc["description"])

        console.print("\n")
        console.print(table)
        console.print(f"\n[dim]Found {len(usecases)} use case template(s)[/dim]\n")

    return 0
