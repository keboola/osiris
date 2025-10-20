"""CLI command for database schema discovery.

Provides standalone discovery functionality that can be used directly
or delegated to from MCP commands.
"""

from datetime import UTC, datetime
import json
import logging
from pathlib import Path
import time

from rich.console import Console
from rich.table import Table

from osiris.components.registry import get_registry
from osiris.core.config import load_config, resolve_connection
from osiris.core.discovery import ProgressiveDiscovery
from osiris.core.identifiers import generate_discovery_id
from osiris.core.session_logging import SessionContext, set_current_session

console = Console()
logger = logging.getLogger(__name__)


def sanitize_for_json(obj):
    """
    Convert objects to JSON-serializable formats.

    Handles datetime, Timestamp, and other non-JSON types.
    """
    if isinstance(obj, (datetime,)) or hasattr(obj, "isoformat"):  # Handles datetime and pandas Timestamp
        return obj.isoformat()
    elif isinstance(obj, dict):
        return {k: sanitize_for_json(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [sanitize_for_json(item) for item in obj]
    else:
        return obj


def discovery_run(  # noqa: PLR0915  # CLI router function, naturally verbose
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
        from osiris.connectors.mysql import MySQLExtractor  # noqa: PLC0415  # Lazy import for CLI performance
        from osiris.connectors.supabase import SupabaseExtractor  # noqa: PLC0415  # Lazy import for CLI performance

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
        import asyncio  # noqa: PLC0415  # Lazy import for CLI performance

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
            # Generate deterministic discovery ID for caching
            discovery_id = generate_discovery_id(connection_id, component_name, samples)

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
                    # Sample data is already a list of dicts, but may contain non-JSON types
                    table_dict["sample_data"] = sanitize_for_json(table.sample_data)

                tables_data.append(table_dict)

            # Determine cache directory from config (filesystem contract)
            try:
                config = load_config("osiris.yaml")
                filesystem = config.get("filesystem", {})
                base_path = Path(filesystem.get("base_path", "."))
                mcp_logs_dir = filesystem.get("mcp_logs_dir", ".osiris/mcp/logs")
                cache_dir = base_path / mcp_logs_dir / "cache"
            except Exception:
                # Fallback to default location
                cache_dir = Path(".osiris/mcp/logs/cache")

            # Create cache directory
            cache_dir.mkdir(parents=True, exist_ok=True)

            # Save discovery artifacts for resource URIs
            overview_data = {
                "discovery_id": discovery_id,
                "connection_id": connection_id,
                "family": family,
                "alias": alias,
                "component": component_name,
                "tables_found": len(tables),
                "samples": samples,
                "duration_ms": duration_ms,
                "session_id": session_id,
                "timestamp": datetime.now(UTC).isoformat(),
            }

            # Save artifacts to cache - create nested directory structure to match URI scheme
            # URIs use osiris://mcp/discovery/<id>/<artifact>.json format
            # Resolver expects cache_dir/<id>/<artifact>.json
            discovery_artifact_dir = cache_dir / discovery_id
            discovery_artifact_dir.mkdir(parents=True, exist_ok=True)

            overview_path = discovery_artifact_dir / "overview.json"
            tables_path = discovery_artifact_dir / "tables.json"
            samples_path = discovery_artifact_dir / "samples.json"

            with open(overview_path, "w") as f:
                json.dump(overview_data, f, indent=2)

            with open(tables_path, "w") as f:
                json.dump({"tables": tables_data, "count": len(tables_data)}, f, indent=2)

            # Extract just sample data for samples artifact
            samples_data = []
            for table in tables:
                if table.sample_data:
                    samples_data.append(
                        {
                            "table": table.name,
                            "rows": sanitize_for_json(table.sample_data),
                            "count": len(table.sample_data),
                        }
                    )

            with open(samples_path, "w") as f:
                json.dump({"samples": samples_data, "tables_with_samples": len(samples_data)}, f, indent=2)

            # Build result with discovery_id and artifacts
            result = {
                "discovery_id": discovery_id,
                "connection_id": connection_id,
                "family": family,
                "alias": alias,
                "component": component_name,
                "tables": tables_data,
                "tables_found": len(tables),
                "duration_ms": duration_ms,
                "session_id": session_id,
                "status": "success",
                "artifacts": {
                    "overview": f"osiris://mcp/discovery/{discovery_id}/overview.json",
                    "tables": f"osiris://mcp/discovery/{discovery_id}/tables.json",
                    "samples": f"osiris://mcp/discovery/{discovery_id}/samples.json",
                },
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
