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
    logs_dir: str | None = None,
):
    """Run database schema discovery on a connection.

    Args:
        connection_id: Connection reference (e.g., "@mysql.main", "@supabase.db")
        samples: Number of sample rows to retrieve (default: 10)
        json_output: Whether to output JSON instead of rich formatting
        session_id: Optional session ID for logging
        logs_dir: Optional directory for session logs (defaults to filesystem contract)

    Returns:
        Exit code (0 for success, non-zero for errors)
    """
    # Respect filesystem contract - get logs_dir from osiris.yaml if not specified
    if logs_dir is None:
        try:
            from osiris.core.config import load_config
            config = load_config("osiris.yaml")
            filesystem = config.get("filesystem", {})
            base_path = Path(filesystem.get("base_path", "."))
            logs_dir = str(base_path / filesystem.get("run_logs_dir", "logs"))
        except Exception:
            # Fallback to relative logs if config not found
            logs_dir = "logs"

    # Create session context
    if session_id is None:
        session_id = f"discovery_{int(time.time() * 1000)}"

    session = SessionContext(session_id=session_id, base_logs_dir=Path(logs_dir), allowed_events=["*"])
    set_current_session(session)
    # In JSON mode, suppress console logging to avoid polluting JSON output
    log_level = logging.WARNING if json_output else logging.INFO
    session.setup_logging(level=log_level)

    start_time = time.time()

    # Log discovery start
    session.log_event(
        "discovery_start",
        connection_id=connection_id,
        samples=samples,
        command="discovery.run",
    )

    try:
        # Parse connection reference (@family.alias format)
        if not connection_id.startswith("@"):
            console.print(f"[red]Error: Connection ID must start with @ (got: {connection_id})[/red]")
            session.log_event("discovery_error", error="invalid_connection_format", connection_id=connection_id)
            return 2

        # Parse @family.alias format
        parts = connection_id[1:].split(".", 1)
        if len(parts) != 2:
            console.print(f"[red]Error: Invalid format '{connection_id}'. Expected @family.alias[/red]")
            session.log_event("discovery_error", error="invalid_connection_format", connection_id=connection_id)
            return 2

        family, alias = parts

        # Resolve connection using correct API
        try:
            config = resolve_connection(family, alias)
        except (ValueError, Exception) as e:
            console.print(f"[red]Error: {e}[/red]")
            session.log_event("discovery_error", error=str(e), connection_id=connection_id)
            return 1

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

        # Note: discover_all_tables doesn't take sample_size, it uses progressive discovery
        # We'll need to call discover_table for each table with specific sample size
        import asyncio
        tables_dict = asyncio.run(discovery.discover_all_tables(max_tables=100))
        tables = list(tables_dict.values())

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
                            "name": col_name,
                            "type": table.column_types.get(col_name, "unknown"),
                        }
                        for col_name in table.columns
                    ],
                }
                if table.sample_data:
                    # Sample data is already a list of dicts
                    table_dict["sample_data"] = table.sample_data

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
                    sample_count = len(table.sample_data) if table.sample_data else 0
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
                    for col_name in table.columns:
                        col_type = table.column_types.get(col_name, "unknown")
                        is_pk = " [PRIMARY KEY]" if col_name in table.primary_keys else ""
                        console.print(f"  • [cyan]{col_name}[/cyan]: {col_type}{is_pk}")

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
