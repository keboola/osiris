"""CLI command for maintenance operations."""

import argparse
import json

from rich.console import Console

console = Console()


def maintenance_command(args: list[str]):
    """Execute maintenance command."""
    # Parse arguments
    parser = argparse.ArgumentParser(description="Maintenance operations", add_help=False)
    parser.add_argument("action", choices=["clean"], default="clean", nargs="?", help="Action to perform")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be deleted without deleting")
    parser.add_argument("--json", action="store_true", help="Output in JSON format")
    parser.add_argument("--help", "-h", action="store_true", help="Show help")

    # Check for help
    if "--help" in args or "-h" in args or not args:
        show_maintenance_help(json_output="--json" in args)
        return

    try:
        parsed_args = parser.parse_args(args)
    except SystemExit:
        return

    use_json = parsed_args.json

    if parsed_args.action == "clean":
        clean_command(parsed_args.dry_run, use_json)


def clean_command(dry_run: bool, json_output: bool):
    """Execute clean command to apply retention policies."""
    try:
        # Load filesystem contract
        from ..core.fs_config import load_osiris_config
        from ..core.fs_paths import FilesystemContract
        from ..core.retention import RetentionPlan

        fs_config, ids_config, _ = load_osiris_config()
        FilesystemContract(fs_config, ids_config)

        # Create retention plan
        plan = RetentionPlan(fs_config)
        actions = plan.compute()

        # Summary stats
        stats = {
            "total_actions": len(actions),
            "run_logs_to_delete": sum(1 for a in actions if a.action_type == "delete_run_logs"),
            "aiop_annex_to_delete": sum(1 for a in actions if a.action_type == "delete_annex"),
            "build_preserved": 0,  # Always 0, we never touch build/
            "dry_run": dry_run,
        }

        if dry_run:
            # Dry run - show plan
            if json_output:
                result = {
                    "dry_run": True,
                    "stats": stats,
                    "actions": [
                        {
                            "action": a.action,
                            "path": a.path,
                            "reason": a.reason,
                            "age_days": a.age_days,
                        }
                        for a in actions
                    ],
                }
                print(json.dumps(result, indent=2, default=str))
            else:
                console.print()
                console.print("[bold cyan]🔍 Retention Clean - Dry Run[/bold cyan]")
                console.print()
                console.print(f"[yellow]Would delete {len(actions)} items:[/yellow]")
                console.print(f"  • Run logs: {stats['run_logs_to_delete']} directories")
                console.print(f"  • AIOP annex: {stats['aiop_annex_to_delete']} items")
                console.print("  • Build artifacts: 0 (preserved)")
                console.print()

                if actions:
                    console.print("[bold]Items to delete:[/bold]")
                    for action in actions[:10]:  # Show first 10
                        age_str = f"({action.age_days}d old)" if action.age_days else ""
                        console.print(f"  [red]✗[/red] {action.path} {age_str}")
                    if len(actions) > 10:
                        console.print(f"  [dim]... and {len(actions) - 10} more[/dim]")
                else:
                    console.print("[green]No items to delete - all within retention policy[/green]")
        else:
            # Real run - execute deletions
            deleted = 0
            errors = []

            for action in actions:
                try:
                    action.execute()
                    deleted += 1
                except Exception as e:
                    errors.append({"path": action.path, "error": str(e)})

            stats["deleted"] = deleted
            stats["errors"] = len(errors)

            if json_output:
                result = {
                    "dry_run": False,
                    "stats": stats,
                    "errors": errors,
                }
                print(json.dumps(result, indent=2, default=str))
            else:
                console.print()
                console.print("[bold green]✅ Retention Clean Complete[/bold green]")
                console.print()
                console.print(f"[green]Deleted {deleted} items:[/green]")
                console.print(f"  • Run logs: {stats['run_logs_to_delete']} directories")
                console.print(f"  • AIOP annex: {stats['aiop_annex_to_delete']} items")
                console.print("  • Build artifacts: 0 (preserved)")

                if errors:
                    console.print()
                    console.print(f"[red]⚠️  {len(errors)} errors occurred:[/red]")
                    for err in errors[:5]:
                        console.print(f"  [red]✗[/red] {err['path']}: {err['error']}")
                    if len(errors) > 5:
                        console.print(f"  [dim]... and {len(errors) - 5} more[/dim]")

    except Exception as e:
        if json_output:
            print(json.dumps({"error": str(e)}))
        else:
            console.print(f"[red]Error: {e}[/red]")


def show_maintenance_help(json_output: bool = False):
    """Show help for maintenance command."""
    if json_output:
        help_data = {
            "command": "maintenance",
            "description": "Perform maintenance operations",
            "usage": "osiris maintenance [clean] [OPTIONS]",
            "actions": {"clean": "Apply retention policies to clean old files"},
            "options": {
                "--dry-run": "Show what would be deleted without deleting",
                "--json": "Output in JSON format",
                "--help": "Show this help message",
            },
            "examples": [
                "osiris maintenance clean --dry-run",
                "osiris maintenance clean",
                "osiris maintenance clean --json",
            ],
            "retention_config": {
                "run_logs_days": "Delete run logs older than N days",
                "aiop_keep_runs_per_pipeline": "Keep last N AIOP runs per pipeline",
                "annex_keep_days": "Delete AIOP annex older than N days",
            },
            "notes": [
                "Build artifacts are never deleted",
                "Retention settings come from osiris.yaml",
                "Use --dry-run to preview before deleting",
            ],
        }
        print(json.dumps(help_data, indent=2))
    else:
        console.print()
        console.print("[bold cyan]osiris maintenance - Maintenance Operations[/bold cyan]")
        console.print()
        console.print("[bold]Usage:[/bold] osiris maintenance [clean] [OPTIONS]")
        console.print()
        console.print("[bold blue]Actions[/bold blue]")
        console.print("  [cyan]clean[/cyan]  Apply retention policies to clean old files")
        console.print()
        console.print("[bold blue]Options[/bold blue]")
        console.print("  [cyan]--dry-run[/cyan]  Show what would be deleted without deleting")
        console.print("  [cyan]--json[/cyan]     Output in JSON format")
        console.print("  [cyan]--help[/cyan]     Show this help message")
        console.print()
        console.print("[bold blue]Retention Config (from osiris.yaml)[/bold blue]")
        console.print("  • run_logs_days: Delete run logs older than N days")
        console.print("  • aiop_keep_runs_per_pipeline: Keep last N AIOP runs")
        console.print("  • annex_keep_days: Delete AIOP annex older than N days")
        console.print()
        console.print("[bold blue]Examples[/bold blue]")
        console.print("  osiris maintenance clean --dry-run  # Preview deletions")
        console.print("  osiris maintenance clean            # Execute cleanup")
        console.print("  osiris maintenance clean --json     # JSON output")
        console.print()
        console.print("[bold yellow]⚠️  Note:[/bold yellow] Build artifacts are never deleted")
        console.print()
