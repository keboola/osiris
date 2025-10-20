"""CLI command for managing pipeline runs."""

import argparse
from datetime import datetime, timedelta
import json

from rich.console import Console
from rich.table import Table

console = Console()


def _render_runs_table(runs):
    """Render runs as a Rich table."""
    table = Table(title=f"Pipeline Runs ({len(runs)} found)")
    table.add_column("Run ID", style="cyan")
    table.add_column("Pipeline", style="green")
    table.add_column("Profile", style="blue")
    table.add_column("Status", style="magenta")
    table.add_column("Started", style="dim")
    table.add_column("Duration", style="dim")

    for run in runs:
        # Format duration from duration_ms
        duration = ""
        if run.duration_ms:
            delta = timedelta(milliseconds=run.duration_ms)
            duration = str(delta)

        # Format started time (run_ts is ISO string)
        started_display = run.run_ts[:19] if run.run_ts else ""  # Trim to datetime part

        table.add_row(
            run.run_id[:20] + "..." if len(run.run_id) > 20 else run.run_id,
            run.pipeline_slug,
            run.profile or "default",
            run.status,
            started_display,
            duration,
        )

    return table


def runs_command(args: list[str]):
    """Execute the runs command."""
    # Parse arguments
    parser = argparse.ArgumentParser(description="Manage pipeline runs", add_help=False)
    parser.add_argument("action", choices=["list"], default="list", nargs="?", help="Action to perform")
    parser.add_argument("--pipeline", help="Filter by pipeline slug")
    parser.add_argument("--profile", help="Filter by profile")
    parser.add_argument("--tag", help="Filter by tag")
    parser.add_argument("--since", help="Filter by time period (e.g., 7d, 24h, 30m)")
    parser.add_argument("--json", action="store_true", help="Output in JSON format")
    parser.add_argument("--help", "-h", action="store_true", help="Show help")

    # Check for help
    if "--help" in args or "-h" in args or not args:
        show_runs_help(json_output="--json" in args)
        return

    try:
        parsed_args = parser.parse_args(args)
    except SystemExit:
        return

    use_json = parsed_args.json

    try:
        # Load filesystem contract
        from ..core.fs_config import load_osiris_config
        from ..core.fs_paths import FilesystemContract
        from ..core.run_index import RunIndexReader

        fs_config, ids_config, _ = load_osiris_config()
        fs_contract = FilesystemContract(fs_config, ids_config)

        # Get index paths
        index_paths = fs_contract.index_paths()
        index_reader = RunIndexReader(index_paths["base"])

        # Parse since filter
        since_dt = None
        if parsed_args.since:
            since_dt = _parse_since(parsed_args.since)

        # Query runs
        runs = index_reader.query_runs(
            pipeline_slug=parsed_args.pipeline,
            profile=parsed_args.profile,
            tag=parsed_args.tag,
            since=since_dt,
        )

        # Output results
        if use_json:
            print(json.dumps([r.to_dict() for r in runs], indent=2, default=str))
        else:
            if not runs:
                console.print("[yellow]No runs found matching filters[/yellow]")
                return

            table = _render_runs_table(runs)
            console.print(table)

    except Exception as e:
        if use_json:
            print(json.dumps({"error": str(e)}))
        else:
            console.print(f"[red]Error: {e}[/red]")


def show_runs_help(json_output: bool = False):
    """Show help for runs command."""
    if json_output:
        help_data = {
            "command": "runs",
            "description": "List and manage pipeline runs",
            "usage": "osiris runs [list] [OPTIONS]",
            "actions": {"list": "List pipeline runs (default)"},
            "options": {
                "--pipeline": "Filter by pipeline slug",
                "--profile": "Filter by profile",
                "--tag": "Filter by tag",
                "--since": "Filter by time period (e.g., 7d, 24h, 30m)",
                "--json": "Output in JSON format",
                "--help": "Show this help message",
            },
            "examples": [
                "osiris runs list",
                "osiris runs list --pipeline orders_etl",
                "osiris runs list --profile prod --since 7d",
                "osiris runs list --tag nightly --json",
            ],
        }
        print(json.dumps(help_data, indent=2))
    else:
        console.print()
        console.print("[bold cyan]osiris runs - Manage Pipeline Runs[/bold cyan]")
        console.print()
        console.print("[bold]Usage:[/bold] osiris runs [list] [OPTIONS]")
        console.print()
        console.print("[bold blue]Actions[/bold blue]")
        console.print("  [cyan]list[/cyan]  List pipeline runs (default)")
        console.print()
        console.print("[bold blue]Options[/bold blue]")
        console.print("  [cyan]--pipeline[/cyan]  Filter by pipeline slug")
        console.print("  [cyan]--profile[/cyan]   Filter by profile")
        console.print("  [cyan]--tag[/cyan]       Filter by tag")
        console.print("  [cyan]--since[/cyan]     Filter by time period (e.g., 7d, 24h, 30m)")
        console.print("  [cyan]--json[/cyan]      Output in JSON format")
        console.print("  [cyan]--help[/cyan]      Show this help message")
        console.print()
        console.print("[bold blue]Examples[/bold blue]")
        console.print("  osiris runs list")
        console.print("  osiris runs list --pipeline orders_etl")
        console.print("  osiris runs list --profile prod --since 7d")
        console.print("  osiris runs list --tag nightly --json")
        console.print()


def _parse_since(since_str: str) -> datetime:
    """Parse since string to datetime.

    Args:
        since_str: Time period string (e.g., "7d", "24h", "30m")

    Returns:
        Datetime representing the cutoff time
    """
    now = datetime.now()

    # Parse number and unit
    import re

    match = re.match(r"(\d+)([dhms])", since_str.lower())
    if not match:
        raise ValueError(f"Invalid since format: {since_str}")

    value = int(match.group(1))
    unit = match.group(2)

    if unit == "d":
        delta = timedelta(days=value)
    elif unit == "h":
        delta = timedelta(hours=value)
    elif unit == "m":
        delta = timedelta(minutes=value)
    elif unit == "s":
        delta = timedelta(seconds=value)
    else:
        raise ValueError(f"Invalid time unit: {unit}")

    return now - delta
