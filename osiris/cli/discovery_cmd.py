"""CLI command for database schema discovery.

Provides standalone discovery functionality that can be used directly
or delegated to from MCP commands.
"""

import json
import logging
import sys
import time
import uuid
from pathlib import Path

from rich.console import Console
from rich.table import Table

from osiris.components.registry import get_registry
from osiris.core.config import load_connections_yaml, resolve_connection
from osiris.core.discovery import ProgressiveDiscovery
from osiris.core.session_logging import SessionContext, set_current_session

console = Console()
logger = logging.getLogger(__name__)


def discovery_run(
    connection_id: str,
    samples: int = 10,
    json_output: bool = False,
    session_id: str | None = None,
    logs_dir: str = "logs",
):
    """Run database schema discovery on a connection.

    Args:
        connection_id: Connection reference (e.g., "@mysql.main", "@supabase.db")
        samples: Number of sample rows to retrieve (default: 10)
        json_output: Whether to output JSON instead of rich formatting
        session_id: Optional session ID for logging
        logs_dir: Directory for session logs

    Returns:
        Exit code (0 for success, non-zero for errors)
    """
    # Create session context
    if session_id is None:
        session_id = f"discovery_{int(time.time() * 1000)}"

    session = SessionContext(session_id=session_id, base_logs_dir=Path(logs_dir), allowed_events=["*"])
    set_current_session(session)
    session.setup_logging(level=logging.INFO)

    start_time = time.time()

    # Log discovery start
    session.log_event(
        "discovery_start",
        connection_id=connection_id,
        samples=samples,
        command="discovery.run",
    )

    try:
        # Parse connection reference
        if not connection_id.startswith("@"):
            console.print(f"[red]Error: Connection ID must start with @ (got: {connection_id})[/red]")
            session.log_event("discovery_error", error="invalid_connection_format", connection_id=connection_id)
            return 2

        # Load connections and resolve
        connections = load_connections_yaml()
        resolved = resolve_connection(connection_id, connections)

        if not resolved:
            console.print(f"[red]Error: Connection '{connection_id}' not found[/red]")
            console.print("[dim]Available connections:[/dim]")
            for family, aliases in connections.items():
                for alias in aliases:
                    console.print(f"  @{family}.{alias}")
            session.log_event("discovery_error", error="connection_not_found", connection_id=connection_id)
            return 1

        family, alias, config = resolved
        component_name = f"{family}.extractor"

        # Get component from registry
        registry = get_registry()
        spec = registry.get_component(component_name)

        if not spec:
            console.print(f"[red]Error: No extractor component found for family '{family}'[/red]")
            session.log_event("discovery_error", error="component_not_found", component=component_name)
            return 1

        # Create extractor instance
        from osiris.connectors.mysql import MySQLExtractor
        from osiris.connectors.supabase import SupabaseExtractor

        extractor_map = {
            "mysql": MySQLExtractor,
            "supabase": SupabaseExtractor,
            "postgresql": SupabaseExtractor,  # Alias
        }

        extractor_class = extractor_map.get(family)
        if not extractor_class:
            console.print(f"[red]Error: Unsupported database family '{family}'[/red]")
            console.print(f"[dim]Supported: {', '.join(extractor_map.keys())}[/dim]")
            session.log_event("discovery_error", error="unsupported_family", family=family)
            return 1

        # Initialize extractor
        extractor = extractor_class(config)

        # Create discovery instance
        discovery = ProgressiveDiscovery(
            extractor=extractor,
            cache_dir=".osiris_cache",
            component_type=component_name,
            component_version=spec.get("version", "0.1.0"),
            connection_ref=connection_id,
            session_id=session_id,
        )

        # Discover all tables
        if not json_output:
            console.print(f"\n[bold cyan]Discovering schema for {connection_id}...[/bold cyan]")
            console.print(f"[dim]Component: {component_name}[/dim]")
            console.print(f"[dim]Samples per table: {samples}[/dim]\n")

        tables = discovery.discover_all_tables(sample_size=samples)

        duration_ms = int((time.time() - start_time) * 1000)

        # Log discovery complete
        session.log_event(
            "discovery_complete",
            connection_id=connection_id,
            tables_found=len(tables),
            duration_ms=duration_ms,
            status="success",
        )

        # Output results
        if json_output:
            # JSON output for MCP/programmatic use
            tables_data = []
            for table in tables:
                table_dict = {
                    "name": table.name,
                    "row_count": table.row_count,
                    "columns": [
                        {
                            "name": col.name,
                            "type": col.type,
                            "nullable": col.nullable,
                        }
                        for col in table.columns
                    ],
                }
                if table.samples:
                    # Convert samples to JSON-serializable format
                    table_dict["samples"] = table.samples.to_dict(orient="records")

                tables_data.append(table_dict)

            result = {
                "connection_id": connection_id,
                "family": family,
                "alias": alias,
                "component": component_name,
                "tables": tables_data,
                "tables_found": len(tables),
                "duration_ms": duration_ms,
                "session_id": session_id,
                "status": "success",
            }
            print(json.dumps(result, indent=2))
        else:
            # Rich table output for human readability
            if not tables:
                console.print("[yellow]No tables found[/yellow]")
            else:
                # Summary table
                summary = Table(title=f"Discovered {len(tables)} tables")
                summary.add_column("Table", style="cyan")
                summary.add_column("Rows", style="yellow", justify="right")
                summary.add_column("Columns", style="green", justify="right")
                summary.add_column("Sample Rows", style="magenta", justify="right")

                for table in tables:
                    sample_count = len(table.samples) if table.samples is not None else 0
                    summary.add_row(
                        table.name,
                        str(table.row_count) if table.row_count is not None else "?",
                        str(len(table.columns)),
                        str(sample_count),
                    )

                console.print(summary)

                # Detail for each table
                for table in tables:
                    console.print(f"\n[bold]{table.name}[/bold] ({len(table.columns)} columns)")
                    for col in table.columns:
                        nullable = " (nullable)" if col.nullable else ""
                        console.print(f"  • [cyan]{col.name}[/cyan]: {col.type}{nullable}")

            console.print(f"\n[dim]Session: {session_id}[/dim]")
            console.print(f"[dim]Duration: {duration_ms}ms[/dim]")

        return 0

    except Exception as e:
        duration_ms = int((time.time() - start_time) * 1000)
        console.print(f"[red]Discovery failed: {e}[/red]")
        session.log_event(
            "discovery_error",
            connection_id=connection_id,
            error=str(e),
            duration_ms=duration_ms,
        )

        if json_output:
            error_result = {
                "connection_id": connection_id,
                "status": "error",
                "error": str(e),
                "duration_ms": duration_ms,
                "session_id": session_id,
            }
            print(json.dumps(error_result, indent=2))

        return 1
    finally:
        session.log_event("run_end", status="completed", duration_ms=int((time.time() - start_time) * 1000))
